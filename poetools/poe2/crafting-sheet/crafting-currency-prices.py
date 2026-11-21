#!/usr/bin/env python3
"""
크래프팅 시트(crafting-sheet.html)용 재화 시세 수집 - poe.ninja (PoE 2)

수집할 재화는 이 파일 맨 위의 '사용자 설정' 구간에서 수정합니다.
가격은 모두 디바인 오브(Divine Orb) 1개 기준 단가로 변환해 저장합니다(페이지의 PRICES 형식과 동일).

사용법:
  python crafting-currency-prices.py                          # CURRENCIES 목록을 받아 crafting-currency-prices.js 생성
  python crafting-currency-prices.py --list                   # poe.ninja가 알려주는 리그 목록 출력
  python crafting-currency-prices.py --league "Runes of Aldur"  # LEAGUE 설정 대신 리그를 직접 지정(이름 또는 id)
  python crafting-currency-prices.py --dump-currencies all.txt  # 조회 가능한 전체 재화 이름을 붙여넣기용 텍스트로 저장
  python crafting-currency-prices.py --no-cache               # 30분 이내 받은 응답도 무시하고 새로 요청
  python crafting-currency-prices.py --out "C:\\path\\to\\folder" # 결과 저장 폴더 지정(기본: 이 스크립트가 있는 폴더)

저장 위치(기본값: 이 스크립트가 있는 폴더):
  crafting-currency-prices.js             결과(페이지가 <script> 로 읽음. 파일을 직접 열어도 동작)
  raw_data/                               poe.ninja 원본 응답 캐시(지워도 됩니다)

데이터 출처: poe.ninja 공식 이코노미 API  https://poe.ninja/docs/api
  · PoE 2 데이터는 대략 1시간마다 갱신됩니다. 그보다 자주 돌려도 새 데이터가 나오지 않습니다.
  · 요청 실패·재화 미발견 등으로 결과가 하나도 없으면 기존 JS 파일은 덮어쓰지 않습니다.
"""

import argparse
import datetime as dt
import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # 결과 파일의 기본 저장 위치(스크립트와 같은 폴더)

# =============================================================================
# 사용자 설정 - 이 구간만 수정하면 됩니다
# =============================================================================

# ---- 리그 --------------------------------------------------------------------
# 비워 두면 poe.ninja 가 알려주는 '현재 챌린지 리그'(리그 목록의 첫 번째)를 자동으로 씁니다.
# 직접 지정하려면 리그 이름이나 id 를 적으세요(대소문자·공백 무시). 예) "Runes of Aldur", "Standard"
# 이름은 `--list` 로 확인할 수 있습니다. 명령줄의 --league 가 있으면 그쪽이 우선합니다.
LEAGUE = ""

