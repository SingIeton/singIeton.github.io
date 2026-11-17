#!/usr/bin/env python3
"""
POE2 커런시 일별 가격(Exalted 기준) 수집 - poe2scout API

수집할 리그와 커런시는 이 파일 맨 위의 '사용자 설정' 구간에서 수정합니다.

사용법:
  python fetch_currency_history.py                              # CURRENCIES_INCLUDE 기준으로 수집
  python fetch_currency_history.py --list                       # API가 알려주는 리그 이름(시작일) 정보를 출력
  python fetch_currency_history.py --all-currencies             # 조회 가능한 모든 커런시를 수집(EXCLUDE만 적용)
  python fetch_currency_history.py --use-cache                  # 이미 받은 응답은 재요청하지 않음(중단 후 이어받기)
  python fetch_currency_history.py --dump-currencies all.txt    # API 전체 커런시를 붙여넣기용 텍스트로 저장
  python fetch_currency_history.py --leagues "리그 이름,2025-08-29"   # LEAGUES 대신 수집할 리그를 직접 지정

저장 위치(기본값: 이 스크립트가 있는 폴더):
  currency_data.js                        가격 이력 결과(HTML에서 <script src>로 읽음)
  raw_data/                               API 원본 응답
    ├ 리그__커런시.json                      커런시별 가격 이력
    └ catalog_id.json                       커런시 이름 -> item id 목록
"""

import argparse
import datetime as dt
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
#   · 한 줄에 이름 하나. 앞에 '#'을 붙이면 그 줄(또는 '#' 뒤)은 무시됩니다.
#   · 빈 줄, [카테고리] 제목 줄은 무시되므로 그룹 구분용으로 자유롭게 쓰세요.
#   · 대소문자는 구분하지 않습니다.
# =============================================================================

# ---- 가격 기준 통화 ----------------------------------------------------------
# 출력 JSON의 quote_currency 에 기록되는 값. API 가격이 이 통화 기준이라는 전제를 적어두는 용도이며,
# 스크립트가 환산하거나 API에 요청하는 값은 아닙니다.
QUOTE_CURRENCY = "Exalted Orb"

# ---- 수집할 리그 + 시즌 시작일 ----------------------------------------------
# 한 줄에 리그 하나. 아래 두 형식 모두 읽습니다(패치 번호는 선택, 구분은 쉼표·탭·공백 모두 가능).
#   패치번호  리그 전체 이름  시작일(YYYY-MM-DD, UTC)     예) 0.2.0  Dawn of the Hunt  2025-04-04
#   리그 전체 이름, 시작일                                  예) Dawn of the Hunt, 2025-04-04
#   · 위에서부터 차례로 수집합니다. 최근 리그부터 받으려면 최신 리그를 위에 적으세요.
#   · 시작일 이전 데이터는 버립니다.
#   · 시작일 당일 데이터가 없으면 하루씩 뒤로 넘겨, 데이터가 있는 가장 가까운 다음 날부터 수집합니다.
#   · 리그 이름은 API 이름과 같아야 합니다. `--list` 로 확인하세요(API가 시작일을 주면 함께 표시).
#   · 하드코어 리그는 수집하지 않습니다.
LEAGUES = """
# 형식 예시 ('#'을 지우면 적용, 여러 개면 줄을 추가)

1.0.0   Conquerors of Wraeclast, 2026-12-11
0.5.5   Forbidden Rites, 2026-09-04
0.5.0   Runes of Aldur, 2026-05-29
0.4.0   Fate of the Vaal, 2025-12-12
0.3.0   Rise of the Abyssal, 2025-08-29
0.2.0   Dawn of the Hunt, 2025-04-04
0.1.0   Early Access, 2024-12-06

"""

