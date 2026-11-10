"""PoE2 trade2: Mageblood 매물 수집 (mageblood-flip.html 용).

조건 : 이름 Mageblood, Instant Buyout(securable)만, identified, NOT corrupted/mirrored,
       판매 가격이 Divine Orb 인 매물만, implicit 'Has # Charm Slot' >= 2,
       같은 Legacy 는 최대 2개(A/B/C/D 또는 A/A/B/C). 그 밖의 조합(A/A/B/B, A/A/A/B, A/A/A/A)은 못 파는 벨트라 수집하지 않는다.
수집 : 가격(Divine)을 PRICE_BANDS 구간으로 나눠 구간마다 싼 쪽 BAND_ASC개 + (구간 매물이 그보다 많으면) 비싼 쪽 BAND_DESC개를 가져와
       전체 가격대를 고르게 덮는다 (싼 쪽 몇 백 건만 보면 모드 가치를 알 수 없기 때문). 매물마다
       Mage's Legacy 4칸(Legacy of Silver 등)과 '중복 1개당 증가 효과 %' 를 읽어 {가격, 통화, 4칸, 효과%, 등록시각} 으로 저장한다.
       모드별 가치 추정과 최적 정지(어디서 리롤을 멈출지)·평균 수익 계산은 mageblood-flip.html 이 한다.
구매가 : 가장 싼 매물 10개로 '적정 최저가'(poe2_overquality-flip.py 의 fair_price 와 같은 규칙)를 계산해 buy 로 저장한다.

레이트리밋·poe.ninja 환율·리그 선택은 poe2_overquality-flip.py 와 같은 방식이다 (환율은 Divine, Chaos 만 읽음).
결과는 이 스크립트 옆 out/prices.json 의 리그 항목 "mageblood" 에 저장된다 (기존 파일이 있으면 병합, rates 보존).

실행:
  python poe2_mageblood-flip.py                      # 최신 리그의 Mageblood 매물 수집 + 환율 갱신
  python poe2_mageblood-flip.py --league "이름"       # 리그 이름 직접 지정
  python poe2_mageblood-flip.py --no-rates           # poe.ninja 환율 갱신 생략
  python poe2_mageblood-flip.py --rates-only         # 환율만 갱신
  python poe2_mageblood-flip.py --out other/prices.json
  (구간 경계·구간당 수집 개수는 스크립트 위쪽 PRICE_BANDS / BAND_ASC / BAND_DESC)
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import requests

BASE = "https://www.pathofexile.com"
POESESSID = ""                        # 선택
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
DEFAULT_OUT = os.path.join(OUT_DIR, "prices.json")
KEEP_LEAGUES = 1
BLOCKED_CHOICES = {"standard", "previous"}
UA = "poe2-price-test/0.1 (contact: augustusminu@gmail.com)"

STATUS = "securable"                  # Instant Buyout 만. 다른 판매 상태(online/available/any 등)는 어떤 검색에도 쓰지 않는다
PRICE_CURRENCY = "divine"             # 판매 가격 통화: Divine Orb 로 올린 매물만 검색 (다른 통화 매물은 조회하지 않음)
MIN_CHARM_SLOTS = 2                   # implicit 'Has # Charm Slot' 최소값
CHARM_STAT_RE = re.compile(r"^Has # Charm Slots?$", re.IGNORECASE)   # trade2 스탯 목록의 텍스트
CHARM_LINE_RE = re.compile(r"Has\s+(\d+)\s+Charm\s+Slots?", re.IGNORECASE)   # 매물 implicit 줄
ITEM_NAME = "Mageblood"
ITEM_TYPE = "Utility Belt"            # 이름 검색 결과가 0건일 때만 type 을 함께 써서 한 번 더 시도
PRICE_BANDS = [1, 140, 160, 200, 260, 350, 500, 800, 1500, 3000, None]   # Divine 구간 경계. 구간 i = [경계 i, 경계 i+1], 마지막 None = 상한 없음
BAND_ASC = 100                        # 구간마다 싼 쪽에서 가져올 매물 수 (검색 1회가 돌려주는 상한이 100)
BAND_DESC = 40                        # 구간 매물이 BAND_ASC 보다 많을 때 비싼 쪽에서 추가로 가져올 매물 수
FETCH_CHUNK = 10                      # fetch 한 번에 최대 10개
BUY_N = 10                            # 구매가(적정 최저가) 판정에 쓰는 가장 싼 매물 수

# Mage's Legacy 14종 (id = 영문 이름 소문자). mageblood-flip.html 의 LEG 와 같아야 한다.
LEGACIES = ["amethyst", "basalt", "bismuth", "diamond", "gold", "granite", "jade",
            "quicksilver", "ruby", "sapphire", "silver", "stibnite", "sulphur", "topaz"]
LEGACY_RE = re.compile(r"Legacy of (%s)\b" % "|".join(LEGACIES), re.IGNORECASE)
EFFECT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*increased\s+effect\s+per\s+duplicate", re.IGNORECASE)
MARKUP_RE = re.compile(r"\[([^\]|]*\|)?([^\]]*)\]")        # "[Silver|Silver]" -> "Silver"


def utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- 적정 최저가 판정 (poe2_overquality-flip.py 와 같은 파라미터) -------------
MIN_LISTINGS = 2
OUTLIER_MIN_N = 4
OUTLIER_RATIO = 0.5
STALE_DAYS = 7
OLD_DAYS = 30
MAX_SKIP = 2
OUTLIER_MAX_AGE_DAYS = 2
CMP_RATES = {"exalted": 1.0, "chaos": 67.0, "divine": 515.0}

session = requests.Session()
session.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
if POESESSID:
    session.cookies.set("POESESSID", POESESSID, domain="www.pathofexile.com")

_printed_headers = False


# ---------------------------------------------------------------- 레이트리밋: 슬라이딩 윈도우 스케줄러
RATE_MARGIN = 1
RATE_PAD = 0.5
MIN_GAP = 0.3
RATE_HEADERS = ("X-Rate-Limit-Ip", "X-Rate-Limit-Account")
DEFAULT_RULES = {
    "search": [(5, 10, 60), (15, 60, 300), (30, 300, 1800), (600, 21600, 3600)],
    "fetch": [(12, 4, 10), (16, 12, 300), (50, 300, 300), (1000, 21600, 1800)],
}


def parse_rules(text):
    out = []
    for part in (text or "").split(","):
        try:
            a, b, c = map(int, part.split(":"))
        except ValueError:
            continue
        out.append((a, b, c))
    return out


class RateLimiter:
    def __init__(self, rules=None):
        self.rules = {k: list(v) for k, v in (rules or {}).items()}
        self.times = {}
        self.pseudo = {}
        self.block = {}
        self.last = -1e9
        self.count = 0

    def wait_time(self, kind, now=None):
        now = time.monotonic() if now is None else now
        wait, why = 0.0, ""
        if self.block.get(kind, 0) - now > 0:
            wait, why = self.block[kind] - now, "차단 해제"
        if self.last + MIN_GAP - now > wait:
            wait, why = self.last + MIN_GAP - now, ""
        ts = self.times.get(kind, [])
        for limit, period, _ in self.rules.get(kind, []):
            cap = max(1, limit - RATE_MARGIN)
            stamps = sorted([t for t in ts if t > now - period] +
                            [t for t in self.pseudo.get((kind, limit, period), []) if t > now - period])
            if len(stamps) >= cap:
                w = stamps[-cap] + period + RATE_PAD - now
                if w > wait:
                    wait, why = w, f"{limit}:{period}"
        return wait, why

    def record(self, kind, now=None):
        now = time.monotonic() if now is None else now
        self.times.setdefault(kind, []).append(now)
        self.last = now
        self.count += 1

    def update(self, kind, headers, now=None):
        now = time.monotonic() if now is None else now
        rules = []
        for name in RATE_HEADERS:
            rules += parse_rules(headers.get(name))
        if rules:
            self.rules[kind] = rules
        ts = self.times.get(kind, [])
        for name in RATE_HEADERS:
            for (limit, period, _), (hits, _p, restricted) in zip(parse_rules(headers.get(name)),
                                                                parse_rules(headers.get(name + "-State"))):
                key = (kind, limit, period)
                ps = [t for t in self.pseudo.get(key, []) if t > now - period]
                local = sum(1 for t in ts if t > now - period) + len(ps)
                if hits > local:
                    ps += [now] * (hits - local)
                self.pseudo[key] = ps
                if restricted > 0:
                    self.block[kind] = max(self.block.get(kind, 0), now + restricted + 1)


limiter = RateLimiter(DEFAULT_RULES)


def request_kind(url):
    return "search" if "/search/" in url else "fetch" if "/fetch/" in url else "data"


def estimate_seconds(n_search, n_fetch, latency=0.5):
    rl = RateLimiter(DEFAULT_RULES)
    seq = []
    for i in range(max(n_search, n_fetch)):
        if i < n_search:
            seq.append("search")
        if i < n_fetch:
            seq.append("fetch")
    now = 0.0
    for kind in seq:
        w, _ = rl.wait_time(kind, now)
        now += w
        rl.record(kind, now)
        now += latency
    return now


def call(method, url, **kw):
    global _printed_headers
    kind = request_kind(url)
    while True:
        wait, why = limiter.wait_time(kind)
        if wait > 0:
            if wait >= 3:
                print(f"  (레이트리밋{' ' + why if why else ''} 보호: {wait:.0f}초 대기)")
            time.sleep(wait)
        limiter.record(kind)
        r = session.request(method, url, timeout=30, **kw)
        limiter.update(kind, r.headers)
        if not _printed_headers:
            for h in ("X-Rate-Limit-Policy", "X-Rate-Limit-Ip", "X-Rate-Limit-Ip-State",
                      "X-Rate-Limit-Account", "X-Rate-Limit-Account-State"):
                if h in r.headers:
                    print(f"  {h}: {r.headers[h]}")
            _printed_headers = True
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60)) + 1
            print(f"  429 -> {wait}초 대기 (같은 IP로 다른 프로그램/브라우저가 요청 중일 수 있음)")
            limiter.block[kind] = max(limiter.block.get(kind, 0), time.monotonic() + wait)
            continue
        if not r.ok:
            raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
        return r.json()


# ---------------------------------------------------------------- poe.ninja 환율 (Exalted 기준, Divine·Chaos 만)
NINJA = "https://poe.ninja/poe2/api/economy"
RATE_ITEMS = {
    "div": ("Divine Orb", ("divine", "divineorb")),
    "chaos": ("Chaos Orb", ("chaos", "chaosorb")),
}
EXALTED_KEYS = ("exalted", "exaltedorb")

ninja_session = requests.Session()
ninja_session.headers.update({"User-Agent": UA, "Accept": "application/json"})


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def ninja_get(path, params=None):
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


def ninja_exalted_values(resp):
    """exchange overview 응답 -> {정규화한 id/이름/detailsId: '1개 = Exalted 몇 개'} (Exalted 를 못 찾으면 {})."""
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
    keys = {}
    for cid in set(value) | set(meta):
        for k in (cid, meta.get(cid, {}).get("name"), meta.get(cid, {}).get("detailsId")):
            if k:
                keys.setdefault(_norm(k), cid)
    ex_id = next((keys[k] for k in EXALTED_KEYS if k in keys), None)
    ex = value.get(ex_id) if ex_id else None
    if not ex:
        return {}
    return {k: value[cid] / ex for k, cid in keys.items() if cid in value}


def ninja_league_id(league, ninja_leagues):
    key = _norm(league)
    for lg in ninja_leagues:
        if key in (_norm(lg.get("id")), _norm(lg.get("name"))):
            return lg.get("id")
    return None


def fetch_ninja_rates(league, ninja_leagues):
    lid = ninja_league_id(league, ninja_leagues)
    if lid is None:
        names = ", ".join(str(x.get("id")) for x in ninja_leagues) or "없음"
        print(f"  [{league}] poe.ninja 에서 같은 이름의 리그를 찾지 못함 (poe.ninja 리그: {names})")
        return None
    try:
        vals = ninja_exalted_values(ninja_get("exchange/current/overview", {"league": lid, "type": "Currency"}))
    except (requests.RequestException, ValueError, AttributeError) as e:
        print(f"  [{league}] poe.ninja Currency 조회 실패 ({str(e)[:200]})")
        return None
    found = {}
    for k, (_, cands) in RATE_ITEMS.items():
        for cand in cands:
            if cand in vals:
                found[k] = vals[cand]
                break
    if "div" in found and "chaos" in found and found["div"] <= found["chaos"]:
        print(f"  [{league}] 값이 비정상(Divine {found['div']:.1f} <= Chaos {found['chaos']:.1f} Ex)이라 저장하지 않음")
        return None
    shown = ", ".join(f"{RATE_ITEMS[k][0]} {found[k]:.4g} Ex" for k in RATE_ITEMS if k in found)
    print(f"  [{league}] {shown or '찾은 항목 없음'}")
    missing = [RATE_ITEMS[k][0] for k in RATE_ITEMS if k not in found]
    if missing:
        print(f"    찾지 못함 (이전 값 유지): {', '.join(missing)}")
    return found or None


def _load(path):
    data = {"version": 1, "leagues": {}}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded.get("leagues"), dict):
                data = loaded
        except (OSError, ValueError):
            print(f"  ⚠ 기존 {path} 를 읽지 못해 새로 만듭니다")
    return data


def _dump(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def save_rates(path, league, found, order=None):
    data = _load(path)
    if order:
        data["order"] = list(order)
    lg = data["leagues"].setdefault(league, {"entries": []})
    rates = lg.setdefault("rates", {})
    for key, v in found.items():
        rates[key] = round(v, 2) if v >= 1 else round(v, 4)
    rates["source"] = "poe.ninja"
    rates["updatedAt"] = utc_stamp()
    _dump(path, data)


def update_rates(leagues, out, order=None):
    print("\n== poe.ninja 환율 (Exalted 기준) ==")
    try:
        nl = ninja_get("leagues")
        if isinstance(nl, dict):
            nl = nl.get("leagues") or []
        nl = [x for x in nl if isinstance(x, dict)]
    except (requests.RequestException, ValueError) as e:
        print(f"  poe.ninja 리그 목록 조회 실패 ({str(e)[:200]}) -> 환율은 이전 값 그대로")
        return
    for league in leagues:
        try:
            found = fetch_ninja_rates(league, nl)
        except Exception as e:
            print(f"  [{league}] 환율 처리 중 오류 ({str(e)[:200]})")
            continue
        if found:
            save_rates(out, league, found, order)
            print(f"  -> {out} 저장 ({league} / rates)")


# ---------------------------------------------------------------- 리그 선택
_EXCLUDE = re.compile(r"\b(hc|ssf|hardcore|ruthless|solo)\b", re.IGNORECASE)


def fetch_leagues():
    data = call("GET", f"{BASE}/api/trade2/data/leagues")
    names = []
    for lg in data.get("result", []):
        if lg.get("realm") not in (None, "poe2"):
            continue
        name = lg.get("id") or lg.get("text")
        if name:
            names.append(name)
    return names


def known_latest(path):
    try:
        with open(path, encoding="utf-8") as f:
            leagues = json.load(f)["leagues"]
        found = [(str(v.get("collectedAt", "")), k) for k, v in leagues.items()
                 if k.lower() != "standard" and (v.get("mageblood") or {}).get("listings")]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return max(found)[1] if found else None


def resolve_league(choice, out_path):
    key = choice.strip().lower()
    if key in BLOCKED_CHOICES:
        print(f"  '{choice.strip()}' 리그는 수집하지 않습니다 (BLOCKED_CHOICES)")
        return None
    if key != "latest":
        return choice.strip()
    names = None
    try:
        names = fetch_leagues()
    except Exception as e:
        print(f"  리그 목록 조회 실패 ({e})")
    if names is not None:
        current = [n for n in names if n.lower() != "standard" and not _EXCLUDE.search(n)]
        print(f"  감지된 리그(API 순서): {current}  (첫 번째를 latest로 간주)")
        if current:
            return current[0]
        print(f"  '{choice}' 리그를 찾지 못함")
    saved = known_latest(out_path)
    if saved:
        print(f"  -> 저장된 데이터의 가장 최근 리그 '{saved}' 사용")
        return saved
    return None


# ---------------------------------------------------------------- 검색 / 파싱
_charm_stat = None


def charm_stat_id():
    """trade2 스탯 목록에서 implicit 'Has # Charm Slot' 의 id 를 찾는다 (한 번만 조회). 못 찾으면 RuntimeError."""
    global _charm_stat
    if _charm_stat:
        return _charm_stat
    data = call("GET", f"{BASE}/api/trade2/data/stats")
    found = [e["id"] for grp in data.get("result") or [] for e in grp.get("entries") or []
             if str(e.get("id", "")).startswith("implicit.") and CHARM_STAT_RE.match(str(e.get("text", "")).strip())]
    if not found:
        raise RuntimeError("trade2 스탯 목록에서 implicit 'Has # Charm Slot' 을 찾지 못함 (CHARM_STAT_RE 확인)")
    if len(found) > 1:
        print(f"  ⚠ 'Has # Charm Slot' 후보 {len(found)}개 {found} -> 첫 번째 사용")
    _charm_stat = found[0]
    print(f"  Charm Slot 스탯 id: {_charm_stat}")
    return _charm_stat


def build_query(with_type=False, pmin=None, pmax=None):
    q = {
        "status": {"option": STATUS},
        "name": ITEM_NAME,
        "stats": [{"type": "and", "filters": [{"id": charm_stat_id(), "value": {"min": MIN_CHARM_SLOTS},
                                                "disabled": False}]}],
        "filters": {
            "misc_filters": {"filters": {"identified": {"option": "true"},
                                         "corrupted": {"option": "false"},
                                         "mirrored": {"option": "false"}}},
            "trade_filters": {"filters": {"price": dict({"option": PRICE_CURRENCY,
                                                         "min": pmin if pmin is not None else 1},
                                                        **({"max": pmax} if pmax is not None else {}))}},
        },
    }
    if with_type:
        q["type"] = ITEM_TYPE
    return q


def search(league, order, with_type=False, pmin=None, pmax=None):
    body = {"query": build_query(with_type, pmin, pmax), "sort": {"price": order}}
    return call("POST", f"{BASE}/api/trade2/search/poe2/{league}", json=body)


def clean(text):
    return MARKUP_RE.sub(lambda m: m.group(2), str(text))


def item_lines(item):
    lines = []
    for key in ("implicitMods", "explicitMods", "fracturedMods", "enchantMods", "craftedMods"):
        for t in item.get(key) or []:
            if isinstance(t, dict):                      # {'description': ..., 'hash': ..., ...} 형식
                t = t.get("description") or ""
            lines.extend(clean(t).split("\n"))
    return lines


def deep_strings(o, skip=("icon",)):
    """item 안의 모든 문자열을 중첩 dict/list 까지 훑어서 돌려준다 (icon URL 은 제외)."""
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in skip:
                yield from deep_strings(v, skip)
    elif isinstance(o, list):
        for v in o:
            yield from deep_strings(v, skip)


def parse_item(item):
    """(Legacy 4칸 id 목록, 중복 1개당 효과 % 또는 None). 4칸을 못 읽으면 legacies 길이가 4가 아니다.
    모드 텍스트 줄(implicit/explicit 등)에 Legacy 가 없으면 extended·properties 같은 dict 전체에서 다시 찾는다."""
    lines = item_lines(item)
    legacies = [m.group(1).lower() for ln in lines for m in LEGACY_RE.finditer(ln)]
    if not legacies:
        lines = [ln for t in deep_strings(item) for ln in clean(t).split("\n")]
        legacies = [m.group(1).lower() for ln in lines for m in LEGACY_RE.finditer(ln)]
    effect = None
    for ln in lines:
        m = EFFECT_RE.search(ln)
        if m:
            effect = float(m.group(1))
            break
    return legacies, effect


def charm_slots(item):
    """매물 implicit 의 'Has N Charm Slots' 값 (못 읽으면 None)."""
    for ln in item_lines(item):
        m = CHARM_LINE_RE.search(ln)
        if m:
            return int(m.group(1))
    return None


def sellable(legacies):
    """판매 가능한 조합: 4칸이 모두 다르거나(1+1+1+1) 한 쌍만 중복(2+1+1)."""
    return sorted(Counter(legacies).values()) in ([1, 1, 1, 1], [1, 1, 2])


def fetch_rows(search_res, ids, seen):
    """ids 를 FETCH_CHUNK 개씩 가져와 파싱한다. seen: 이미 가져온 id 집합.
    반환 (rows, 파싱 실패 수, 조건 불일치로 제외한 수의 Counter)."""
    rows, bad, ex = [], 0, Counter()
    ids = [i for i in ids if i not in seen]
    for k in range(0, len(ids), FETCH_CHUNK):
        chunk = ids[k:k + FETCH_CHUNK]
        f = call("GET", f"{BASE}/api/trade2/fetch/{','.join(chunk)}", params={"query": search_res["id"]})
        for e in f.get("result") or []:
            if not e:
                continue
            seen.add(e.get("id"))
            listing = e.get("listing") or {}
            price = listing.get("price") or {}
            item = e.get("item") or {}
            legacies, effect = parse_item(item)
            if item.get("name") and item["name"] != ITEM_NAME:
                continue
            if item.get("corrupted") or price.get("amount") is None or price.get("currency") is None:
                continue
            if item.get("identified") is False:
                ex["미감정"] += 1
                continue
            if price["currency"] != PRICE_CURRENCY:
                ex["Divine 외 통화"] += 1
                continue
            slots = charm_slots(item)
            if slots is not None and slots < MIN_CHARM_SLOTS:
                ex["Charm Slot 부족"] += 1
                continue
            if len(legacies) != 4:
                bad += 1
                if bad <= 2:
                    print(f"  ⚠ Legacy 4칸을 읽지 못한 매물(읽은 것: {legacies}). 항목: {sorted(item.keys())}. 아래 모드 줄을 확인하세요:")
                    for ln in item_lines(item):
                        print(f"      {ln}")
                    if bad == 1:      # 첫 실패 매물은 원본 구조를 그대로 보여 준다 (파서를 맞추기 위함)
                        raw = json.dumps({k: v for k, v in item.items() if k != "icon"}, ensure_ascii=False)
                        print(f"      raw item (icon 제외, 앞 3000자): {raw[:3000]}")
                continue
            if not sellable(legacies):
                ex["못 파는 조합"] += 1
                continue
            dup = 4 - len(set(legacies))
            rows.append({"a": price["amount"], "c": price["currency"], "g": legacies,
                         "e": effect if dup else None, "t": listing.get("indexed")})
    return rows, bad, ex


def collect(league):
    """Mageblood 매물을 가격 구간별로 가져와 prices.json 의 league.mageblood 로 저장할 dict 를 반환. 매물이 없으면 None.
    구간마다 싼 쪽 BAND_ASC 건, 구간 매물이 더 많으면 비싼 쪽 BAND_DESC 건도 가져온다 (같은 매물은 한 번만)."""
    print(f"\n=== {ITEM_NAME} ({league}) ===")
    seen, rows, bad, total, with_type, excl, bands = set(), [], 0, 0, False, Counter(), []
    for bi in range(len(PRICE_BANDS) - 1):
        lo, hi = PRICE_BANDS[bi], PRICE_BANDS[bi + 1]
        s = search(league, "asc", with_type, lo, hi)
        if bi == 0 and not s.get("result"):
            s2 = search(league, "asc", True, lo, hi)
            if s2.get("result"):
                print("  이름 검색 결과 0건 -> type 을 함께 지정해 검색")
                with_type, s = True, s2
        n = s.get("total", 0)
        total += n
        ids = (s.get("result") or [])[:BAND_ASC]
        got, b, x = fetch_rows(s, ids, seen) if ids else ([], 0, Counter())
        if n > len(ids):                          # 구간에 더 있으면 비싼 쪽 끝도 본다
            d = search(league, "desc", with_type, lo, hi)
            r2, b2, x2 = fetch_rows(d, (d.get("result") or [])[:BAND_DESC], seen)
            got, b, x = got + r2, b + b2, x + x2
        rows += got
        bad += b
        excl += x
        bands.append({"lo": lo, "hi": hi, "total": n, "used": len(got)})
        print(f"  [{lo}~{hi if hi is not None else '∞'} D] {n}건 중 {len(got)}건 사용 (누적 {len(rows)}건)")
    if excl:
        print(f"  조건 불일치로 제외: {', '.join(f'{k} {v}건' for k, v in excl.items())}")
    if bad:
        print(f"  ⚠ 파싱하지 못해 제외한 매물 {bad}건 (읽은 매물 {len(rows)}건)")
    if rows:
        r = rows[0]
        print(f"  예시: {r['a']} {r['c']} | {', '.join(r['g'])} | 효과 {r['e']}")
    if not rows:
        return None
    buy_rows = sorted(({"amount": r["a"], "currency": r["c"], "indexed": r["t"]} for r in rows),
                      key=lambda r: (_ex(r) if _ex(r) is not None else 1e18))[:BUY_N]
    buy = fair_price(buy_rows)
    if buy["status"] == "ok":
        print(f"  구매가(적정 최저가): {buy['a']} {buy['c']}  [{buy['confidence']}] {buy['reason']}")
    else:
        print(f"  구매가 판정 불가: {buy['reason']}")
    return {"total": total, "fetched": len(rows), "partial": total > len(seen), "bands": bands,
            "listings": rows, "buy": buy, "skipped": bad, "excluded": dict(excl)}


# ---------------------------------------------------------------- 후처리: 구매가(적정 최저가)
def _ex(r):
    rate = CMP_RATES.get(r["currency"])
    if rate is None or r["amount"] is None:
        return None
    return r["amount"] * rate


def age_days(r):
    t = r.get("indexed")
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)


_CONF_LEVELS = ["low", "medium", "high"]


def fair_price(rows):
    """적정 최저가 판정 (poe2_overquality-flip.py 의 fair_price 와 같음).
    반환: status(ok|insufficient), a, c, n, confidence(high|medium|low|None), skipped, age, reason"""
    usable = sorted((r for r in rows if _ex(r) is not None), key=_ex)
    n = len(usable)
    if n < MIN_LISTINGS:
        return {"status": "insufficient", "a": None, "c": None, "n": n,
                "confidence": None, "skipped": 0,
                "reason": f"정상 매물 {n}개 < 최소 {MIN_LISTINGS}개"}
    vals = [_ex(r) for r in usable]
    skipped = 0
    notes = []
    if n >= OUTLIER_MIN_N:
        med = statistics.median(vals)
        cheap = 0
        while cheap < n and vals[cheap] < med * OUTLIER_RATIO:
            a = age_days(usable[cheap])
            if a is not None and a >= OUTLIER_MAX_AGE_DAYS:
                break
            cheap += 1
        limit = min(MAX_SKIP, n // 3)
        if 0 < cheap <= limit:
            skipped = cheap
            notes.append(f"중앙값의 {OUTLIER_RATIO:.0%} 미만인 최근 저가 {cheap}개 제외")
        elif cheap > limit:
            notes.append(f"저가 {cheap}개가 몰려 있어 실제 시세로 간주")
        if cheap < n and vals[cheap] < med * OUTLIER_RATIO:
            notes.append(f"중앙값의 {OUTLIER_RATIO:.0%} 미만이지만 {age_days(usable[cheap]):.0f}일째 안 팔린 매물이라 "
                         f"제외하지 않음(그 가격에 거래되지 않는다는 뜻)")
    else:
        notes.append(f"매물 {n}개뿐이라 이상치 판정 불가, 최저가 사용")
    chosen = usable[skipped]
    valid = vals[skipped:]
    valid_n = len(valid)
    rel = valid[0] / statistics.median(valid)
    if valid_n >= 5 and rel >= 0.8:
        conf = "high"
    elif valid_n >= 3 and rel >= 0.6:
        conf = "medium"
    else:
        conf = "low"
    notes.insert(0, f"매물 {valid_n}개, 최저가/중앙값 {rel:.0%}")
    age = age_days(chosen)
    if age is not None:
        drop = 2 if age >= OLD_DAYS else 1 if age >= STALE_DAYS else 0
        if drop:
            conf = _CONF_LEVELS[max(0, _CONF_LEVELS.index(conf) - drop)]
            notes.append(f"최저가 매물이 {age:.0f}일 전 등록이라 신뢰도 {drop}단계 하향")
    return {"status": "ok", "a": chosen["amount"], "c": chosen["currency"], "n": valid_n,
            "confidence": conf, "skipped": skipped,
            "age": None if age is None else round(age, 1), "reason": "; ".join(notes)}


# ---------------------------------------------------------------- 저장 (mageblood-flip.html 이 읽는 prices.json)
def load_order(path):
    try:
        with open(path, encoding="utf-8") as f:
            order = json.load(f).get("order")
    except (OSError, ValueError, AttributeError):
        return []
    return [x for x in order if isinstance(x, str)] if isinstance(order, list) else []


def merge_order(path, seasonal, has_latest):
    old = load_order(path)
    if old and not has_latest:
        return old[:KEEP_LEAGUES]
    return (seasonal + [x for x in old if x not in seasonal])[:KEEP_LEAGUES]


def save_mageblood(path, league, payload, order=None):
    """같은 리그의 mageblood 항목만 갈아끼우고 rates 등 나머지는 보존한다."""
    data = _load(path)
    if order:
        data["order"] = list(order)
    lg = data["leagues"].setdefault(league, {"entries": []})
    payload["collectedAt"] = utc_stamp()
    lg["mageblood"] = payload
    lg["collectedAt"] = payload["collectedAt"]
    _dump(path, data)


def main():
    ap = argparse.ArgumentParser(description="PoE2 trade2 Mageblood 매물 수집")
    ap.add_argument("--league", default="latest",
                    help="latest | 리그 이름 직접 지정. 쉼표로 여러 개. standard, previous 는 수집하지 않음 (기본: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="결과 저장 경로 (기본: 스크립트 옆 out/prices.json, 기존 파일이 있으면 병합)")
    ap.add_argument("--no-rates", action="store_true", help="poe.ninja 환율 갱신을 건너뜀")
    ap.add_argument("--rates-only", action="store_true", help="poe.ninja 환율만 갱신하고 끝냄 (GGG 검색 없음)")
    args = ap.parse_args()

    leagues, choices = [], [c.strip().lower() for c in args.league.split(",")]
    for choice in args.league.split(","):
        if not choice.strip():
            continue
        lg = resolve_league(choice, args.out)
        if lg is None:
            print(f"리그 '{choice.strip()}' 를 확인하지 못해 건너뜁니다")
        elif lg not in leagues:
            leagues.append(lg)
    if not leagues:
        sys.exit('수집할 리그를 확인하지 못했습니다. --league "이름" 으로 직접 지정하세요.')

    seasonal = [l for l in leagues if l.lower() != "standard"]
    order = merge_order(args.out, seasonal, "latest" in choices)
    if not args.no_rates:
        update_rates(leagues, args.out, order)
        if args.rates_only:
            return
    n_band = len(PRICE_BANDS) - 1
    n_search = n_band * 2 * len(leagues)                                  # 구간마다 asc + (필요하면) desc
    n_fetch = n_band * (BAND_ASC + BAND_DESC) // FETCH_CHUNK * len(leagues)
    print(f"리그: {', '.join(leagues)}")
    print(f"요청 최대 {n_search + n_fetch}회 (검색 {n_search} + fetch {n_fetch}) · 레이트리밋 기준 최단 약 "
          f"{estimate_seconds(n_search, n_fetch) / 60:.1f}분")

    started = time.monotonic()
    failed = []
    for league in leagues:
        print(f"\n######## 리그: {league} ########")
        try:
            payload = collect(league)
        except (RuntimeError, requests.RequestException) as e:
            print(f"  ✗ {league} 조회 실패: {str(e)[:300]}")
            failed.append(league)
            continue
        if payload is None:
            print("  저장할 매물이 없습니다 (기존 데이터 유지)")
            failed.append(league)
            continue
        save_mageblood(args.out, league, payload, order)
        print(f"  -> {args.out} 저장 ({league} / mageblood, 매물 {payload['fetched']}건)")
    print(f"\n완료: 요청 {limiter.count}회, 소요 {(time.monotonic() - started) / 60:.1f}분"
          + (f", 실패 {len(failed)}건: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
