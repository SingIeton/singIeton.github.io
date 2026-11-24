#!/usr/bin/env python3
"""
크래프팅 시트용 '과거 리그 N일차' 재화 시세 수집 - poe2scout (PoE 2)

crafting-sheet-prices.js 에 시세가 들어 있는 항목들을 대상으로, 지정한 리그의 N일차 가격을
디바인 오브(Divine Orb) 1개 기준 단가로 변환해 저장합니다(기존 파일의 prices 와 같은 단위).

사용법:
  python crafting-sheet-history-scout.py --list                                        # poe2scout 리그 목록 출력
  python crafting-sheet-history-scout.py --league "Fate of the Vaal" --day 4 7 10 15 30
  python crafting-sheet-history-scout.py --league "Fate of the Vaal" --day 7 --start 2025-12-12   # 리그 시작일 직접 지정
  python crafting-sheet-history-scout.py --league "Fate of the Vaal" --day 7 --source "C:\\path\\crafting-sheet-prices.js"
  python crafting-sheet-history-scout.py --league "Fate of the Vaal" --day 7 --no-cache
  python crafting-sheet-history-scout.py --league "Fate of the Vaal" --day 7 --use-cache   # 만료 시간과 무관하게 기존 응답 사용

저장 위치(기본값: 이 스크립트 옆 price-history 폴더):
  crafting-sheet-prices-<리그>-day<일차>.js      결과(window.CRAFT_PRICES_HISTORY). 일차마다 파일이 하나씩 만들어집니다
  raw_data/poe2scout/                              원본 응답 캐시(지워도 됩니다)

계산 방식:
  · poe2scout 의 가격은 엑잘티드 오브 기준이므로, 같은 날 디바인 오브의 엑잘티드 가격으로 나눠 디바인 기준으로 바꿉니다.
    (리그 초반에는 디바인이 매우 비싸므로 '오늘 환율'이 아니라 '그날 환율'을 써야 합니다.)
  · '리그 시작일'은 받아온 시계열 중 가장 이른 날짜(= 1일차)로 잡습니다. --start 로 바꿀 수 있습니다.
  · N일차 = 시작일 + (N-1)일. 그날 데이터가 없으면 ±TOLERANCE_DAYS 안에서 가장 가까운 날을 쓰고, 실제 날짜를 details 에 기록합니다.
  · 이 스크립트는 poe2scout API 의 응답 필드 이름을 문서로 확인하지 못한 채 작성되었습니다. 필드를 찾지 못하면
    실제 필드 목록을 출력하고 멈추니, 그 목록을 알려 주세요(아래 *_FIELDS 후보를 고치면 됩니다).
"""

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SCRIPT_DIR / "price-history"  # 결과 파일의 기본 저장 위치(스크립트 옆 price-history 폴더)

# =============================================================================
# 사용자 설정
# =============================================================================
SOURCE_JS = "crafting-sheet-prices.js"   # 항목 목록을 읽을 파일(price-history 폴더 안). --source 로 바꿀 수 있음
JS_VARIABLE = "CRAFT_PRICES_HISTORY"        # 결과 JS 가 만드는 전역 변수 이름
DAY_COUNT = 500             # DailyStatsHistory 로 요청할 일수(API 는 '최근 N일'을 돌려줌. 리그보다 길어야 시작일이 잘리지 않음)
TOLERANCE_DAYS = 1          # N일차 데이터가 없을 때 허용하는 날짜 차이
FORCE_CACHE = False         # --use-cache 지정 시 True: 만료 시간 무시
CACHE_HOURS = 12            # 이 시간 안에 받은 응답은 재사용(0 이면 캐시 안 씀)
MIN_INTERVAL = 0.5          # 초. 요청 사이 최소 간격(개인이 운영하는 서비스이므로 여유를 둠)
# poe2scout 은 지속 사용 시 User-Agent 에 연락처를 요구합니다. 본인 정보로 바꿔 주세요.
USER_AGENT = "crafting-sheet-history/1.0 (personal tool; contact: your-email@example.com)"

