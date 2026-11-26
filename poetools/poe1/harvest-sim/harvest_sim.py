"""PoE1 수확(Harvest) 시뮬레이터용 시세 수집: poe.ninja -> out/harvest-rates.json

harvest-sim.html 의 아래 입력값을 poe.ninja 의 PoE1 경제 API 에서 읽어 JSON 으로 저장한다.
최신 시즌 리그 2개(최신, 직전)와 Standard 를 한 파일에 리그별로 담고, harvest-sim.html 의 '리그' 드롭다운이 이 목록을 보여 준다.

  JSON 키 (리그마다)       harvest-sim.html          의미
  ----------------------   -----------------------   ------------------------------------------
  ratio                    #ratio  (디바인)          디바인 1개 = 카오스 N개
  lifeforce.yellow         #py  (노랑 = Vivid)       카오스 1개당 생기 개수  (시뮬레이터는 생기 / 이 값 = 카오스 로 계산)
  lifeforce.blue           #pb  (파랑 = Primal)      〃
  lifeforce.purple         #pp  (보라 = Wild)        〃
  scarab.doubling          #scdp (복제의 수확 갑충석)   Harvest Scarab of Doubling 1개 = 카오스 N개
  scarab.lineage           #sclp (기괴한 혈통의 갑충석) Scarab of Monstrous Lineage 1개 = 카오스 N개
  fragment.sacrifice       #fsp  (희생의 조각)         Sacrifice at Dusk / Midday / Midnight / Dawn 중 가장 싼 값 (카오스)
  fragment.mortal          #fmp  (필멸의 조각)         Mortal Grief / Ignorance / Rage / Hope 중 가장 싼 값 (카오스)
  fragment.sacrificeItem   (조각 효율 패널의 이름·이미지)  위에서 가장 싼 희생의 조각 이름 (예: "Sacrifice at Dusk")
  fragment.mortalItem      〃                              위에서 가장 싼 필멸의 조각 이름 (예: "Mortal Hope")
  updatedAt                (화면 표시용)             그 리그를 마지막으로 갱신한 시각 (UTC)

파일 형식 (version 2):
  {"version": 2, "source": "poe.ninja", "updatedAt": "...Z",
   "order": ["최신 시즌 리그", "직전 시즌 리그"],
   "leagues": {"최신 시즌 리그": {ratio, lifeforce, scarab, fragment, updatedAt}, "직전 시즌 리그": {...}, "Standard": {...}}}
  이전 형식(version 1: 단일 리그)의 파일은 읽을 때 자동으로 version 2 로 바꿔 저장한다.

poe.ninja 규칙 (https://poe.ninja/docs/api):
  - 경제 API 만 공개 사용 가능. 응답은 HTTP 캐시(약 5분)되고 PoE1 데이터는 약 15분마다 갱신되므로 자주 부를 필요가 없다.
  - 식별 가능한 User-Agent(앱 이름 + 연락처)를 보낸다. 과도한 요청은 차단될 수 있다.
  - 리그당 요청 2~3회(Currency, Scarab, 필요 시 Fragment) + 리그 목록 1회. 리그 사이에는 잠깐 쉰다.

동작:
  - 리그 목록(/leagues)은 '진행 중인' 리그만 알려 준다. 첫 번째 소프트코어 챌린지 리그가 최신 시즌 리그다.
    종료된 직전 리그는 목록에서 사라지므로, 파일에 저장해 둔 order 에서 이어받아 마지막 값을 그대로 보관한다
    (종료된 리그는 값이 더 바뀌지 않으므로 다시 요청하지 않는다). 새 리그가 시작되면 order 가 한 칸씩 밀리고 가장 오래된 리그는 파일에서 빠진다.
  - 리그별 갱신 간격: 최신 시즌 1시간, 직전 시즌 6시간, Standard 12시간 (updatedAt 기준, 간격 이내면 요청 생략).
  - 일부 항목을 못 찾으면 그 항목은 같은 리그의 이전 값을 유지한다. 어느 리그에서도 값을 하나도 못 읽으면 종료 코드 1 (GitHub Actions 에서 실패로 보이도록).
  - 수집 시각은 항상 UTC ISO 형식이라 PC(KST)와 Actions(UTC) 어디서 돌려도 같다.
  - 의존성은 requests 하나뿐이고 입력·키 설정이 필요 없어 그대로 Actions 에 올릴 수 있다.

실행:
  python harvest_rates.py --force                          # 갱신 간격(최신 1h / 직전 6h / Standard 12h) 무시하고 전부 요청
  python harvest_rates.py                                  # 최신 시즌 리그 2개 + Standard -> out/harvest-rates.json
  python harvest_rates.py --league latest "Mirage"         # 직전 리그를 이름으로 직접 채워 넣기 (파일에 아직 없을 때, 처음 한 번)
  python harvest_rates.py --out other/rates.json
  python harvest_rates.py --dry-run                        # 저장하지 않고 결과만 출력
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

NINJA = "https://poe.ninja/poe1/api/economy"
UA = "poe1-harvest-sim/0.1 (contact: augustusminu@gmail.com)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
DEFAULT_OUT = os.path.join(OUT_DIR, "harvest-rates.json")

# 수집 항목: 키 -> (표시 이름, 매칭 후보, 찾아볼 exchange type 순서)
# 후보는 id·이름·detailsId 에서 영숫자만 남겨 소문자로 만든 값과 비교한다
# ("harvest-scarab-of-doubling", "Harvest Scarab of Doubling" 같은 표기 차이는 문제되지 않는다).
ITEMS = {
    "divine":   ("Divine Orb", ("divine", "divineorb"), ("Currency",)),
    "chaos":    ("Chaos Orb", ("chaos", "chaosorb"), ("Currency",)),
    "yellow":   ("Vivid Crystallised Lifeforce", ("vividcrystallisedlifeforce", "vividlifeforce"), ("Currency",)),
    "blue":     ("Primal Crystallised Lifeforce", ("primalcrystallisedlifeforce", "primallifeforce"), ("Currency",)),
    "purple":   ("Wild Crystallised Lifeforce", ("wildcrystallisedlifeforce", "wildlifeforce"), ("Currency",)),
    "doubling": ("Harvest Scarab of Doubling", ("harvestscarabofdoubling",), ("Scarab", "Fragment")),
    "lineage":  ("Scarab of Monstrous Lineage", ("scarabofmonstrouslineage",), ("Scarab", "Fragment")),
    # 조각: 희생의 조각 4종, 필멸의 조각 4종 (아래 FRAGMENT_GROUPS 로 묶어 그룹마다 가장 싼 값을 쓴다)
    "sac_dusk":      ("Sacrifice at Dusk", ("sacrificeatdusk",), ("Fragment",)),
    "sac_midday":    ("Sacrifice at Noon", ("sacrificeatnoon", "sacrificeatmidday"), ("Fragment",)),
    "sac_midnight":  ("Sacrifice at Midnight", ("sacrificeatmidnight",), ("Fragment",)),
    "sac_dawn":      ("Sacrifice at Dawn", ("sacrificeatdawn",), ("Fragment",)),
    "mortal_grief":     ("Mortal Grief", ("mortalgrief",), ("Fragment",)),
    "mortal_ignorance": ("Mortal Ignorance", ("mortalignorance",), ("Fragment",)),
    "mortal_rage":      ("Mortal Rage", ("mortalrage",), ("Fragment",)),
    "mortal_hope":      ("Mortal Hope", ("mortalhope",), ("Fragment",)),
}
FRAGMENT_GROUPS = {
    "sacrifice": ("sac_dusk", "sac_midday", "sac_midnight", "sac_dawn"),
    "mortal": ("mortal_grief", "mortal_ignorance", "mortal_rage", "mortal_hope"),
}
CHAOS_KEYS = ITEMS["chaos"][1]

# 리그 목록에서 건너뛸 리그 (하드코어·SSF·러스리스·Standard 등). 소프트코어 챌린지 리그만 시즌 리그로 쓴다.
_EXCLUDE = re.compile(r"\b(hc|ssf|hardcore|ruthless|solo|standard|eternal)\b", re.IGNORECASE)
STANDARD = "Standard"
N_SEASON = 2          # 파일에 담는 시즌 리그 수 (최신, 직전). Standard 는 별도로 항상 포함

# 리그별 최소 갱신 간격(시간). 워크플로우는 1시간마다 돌지만, 마지막 갱신(updatedAt)이 이 간격보다
# 최근이면 해당 리그는 poe.ninja 에 요청하지 않고 저장된 값을 유지한다.
INTERVAL_LATEST_H = 1     # 최신 시즌 리그: 실행할 때마다
INTERVAL_PREVIOUS_H = 6   # 직전 시즌 리그
INTERVAL_STANDARD_H = 12  # Standard
# cron 지연/실행 시간 때문에 간격이 몇 분 모자라게 측정되어도 한 번 건너뛰지 않도록 주는 여유
INTERVAL_SLACK_MIN = 20

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "application/json"})


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hours_since(stamp):
    """updatedAt 문자열(UTC) 이후 경과 시간(시간 단위). 값이 없거나 읽을 수 없으면 None."""
    try:
        t = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# ---------------------------------------------------------------- poe.ninja 호출
def ninja_get(path, params=None):
    """poe.ninja 경제 API GET. 429/503 이면 잠깐 기다렸다 최대 3번 시도한다."""
    url = f"{NINJA}/{path}"
    for attempt in range(3):
        r = session.get(url, params=params, timeout=30)
        if r.status_code in (429, 503) and attempt < 2:
            try:
                wait = int(r.headers.get("Retry-After", 10))
            except ValueError:
                wait = 10
            print(f"  {r.status_code} -> {wait}초 대기 후 재시도")
            time.sleep(min(max(wait, 1), 60))
            continue
        r.raise_for_status()
        return r.json()


def _meta_list(src):
    """items 메타데이터(목록 또는 id->정보 딕셔너리)를 [{id, name, ...}] 로 통일."""
    if isinstance(src, dict):
        src = [dict(v, id=v.get("id", k)) if isinstance(v, dict) else {"id": k, "name": v} for k, v in src.items()]
    return [x for x in (src or []) if isinstance(x, dict) and x.get("id") is not None]


def parse_exchange(resp):
    """exchange overview 응답 -> {"primary": 기준 화폐 id, "vals": {정규화한 id/이름/detailsId: primaryValue}}.
    primaryValue 는 '1개 = 기준 화폐(core.primary) 몇 개'다. 기준 화폐 자신은 정의상 1."""
    core = resp.get("core") or {}
    meta = {}
    for src in (resp.get("items"), core.get("items")):
        for it in _meta_list(src):
            meta.setdefault(str(it["id"]), {}).update({k: it[k] for k in ("name", "detailsId") if it.get(k)})
    value = {}
    for ln in resp.get("lines") or []:
        v = ln.get("primaryValue") if isinstance(ln, dict) else None
        if isinstance(v, (int, float)) and v > 0 and ln.get("id") is not None:
            value[str(ln["id"])] = float(v)
    primary = str(core.get("primary") or "")
    if primary and primary not in value:
        value[primary] = 1.0
    vals = {}
    for cid in set(value) | set(meta):
        if cid not in value:
            continue
        for k in (cid, meta.get(cid, {}).get("name"), meta.get(cid, {}).get("detailsId")):
            if k:
                vals.setdefault(_norm(k), value[cid])
    return {"primary": primary, "vals": vals}


def parse_stash_currency(resp):
    """stash currency overview(chaosEquivalent) 응답 -> parse_exchange 와 같은 형태 (기준 화폐 = 카오스)."""
    vals = {k: 1.0 for k in CHAOS_KEYS}
    for ln in resp.get("lines") or []:
        v = ln.get("chaosEquivalent") if isinstance(ln, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            for k in (ln.get("currencyTypeName"), ln.get("detailsId")):
                if k:
                    vals[_norm(k)] = float(v)
    return {"primary": "chaos", "vals": vals}


def lookup(snap, candidates):
    for c in candidates:
        if c in snap["vals"]:
            return snap["vals"][c]
    return None


def load_snapshot(league_id, typ):
    """한 카테고리의 가격표를 읽는다. Currency 는 exchange 실패 시 문서에 있는 stash currency 로 한 번 더 시도."""
    try:
        return parse_exchange(ninja_get("exchange/current/overview", {"league": league_id, "type": typ}))
    except (requests.RequestException, ValueError, AttributeError) as e:
        print(f"  exchange {typ} 조회 실패 ({str(e)[:160]})")
        if typ not in ("Currency", "Fragment"):
            return None
    try:
        snap = parse_stash_currency(ninja_get("stash/current/currency/overview", {"league": league_id, "type": typ}))
        print(f"  -> stash {typ} 로 대체")
        return snap
    except (requests.RequestException, ValueError, AttributeError) as e:
        print(f"  stash {typ} 조회도 실패 ({str(e)[:160]})")
        return None


# ---------------------------------------------------------------- 리그 선택
def is_standard(lid):
    return _norm(lid) == "standard"


def list_active_leagues():
    """poe.ninja 가 알려 주는 진행 중인 리그 [{id, name}] (첫 번째 = 현재 챌린지 리그). 실패하면 None."""
    try:
        data = ninja_get("leagues")
        if isinstance(data, dict):
            data = data.get("leagues") or []
        return [x for x in data if isinstance(x, dict) and x.get("id")]
    except (requests.RequestException, ValueError) as e:
        print(f"  리그 목록 조회 실패 ({str(e)[:160]})")
        return None


def resolve_leagues(choices, active, store):
    """-> (시즌 리그 id 목록(최신 순, 최대 N_SEASON), Standard id).
    'latest' 는 진행 중인 소프트코어 챌린지 리그를 뜻하고, 이름은 리그 목록의 id/이름과 맞춰 본다.
    진행 중 목록에 없는 직전 리그는 저장된 파일의 order 에서 이어받는다."""
    active = active or []
    by_norm = {}
    for lg in active:
        for k in (lg.get("id"), lg.get("name")):
            if k:
                by_norm.setdefault(_norm(k), lg["id"])
    current = [lg["id"] for lg in active if not _EXCLUDE.search(f"{lg.get('id')} {lg.get('name')}")]
    if active:
        print(f"  poe.ninja 리그: {[lg['id'] for lg in active]}")

    season = []

    def add(lid):
        if lid and not is_standard(lid) and lid not in season:
            season.append(lid)

    for c in choices:
        if c.strip().lower() == "latest":
            for lid in current[:N_SEASON]:
                add(lid)
        else:
            hit = by_norm.get(_norm(c))
            if not hit:
                print(f"  '{c.strip()}' 이(가) 진행 중인 리그 목록에 없지만 입력한 이름 그대로 조회합니다")
            add(hit or c.strip())
    for lid in store["order"]:          # 종료되어 목록에서 사라진 직전 리그
        add(lid)
    return season[:N_SEASON], by_norm.get(_norm(STANDARD), STANDARD)


# ---------------------------------------------------------------- 파일 읽기·저장
def load_store(path):
    """기존 파일 -> version 2 구조 {order, leagues}. 이전 형식(단일 리그)이면 변환한다."""
    store = {"order": [], "leagues": {}}
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
    except OSError:
        return store
    except ValueError:
        print(f"  ⚠ 기존 {path} 를 읽지 못해 새로 만듭니다")
        return store
    if not isinstance(loaded, dict):
        return store
    if isinstance(loaded.get("leagues"), dict):
        store["leagues"] = {k: v for k, v in loaded["leagues"].items() if isinstance(v, dict)}
        store["order"] = [k for k in (loaded.get("order") or []) if isinstance(k, str)]
    elif loaded.get("league"):                              # version 1: 단일 리그
        lid = loaded["league"]
        store["leagues"][lid] = {k: loaded[k] for k in ("ratio", "lifeforce", "scarab", "updatedAt") if k in loaded}
        if not is_standard(lid):
            store["order"] = [lid]
    return store


# ---------------------------------------------------------------- 시세 계산
def fetch_chaos_prices(league_id):
    """{키: 카오스 몇 개} (찾은 항목만). 카테고리마다 기준 화폐가 다를 수 있어 카오스를 기준 화폐 단위로 환산해 쓴다."""
    types = []
    for _, _, ts in ITEMS.values():
        for t in ts:
            if t not in types:
                types.append(t)
    found, base, sample = {}, None, []        # base = (기준 화폐 id, 그 단위로 본 카오스 가격) — Currency 응답에서 얻는다
    for typ in types:
        want = [k for k, (_, _, ts) in ITEMS.items() if k not in found and typ in ts]
        if not want:
            continue
        if typ != types[0] and all(k in found for k in ITEMS):
            break
        snap = load_snapshot(league_id, typ)
        if snap is None:
            if typ == types[0]:
                return {}                       # 첫 요청(Currency)부터 실패하면 카오스 기준을 알 수 없다
            continue
        if not sample:
            sample = sorted(snap["vals"])[:25]
        chaos = lookup(snap, CHAOS_KEYS)
        if chaos:
            ref = (snap["primary"], chaos)
            if base is None:
                base = ref
        elif base and base[0] == snap["primary"]:
            ref = base                          # 이 응답에 카오스가 없으면 Currency 응답의 카오스 가격을 같은 기준 화폐로 재사용
        else:
            print(f"  {typ}: 카오스 기준을 알 수 없어 건너뜀 (기준 화폐 {snap['primary'] or '?'})")
            continue
        for k in want:
            v = lookup(snap, ITEMS[k][1])
            if v:
                found[k] = v / ref[1]
        time.sleep(0.5)
    missing = [ITEMS[k][0] for k in ITEMS if k not in found]
    if missing:
        print(f"  찾지 못함 (이전 값 유지): {', '.join(missing)}")
        print(f"  Currency 응답의 키 예시: {', '.join(sample) or '(비어 있음)'}")
    return found


def build_rates(chaos):
    """카오스 가격 -> 시뮬레이터 입력 형식. 비정상 값은 버린다."""
    out = {}
    d, c = chaos.get("divine"), chaos.get("chaos")
    if d and c and abs(c - 1.0) < 1e-9:
        if d > 1:
            out["ratio"] = round(d, 1)
        else:
            print(f"  Divine 이 {d:.2f} 카오스라 비정상 -> 환율 저장 안 함")
    elif d:
        out["ratio"] = round(d, 1)
    for k in ("yellow", "blue", "purple"):
        if chaos.get(k):
            out.setdefault("lifeforce", {})[k] = round(1 / chaos[k], 2)       # 카오스 1개당 생기 개수
    for k in ("doubling", "lineage"):
        if chaos.get(k):
            out.setdefault("scarab", {})[k] = round(chaos[k], 1)
    for grp, keys in FRAGMENT_GROUPS.items():       # 조각: 그룹 안에서 가장 싼 값 (카오스 기준, 싼 조각은 1 미만일 수 있어 소수 둘째 자리까지)
        found = [(chaos[k], k) for k in keys if chaos.get(k)]
        prices = [v for v, _ in found]
        if found:
            low, lowk = min(found)
            out.setdefault("fragment", {})[grp] = round(low, 2)
            out["fragment"][grp + "Item"] = ITEMS[lowk][0]      # 가장 싼 조각의 영문 이름 (harvest-sim.html 이 이름·이미지를 고르는 데 씀)
            if len(prices) < len(keys):
                print(f"  ⚠ {grp} 조각: {len(keys)}종 중 {len(prices)}종만 찾아 그중 최저가를 사용")
    return out


def save(path, store, season, std, results):
    """읽은 리그별 값을 기존 내용에 병합 저장 (못 찾은 항목은 같은 리그의 이전 값 유지).
    파일에는 시즌 리그(최신 순)와 Standard 만 남기고, 그보다 오래된 리그는 버린다."""
    leagues = store["leagues"]
    stamp = utc_stamp()
    for lid, rates in results.items():
        cur = leagues.setdefault(lid, {})
        for key, v in rates.items():
            if isinstance(v, dict):
                cur.setdefault(key, {}).update(v)
            else:
                cur[key] = v
        cur["updatedAt"] = stamp
    keep = [k for k in season + [std] if k in leagues]
    data = {
        "version": 2,
        "source": "poe.ninja",
        "updatedAt": stamp,
        "order": [k for k in season if k in leagues],
        "leagues": {k: leagues[k] for k in keep},
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def show(league_id, chaos, rates):
    print(f"\n[{league_id}]")
    for k, (name, _, _) in ITEMS.items():
        print(f"  {name:32} " + (f"{chaos[k]:.4g} 카오스" if k in chaos else "-"))
    print("  --- 시뮬레이터 입력값 ---")
    if "ratio" in rates:
        print(f"  디바인              : 카오스 {rates['ratio']:g}")
    for k, label in (("yellow", "노랑(Vivid)"), ("blue", "파랑(Primal)"), ("purple", "보라(Wild)")):
        if k in rates.get("lifeforce", {}):
            print(f"  생기 {label:10}: 카오스 1개당 {rates['lifeforce'][k]:g}")
    for k, label in (("doubling", "복제의 수확 갑충석"), ("lineage", "기괴한 혈통의 갑충석")):
        if k in rates.get("scarab", {}):
            print(f"  {label:14}: {rates['scarab'][k]:g} 카오스")
    for k, label in (("sacrifice", "희생의 조각(최저가)"), ("mortal", "필멸의 조각(최저가)")):
        if k in rates.get("fragment", {}):
            print(f"  {label:14}: {rates['fragment'][k]:g} 카오스  ({rates['fragment'].get(k + 'Item', '?')})")


def skipped_only(leagues, store, intervals, force, active_ids):
    """요청 대상이 없어서(모두 간격 이내이거나 종료된 리그) 결과가 비었는지 판단."""
    if force:
        return False
    for lid in leagues:
        if active_ids and lid not in active_ids and lid in store["leagues"]:
            continue
        age_h = hours_since(store["leagues"].get(lid, {}).get("updatedAt"))
        if age_h is None or age_h * 60 >= intervals[lid] * 60 - INTERVAL_SLACK_MIN:
            return False      # 요청했어야 했는데 값을 못 읽은 경우 -> 실패로 취급
    return True


def main():
    ap = argparse.ArgumentParser(description="poe.ninja 에서 수확 시뮬레이터용 시세 수집 (PoE1)")
    ap.add_argument("--league", nargs="+", default=["latest"], metavar="LEAGUE",
                    help="latest | 리그 id 또는 이름 (여러 개 가능, 기본: latest = 진행 중인 최신 챌린지 리그). "
                         "시즌 리그는 최대 %d개, Standard 는 항상 함께 수집" % N_SEASON)
    ap.add_argument("--out", default=DEFAULT_OUT, help="저장 경로 (기본: 스크립트 옆 out/harvest-rates.json)")
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    ap.add_argument("--force", action="store_true", help="갱신 간격을 무시하고 모든 리그를 요청")
    args = ap.parse_args()

    print("== poe.ninja 시세 (PoE1) ==")
    store = load_store(args.out)
    active = list_active_leagues()
    season, std = resolve_leagues(args.league, active, store)
    if not season:
        print("  시즌 리그를 확인하지 못했습니다 (--league \"이름\" 으로 직접 지정할 수 있음). Standard 만 수집합니다.")
    active_ids = {lg["id"] for lg in active or []}

    # 리그별 갱신 간격: 최신 1시간, 직전 6시간, Standard 12시간
    intervals = {std: INTERVAL_STANDARD_H}
    for i, lid in enumerate(season):
        intervals[lid] = INTERVAL_LATEST_H if i == 0 else INTERVAL_PREVIOUS_H

    results = {}
    for lid in season + [std]:
        if active_ids and lid not in active_ids and lid in store["leagues"]:
            print(f"\n[{lid}] 종료된 리그: 저장된 값을 유지하고 다시 요청하지 않습니다")
            continue
        need_h = intervals[lid]
        age_h = hours_since(store["leagues"].get(lid, {}).get("updatedAt"))
        if not args.force and age_h is not None and age_h * 60 < need_h * 60 - INTERVAL_SLACK_MIN:
            print(f"\n[{lid}] 건너뜀: {age_h:.1f}시간 전에 갱신됨 (간격 {need_h}시간)")
            continue
        chaos = fetch_chaos_prices(lid)
        rates = build_rates(chaos)
        show(lid, chaos, rates)
        if rates:
            results[lid] = rates
        time.sleep(0.5)
    if not results:
        if skipped_only(season + [std], store, intervals, args.force, active_ids):
            print("\n이번 실행에서 갱신할 리그가 없습니다 (모두 갱신 간격 이내).")
            return
        sys.exit("poe.ninja 에서 읽은 값이 없어 저장하지 않습니다.")
    if args.dry_run:
        print("\n(--dry-run: 저장하지 않음)")
        return
    data = save(args.out, store, season, std, results)
    print(f"\n-> {args.out} 저장 (리그: {', '.join(data['leagues'])})")


if __name__ == "__main__":
    main()