# ---- 수집할 재화 ---------------------------------------------------------------
#   · 한 줄에 이름 하나. 앞에 '#'을 붙이면 그 줄(또는 '#' 뒤)은 무시됩니다.
#   · 빈 줄, [카테고리] 제목 줄은 무시되므로 그룹 구분용으로 자유롭게 쓰세요(카테고리는 검색에 쓰이지 않음).
#   · 대소문자와 기호(' - 공백 등)는 구분하지 않습니다. 예) "Perfect Jewellers Orb" = "Perfect Jeweller's Orb"
#   · 결과 파일에는 poe.ninja 의 정식 영어 이름으로 기록됩니다(페이지의 재화 이름과 같은 표기).
#   · 영어 이름 오른쪽에 한글명을 적으면 결과 파일의 names_ko 에 함께 담기고, 페이지가 한글로 표시·검색합니다.
#       Divine Orb 디바인 오브             <- 영어 뒤에 한글이 오면 자동으로 구분됩니다
#       Chaos Orb | 카오스 오브             <- '|' · 탭 · ',' 로 구분해도 됩니다
#     한글명은 생략해도 되고, 일부 줄에만 적어도 됩니다.
#   · 목록에 없는 이름은 경고와 함께 비슷한 이름을 알려 줍니다. 전체 이름은 `--dump-currencies 파일.txt` 로 뽑을 수 있습니다.
CURRENCIES = """

[Currency]
Divine Orb                      디바인 오브
Exalted Orb                     엑잘티드 오브
Greater Exalted Orb             상위 엑잘티드 오브
Perfect Exalted Orb             완벽한 엑잘티드 오브
Chaos Orb                       카오스 오브
Greater Chaos Orb               상위 카오스 오브
Perfect Chaos Orb               완벽한 카오스 오브
Regal Orb                       제왕의 오브
Greater Regal Orb               상위 제왕의 오브
Perfect Regal Orb               완벽한 제왕의 오브
Orb of Transmutation            진화의 오브
Greater Orb of Transmutation    상위 진화의 오브
Perfect Orb of Transmutation    완벽한 진화의 오브
Orb of Augmentation             확장의 오브
Greater Orb of Augmentation     상위 확장의 오브
Perfect Orb of Augmentation     완벽한 확장의 오브
Orb of Annulment                소멸의 오브
Orb of Alchemy                  연금술의 오브
Vaal Orb                        바알 오브
Fracturing Orb                  분열의 오브
Hinekora's Lock                 히네코라의 머리카락

[Essences]
Essence of the Breach               균열의 에센스
Essence of the Abyss                심연의 에센스
Greater Essence of Body             상위 육신의 에센스
Perfect Essence of Body             완벽한 육신의 에센스
Greater Essence of Mind             상위 정신의 에센스
Perfect Essence of Mind             완벽한 정신의 에센스
Greater Essence of Insulation       상위 절연의 에센스
Greater Essence of Thawing          상위 해동의 에센스
Greater Essence of Grounding        상위 접지의 에센스
Greater Essence of Ruin             상위 폐허의 에센스
Perfect Essence of Ruin             완벽한 폐허의 에센스
Greater Essence of Opulence         상위 풍요의 에센스
Perfect Essence of Opulence         완벽한 풍요의 에센스
Perfect Essence of Enhancement      완벽한 강화의 에센스

[Abyss]
Preserved Jawbone               보존된 턱뼈
Preserved Rib                   보존된 갈비뼈
Preserved Collarbone            보존된 빗장뼈
Preserved Cranium               보존된 두개골
Ancient Jawbone                 고대의 턱뼈   
Ancient Rib                     고대의 갈비뼈
Ancient Collarbone              고대의 빗장뼈
Omen of Light                   빛의 징조
Omen of Abyssal Echoes          심연의 메아리의 징조
Omen of the Liege               군왕의 징조 (아마나무)
Omen of the Sovereign           군주의 징조 (울라만)
Omen of the Blackblooded        검은 피의 징조 (쿠르갈)

[Ritual]
Omen of Whittling                   절사의 징조
Omen of Sinistral Annulment         좌측 소멸의 징조
Omen of Sinistral Erasure           좌측 말소의 징조
Omen of Dextral Annulment           우측 소멸의 징조
Omen of Dextral Erasure             우측 말소의 징조
Omen of Sinistral Crystallisation   좌측 결정화의 징조
Omen of Dextral Crystallisation     우측 결정화의 징조
Omen of Greater Exaltation          상위 찬미의 징조
Omen of Sinistral Exaltation        좌측 찬미의 징조
Omen of Dextral Exaltation          우측 찬미의 징조
Omen of Catalysing Exaltation       촉진하는 찬미의 징조
Omen of Sinistral Necromancy        좌측 강령술의 징조
Omen of Dextral Necromancy          우측 강령술의 징조

[Breach]
Flesh Catalyst          육체 기폭제
Neural Catalyst         신경 기폭제
Carapace Catalyst       갑각 기폭제
Uul-Netol's Catalyst    울네툴의 기폭제
Xoph's Catalyst         조프의 기폭제
Tul's Catalyst          툴의 기폭제
Esh's Catalyst          에쉬의 기폭제
Chayula's Catalyst      차율라의 기폭제
Reaver Catalyst         강탈자 기폭제
Sibilant Catalyst       쇳소리 기폭제

[Expedition]
Runic Alloy             룬 합금
Swift Alloy             재빠른 합금
Sovereign Alloy         군왕의 합금
# Mystic Alloy          신비한 합금
# Prismatic Alloy       분광 합금  
# Cyclonic Alloy        회오리바람 합금
# Expansive Alloy       팽창하는 합금 
# Protective Alloy      보호의 합금 
# Adaptive Alloy        적응형 합금 

[Bloodmark]



"""