# 응답 필드 후보(소문자로 비교, 앞에 있는 것이 우선). 실제 이름과 다르면 여기에 추가하세요.
NAME_FIELDS = ["text", "name", "itemname", "apiid"]
ID_FIELDS = ["itemid", "id"]
DATE_FIELDS = ["date", "day", "time", "timestamp", "createdat", "datetime"]
PRICE_FIELDS = ["price", "avgprice", "averageprice", "avg", "average", "close"]  # 하루 대표 가격(평균 계열 우선, 없으면 종가)
VOLUME_FIELDS = ["volume", "quantity", "count"]
LEAGUE_NAME_FIELDS = ["value", "name", "leaguename", "text"]

# =============================================================================
BASE = "https://api.poe2scout.com/poe2"
DIVINE = "Divine Orb"
EXALTED_KEY = "exaltedorb"  # poe2scout 가격의 기준 통화(1.0 엑잘티드)

_last_request = 0.0


def log(msg=""):
    print(msg, flush=True)


def warn(msg):
    print(msg, file=sys.stderr, flush=True)


def key(s):
    """이름 비교용 키: 소문자로 바꾸고 글자·숫자 외 문자를 제거."""
    return re.sub(r"[\W_]+", "", str(s).lower())


def safe_name(s):
    return re.sub(r"[^\w\-]+", "_", s).strip("_")


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def round_sig(x, digits=6):
    return float(f"{x:.{digits}g}")


def lower_keys(o):
    if isinstance(o, dict):
        return {str(k).lower(): lower_keys(v) for k, v in o.items()}
    if isinstance(o, list):
        return [lower_keys(x) for x in o]
    return o


def pick(d, candidates):
    for c in candidates:
        if isinstance(d, dict) and d.get(c) is not None:
            return d[c]
    return None


def as_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "history", "data", "logs", "leagues"):
            if isinstance(data.get(k), list):
                return data[k]
        return next((v for v in data.values() if isinstance(v, list)), [])
    return []