# ---- 수집할 커런시 ----------------------------------------------------------
# 기본 수집 대상 = CURRENCIES_INCLUDE 에서 CURRENCIES_EXCLUDE 를 뺀 것.
# (`--all-currencies` 옵션을 주면 INCLUDE 를 무시하고 조회 가능한 모든 커런시에서 EXCLUDE 만 뺍니다.)
# 빼고 싶은 줄을 INCLUDE 에서 잘라내 EXCLUDE 에 붙여넣으면 됩니다(나중에 되돌리기 쉬움).
# API의 전체 커런시 이름은 `--dump-currencies 파일.txt` 로 같은 형식으로 뽑아낼 수 있습니다.
CURRENCIES_INCLUDE = """

Mirror of Kalandra
Hinekora's Lock
Divine Orb
Perfect Chaos Orb
Greater Chaos Orb
Chaos Orb
Fracturing Orb
Orb of Annulment
Perfect Jewellers Orb

[Abyss]
Preserved Collarbone
Preserved Cranium
Ancient Jawbone
Ancient Rib
Ancient Collarbone
Altered Collarbone
Omen of Light

[Omen]
Omen of Whittling
Omen of Sinistral Annulment
Omen of Sinistral Erasure
Omen of Dextral Annulment
Omen of Dextral Erasure

[Essences]
#Essence of the Breach

[Lineage Gem]
Uul-Netol's Embrace
Uhtred's Exodus
Uhtred's Augury
Garukhan's Resolve
Dialla's Desire
Rakiata's Flow
#Rigwald's Ferocity

[Temple]
Architect's Orb
Vaal Cultivation Orb
Crystallised Corruption
Vaal Catalysing Infuser

[Key]
# Ancient Crisis Fragment
# Weathered Crisis Fragment
# Faded Crisis Fragment
# Origin Cradle
# Origin Spark

"""

CURRENCIES_EXCLUDE = """
# 수집하지 않을 커런시를 여기에 붙여넣으세요
"""

# =============================================================================
# 여기부터는 수정할 필요 없는 코드
# =============================================================================
BASE = "https://api.poe2scout.com"
UA = "poe2-currency-snapshot/0.4 (personal test script)"
MIN_INTERVAL = 7.0  # 초. 분당 ~10회 제한 보고가 있어 여유를 둠
HC_RE = re.compile(r"\b(hardcore|hc)\b", re.I)  # 하드코어: 목록/수집에서 완전히 제거

_last_request = 0.0


def log(msg=""):
    print(msg, flush=True)


def warn(msg):
    print(msg, file=sys.stderr, flush=True)


def parse_block(text):
    """설정 블록 -> 이름 목록. '#' 주석, 빈 줄, [카테고리] 줄은 무시하고 중복(대소문자 무시)은 제거."""
    names, seen = [], set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or (line.startswith("[") and line.endswith("]")):
            continue
        if line.lower() not in seen:
            seen.add(line.lower())
            names.append(line)
    return names


LEAGUE_LINE_RE = re.compile(r"^(?:(\d+(?:\.\d+)+)[\s,]+)?(.+?)[\s,]+(\d{4}-\d{2}-\d{2})$")


def parse_leagues(items):
    """['[패치번호] 리그 이름 YYYY-MM-DD', ...] -> [(리그 이름, 'YYYY-MM-DD', 패치번호 또는 None), ...]
    구분자는 쉼표/탭/공백 어느 것이든 되고, 패치번호(0.2.0 등)는 있어도 없어도 된다."""
    out = []
    for item in items:
        m = LEAGUE_LINE_RE.match(item.strip())
        try:
            if not m or re.fullmatch(r"\d+(\.\d+)+", m.group(2)):  # 패치 번호만 있고 리그 이름이 없는 줄
                raise ValueError
            patch, name, date = m.groups()
            dt.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            sys.exit(f"리그 형식 오류: '{item}'\n'[패치번호] 리그 이름 YYYY-MM-DD' 형식으로 적어 주세요. "
                     f"예) 0.2.0  Dawn of the Hunt  2025-04-04")
        out.append((name.strip(), date, patch))
    return out