# ---- 이름 별칭 ------------------------------------------------------------------------
# poe.ninja 는 기본 재화 등 일부를 짧은 id(annul, regal, vaal …)로만 알려 줘서, 위 목록의 영어 이름과 글자가 달라
# 못 찾는 경우가 있습니다. 이럴 때 "목록에 적은 영어 이름": "poe.ninja id" 로 연결하세요.
#   · 별칭으로 찾은 재화는 목록에 적은 영어 이름 그대로 결과 파일에 기록됩니다(페이지의 이름·아이콘·한글명과 같은 표기).
#   · id 는 `--dump-currencies 파일.txt` 결과에서 확인할 수 있습니다(재화 이름 자리에 id 가 그대로 나옴).
ALIASES = {
    "Regal Orb": "regal",
    "Orb of Transmutation": "transmute",
    "Orb of Augmentation": "aug",
    "Orb of Annulment": "annul",
    "Orb of Alchemy": "alch",
    "Vaal Orb": "vaal",
    "Orb of Chance": "chance",
    "Mirror of Kalandra": "mirror",
    # 에센스: poe.ninja id 에는 'the' 가 들어감
    "Greater Essence of Body": "greater-essence-of-the-body",
    "Perfect Essence of Body": "perfect-essence-of-the-body",
    "Greater Essence of Mind": "greater-essence-of-the-mind",
    "Perfect Essence of Mind": "perfect-essence-of-the-mind",
}

# ---- 유니크 아이템 검색 ------------------------------------------------------------
# True 면 위 목록 중 '재화 카테고리'에서 못 찾은 이름만 유니크 아이템 시세(stash 엔드포인트)에서 추가로 찾습니다.
# (못 찾은 이름이 없으면 요청하지 않습니다.) 같은 이름의 변형(variant)이 여럿이면 매물이 가장 많은 것을 씁니다.
SEARCH_UNIQUES = True

# ---- 기타 --------------------------------------------------------------------
OUTPUT_JS_FILE = "crafting-currency-prices.js"  # 결과 JS 파일 이름(페이지가 <script> 로 읽음)
JS_VARIABLE = "CRAFT_PRICES"  # JS 파일이 만드는 전역 변수 이름(window.CRAFT_PRICES). 페이지 쪽과 같아야 함
CACHE_MINUTES = 30        # 이 시간(분) 안에 받은 원본 응답이 있으면 재사용. 0 이면 캐시 안 씀
# poe.ninja 는 앱을 식별할 수 있는 User-Agent 와 연락처를 요청합니다. 본인 정보로 바꿔 주세요.
USER_AGENT = "crafting-sheet-prices/1.0 (personal tool; contact: your-email@example.com)"

# =============================================================================
# 여기부터는 수정할 필요 없는 코드
# =============================================================================
BASE = "https://poe.ninja/poe2/api/economy"
MIN_INTERVAL = 1.5  # 초. 요청 사이 최소 간격(커뮤니티 API 이므로 여유를 둠)
QUOTE_CURRENCY = "Divine Orb"

# 재화 교환(exchange) 카테고리 - 위에서부터 차례로 조회하며, 모든 이름을 찾으면 나머지는 요청하지 않음.
# Currency 는 항상 먼저 받습니다(디바인 환산 기준).
EXCHANGE_TYPES = [
    "Currency", "Ritual", "Abyss", "Breach", "Essences", "Fragments", "Expedition", "Delirium",
    "UncutGems", "LineageSupportGems", "SoulCores", "Runes", "Idols", "Verisium",
]
# 유니크 아이템(stash) 카테고리
UNIQUE_TYPES = [
    "UniqueWeapons", "UniqueArmours", "UniqueAccessories", "UniqueFlasks", "UniqueCharms",
    "UniqueJewels", "UniqueSanctumRelics", "UniqueTablets", "PrecursorTablets",
]