# ---------------------------------------------------------------- HTTP (+캐시)
def get_json(path, params=None, raw_dir=None, use_cache=True, retries=4):
    global _last_request
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    cache = None
    if raw_dir is not None and (CACHE_HOURS > 0 or FORCE_CACHE):
        cache = raw_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if use_cache and cache.exists() and (FORCE_CACHE or time.time() - cache.stat().st_mtime < CACHE_HOURS * 3600):
            try:
                return lower_keys(json.loads(cache.read_text(encoding="utf-8")))
            except ValueError:
                pass
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
                data = json.loads(body)
            except ValueError:
                raise RuntimeError(f"JSON 이 아닌 응답: {url}") from None
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return lower_keys(data)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                ra = e.headers.get("Retry-After") if e.headers else None
                backoff = int(ra) if ra and ra.isdigit() else 15 * attempt
                log(f"  서버 응답 HTTP {e.code}, {backoff}초 후 재시도 ({attempt}/{retries})")
                time.sleep(backoff)
                continue
            raise RuntimeError(f"HTTP {e.code}: {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            log(f"  네트워크 오류({getattr(e, 'reason', e)}), 5초 후 재시도 ({attempt}/{retries})")
            time.sleep(5)
    raise RuntimeError(f"요청 실패: {url}")


# ---------------------------------------------------------------- 입력(기존 JS)
def load_wanted(path):
    """crafting-sheet-prices.js -> 시세가 있는 항목 이름 목록(파일 순서 유지)."""
    if not path.exists():
        sys.exit(f"항목 목록 파일을 찾지 못했습니다: {path}  (--source 로 지정하세요)")
    text = path.read_text(encoding="utf-8")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        sys.exit(f"JS 파일에서 JSON 본문을 찾지 못했습니다: {path}")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as e:
        sys.exit(f"JS 파일 본문을 JSON 으로 읽지 못했습니다: {e}")
    names = list((data.get("prices") or {}).keys())
    if not names:
        sys.exit("prices 에 항목이 없습니다.")
    return names


# ---------------------------------------------------------------- 리그
def fetch_leagues(raw_dir, use_cache):
    out = []
    for l in as_list(get_json("/Leagues", raw_dir=raw_dir, use_cache=use_cache)):
        name = l if isinstance(l, str) else pick(l, LEAGUE_NAME_FIELDS)
        if name:
            out.append(str(name))
    return out


def pick_league(leagues, wanted):
    k = key(wanted)
    for l in leagues:
        if key(l) == k:
            return l
    sys.exit(f"리그 '{wanted}' 를 찾지 못했습니다. 조회 가능한 리그: {', '.join(leagues)}")


# ---------------------------------------------------------------- 카탈로그(이름 -> itemId)
def load_catalog(league, wanted_keys, raw_dir, use_cache):
    """재화 카테고리를 차례로 조회하며 원하는 이름을 찾는다. 모두 찾으면 나머지 카테고리는 요청하지 않는다."""
    q = urllib.parse.quote(league, safe="")
    cats = get_json(f"/Leagues/{q}/Items/Categories", raw_dir=raw_dir, use_cache=use_cache)
    raw_cats = cats.get("currencycategories") if isinstance(cats, dict) else None
    categories = []
    for c in raw_cats or []:
        v = c if isinstance(c, str) else pick(c, ["apiid", "id", "name", "label"])
        if v is not None:
            categories.append(str(v))
    if not categories:
        raise RuntimeError(f"재화 카테고리 목록을 읽지 못했습니다. 응답 필드: {list(cats) if isinstance(cats, dict) else type(cats)}")

    index, remaining = {}, set(wanted_keys)
    for c in categories:
        page = 1
        while True:
            data = get_json(f"/Leagues/{q}/Currencies/ByCategory", {"category": c, "page": page, "perPage": 100},
                            raw_dir=raw_dir, use_cache=use_cache)
            for it in as_list(data):
                if not isinstance(it, dict):
                    continue
                name, iid = pick(it, NAME_FIELDS), pick(it, ID_FIELDS)
                if name is None or iid is None:
                    continue
                entry = {"name": str(name), "item_id": iid, "category": c}
                index.setdefault(key(name), entry)
                if it.get("apiid"):
                    index.setdefault(key(it["apiid"]), entry)
            pages = data.get("pages") if isinstance(data, dict) else 1
            if not is_num(pages) or page >= pages:
                break
            page += 1
        remaining = {k for k in remaining if k not in index}
        log(f"  카테고리 {c}: 누적 {len(index)}종 / 남은 이름 {len(remaining)}개")
        if not remaining:
            break
    return index


# ---------------------------------------------------------------- 일별 시계열
def to_date(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, dt.timezone.utc).date()
    if isinstance(v, str):
        try:
            return dt.date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return None


def fetch_series(league, item_id, raw_dir, use_cache):
    """DailyStatsHistory -> {date: (price_in_exalted, volume_or_None)}"""
    q = urllib.parse.quote(league, safe="")
    data = get_json(f"/Leagues/{q}/Items/{item_id}/DailyStatsHistory", {"dayCount": DAY_COUNT},
                    raw_dir=raw_dir, use_cache=use_cache)
    rows = as_list(data)
    series = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        d, p, v = to_date(pick(r, DATE_FIELDS)), pick(r, PRICE_FIELDS), pick(r, VOLUME_FIELDS)
        if d is None or not is_num(p) or p <= 0:
            continue
        series[d] = (float(p), v if is_num(v) else None)
    if rows and not series:
        first = rows[0] if isinstance(rows[0], dict) else rows[0]
        raise RuntimeError(f"일별 시계열에서 날짜/가격 필드를 찾지 못했습니다(itemId {item_id}). 실제 필드: "
                           f"{list(first) if isinstance(first, dict) else first}")
    if len(rows) >= DAY_COUNT:
        warn(f"  경고: itemId {item_id} 의 시계열이 {DAY_COUNT}일에 달해 리그 시작 부분이 잘렸을 수 있습니다(DAY_COUNT 를 늘리세요).")
    return series


def nearest(series, target):
    """target 날짜에 가장 가까운(±TOLERANCE_DAYS 이내) 날 -> (날짜, (가격, 거래량)) 또는 None"""
    best = None
    for d in series:
        diff = abs((d - target).days)
        if diff <= TOLERANCE_DAYS and (best is None or (diff, d) < best[0]):
            best = ((diff, d), d)
    return (best[1], series[best[1]]) if best else None


def write_atomic(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- 메인
def main():
    ap = argparse.ArgumentParser(description="poe2scout 에서 과거 리그 N일차 재화 시세(디바인 기준)를 받아 JS 파일로 저장")
    ap.add_argument("--list", action="store_true", help="리그 목록만 출력")
    ap.add_argument("--league", metavar="이름", help="리그 이름(예: \"Fate of the Vaal\")")
    ap.add_argument("--day", type=int, nargs="+", metavar="N", help="일차(여러 개 가능). 예: --day 4 7 10 15 30")
    ap.add_argument("--start", metavar="YYYY-MM-DD", help="리그 시작일(1일차) 직접 지정. 생략하면 시계열의 가장 이른 날짜")
    ap.add_argument("--source", default=str(DEFAULT_OUT / SOURCE_JS), help="항목 목록을 읽을 JS 파일(기본: price-history/crafting-sheet-prices.js)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="결과 저장 폴더(기본: 스크립트 옆 price-history 폴더)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--no-cache", action="store_true", help="캐시를 무시하고 새로 요청")
    grp.add_argument("--use-cache", action="store_true", help="만료 시간과 무관하게 기존 캐시를 사용(없는 항목만 새로 요청)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass

    global FORCE_CACHE
    FORCE_CACHE = args.use_cache
    use_cache = not args.no_cache
    out_dir = Path(args.out)
    raw_dir = out_dir / "raw_data" / "poe2scout"

    log("리그 목록 조회 중...")
    try:
        leagues = fetch_leagues(raw_dir, use_cache)
    except RuntimeError as e:
        sys.exit(f"리그 목록을 받지 못했습니다: {e}")
    if args.list:
        print("poe2scout 리그 목록:")
        for l in leagues:
            print(f"  {l}")
        return
    if not args.league or not args.day:
        sys.exit("--league 와 --day 가 필요합니다. 예: --league \"Fate of the Vaal\" --day 4 7 10")
    if any(d < 1 for d in args.day):
        sys.exit("--day 는 1 이상이어야 합니다.")
    days = sorted(set(args.day))
    start_override = None
    if args.start:
        try:
            start_override = dt.date.fromisoformat(args.start)
        except ValueError:
            sys.exit("--start 형식은 YYYY-MM-DD 입니다.")

    league = pick_league(leagues, args.league)
    wanted = load_wanted(Path(args.source))
    log(f"리그: {league} / 대상 항목 {len(wanted)}개 / 일차: {', '.join(map(str, days))}")

    # 1) 이름 -> itemId
    need = {key(w) for w in wanted} | {key(DIVINE)}
    need.discard(EXALTED_KEY)  # 엑잘티드는 기준 통화(=1)라 시계열이 필요 없음
    try:
        index = load_catalog(league, need, raw_dir, use_cache)
    except RuntimeError as e:
        sys.exit(f"카탈로그를 읽지 못했습니다: {e}")
    if key(DIVINE) not in index:
        sys.exit(f"{league} 에는 {DIVINE} 시세가 없어 디바인 기준으로 환산할 수 없습니다.")

    # 2) 시계열
    log("일별 시세 조회 중...")
    series, found, missing = {}, {}, []
    try:
        divine_series = fetch_series(league, index[key(DIVINE)]["item_id"], raw_dir, use_cache)
        for w in wanted:
            k = key(w)
            if k == EXALTED_KEY:
                continue
            e = index.get(k)
            if e is None:
                missing.append(w)
                close = difflib.get_close_matches(k, list(index), n=3, cutoff=0.6)
                hint = ", ".join(dict.fromkeys(index[c]["name"] for c in close))
                warn(f"  경고: '{w}' 을(를) {league} 에서 찾지 못해 건너뜁니다." + (f" 비슷한 이름: {hint}" if hint else ""))
                continue
            found[w] = e
            series[w] = divine_series if k == key(DIVINE) else fetch_series(league, e["item_id"], raw_dir, use_cache)
    except RuntimeError as e:
        sys.exit(f"시계열을 읽지 못했습니다: {e}")
    if not divine_series:
        sys.exit("디바인 오브의 일별 시세가 비어 있습니다.")

    # 3) 리그 시작일(1일차)
    if start_override:
        start = start_override
    else:
        start = min(min(s) for s in [divine_series, *series.values()] if s)
    log(f"리그 시작일(1일차): {start}" + (" (직접 지정)" if start_override else " (시계열의 가장 이른 날짜)"))

    # 4) 일차별 계산
    result_days = {}
    for n in days:
        target = start + dt.timedelta(days=n - 1)
        prices, details, no_data = {}, {}, []
        for w in wanted:
            k = key(w)
            if k == EXALTED_KEY:
                hit = nearest(divine_series, target)
                if hit is None:
                    no_data.append(w)
                    continue
                d, (div_ex, _) = hit
                prices[w], details[w] = round_sig(1.0 / div_ex), {"date": d.isoformat()}
                continue
            if w not in found:
                continue
            hit = nearest(series[w], target)
            div_hit = nearest(divine_series, hit[0]) if hit else None
            if hit is None or div_hit is None:
                no_data.append(w)
                continue
            d, (price_ex, vol) = hit
            div_ex = 1.0 if k == key(DIVINE) else div_hit[1][0]
            prices[w] = 1.0 if k == key(DIVINE) else round_sig(price_ex / div_ex)
            details[w] = {"item_id": found[w]["item_id"], "category": found[w]["category"], "date": d.isoformat(),
                          **({"volume_raw": vol} if vol is not None else {})}
        result_days[str(n)] = {"date": target.isoformat(), "prices": prices, "details": details, "no_data": no_data}
        log(f"  {n}일차({target}): {len(prices)}개 가격" + (f", 데이터 없음 {len(no_data)}개" if no_data else ""))

    if not any(d["prices"] for d in result_days.values()):
        sys.exit("가격을 하나도 계산하지 못했습니다. 파일을 만들지 않습니다. 리그 이름과 --start 를 확인하세요.")

    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for n, day in result_days.items():  # 일차마다 개별 파일로 저장
        if not day["prices"]:
            warn(f"  {n}일차: 가격이 없어 파일을 만들지 않습니다.")
            continue
        result = {
            "generated_at": generated_at,
            "source": "poe2scout",
            "league": league,
            "league_start": start.isoformat(),
            "quote_currency": DIVINE,
            "days": {n: day},      # {"4": {date, prices: {재화 이름: 디바인 단가}, details, no_data}}
            "missing": missing,    # 이 리그에서 이름을 찾지 못한 항목
        }
        body = json.dumps(result, ensure_ascii=False, indent=1).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        path = out_dir / f"crafting-sheet-prices-{safe_name(league)}-day{n}.js"
        write_atomic(path, f"window.{JS_VARIABLE} = {body};\n")
        log(f"  완료 -> {path}")

if __name__ == "__main__":
    main()