def excluded_keys():
    return {n.lower() for n in parse_block(CURRENCIES_EXCLUDE)}


def selected_currency_names():
    exclude = excluded_keys()
    return [n for n in parse_block(CURRENCIES_INCLUDE) if n.lower() not in exclude]


def get_json(path, params=None, retries=4, label=None):
    """요청 간격은 조용히 유지하고, 재시도가 필요한 경우에만 한 줄 안내를 출력한다."""
    global _last_request
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    tag = label or path
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                backoff = 15 * (attempt + 1)
                log(f"  {tag}: 서버 응답 HTTP {e.code}, {backoff}초 후 재시도 ({attempt + 1}/{retries})")
                time.sleep(backoff)
                continue
            raise RuntimeError(f"HTTP {e.code}: {url}") from e
        except urllib.error.URLError as e:
            log(f"  {tag}: 네트워크 오류({e.reason}), 5초 후 재시도 ({attempt + 1}/{retries})")
            time.sleep(5)
    raise RuntimeError(f"요청 실패: {url}")


def pick(d, *names, default=None):
    """대소문자 무시하고 첫 번째로 존재하는 키의 값을 반환."""
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(n.lower())
        if v is not None:
            return v
    return default


def as_list(data, *keys):
    if isinstance(data, list):
        return data
    v = pick(data, *keys)
    if isinstance(v, list):
        return v
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


def norm_date(v):
    if isinstance(v, (int, float)):
        if v > 1e11:
            v /= 1000
        return dt.datetime.fromtimestamp(v, dt.timezone.utc).strftime("%Y-%m-%d")
    if isinstance(v, str):
        return v[:10]
    return None


def q(s):
    return urllib.parse.quote(s, safe="")


def safe_name(s):
    return re.sub(r"[^\w\-]+", "_", s).strip("_")


def is_hardcore(name):
    return bool(HC_RE.search(name))


# ---------------------------------------------------------------- 리그 / 카탈로그
def fetch_leagues():
    out = []
    for l in as_list(get_json("/poe2/Leagues", label="리그 목록"), "leagues", "items"):
        if isinstance(l, str):
            out.append({"name": l, "current": False})
            continue
        out.append({
            "name": pick(l, "Value", "Name", "LeagueName", "Text"),
            "short": pick(l, "ShortName"),
            "current": bool(pick(l, "IsCurrent", "Current", default=False)),
            "start": pick(l, "StartDate", "StartAt", "Start", "CreatedAt"),
        })
    return [l for l in out if l["name"]]


_catalog_cache = {}
_catalog_path = None    # main()에서 지정: <출력 폴더>/raw_data/catalog_id.json
_catalog_league = None  # catalog_id.json 에 저장되는 기준 리그(나머지 리그는 메모리에만 보관)
_use_cache = False


def fetch_catalog(league):
    """리그의 모든 커런시 -> {소문자 이름: {name, id, category}}. 리그당 1회만 조회.
    기준 리그의 카탈로그는 catalog_id.json 에 저장되며, --use-cache 이면 그 파일을 재사용한다."""
    if league in _catalog_cache:
        return _catalog_cache[league]
    cpath = _catalog_path if league == _catalog_league else None
    if cpath and _use_cache and cpath.exists():
        catalog = json.loads(cpath.read_text(encoding="utf-8"))
        _catalog_cache[league] = catalog
        return catalog
    cats_data = get_json(f"/poe2/Leagues/{q(league)}/Items/Categories", label="카테고리 목록")
    cats = pick(cats_data, "CurrencyCategories", default=[])
    keys = [c if isinstance(c, str) else pick(c, "ApiId", "Id", "Name", "Text") for c in cats]
    keys = [k for k in keys if k]
    catalog = {}
    for cat in keys:
        page = 1
        while True:
            data = get_json(
                f"/poe2/Leagues/{q(league)}/Currencies/ByCategory",
                {"category": cat, "page": page, "perPage": 100},
                label=f"카테고리 '{cat}'",
            )
            for item in as_list(data, "Items"):
                name = pick(item, "Text", "Name", "ItemName")
                item_id = pick(item, "ItemId", "Id", "ApiId")
                if name and item_id is not None:
                    catalog.setdefault(str(name).lower(), {"name": str(name), "id": item_id, "category": cat})
            pages = pick(data, "Pages", default=1) or 1
            if page >= pages:
                break
            page += 1
    _catalog_cache[league] = catalog
    if cpath:
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    return catalog