_last_request = 0.0


def log(msg=""):
    print(msg, flush=True)


def warn(msg):
    print(msg, file=sys.stderr, flush=True)


def key(s):
    """이름 비교용 키: 소문자로 바꾸고 글자·숫자 외 문자(공백, 아포스트로피 등)를 제거."""
    return re.sub(r"[\W_]+", "", str(s).lower())


ALIAS = {key(k): v for k, v in ALIASES.items()}


def find(index, w):
    """목록의 이름 w -> (찾은 항목 또는 None, 별칭으로 찾았는지). 이름·id 로 먼저 찾고, 없으면 ALIASES 의 id 로 찾는다."""
    e = index.get(key(w))
    if e is None and key(w) in ALIAS:
        e = index.get(key(ALIAS[key(w)]))
        if e is not None:
            return e, True
    return e, False


def safe_name(s):
    return re.sub(r"[^\w\-]+", "_", s).strip("_")


HANGUL = re.compile(r"[\u1100-\u11FF\u3131-\u318E\uAC00-\uD7A3]")


def split_ko(line):
    """'English Name 한글명' / 'English Name | 한글명' -> (영어 이름, 한글명). 한글명이 없으면 ''."""
    for sep in ("|", "\t", ","):
        if sep in line:
            en, ko = line.split(sep, 1)
            return en.strip(), ko.strip()
    m = HANGUL.search(line)
    if m:
        return line[:m.start()].strip(), line[m.start():].strip()
    return line.strip(), ""


def parse_block(text):
    """설정 블록 -> (영어 이름 목록, {key(영어 이름): 한글명}).
    '#' 주석, 빈 줄, [카테고리] 줄은 무시하고 중복(대소문자·기호 무시)은 제거."""
    names, ko, seen = [], {}, set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or (line.startswith("[") and line.endswith("]")):
            continue
        en, kor = split_ko(line)
        if not en:
            warn(f"  경고: 영어 이름이 없는 줄은 건너뜁니다: '{line}'")
            continue
        if key(en) not in seen:
            seen.add(key(en))
            names.append(en)
        if kor:
            ko.setdefault(key(en), kor)
    return names, ko


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def round_sig(x, digits=6):
    return float(f"{x:.{digits}g}")


# ---------------------------------------------------------------- HTTP
def get_json(url, params=None, retries=4, label=None):
    """요청 간격은 조용히 유지하고, 재시도가 필요한 경우에만 한 줄 안내를 출력한다."""
    global _last_request
    if params:
        url += "?" + urllib.parse.urlencode(params)
    tag = label or url
    for attempt in range(1, retries + 1):
        wait = MIN_INTERVAL - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            try:
                return json.loads(body)
            except ValueError:
                raise RuntimeError(f"JSON 이 아닌 응답: {url}") from None
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                backoff = int(retry_after) if retry_after and retry_after.isdigit() else 15 * attempt
                log(f"  {tag}: 서버 응답 HTTP {e.code}, {backoff}초 후 재시도 ({attempt}/{retries})")
                time.sleep(backoff)
                continue
            raise RuntimeError(f"HTTP {e.code}: {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            reason = getattr(e, "reason", e)
            log(f"  {tag}: 네트워크 오류({reason}), 5초 후 재시도 ({attempt}/{retries})")
            time.sleep(5)
    raise RuntimeError(f"요청 실패: {url}")


# ---------------------------------------------------------------- 리그
def fetch_leagues():
    """/poe2/api/economy/leagues -> [{id, name}, ...]. 첫 번째가 현재 챌린지 리그."""
    data = get_json(f"{BASE}/leagues", label="리그 목록")
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [])
    out = []
    for l in data if isinstance(data, list) else []:
        if isinstance(l, str):
            out.append({"id": l, "name": l})
        elif isinstance(l, dict):
            lid = l.get("id") or l.get("name")
            if lid:
                out.append({"id": str(lid), "name": str(l.get("name") or lid)})
    return out


