"""PoE2 poe.ninja: 핵 불안정화기(Core Destabiliser) + 영혼 핵(Soul Core) 가격 조회 (soulcore-flip.txt 기준).

조회 대상 (52종 = 불안정화기 1 + 영혼 핵 51):
  - 핵 불안정화기 Core Destabiliser                        1종
  - 영혼 핵 [Soul Cores]                                   15종  (soulcore)
  - 엔드게임 영혼 핵 [Endgame Soul Cores]                  32종  (endgame)
  - 고대 영혼 핵 [Ancient Soul Cores] (Thesis)             4종   (ancient)

가격 읽는 방법 (poe2_overquality-flip.py 의 poe.ninja 환율 로직과 같다):
  - poe.ninja PoE2 화폐 거래소 집계(exchange overview, 약 1시간 단위 갱신)를 카테고리별로 읽는다.
    Currency 에서 Divine / Chaos 의 Exalted 가격(환율)을 구하고, 품목마다 포함된 카테고리를 찾아 Exalted 기준 가격으로 환산한다.
  - poe.ninja 의 primaryValue 는 기준 화폐(core.primary, adaptive)로 매긴 값이라 싼 품목은 오차가 크다.
    그래서 '그 품목이 실제로 거래되는 화폐로 매겨진 시세'(maxVolumeCurrency / maxVolumeRate)를 우선 쓴다. 순서: Exalted -> Divine -> Chaos.
  - 고대 영혼 핵(ancient)만 순서가 다르다: Divine Orb 로 매겨진 시세를 먼저 보고, 없으면 그 품목의 maxVolumeCurrency(거래량이 가장 많은
    상대 화폐)로 매겨진 시세를 Exalted 로 환산한다. 그래도 없으면 위의 기본 순서(Exalted -> Divine -> Chaos)로 읽는다.
  - 모든 가격은 Exalted 기준(ex)과 Divine 환산(div)을 함께 저장한다. 소프트코어 리그만 쓴다 (하드코어·SSF 제외).
  - 이번 실행에서 가격을 못 찾은 품목은, 같은 리그의 이전 값이 있으면 stale=true 로 표시해 유지한다.

리그: 최신(latest) 시즌 리그만 (GGG trade2 리그 목록 순서 = 최신 순. 실패하면 poe.ninja 리그 목록 사용).

결과는 이 스크립트 옆의 out/soulcore-prices.json 에 저장된다.

실행:
  python soulcore-prices.py                       # 최신 리그 (기본)
  python soulcore-prices.py --league "이름"        # 리그 이름 직접 지정 (standard 도 가능)
  python soulcore-prices.py --out other/soulcore-prices.json
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

GGG_LEAGUES = "https://www.pathofexile.com/api/trade2/data/leagues"
NINJA = "https://poe.ninja/poe2/api/economy"
UA = "poe2-price-test/0.1 (contact: augustusminu@hotmail.com)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
DEFAULT_OUT = os.path.join(OUT_DIR, "soulcore-prices.json")


# (category, English name, 한글 이름) -- soulcore-flip.txt 의 목록
ITEMS = [
    ("destabiliser", "Core Destabiliser", "핵 불안정화기"),
    # soulcore
    ("soulcore", "Soul Core of Atmohua", "앗모후아의 영혼 핵"),
    ("soulcore", "Soul Core of Azcapa", "아즈카파의 영혼 핵"),
    ("soulcore", "Soul Core of Cholotl", "촐로틀의 영혼 핵"),
    ("soulcore", "Soul Core of Citaqualotl", "시타콰로틀의 영혼 핵"),
    ("soulcore", "Soul Core of Jiquani", "지콰니의 영혼 핵"),
    ("soulcore", "Soul Core of Opiloti", "오필로티의 영혼 핵"),
    ("soulcore", "Soul Core of Puhuarte", "푸후알테의 영혼 핵"),
    ("soulcore", "Soul Core of Quipolatl", "퀴폴라틀의 영혼 핵"),
    ("soulcore", "Soul Core of Tacati", "타카티의 영혼 핵"),
    ("soulcore", "Soul Core of Ticaba", "티카바의 영혼 핵"),
    ("soulcore", "Soul Core of Topotante", "토포탄테의 영혼 핵"),
    ("soulcore", "Soul Core of Tzamoto", "자모토의 영혼 핵"),
    ("soulcore", "Soul Core of Xopec", "조펙의 영혼 핵"),
    ("soulcore", "Soul Core of Zalatl", "잘라틀의 영혼 핵"),
    ("soulcore", "Soul Core of Zantipi", "잔티피의 영혼 핵"),
    # endgame
    ("endgame", "Atmohua's Soul Core of Retreat", "앗모후아의 후퇴의 영혼 핵"),
    ("endgame", "Atziri's Soul Core of Alacrity", "앗지리의 기민성 영혼 핵"),
    ("endgame", "Atziri's Soul Core of Devotion", "앗지리의 현신 영혼 핵"),
    ("endgame", "Atziri's Soul Core of Inoculation", "앗지리의 접종 영혼 핵"),
    ("endgame", "Atziri's Soul Core of Vitality", "앗지리의 활력 영혼 핵"),
    ("endgame", "Cholotl's Soul Core of War", "촐로틀의 전쟁의 영혼 핵"),
    ("endgame", "Citaqualotl's Soul Core of Foulness", "시타콰로틀의 부정의 영혼 핵"),
    ("endgame", "Estazunti's Soul Core of Convalescence", "에스타준티의 요양의 영혼 핵"),
    ("endgame", "Guatelitzi's Soul Core of Endurance", "과텔리치의 인내의 영혼 핵"),
    ("endgame", "Hayoxi's Soul Core of Heatproofing", "하욕시의 내열의 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Abundance", "지콰니의 풍부 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Automation", "지콰니의 자동화 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Malediction", "지콰니의 악담 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Munitions", "지콰니의 군수품 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Quaking", "지콰니의 진동 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Radiance", "지콰니의 광휘 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Rallying", "지콰니의 재집결 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Rippling", "지콰니의 물결 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Severing", "지콰니의 단절 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Snares", "지콰니의 올가미 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Squalls", "지콰니의 돌풍 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Targeting", "지콰니의 대상 지정 영혼 핵"),
    ("endgame", "Jiquani's Soul Core of Thundering", "지콰니의 천둥 영혼 핵"),
    ("endgame", "Opiloti's Soul Core of Assault", "오필로티의 맹공의 영혼 핵"),
    ("endgame", "Quipolatl's Soul Core of Flow", "퀴폴라틀의 흐름의 영혼 핵"),
    ("endgame", "Tacati's Soul Core of Affliction", "타카티의 수난의 영혼 핵"),
    ("endgame", "Topotante's Soul Core of Dampening", "토포탄테의 완화의 영혼 핵"),
    ("endgame", "Tzamoto's Soul Core of Ferocity", "자모토의 흉포함의 영혼 핵"),
    ("endgame", "Uromoti's Soul Core of Attenuation", "우로모티의 감쇠의 영혼 핵"),
    ("endgame", "Xipocado's Soul Core of Dominion", "지포카도의 지배의 영혼 핵"),
    ("endgame", "Xopec's Soul Core of Power", "조펙의 힘의 영혼 핵"),
    ("endgame", "Zalatl's Soul Core of Insulation", "잘라틀의 절연의 영혼 핵"),
    # ancient
    ("ancient", "Citaqualotl's Thesis", "시타콰로틀의 명제"),
    ("ancient", "Guatelitzi's Thesis", "과텔리치의 명제"),
    ("ancient", "Jiquani's Thesis", "지콰니의 명제"),
    ("ancient", "Quipolatl's Thesis", "퀴폴라틀의 명제"),
]

# poe.ninja 에서 찾아볼 카테고리 순서 (PoE2 type 값). Currency 는 환율 때문에 항상 먼저 읽는다.
# 품목을 모두 찾으면 나머지 카테고리는 읽지 않는다.
NINJA_TYPES = ["Currency", "SoulCores", "Abyss", "Fragments", "Essences", "Runes", "Ritual", "Expedition",
               "Delirium", "Breach", "Verisium", "UncutGems", "Idols", "LineageSupportGems"]
CHAIN = ("exalted", "divine", "chaos")       # 품목 가격을 읽을 때 '어떤 화폐로 매겨진 시세'를 볼지의 우선순위
ANCHORS = {"exalted": ("exalted", "exaltedorb"), "divine": ("divine", "divineorb"), "chaos": ("chaos", "chaosorb")}
_EXCLUDE = re.compile(r"\b(hc|ssf|hardcore|ruthless|solo)\b", re.IGNORECASE)

ninja_session = requests.Session()
ninja_session.headers.update({"User-Agent": UA, "Accept": "application/json"})


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _round(v):
    return round(v, 2) if v >= 1 else round(v, 4)


# ---------------------------------------------------------------- poe.ninja (poe2_overquality-flip.py 와 같은 로직)
def ninja_get(path, params=None):
    """poe.ninja 경제 API GET. 429/503 이면 잠깐 기다렸다 최대 3번 시도한다."""
    url = f"{NINJA}/{path}"
    for attempt in range(3):
        r = ninja_session.get(url, params=params, timeout=30)
        if r.status_code in (429, 503) and attempt < 2:
            try:
                wait = int(r.headers.get("Retry-After", 10))
            except ValueError:
                wait = 10
            time.sleep(min(max(wait, 1), 60))
            continue
        r.raise_for_status()
        return r.json()


def _meta_list(src):
    if isinstance(src, dict):
        src = [dict(v, id=v.get("id", k)) if isinstance(v, dict) else {"id": k, "name": v} for k, v in src.items()]
    return [x for x in (src or []) if isinstance(x, dict) and x.get("id") is not None]


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def ninja_parse(resp):
    """exchange overview 응답 정리: lines{id: line}, keys{정규화한 id/이름/detailsId: id}, primary, anchor{exalted/divine/chaos: id}."""
    core = resp.get("core") or {}
    meta = {}
    for src in (resp.get("items"), core.get("items")):
        for it in _meta_list(src):
            meta.setdefault(str(it["id"]), {}).update({k: it[k] for k in ("name", "detailsId") if it.get(k)})
    lines = {str(ln["id"]): ln for ln in resp.get("lines") or [] if isinstance(ln, dict) and ln.get("id") is not None}
    primary = str(core.get("primary") or "")
    keys = {}
    for cid in set(lines) | set(meta) | ({primary} if primary else set()):
        for k in (cid, meta.get(cid, {}).get("name"), meta.get(cid, {}).get("detailsId")):
            if k:
                keys.setdefault(_norm(k), cid)
    anchor = {}
    for name, cands in ANCHORS.items():
        cid = next((keys[k] for k in cands if k in keys), None)
        if cid:
            anchor[name] = cid
    return {"lines": lines, "keys": keys, "primary": primary, "anchor": anchor}


def _direct(ov, cid, cur):
    """cid 1개를 cur 화폐로 나타낸 시세(cur 몇 개). maxVolumeCurrency 가 cur 이면 1 / maxVolumeRate, cur 이 core.primary 면 primaryValue."""
    ln = ov["lines"].get(cid)
    if not ln:
        return None
    rate = _num(ln.get("maxVolumeRate"))
    if rate and _norm(ln.get("maxVolumeCurrency")) == _norm(cur):
        return 1 / rate, "pair"
    pv = _num(ln.get("primaryValue"))
    if pv and cur == ov["primary"]:
        return pv, "primary"
    return None


def _quote(ov, cid, cur):
    if cid == cur:
        return 1.0, "자신"
    r = _direct(ov, cid, cur)
    if r:
        return r
    r = _direct(ov, cur, cid)                      # 직접 시세가 없으면 반대쪽 line 의 역수
    return (1 / r[0], r[1] + " 역수") if r else None


def _ex_price(ov, cid, chain, per):
    """cid 1개의 Exalted 가격. chain 순서대로 '그 화폐로 매겨진 시세'를 찾아 Exalted 로 환산. (Ex 값, 화폐 이름, 출처) 또는 None."""
    for name in chain:
        cur = ov["anchor"].get(name)
        if cur is None or per.get(name) is None:
            continue
        q = _quote(ov, cid, cur)
        if q:
            return q[0] * per[name], name, q[1]
    return None


def ninja_ex_per(ov):
    """Divine / Chaos 1개 = Exalted 몇 개 -> {'exalted': 1.0, 'divine': .., 'chaos': ..}. Exalted 를 찾지 못하면 {}."""
    if "exalted" not in ov["anchor"]:
        return {}
    per = {"exalted": 1.0}
    for fallback in (False, True):
        for name, other in (("divine", "chaos"), ("chaos", "divine")):
            cid = ov["anchor"].get(name)
            if cid is None or name in per:
                continue
            r = _ex_price(ov, cid, (other,) if fallback else ("exalted",), per)
            if r:
                per[name] = r[0]
    return per


# ---------------------------------------------------------------- 리그 선택 (최신 소프트코어 시즌 리그)
def ninja_leagues():
    nl = ninja_get("leagues")
    if isinstance(nl, dict):
        nl = nl.get("leagues") or []
    return [x for x in nl if isinstance(x, dict)]


def ninja_league_id(league, nl):
    """우리 리그 이름에 해당하는 poe.ninja 리그 id (정규화한 id/이름이 정확히 같은 것만)."""
    key = _norm(league)
    for lg in nl:
        if key in (_norm(lg.get("id")), _norm(lg.get("name"))):
            return lg.get("id")
    return None


def latest_league(nl):
    """GGG trade2 리그 목록(API 순서 = 최신 순)의 첫 번째 소프트코어 시즌 리그. 실패하면 poe.ninja 목록의 첫 번째."""
    try:
        r = requests.get(GGG_LEAGUES, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        names = [lg.get("id") or lg.get("text") for lg in r.json().get("result", []) if lg.get("realm") in (None, "poe2")]
        current = [n for n in names if n and n.lower() != "standard" and not _EXCLUDE.search(n)]
        print(f"  감지된 리그(API 순서): {current}  (첫 번째=latest)")
        if current:
            return current[0]
    except (requests.RequestException, ValueError) as e:
        print(f"  GGG 리그 목록 조회 실패 ({str(e)[:200]}) -> poe.ninja 리그 목록으로 대체")
    for lg in nl:
        name = lg.get("name") or lg.get("id")
        if name and str(name).lower() != "standard" and not _EXCLUDE.search(str(name)) and not _EXCLUDE.search(str(lg.get("id"))):
            print(f"  poe.ninja 목록의 첫 시즌 리그 '{name}' 사용 (순서가 최신 순이라는 보장은 없음)")
            return name
    return None


# ---------------------------------------------------------------- 가격 수집
def _max_volume_price(ov, cid, per, cur_ov):
    """품목 line 의 maxVolumeCurrency(거래량이 가장 많은 상대 화폐)로 매겨진 시세를 Exalted 로 환산. (Ex 값, 화폐 이름, 출처) 또는 None.
    1 / maxVolumeRate = 그 화폐로 나타낸 이 품목 1개의 가격. 상대 화폐가 Exalted/Divine/Chaos 가 아니면 Currency 집계(cur_ov)에서 그 화폐의 Exalted 가격을 찾는다."""
    ln = ov["lines"].get(cid) or {}
    rate, mvc = _num(ln.get("maxVolumeRate")), ln.get("maxVolumeCurrency")
    if not rate or not mvc:
        return None
    key = _norm(mvc)
    for name, cands in ANCHORS.items():
        if key in cands or key == _norm(ov["anchor"].get(name)):
            return (per[name] / rate, name, "maxVolumeCurrency") if per.get(name) else None
    cid2 = cur_ov["keys"].get(key) if cur_ov else None
    r = _ex_price(cur_ov, cid2, CHAIN, per) if cid2 else None
    return (r[0] / rate, str(mvc), "maxVolumeCurrency") if r else None


def price_item(ov, cid, category, per, cur_ov):
    """품목 1개의 Exalted 가격. (Ex 값, 화폐 이름, 출처) 또는 None.
    고대 영혼 핵: Divine Orb 시세 -> maxVolumeCurrency 시세 -> (없으면) 기본 순서. 그 외: 기본 순서(Exalted -> Divine -> Chaos)."""
    if category == "ancient":
        r = _ex_price(ov, cid, ("divine",), per) or _max_volume_price(ov, cid, per, cur_ov)
        if r:
            return r
    return _ex_price(ov, cid, CHAIN, per)


def fetch_prices(lid, items):
    """카테고리를 돌며 품목 가격을 읽는다. 반환: (prices{key: dict}, rates{'exalted','divine','chaos'}, 가격 없는 품목 key 집합)."""
    todo = {it["key"]: it for it in items}
    prices, no_price, per, cur_ov = {}, set(), {}, None
    for typ in NINJA_TYPES:
        if not todo and typ != "Currency":
            break
        try:
            ov = ninja_parse(ninja_get("exchange/current/overview", {"league": lid, "type": typ}))
        except (requests.RequestException, ValueError, AttributeError) as e:
            print(f"  poe.ninja {typ} 조회 실패 ({str(e)[:200]})")
            if typ == "Currency":
                raise RuntimeError("Currency 조회 실패: 환율을 알 수 없어 중단")
            continue
        if typ == "Currency":                       # 환율은 Currency 에서 한 번만 구해 모든 카테고리에 쓴다
            per, cur_ov = ninja_ex_per(ov), ov
            if not per:
                raise RuntimeError("Currency 에서 Exalted 를 찾지 못해 중단")
            if "divine" in per and "chaos" in per and per["divine"] <= per["chaos"]:
                raise RuntimeError(f"환율이 비정상 (Divine {per['divine']:.1f} <= Chaos {per['chaos']:.1f} Ex)")
            print(f"  환율: " + ", ".join(f"{k.title()} = {v:.4g} Ex" for k, v in per.items() if k != "exalted"))
        got = 0
        for key, it in list(todo.items()):
            cid = ov["keys"].get(_norm(it["name"]))
            if cid is None:
                continue
            r = price_item(ov, cid, it["category"], per, cur_ov)
            if r:
                prices[key] = {"ex": r[0], "via": r[1], "source": r[2], "type": typ}
                del todo[key]
                no_price.discard(key)
                got += 1
            else:
                no_price.add(key)                   # 카테고리에는 있으나 거래 시세가 없음 (다른 카테고리에 같은 이름이 있을 수도 있어 계속 찾는다)
        print(f"  {typ}: {got}종 찾음 (남은 품목 {len(todo)}종)")
        time.sleep(0.5)
    return prices, per, no_price & set(todo)


def load_previous(path, league):
    """같은 리그의 이전 결과 {key: item}. 다른 리그이거나 읽지 못하면 {}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("league") != league:
            return {}
        return {x["key"]: x for x in data.get("items", []) if isinstance(x, dict) and "key" in x}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def main():
    ap = argparse.ArgumentParser(description="poe.ninja 핵 불안정화기 + 영혼 핵 가격 조회")
    ap.add_argument("--league", default="latest", help="latest(기본) | standard | 리그 이름 직접 지정")
    ap.add_argument("--out", default=DEFAULT_OUT, help="결과 저장 경로 (기본: 스크립트 옆 out/soulcore-prices.json)")
    args = ap.parse_args()

    items = [{"key": slug(en), "category": c, "name": en, "ko": ko} for c, en, ko in ITEMS]

    try:
        nl = ninja_leagues()
    except (requests.RequestException, ValueError) as e:
        sys.exit(f"poe.ninja 리그 목록 조회 실패: {str(e)[:200]}")
    choice = args.league.strip()
    league = latest_league(nl) if choice.lower() == "latest" else ("Standard" if choice.lower() == "standard" else choice)
    if not league:
        sys.exit('최신 리그를 확인하지 못했습니다. --league "이름" 으로 직접 지정하세요.')
    lid = ninja_league_id(league, nl)
    if lid is None:
        names = ", ".join(str(x.get("id")) for x in nl) or "없음"
        sys.exit(f"poe.ninja 에서 '{league}' 리그를 찾지 못함 (poe.ninja 리그: {names})")
    print(f"리그: {league}  (poe.ninja id: {lid})  /  조회 품목 {len(items)}종")

    try:
        prices, per, no_price = fetch_prices(lid, items)
    except RuntimeError as e:
        sys.exit(f"✗ {e}")

    now = utc_stamp()
    prev = load_previous(args.out, league)
    out_items, stale, missing = [], [], []
    for it in items:
        p = prices.get(it["key"])
        row = dict(it)
        if p:
            row.update(ex=_round(p["ex"]), div=_round(p["ex"] / per["divine"]) if per.get("divine") else None,
                       via=p["via"], source=p["source"], type=p["type"], updatedAt=now)
        elif it["key"] in prev and prev[it["key"]].get("ex") is not None:     # 이번에 못 찾음 -> 이전 값 유지
            old = prev[it["key"]]
            row.update({k: old.get(k) for k in ("ex", "div", "via", "source", "type", "updatedAt")}, stale=True)
            stale.append(it["name"])
        else:
            row.update(ex=None, div=None)
            missing.append(it["name"])
        out_items.append(row)

    data = {"version": 1, "league": league, "ninjaLeague": lid, "source": "poe.ninja", "updatedAt": now,
            "rates": {"div": _round(per["divine"]) if per.get("divine") else None,
                      "chaos": _round(per["chaos"]) if per.get("chaos") else None},
            "items": out_items}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, args.out)                       # 쓰다 끊겨도 기존 파일이 깨지지 않도록

    priced = [x for x in out_items if x.get("ex") is not None and not x.get("stale")]
    print(f"\n-> {args.out} 저장: 가격 {len(priced)}종 / 전체 {len(items)}종")
    for x in sorted(priced, key=lambda r: -r["ex"]):
        d = f"{x['div']:.3g} Div" if x.get("div") is not None else "-"
        print(f"  {x['ex']:>10.4g} Ex  ({d:>10})  {x['name']}  |  {x['ko']}")
    if stale:
        print(f"\n이번에 못 찾아 이전 값을 유지(stale) {len(stale)}종: {', '.join(stale)}")
    if missing:
        npc = [m for m in missing if any(it["name"] == m and it["key"] in no_price for it in items)]
        print(f"\n가격 없음 {len(missing)}종: {', '.join(missing)}")
        if npc:
            print(f"  └ 이 중 {len(npc)}종은 poe.ninja 에 항목은 있으나 거래 시세(Exalted/Divine/Chaos 쌍)가 없음")


if __name__ == "__main__":
    main()