# ---------------------------------------------------------------- 커런시 목록
def resolve_currencies(names, catalog):
    resolved = []
    for name in names:
        hit = catalog.get(name.lower())
        if hit is None:
            warn(f"  경고: '{name}' 을(를) 카탈로그에서 찾지 못해 건너뜁니다.")
            continue
        resolved.append({"name": hit["name"], "id": hit["id"], "category": hit["category"]})
    return resolved


def dump_currencies(path, catalog):
    """API 전체 커런시를 설정 블록과 같은 형식([카테고리] + 이름들)의 텍스트로 저장."""
    groups = {}
    for c in catalog.values():
        groups.setdefault(str(c["category"]), []).append(c["name"])
    lines = []
    for cat in sorted(groups):
        lines.append(f"[{cat}]")
        lines.extend(sorted(groups[cat]))
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    log(f"전체 {len(catalog)}개 커런시를 {path} 에 저장했습니다. "
        f"필요한 줄만 스크립트 상단 CURRENCIES_INCLUDE 에 붙여넣으세요.")


# ---------------------------------------------------------------- 이력
def fetch_history(league, currency, item_id, days, raw_dir, use_cache):
    raw_path = raw_dir / f"{safe_name(league)}__{safe_name(currency)}.json"
    if use_cache and raw_path.exists():
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        data = get_json(f"/poe2/Leagues/{q(league)}/Items/{item_id}/DailyStatsHistory", {"dayCount": days},
                        label=f"{league} / {currency}")
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    rows, skipped = [], 0
    for r in as_list(data, "DailyStats", "History", "Items", "Data"):
        row = {
            "date": norm_date(pick(r, "Time", "Date", "Day", "Timestamp")),
            "open": pick(r, "Open", "OpenPrice"),
            "high": pick(r, "High", "HighPrice"),
            "low": pick(r, "Low", "LowPrice"),
            "close": pick(r, "Close", "ClosePrice", "Price"),
            "average": pick(r, "Average"),
            "volume": pick(r, "Volume"),
        }
        if row["date"] is None or all(row[k] is None for k in ("open", "high", "low", "close")):
            skipped += 1
            continue
        if row["date"] == today:
            row["partial"] = True  # 아직 진행 중인 날(UTC 기준)
        rows.append(row)
    if skipped:
        warn(f"  경고: {league} / {currency} - 형식을 인식하지 못한 행 {skipped}개 무시")
    rows.sort(key=lambda r: r["date"])
    return rows


def write_output(result, out):
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    # file:// 로 열린 HTML은 fetch()로 JSON을 못 읽으므로 <script src>로 읽는 JS 파일 하나로 저장
    (out / "currency_data.js").write_text(f"window.CURRENCY_DATA = {text};\n", encoding="utf-8")