def pick_league(leagues, wanted):
    if not leagues:
        sys.exit("poe.ninja 가 리그 목록을 주지 않았습니다. 잠시 후 다시 시도하세요.")
    if not wanted:
        return leagues[0]
    k = key(wanted)
    for l in leagues:
        if k in (key(l["id"]), key(l["name"])):
            return l
    names = ", ".join(f"{l['name']}" for l in leagues)
    sys.exit(f"리그 '{wanted}' 를 찾지 못했습니다. 조회 가능한 리그: {names}")


# ---------------------------------------------------------------- 개요(overview) 조회
def fetch_overview(kind, league_id, type_, raw_dir, use_cache):
    """kind: 'exchange'(재화 교환) | 'stash'(아이템). 원본 응답은 raw_data/ 에 저장하고, 최근 것이 있으면 재사용."""
    path = raw_dir / f"{safe_name(league_id)}__{kind}__{type_}.json"
    if use_cache and CACHE_MINUTES > 0 and path.exists() and time.time() - path.stat().st_mtime < CACHE_MINUTES * 60:
        try:
            return json.loads(path.read_text(encoding="utf-8")), True
        except ValueError:
            pass  # 깨진 캐시는 무시하고 다시 받음
    url = f"{BASE}/exchange/current/overview" if kind == "exchange" else f"{BASE}/stash/current/item/overview"
    data = get_json(url, {"league": league_id, "type": type_}, label=type_)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data, False


def divine_factor(core, lines):
    """primaryValue 1단위가 디바인 몇 개인지. core.primary 가 항상 divine 이라고 가정하지 않는다.
       1) primary 가 divine 이면 1
       2) core.rates['divine'] (= primary 1개당 divine 수)
       3) 같은 응답의 divine 줄 primaryValue (= divine 1개의 primary 가격)"""
    core = core if isinstance(core, dict) else {}
    if key(core.get("primary") or "") in ("divine", "divineorb"):
        return 1.0
    rates = core.get("rates")
    if isinstance(rates, dict) and is_num(rates.get("divine")) and rates["divine"] > 0:
        return float(rates["divine"])
    for l in lines:
        if key(l.get("id") or "") == "divine" and is_num(l.get("primaryValue")) and l["primaryValue"] > 0:
            return 1.0 / l["primaryValue"]
    return None


def parse_exchange(data):
    """exchange overview -> ([{name, id, div, volume}], 디바인 환산 계수).
    lines[].id 를 core.items(없으면 최상위 items)의 id 와 맞춰 이름을 얻는다."""
    if not isinstance(data, dict):
        raise RuntimeError("예상한 형식이 아닌 응답(exchange)")
    core = data.get("core") if isinstance(data.get("core"), dict) else {}
    meta = {}
    for it in core.get("items") or data.get("items") or []:
        if isinstance(it, dict) and it.get("id") is not None:
            meta[str(it["id"])] = it
    lines = [l for l in data.get("lines") or [] if isinstance(l, dict) and l.get("id") is not None]
    factor = divine_factor(core, lines)
    if factor is None:
        raise RuntimeError("디바인 환산 기준(core.primary / core.rates / divine 줄)을 찾지 못했습니다.")
    out = []
    for l in lines:
        pv = l.get("primaryValue")
        if not is_num(pv) or pv <= 0:
            continue
        lid = str(l["id"])
        name = (meta.get(lid) or {}).get("name") or lid
        vol = l.get("volumePrimaryValue")
        out.append({
            "name": str(name),
            "id": lid,
            "div": 1.0 if key(lid) == "divine" else pv * factor,
            "volume": vol * factor if is_num(vol) else None,
        })
    return out, factor


def parse_stash(data, fallback_factor):
    """stash(유니크) overview -> [{name, id, div, volume}]. 같은 이름은 매물(listingCount)이 가장 많은 줄만 남긴다."""
    if not isinstance(data, dict):
        raise RuntimeError("예상한 형식이 아닌 응답(stash)")
    lines = [l for l in data.get("lines") or [] if isinstance(l, dict) and l.get("name")]
    factor = divine_factor(data.get("core"), lines) or fallback_factor
    if factor is None:
        raise RuntimeError("디바인 환산 기준을 찾지 못했습니다.")
    best = {}
    for l in lines:
        pv = l.get("primaryValue")
        if not is_num(pv) or pv <= 0:
            continue
        k = key(l["name"])
        cnt = l.get("listingCount") if is_num(l.get("listingCount")) else 0
        if k not in best or cnt > best[k][0]:
            best[k] = (cnt, l, pv)
    return [{"name": str(l["name"]), "id": str(l.get("detailsId") or l.get("itemId") or l.get("id") or ""),
             "div": pv * factor, "volume": None} for _, l, pv in best.values()]


# ---------------------------------------------------------------- 메인
def add_entries(index, entries, category):
    for e in entries:
        e["category"] = category
        index.setdefault(key(e["name"]), e)
        if e["id"]:
            index.setdefault(key(e["id"]), e)  # poe.ninja id(exalted 등)로 적어도 찾을 수 있게


def write_atomic(path, text):
    """쓰는 도중 실패해도 기존 파일이 깨지지 않도록 임시 파일에 쓴 뒤 교체한다."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_outputs(out_dir, result):
    """결과를 JS 파일(페이지가 <script> 로 읽음)로 저장하고 저장한 경로 목록을 돌려준다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(result, ensure_ascii=False, indent=1)
    body = body.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")  # 구형 JS 엔진 대비
    js_path = out_dir / OUTPUT_JS_FILE
    write_atomic(js_path, f"window.{JS_VARIABLE} = {body};\n")
    return [js_path]


def dump_currencies(path, league_id, raw_dir, use_cache):
    groups = {}
    for t in EXCHANGE_TYPES:
        try:
            data, cached = fetch_overview("exchange", league_id, t, raw_dir, use_cache)
            entries, _ = parse_exchange(data)
        except RuntimeError as e:
            warn(f"  건너뜀({t}): {e}")
            continue
        groups[t] = sorted({e["name"] for e in entries}, key=str.lower)
        log(f"  {t}: {len(groups[t])}개" + (" (캐시)" if cached else ""))
    lines = []
    for t, names in groups.items():
        lines.append(f"[{t}]")
        lines.extend(names)
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    log(f"전체 {sum(len(v) for v in groups.values())}개 재화를 {path} 에 저장했습니다. "
        f"필요한 줄만 스크립트 상단 CURRENCIES 에 붙여넣으세요.")