class HistoryLoader:
    """(리그, 커런시)별 이력 캐시. itemId는 대개 리그 간 동일하므로 먼저 재사용하고, 비면 해당 리그 카탈로그로 재조회."""

    def __init__(self, days, raw_dir, use_cache, starts):
        self.days, self.raw_dir, self.use_cache, self.starts = days, raw_dir, use_cache, starts
        self.cache, self.ids = {}, {}

    def _load(self, league, cur, item_id):
        """이력을 받아 시작일 이후 행만 남긴다. 시작일 당일이 비어 있으면 자연히 다음 날 중
        데이터가 있는 가장 이른 날부터 시작한다."""
        rows = fetch_history(league, cur["name"], item_id, self.days, self.raw_dir, self.use_cache)
        return [r for r in rows if r["date"] >= self.starts[league]]

    def get(self, league, cur):
        key = (league, cur["name"])
        if key in self.cache:
            return self.cache[key]
        rows, used = [], cur["id"]
        try:
            rows = self._load(league, cur, cur["id"])
            if not rows:
                alt = fetch_catalog(league).get(cur["name"].lower())
                if alt and alt["id"] != cur["id"]:
                    used = alt["id"]
                    rows = self._load(league, cur, used)
        except RuntimeError as e:
            warn(f"  건너뜀({league}/{cur['name']}): {e}")
        self.cache[key] = rows
        self.ids[key] = used
        return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="리그 목록만 출력")
    ap.add_argument("--all-currencies", action="store_true",
                    help="CURRENCIES_INCLUDE 대신 조회 가능한 모든 커런시를 수집(CURRENCIES_EXCLUDE는 적용)")
    ap.add_argument("--dump-currencies", metavar="PATH", help="전체 커런시 목록을 붙여넣기용 텍스트로 저장하고 종료")
    ap.add_argument("--leagues", nargs="+", metavar="이름,시작일",
                    help="수집할 리그를 '[패치번호,]리그 이름,YYYY-MM-DD' 형식으로 직접 지정(스크립트 상단 LEAGUES보다 우선)")
    ap.add_argument("--days", type=int, default=300, help="이력 조회 일수 최소값(시작일이 더 오래되면 자동 확장)")
    ap.add_argument("--out", default=str(SCRIPT_DIR),
                    help="결과 저장 폴더(기본: 스크립트가 있는 폴더). 원본 응답은 그 안의 raw_data/ 에 저장")
    ap.add_argument("--use-cache", action="store_true", help="raw_data/에 이미 받은 응답은 재요청하지 않음")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    names = selected_currency_names()
    if not names and not (args.list or args.dump_currencies or args.all_currencies):
        sys.exit("수집할 커런시가 없습니다. 스크립트 상단 CURRENCIES_INCLUDE 를 확인하세요.")
    requested = args.leagues or parse_block(LEAGUES)
    if not requested and not (args.list or args.dump_currencies):
        sys.exit("수집할 리그가 없습니다. 스크립트 상단 LEAGUES 에 '[패치번호] 리그 이름 YYYY-MM-DD' 를 적어 주세요.")

    log("리그 목록 조회 중...")
    leagues = [l for l in fetch_leagues() if not is_hardcore(l["name"])]  # 소프트코어만 사용
    if args.list:
        print("API가 반환한 리그 목록 (하드코어 제외, 반환 순서 그대로):")
        for i, l in enumerate(leagues):
            extra = []
            if l["current"]:
                extra.append("CURRENT")
            start = norm_date(l.get("start"))
            if start:
                extra.append(f"시작일 {start}")
            print(f"  [{i}] {l['name']}  {' '.join(extra)}")
        return

    out = Path(args.out)
    raw_dir = out / "raw_data"

    starts, patches = {}, {}  # {API 정식 리그 이름: 시작일 / 패치 번호}
    if requested:
        by_lower = {l["name"].lower(): l["name"] for l in leagues}
        hc, unknown = [], []
        for name, start, patch in parse_leagues(requested):
            if is_hardcore(name):
                hc.append(name)
            elif name.lower() not in by_lower:
                unknown.append(name)
            else:
                real = by_lower[name.lower()]
                if real not in starts:
                    starts[real] = start
                    if patch:
                        patches[real] = patch
        if hc:
            warn(f"하드코어 리그는 수집하지 않습니다. 제외: {hc}")
        if unknown:
            warn(f"API 리그 목록에 없어 건너뜁니다: {unknown} (오타라면 --list 로 정확한 이름을 확인하세요)")
        if not starts:
            sys.exit("수집할 수 있는 리그가 없습니다.")
        ref_league = next(iter(starts))
    else:  # --dump-currencies 만 해당: 현재 리그의 카탈로그를 사용
        ref_league = next((l["name"] for l in leagues if l["current"]), None)
        if ref_league is None:
            sys.exit("현재 리그를 찾지 못했습니다. 스크립트 상단 LEAGUES 에 리그를 적어 주세요.")

    global _catalog_path, _catalog_league, _use_cache
    _catalog_path, _catalog_league, _use_cache = raw_dir / "catalog_id.json", ref_league, args.use_cache

    log(f"[{ref_league}] 커런시 목록 조회 중...")
    catalog = fetch_catalog(ref_league)

    if args.dump_currencies:
        dump_currencies(args.dump_currencies, catalog)
        return

    if args.all_currencies:
        skip = excluded_keys()
        names = [c["name"] for c in sorted(catalog.values(), key=lambda c: (str(c["category"]), c["name"]))
                 if c["name"].lower() not in skip]
    currencies = resolve_currencies(names, catalog)
    if not currencies:
        sys.exit("수집할 수 있는 커런시가 없습니다.")

    # 가장 오래된 시작일까지 이력이 닿도록 조회 일수를 확장
    today = dt.datetime.now(dt.timezone.utc).date()
    oldest = min(dt.datetime.strptime(d, "%Y-%m-%d").date() for d in starts.values())
    days = max(args.days, (today - oldest).days + 1)
    targets = list(starts)
    loader = HistoryLoader(days, raw_dir, args.use_cache, starts)

    todo = len(targets) * len(currencies)
    log(f"\n수집 리그 {len(targets)}개:")
    for lg in targets:
        log(f"  - {lg} (시작일 {starts[lg]})")
    log(f"수집 커런시 {len(currencies)}개 / 요청 약 {todo}회 (최소 {todo * MIN_INTERVAL / 60:.1f}분 소요)\n")

    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "api.poe2scout.com",
        "quote_currency": QUOTE_CURRENCY,
        "complete": False,  # 수집이 끝까지 끝나면 True
        "leagues": {},
    }
    try:
        for lg in targets:
            lg_out = {}
            for i, cur in enumerate(currencies, 1):
                rows = loader.get(lg, cur)
                if not rows:
                    warn(f"[{lg}] ({i}/{len(currencies)}) {cur['name']}: 시작일({starts[lg]}) 이후 이력 없음")
                    continue
                lg_out[cur["name"]] = {
                    "item_id": loader.ids.get((lg, cur["name"]), cur["id"]),
                    "category": cur["category"],
                    "first_date": rows[0]["date"],
                    "last_date": rows[-1]["date"],
                    "days": rows,
                }
                result["leagues"][lg] = {"start_date": starts[lg], **({"patch": patches[lg]} if lg in patches else {}),
                                         "currencies": lg_out}
                write_output(result, out)  # 커런시 하나 끝날 때마다 저장
                shifted = f"  [시작일 당일 데이터 없음 -> {rows[0]['date']}부터]" if rows[0]["date"] != starts[lg] else ""
                log(f"[{lg}] ({i}/{len(currencies)}) {cur['name']}: {len(rows)}일치 "
                    f"({rows[0]['date']} ~ {rows[-1]['date']}){shifted}")
        result["complete"] = True
    except KeyboardInterrupt:
        log("\n중단됨. 지금까지 받은 결과는 저장되어 있습니다. --use-cache 로 다시 실행하면 이어받습니다.")
    write_output(result, out)
    state = "완료" if result["complete"] else "부분 저장(중단됨)"
    log(f"\n{state}: {out / 'currency_data.js'}")


if __name__ == "__main__":
    main()