def main():
    ap = argparse.ArgumentParser(description="크래프팅 시트용 재화 시세(디바인 기준)를 poe.ninja 에서 받아 JS 파일로 저장")
    ap.add_argument("--list", action="store_true", help="리그 목록만 출력")
    ap.add_argument("--league", metavar="이름 또는 id", help="수집할 리그(스크립트 상단 LEAGUE 보다 우선)")
    ap.add_argument("--dump-currencies", metavar="PATH", help="전체 재화 이름을 붙여넣기용 텍스트로 저장하고 종료")
    ap.add_argument("--out", default=str(SCRIPT_DIR), help="결과 저장 폴더(기본: 스크립트가 있는 폴더)")
    ap.add_argument("--no-cache", action="store_true", help="raw_data/ 의 최근 응답을 무시하고 새로 요청")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

    use_cache = not args.no_cache
    out_dir = Path(args.out)
    raw_dir = out_dir / "raw_data"

    wanted, ko_input = parse_block(CURRENCIES)
    if not wanted and not (args.list or args.dump_currencies):
        sys.exit("수집할 재화가 없습니다. 스크립트 상단 CURRENCIES 를 확인하세요.")

    log("리그 목록 조회 중...")
    try:
        leagues = fetch_leagues()
    except RuntimeError as e:
        sys.exit(f"리그 목록을 받지 못했습니다: {e}")
    if args.list:
        print("poe.ninja 가 반환한 리그 목록 (첫 번째 = 현재 챌린지 리그):")
        for i, l in enumerate(leagues):
            print(f"  [{i}] {l['name']}  (id: {l['id']})")
        return
    league = pick_league(leagues, args.league or LEAGUE)
    log(f"리그: {league['name']} (id: {league['id']})")

    if args.dump_currencies:
        dump_currencies(args.dump_currencies, league["id"], raw_dir, use_cache)
        return

    # 1) 재화 교환 카테고리: Currency 를 먼저 받고, 못 찾은 이름이 남아 있을 때만 다음 카테고리를 조회
    index, base_factor, remaining = {}, None, list(wanted)
    for n, t in enumerate(EXCHANGE_TYPES):
        if n > 0 and not remaining:
            break
        try:
            data, cached = fetch_overview("exchange", league["id"], t, raw_dir, use_cache)
            entries, factor = parse_exchange(data)
        except RuntimeError as e:
            if t == "Currency":
                sys.exit(f"Currency 카테고리를 받지 못해 중단합니다(디바인 환산 기준이 필요): {e}")
            warn(f"  건너뜀({t}): {e}")
            continue
        if t == "Currency":
            base_factor = factor
        add_entries(index, entries, t)
        remaining = [w for w in wanted if find(index, w)[0] is None]
        log(f"  {t}: {len(entries)}종" + (" (캐시)" if cached else "") + (f" / 남은 이름 {len(remaining)}개" if remaining else ""))

    # 2) 남은 이름은 유니크 아이템 시세에서 검색
    if remaining and SEARCH_UNIQUES:
        for t in UNIQUE_TYPES:
            if not remaining:
                break
            try:
                data, cached = fetch_overview("stash", league["id"], t, raw_dir, use_cache)
                entries = parse_stash(data, base_factor)
            except RuntimeError as e:
                warn(f"  건너뜀({t}): {e}")
                continue
            add_entries(index, entries, t)
            remaining = [w for w in wanted if find(index, w)[0] is None]
            log(f"  {t}: {len(entries)}종" + (" (캐시)" if cached else "") + (f" / 남은 이름 {len(remaining)}개" if remaining else ""))

    # 3) 결과 정리(설정 목록의 순서를 유지)
    prices, details, missing, names_ko = {}, {}, [], {}
    for w in wanted:
        e, aliased = find(index, w)
        kor = ko_input.get(key(w), "")
        if e is None:
            missing.append(w)
            if kor:
                names_ko[w] = kor
            close = difflib.get_close_matches(key(w), list(index), n=3, cutoff=0.6)
            hint = ", ".join(dict.fromkeys(index[c]["name"] for c in close))
            warn(f"  경고: '{w}' 을(를) 찾지 못해 건너뜁니다." + (f" 비슷한 이름: {hint}" if hint else ""))
            continue
        name = w if aliased else e["name"]  # 별칭으로 찾았으면 목록에 적은 이름으로 기록
        if kor:
            names_ko.setdefault(name, kor)
        if name in prices:
            continue
        prices[name] = round_sig(e["div"])
        details[name] = {"category": e["category"], "id": e["id"],
                         **({"volume": round_sig(e["volume"], 4)} if e.get("volume") is not None else {})}
        note = f"  (입력 '{w}' -> 정식 이름)" if w != name else (f"  (별칭: {e['name']})" if aliased else "")
        log(f"  {name}{f' ({kor})' if kor else ''}: {prices[name]:g} Div  [{e['category']}]{note}")

    if not prices:
        sys.exit("가격을 하나도 찾지 못했습니다. 기존 파일은 그대로 둡니다. 재화 이름과 리그를 확인하세요.")

    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "poe.ninja",
        "league": league["name"],
        "league_id": league["id"],
        "quote_currency": QUOTE_CURRENCY,
        "prices": prices,      # 페이지의 PRICES 와 같은 형식: {재화 이름: 디바인 단가}
        "details": details,    # 카테고리, poe.ninja id, 거래량(디바인 환산; 낮을수록 가격 신뢰도가 떨어짐)
        "missing": missing,    # 찾지 못한 이름
        "names_ko": names_ko,  # {영어 이름: 한글명} - CURRENCIES 에서 영어 이름 오른쪽에 적은 한글명(페이지가 표시·검색에 사용)
    }
    written = write_outputs(out_dir, result)
    log(f"\n완료: {len(prices)}개 저장" + (f", {len(missing)}개 못 찾음" if missing else "") + " -> " + ", ".join(str(w) for w in written))


if __name__ == "__main__":
    main()
