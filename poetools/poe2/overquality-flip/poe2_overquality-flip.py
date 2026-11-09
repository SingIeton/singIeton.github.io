"""PoE2 trade2: 베이스별 최저가 조회 + 적정 최저가 계산 (basequality.txt 명세 기준).

공통 조건 : Instant Buyout(securable), Rarity=Normal, NOT corrupted/mirrored/fractured
4-A : ilvl >= 82, Quality >= 30  -> 최저가 TOP_N   (index.html: ilvl 82 행의 30% 판매가)
4-B : ilvl >= 82, Quality = 0    -> 최저가 TOP_N   (index.html: ilvl 82 행의 0% 베이스)
5-A : ilvl  = 81, Quality >= 30  -> 최저가 TOP_N   (index.html: ilvl 81 행의 30% 판매가)
5-B : ilvl  = 81, Quality = 0    -> 최저가 TOP_N   (index.html: ilvl 81 행의 0% 베이스)
소켓 수는 베이스별로 다르다 (BASES 참고).

후처리:
  1) 정상 매물(가격·통화를 알 수 있는 매물)이 2개 미만이면 '데이터 부족'
  2) 매물 수와 가격 분포로 신뢰도를 매기고 적정 최저가를 고른다.
     Instant Buyout은 허위 매물이 드물어 최저가가 시장 최저가에 가깝다고 보되,
     중앙값보다 지나치게 싼 고립 매물(시세를 모르거나 급처)은 제외한다.
     단, 제외 대상은 '최근 등록된' 매물뿐이다. 싸게 나온 매물은 금방 팔려야 정상이므로, 오래 안 팔리고
     남아 있는 저가 매물은 '급처'가 아니라 그 가격이 실제로는 거래되지 않는다(허위·비활성 판매자·시세 오기 등)는
     증거다. 이런 매물은 제외하지 않고 최저가로 남겨, 아래 3)의 경과일 규칙으로 신뢰도를 깎는다.
  3) 고른 최저가 매물이 오래됐으면(listing.indexed 기준 STALE_DAYS 이상 한 단계, OLD_DAYS 이상 두 단계) 신뢰도를 낮춘다.
     오래된 최저가는 이미 시세와 어긋났을 가능성이 크기 때문이다. 등록 시각을 알 수 없으면 보정하지 않는다.

요청 절약 규칙:
  - 30% 매물(4-A / 5-A)이 데이터 부족(정상 매물 1개 이하)이면 같은 ilvl 의 0% 검색(4-B / 5-B)은 생략한다.
    생략된 항목은 prices.json 에 buy0.omitted = true 로 저장되고, index.html 은 '-', '-개' 로 표시한다.
  - 30% 매물이 데이터 부족인 '베이스+ilvl' 은 각각 '수집 중지'로 prices.json (리그 항목의 stopped, 키 "베이스:ilvl")에
    기록하고, 이후 실행에서는 그 항목만 건너뛴다 (예: Siege Crossbow ilvl 82 만 중지, 81 은 계속 조회).
    index.html 은 해당 ilvl 행을 '수집 중지'로 표시한다. 다시 조회하려면 --retry-stopped 를 쓰거나 베이스 이름을
    직접 지정한다. 조회 결과 30% 매물이 생기면 자동으로 해제된다.

레이트리밋:
  - 실행 전에 조회할 항목으로 최대 요청 수와 최단 소요 시간을 계산해 출력한다.
  - 보낸 시각을 기록하는 슬라이딩 윈도우 방식으로 모든 규칙(5:10, 15:60, 30:300 ...)을 한도 미만으로 유지한다.
    한도 직전까지 몰아 보내고 기간 전체(301초)를 쉬던 이전 방식보다 짧고, 한도 초과로 인한 차단이 걸리지 않는다.
    규칙은 응답 헤더로 매번 갱신하고, 서버가 센 횟수가 더 많으면(브라우저·다른 프로그램 사용분) 그만큼 더 기다린다.

화폐 환율 (poe.ninja):
  - 실행할 때마다 리그별로 Divine, Chaos, 바알 대장장이의 주입기, 대장장이의 숫돌 가격을 poe.ninja 의 PoE2 화폐 거래소
    집계(Exalted 기준, 약 1시간 단위 갱신)에서 읽어 prices.json 의 리그 항목 "rates" 에 저장한다.
    overquality-flip.html 이 이 값을 리그별 기본 환율로 쓴다. 모든 리그는 소프트코어(하드코어 제외)다.
  - 일부 항목을 찾지 못하면 그 항목은 이전 값을 유지하고, poe.ninja 접속에 실패해도 GGG 가격 수집은 계속한다.
  - --no-rates 로 건너뛰고, --rates-only 로 환율만 갱신할 수 있다 (GGG 검색 없이 몇 초).

결과는 이 스크립트 옆의 out/prices.json 에 저장된다 (index.html 이 같은 out/ 에서 읽음, 기존 파일이 있으면 병합).

실행:
  python poe2_basequality.py                          # 기본: 전체 13종 (QUERY_BASES = BASES), 최신 리그만, 수집 중지 항목 제외
  python poe2_basequality.py "Warmonger Bow"          # 지정한 베이스 하나 (수집 중지여도 조회)
  python poe2_basequality.py all                      # 전체 13종 (베이스당 요청 최대 8회)
  python poe2_basequality.py all --retry-stopped      # 수집 중지된 항목도 다시 조회
  python poe2_basequality.py all --league latest      # 최신 리그만 (기본값)
  python poe2_basequality.py all --league "이름"       # 리그 이름 직접 지정
  # standard 와 previous(직전 리그)는 수집하지 않도록 막혀 있다 (BLOCKED_CHOICES)
  python poe2_basequality.py all --out other/prices.json   # 저장 위치 지정 (기본: out/prices.json)
  python poe2_basequality.py --rates-only             # poe.ninja 환율만 갱신 (GGG 검색 없음)
  python poe2_basequality.py all --no-rates           # poe.ninja 환율 갱신 생략
"""
import argparse
import json
import os
import re
import sys
import time
import statistics
from datetime import datetime, timezone

import requests

BASE = "https://www.pathofexile.com"
POESESSID = ""                        # 선택
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")   # index.html 과 같은 위치의 ./out
DEFAULT_OUT = os.path.join(OUT_DIR, "prices.json")
KEEP_LEAGUES = 1               # 수집·표시할 시즌 리그 수 (최신만)
# 수집하지 않는 리그 선택값. Standard 와 직전(second latest) 리그는 막아 두었다.
# 다시 수집하려면 여기서 해당 값을 지우고 --league 기본값과 KEEP_LEAGUES 를 함께 바꾼다.
BLOCKED_CHOICES = {"standard", "previous"}
UA = "poe2-price-test/0.1 (contact: augustusminu@hotmail.com)"

TOP_N = 10                     # fetch 한 번에 최대 10개


def utc_stamp():
    """수집 시각: 실행 환경(PC=KST, Actions=UTC)과 무관하게 항상 UTC ISO 형식 (예: 2026-11-08T12:21:00Z).
    index.html 이 시간대가 붙은 값을 Date 로 비교하고 사용자 로컬 시간으로 보여준다."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- 적정 최저가 판정 파라미터 -------------------------------------------
MIN_LISTINGS = 2               # 정상 매물이 이보다 적으면 '데이터 부족'
OUTLIER_MIN_N = 4              # 이상치 판정은 매물이 이 수 이상일 때만 (그 미만이면 비교 기준이 부족)
OUTLIER_RATIO = 0.5            # 중앙값의 이 비율 미만이면 '너무 싼' 매물
STALE_DAYS = 7                 # 적정 최저가로 고른 매물이 이 일수 이상 오래되면 신뢰도를 한 단계 낮춘다
OLD_DAYS = 30                  # 이 일수 이상이면 두 단계 낮춘다 (시세와 어긋났을 가능성이 큼)
MAX_SKIP = 2                   # 고립된 저가 매물로 보고 제외할 최대 개수 (그 이상 몰려 있으면 실제 시세)
OUTLIER_MAX_AGE_DAYS = 2            # 이상치로 제외할 수 있는 저가 매물의 최대 경과 일수. 이보다 오래된 저가 매물은 '안 팔리는 가격'이라 제외하지 않는다
# 서로 다른 통화의 매물을 비교하기 위한 환율(Exalted 기준). 이상치 판정과 정렬에만 쓰이고, 저장되는 가격은 매물 원래의 (금액, 통화)다.
# 실제 값은 리그 수집을 시작할 때 prices.json 의 그 리그 poe.ninja 환율(rates)로 덮어쓴다 (use_cmp_rates).
# 아래 기본값은 poe.ninja 환율이 없을 때(--no-rates 이고 저장된 값도 없음, 조회 실패)만 쓰인다.
DEFAULT_CMP_RATES = {"exalted": 1.0, "chaos": 67.0, "divine": 515.0}
CMP_RATES = dict(DEFAULT_CMP_RATES)

# 검색 조건 (basequality.txt 4-A, 4-B, 5-A, 5-B)
# ilvl_max / q_max 가 None 이면 "이상(>=)", 값이 있으면 min~max 범위(같으면 정확히 일치)
# entry_ilvl : prices.json 에서 이 결과가 들어갈 행 / side : sell30(30% 판매가) 또는 buy0(0% 베이스)
SEARCHES = [
    {"label": "4-A", "ilvl_min": 82, "ilvl_max": None, "q_min": 30, "q_max": None, "entry_ilvl": 82, "side": "sell30"},
    {"label": "4-B", "ilvl_min": 82, "ilvl_max": None, "q_min": 0,  "q_max": 0,    "entry_ilvl": 82, "side": "buy0"},
    {"label": "5-A", "ilvl_min": 81, "ilvl_max": 81,   "q_min": 30, "q_max": None, "entry_ilvl": 81, "side": "sell30"},
    {"label": "5-B", "ilvl_min": 81, "ilvl_max": 81,   "q_min": 0,  "q_max": 0,    "entry_ilvl": 81, "side": "buy0"},
]
ILVLS = sorted({sp["entry_ilvl"] for sp in SEARCHES}, reverse=True)   # prices.json 의 ilvl 행 (82, 81)

# 베이스 이름 -> 증강 가능 소켓 수 (정확히 이 값)
BASES = {
    "Obliterator Bow": 3, "Warmonger Bow": 3,                                       # 활
    "Siege Crossbow": 3, "Gemini Crossbow": 3, "Desolate Crossbow": 3,              # 석궁
    "Sinister Quarterstaff": 3, "Bolting Quarterstaff": 3,                          # 육척봉
    "Soaring Spear": 2, "Akoyan Spear": 2, "Flying Spear": 2,                       # 창
    "Spiny Talisman": 3,                                                            # 부적
    "Massive Greathammer": 3, "Ironwood Greathammer": 3,                            # 양손 철퇴
}
# 기본 조회 대상 (all 과 같음): BASES 전체 (활·석궁·육척봉·창·부적·양손 철퇴).
# 조회에서 빼려면 BASES 에서 지우거나, 데이터 부족이면 아래 '수집 중지' 기능이 자동으로 막는다.
QUERY_BASES = list(BASES)

session = requests.Session()
session.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
if POESESSID:
    session.cookies.set("POESESSID", POESESSID, domain="www.pathofexile.com")

_printed_headers = False


def slug(name):
    """'Obliterator Bow' -> 'obliterator-bow' (index.html 의 bases[].id 와 같은 규칙)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ---------------------------------------------------------------- 레이트리밋: 슬라이딩 윈도우 스케줄러
# 응답 헤더(X-Rate-Limit-Ip 등)는 "허용횟수:기간(초):초과 시 차단(초)" 규칙의 목록이다.
#   예) 30:300:1800 = 300초 동안 30회까지, 넘기면 1800초 차단.
# 예전 방식은 한도 직전까지 몰아 보낸 뒤 기간 전체(301초)를 쉬었다. 여기서는 보낸 시각을 모두 기록해 두고,
# 모든 규칙에서 '가장 오래된 요청이 윈도우 밖으로 나가는 순간' 바로 다음 요청을 보낸다. 한도는 절대 넘기지 않는다.
RATE_MARGIN = 1        # 한도보다 이만큼 적게만 쓴다 (초과하면 최대 30분 차단이라 여유를 둔다)
RATE_PAD = 0.5         # 윈도우가 풀리는 시각에 더하는 여유(초): 서버/클라이언트 지연 차이 대비
MIN_GAP = 0.3          # 요청 사이 최소 간격(초)
RATE_HEADERS = ("X-Rate-Limit-Ip", "X-Rate-Limit-Account")
# 첫 응답을 받기 전의 계획·예상 시간 계산과 첫 요청 페이싱용 (실제 값은 응답 헤더로 매번 갱신된다)
DEFAULT_RULES = {
    "search": [(5, 10, 60), (15, 60, 300), (30, 300, 1800), (600, 21600, 3600)],
    "fetch": [(12, 4, 10), (16, 12, 300), (50, 300, 300), (1000, 21600, 1800)],
}


def parse_rules(text):
    """'5:10:60,15:60:300' 또는 상태 '1:10:0,2:60:0' -> [(5, 10, 60), (15, 60, 300)]"""
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
        self.rules = {k: list(v) for k, v in (rules or {}).items()}   # kind -> [(limit, period, penalty)]
        self.times = {}        # kind -> 보낸 시각들
        self.pseudo = {}       # (kind, limit, period) -> 다른 프로그램이 쓴 것으로 추정되는 요청 시각들
        self.block = {}        # kind -> 이 시각까지 차단
        self.last = -1e9
        self.count = 0

    def wait_time(self, kind, now=None):
        """다음 요청을 보내기 전에 기다릴 시간(초)과, 가장 오래 기다리게 만든 규칙을 반환."""
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
        """응답 헤더로 규칙을 갱신하고, 서버가 센 횟수가 우리 기록보다 많으면(다른 프로그램/브라우저 사용분) 보수적으로 반영."""
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
                    ps += [now] * (hits - local)          # 방금 쓴 것으로 간주 (보수적)
                self.pseudo[key] = ps
                if restricted > 0:
                    self.block[kind] = max(self.block.get(kind, 0), now + restricted + 1)


limiter = RateLimiter(DEFAULT_RULES)


def request_kind(url):
    return "search" if "/search/" in url else "fetch" if "/fetch/" in url else "data"


def estimate_seconds(n_search, n_fetch, latency=0.5):
    """요청을 검색->fetch 순서로 번갈아 보낼 때 레이트리밋을 지키는 최단 소요 시간(초)을 시뮬레이션."""
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


# ---------------------------------------------------------------- poe.ninja 환율 (Exalted 기준)
# 오버퀄리티 계산에 쓰는 가격을 리그별로 poe.ninja 의 PoE2 화폐 거래소 집계(exchange overview, 약 1시간 단위 갱신)에서 읽어
# prices.json 의 리그 항목 "rates" 에 저장한다. 값은 모두 '해당 화폐 1개 = Exalted 몇 개'이고,
# overquality-flip.html 이 같은 키(div, chaos, inf.blacksmith, q.whetstone)로 읽는다 (키를 바꾸면 html 도 같이 바꿀 것).
#   "rates": {"div": 515.0, "chaos": 67.0, "inf": {"blacksmith": 60.0}, "q": {"whetstone": 0.15},
#             "source": "poe.ninja", "updatedAt": "2026-11-08T12:30:00Z"}
NINJA = "https://poe.ninja/poe2/api/economy"
# rates 키 -> (표시 이름, 매칭 후보). id·이름·detailsId 에서 영숫자만 남겨 소문자로 만든 값과 비교하므로
# "vaal-blacksmith-s-infuser", "Vaal Blacksmith's Infuser" 같은 표기 차이는 문제되지 않는다.
RATE_ITEMS = {
    "div": ("Divine Orb", ("divine", "divineorb")),
    "chaos": ("Chaos Orb", ("chaos", "chaosorb")),
    "inf.blacksmith": ("Vaal Blacksmith's Infuser", ("vaalblacksmithsinfuser", "vaalblacksmithinfuser")),
    "q.whetstone": ("Blacksmith's Whetstone", ("blacksmithswhetstone", "blacksmithwhetstone", "whetstone")),
}
EXALTED_KEYS = ("exalted", "exaltedorb")
# Currency 에서 못 찾은 항목을 찾아볼 다른 카테고리 (poe.ninja 문서의 PoE2 type 값)
NINJA_TYPES = ["Currency", "Fragments", "Abyss", "Essences", "SoulCores", "Runes", "Ritual", "Expedition",
               "Delirium", "Breach", "Verisium", "UncutGems", "Idols", "LineageSupportGems"]

ninja_session = requests.Session()
ninja_session.headers.update({"User-Agent": UA, "Accept": "application/json"})


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def ninja_get(path, params=None):
    """poe.ninja 경제 API GET. 429/503 이면 잠깐 기다렸다 최대 3번 시도한다 (응답은 HTTP 캐시되고 PoE2는 1시간 단위 갱신)."""
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
    """items 메타데이터(목록 또는 id->정보 딕셔너리)를 [{id, name, ...}] 로 통일."""
    if isinstance(src, dict):
        src = [dict(v, id=v.get("id", k)) if isinstance(v, dict) else {"id": k, "name": v} for k, v in src.items()]
    return [x for x in (src or []) if isinstance(x, dict) and x.get("id") is not None]


def ninja_exalted_values(resp):
    """exchange overview 응답 -> {정규화한 id/이름/detailsId: '1개 = Exalted 몇 개'}.
    lines[].primaryValue 는 기준 화폐(core.primary) 단위 가격이므로 Exalted 의 primaryValue 로 나눠 환산한다
    (기준 화폐가 Exalted 이면 그대로). Exalted 를 찾지 못하면 {} 를 반환한다."""
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
        value[primary] = 1.0                       # 기준 화폐 자신은 정의상 1
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
    """우리 리그 이름(trade2 기준)에 해당하는 poe.ninja 리그 id. 정규화한 id/이름이 정확히 같은 것만 인정하므로
    'Hardcore ...' 같은 다른 리그와 섞이지 않는다 (소프트코어만 사용)."""
    key = _norm(league)
    for lg in ninja_leagues:
        if key in (_norm(lg.get("id")), _norm(lg.get("name"))):
            return lg.get("id")
    return None


def fetch_ninja_rates(league, ninja_leagues):
    """리그 하나의 환율을 읽어 {"div": .., "chaos": .., "inf.blacksmith": .., "q.whetstone": ..} 로 반환 (찾은 것만).
    아무것도 못 얻거나 값이 비정상이면 None."""
    lid = ninja_league_id(league, ninja_leagues)
    if lid is None:
        names = ", ".join(str(x.get("id")) for x in ninja_leagues) or "없음"
        print(f"  [{league}] poe.ninja 에서 같은 이름의 리그를 찾지 못함 (poe.ninja 리그: {names})")
        return None
    found, sample = {}, []
    for typ in NINJA_TYPES:
        want = [k for k in RATE_ITEMS if k not in found]
        if not want:
            break
        try:
            vals = ninja_exalted_values(ninja_get("exchange/current/overview", {"league": lid, "type": typ}))
        except (requests.RequestException, ValueError, AttributeError) as e:
            print(f"  [{league}] poe.ninja {typ} 조회 실패 ({str(e)[:200]})")
            if typ == "Currency":
                return None                         # 첫 요청부터 실패하면 나머지 카테고리도 소용없다
            continue
        if not sample:
            sample = sorted(vals)[:25]
        for k in want:
            for cand in RATE_ITEMS[k][1]:
                if cand in vals:
                    found[k] = vals[cand]
                    break
        time.sleep(0.5)
    missing = [RATE_ITEMS[k][0] for k in RATE_ITEMS if k not in found]
    if "div" in found and "chaos" in found and found["div"] <= found["chaos"]:
        print(f"  [{league}] 값이 비정상(Divine {found['div']:.1f} <= Chaos {found['chaos']:.1f} Ex)이라 저장하지 않음")
        return None
    shown = ", ".join(f"{RATE_ITEMS[k][0]} {found[k]:.4g} Ex" for k in RATE_ITEMS if k in found)
    print(f"  [{league}] {shown or '찾은 항목 없음'}")
    if missing:
        print(f"    찾지 못함 (이전 값 유지): {', '.join(missing)}")
        print(f"    poe.ninja Currency 응답의 키 예시: {', '.join(sample) or '(비어 있음 - Exalted 를 찾지 못함)'}")
    return found or None


def save_rates(path, league, found, order=None):
    """found 를 prices.json 의 league.rates 에 병합 저장 (찾지 못한 항목은 이전 값 유지)."""
    data = {"version": 1, "leagues": {}}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded.get("leagues"), dict):
                data = loaded
        except (OSError, ValueError):
            print(f"  ⚠ 기존 {path} 를 읽지 못해 새로 만듭니다")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if order:
        data["order"] = list(order)
    lg = data["leagues"].setdefault(league, {"entries": []})
    rates = lg.setdefault("rates", {})
    for key, v in found.items():
        parts = key.split(".")
        t = rates
        for p in parts[:-1]:
            t = t.setdefault(p, {})
        t[parts[-1]] = round(v, 2) if v >= 1 else round(v, 4)
    rates["source"] = "poe.ninja"
    rates["updatedAt"] = utc_stamp()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def update_rates(leagues, out, order=None):
    """모든 리그의 환율을 poe.ninja 에서 읽어 저장한다. 실패해도 예외를 내지 않는다 (GGG 가격 수집은 계속)."""
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
        except Exception as e:                      # poe.ninja 문제로 전체 수집이 멈추지 않도록
            print(f"  [{league}] 환율 처리 중 오류 ({str(e)[:200]})")
            continue
        if found:
            save_rates(out, league, found, order)
            print(f"  -> {out} 저장 ({league} / rates)")


def use_cmp_rates(path, league):
    """이 리그의 poe.ninja 환율(prices.json 의 rates.chaos / rates.div)을 CMP_RATES 에 반영한다.
    값이 없거나 비정상(숫자가 아니거나 0 이하, Divine <= Chaos)이면 기본값을 쓴다. 리그마다 호출해 다른 리그 값이 섞이지 않게 한다.
    index.html 이 같은 rates 를 읽어 정렬·계산하므로, 이상치 판정(몇 개를 제외할지)이 화면의 기준과 일치한다."""
    CMP_RATES.clear()
    CMP_RATES.update(DEFAULT_CMP_RATES)
    try:
        with open(path, encoding="utf-8") as f:
            rates = (json.load(f).get("leagues", {}).get(league) or {}).get("rates") or {}
    except (OSError, ValueError, AttributeError):
        rates = {}
    chaos, div = rates.get("chaos"), rates.get("div")
    ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in (chaos, div)) and div > chaos
    if ok:
        CMP_RATES["chaos"], CMP_RATES["divine"] = float(chaos), float(div)
    src = f"poe.ninja {rates.get('updatedAt', '')}".strip() if ok else "기본값 (poe.ninja 환율 없음)"
    print(f"  이상치 판정 환율: Chaos = {CMP_RATES['chaos']:g} Ex, Divine = {CMP_RATES['divine']:g} Ex  [{src}]")


# ---------------------------------------------------------------- 리그 선택
_EXCLUDE = re.compile(r"\b(hc|ssf|hardcore|ruthless|solo)\b", re.IGNORECASE)


def fetch_leagues():
    """trade2 리그 목록에서 poe2 리그 이름들을 API가 주는 순서대로 반환."""
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
    """리그 목록 조회가 실패했을 때의 대체값: prices.json 에 저장된 Standard 아닌 리그 중 가장 최근에 수집한 리그."""
    try:
        with open(path, encoding="utf-8") as f:
            leagues = json.load(f)["leagues"]
        found = [(str(v.get("collectedAt", "")), k) for k, v in leagues.items() if k.lower() != "standard"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return max(found)[1] if found else None


def resolve_league(choice, out_path):
    """choice: latest | 리그 이름 직접 지정 (standard, previous 는 BLOCKED_CHOICES 로 막혀 None). 확인하지 못하면 None."""
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
        # 일반 소프트코어 시즌 리그만 (Standard / Hardcore / SSF / Ruthless 제외)
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


# ---------------------------------------------------------------- 검색
def _range(lo, hi):
    r = {"min": lo}
    if hi is not None:
        r["max"] = hi
    return r


def build_query(base_name, spec, sockets):
    return {
        "query": {
            "status": {"option": "securable"},
            "type": base_name,
            "filters": {
                "type_filters": {"filters": {"rarity": {"option": "normal"}}},
                "misc_filters": {
                    "filters": {
                        "ilvl": _range(spec["ilvl_min"], spec["ilvl_max"]),
                        "quality": _range(spec["q_min"], spec["q_max"]),
                        "corrupted": {"option": "false"},
                        "mirrored": {"option": "false"},
                        "fractured_item": {"option": "false"},
                    }
                },
                "equipment_filters": {
                    "filters": {"rune_sockets": {"min": sockets, "max": sockets}}
                },
            },
        },
        "sort": {"price": "asc"},
    }


def cheapest(league, base_name, spec, sockets):
    """(총 매물 수, 최저가 행 리스트) 반환. 요청 2회(검색+fetch)."""
    s = call("POST", f"{BASE}/api/trade2/search/poe2/{league}",
             json=build_query(base_name, spec, sockets))
    total = s.get("total", 0)
    ids = s.get("result", [])[:TOP_N]
    if not ids:
        return total, []
    f = call("GET", f"{BASE}/api/trade2/fetch/{','.join(ids)}", params={"query": s["id"]})
    rows = []
    for e in f.get("result", []):
        listing = e.get("listing") or {}
        price = listing.get("price") or {}
        item = e.get("item") or {}
        rows.append({
            "amount": price.get("amount"),
            "currency": price.get("currency"),
            "name": f"{item.get('name', '')} {item.get('typeLine', '')}".strip(),
            "ilvl": item.get("ilvl"),
            "seller": (listing.get("account") or {}).get("name", "?"),
            "indexed": listing.get("indexed"),      # 등록(마지막 갱신) 시각, ISO 8601
        })
    return total, rows


# ---------------------------------------------------------------- 후처리: 적정 최저가
def _ex(r):
    """매물 가격을 Exalted 환산값으로. 가격이 없거나 모르는 통화면 None."""
    rate = CMP_RATES.get(r["currency"])
    if rate is None or r["amount"] is None:
        return None
    return r["amount"] * rate


def age_days(r):
    """매물의 등록(indexed) 후 경과 일수. 시각을 모르거나 해석하지 못하면 None."""
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
    """적정 최저가 판정.

    반환 dict (prices.json 의 sell30.fair / buy0.fair 로 그대로 저장됨):
      status     : "ok" | "insufficient"(데이터 부족)
      a, c       : 적정 최저가 (매물 원래의 금액, 통화). insufficient 면 None
      n          : 판정에 쓴 정상 매물 수
      confidence : "high" | "medium" | "low" | None
      skipped    : 너무 싸서 제외한 매물 수
      age        : 고른 최저가 매물의 경과 일수 (등록 시각을 모르면 None)
      reason     : 사람이 읽는 판정 사유
    """
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
        cheap = 0                                   # 중앙값 대비 너무 싸고 '최근 등록된' 매물이 앞에서부터 몇 개인지
        while cheap < n and vals[cheap] < med * OUTLIER_RATIO:
            a = age_days(usable[cheap])
            if a is not None and a >= OUTLIER_MAX_AGE_DAYS:
                break                               # 오래 안 팔린 저가: 급처가 아니라 신뢰할 수 없는 가격 -> 제외하지 않는다
            cheap += 1                              # (등록 시각을 모르면 예전처럼 제외 후보로 본다)
        limit = min(MAX_SKIP, n // 3)               # 소수일 때만 '고립된 이상치'로 본다
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
    rel = round(valid[0] / statistics.median(valid), 6)   # 최저가가 나머지 무리에 얼마나 붙어 있는지 (1에 가까울수록 좋음). 반올림: 정확히 0.8 같은 경계값이 환율 곱셈의 부동소수점 오차로 갈리지 않게

    if valid_n >= 5 and rel >= 0.8:
        conf = "high"
    elif valid_n >= 3 and rel >= 0.6:
        conf = "medium"
    else:
        conf = "low"

    notes.insert(0, f"매물 {valid_n}개, 최저가/중앙값 {rel:.0%}")

    age = age_days(chosen)                          # 고른 최저가 매물이 오래됐으면 신뢰도를 낮춘다
    if age is not None:
        drop = 2 if age >= OLD_DAYS else 1 if age >= STALE_DAYS else 0
        if drop:
            conf = _CONF_LEVELS[max(0, _CONF_LEVELS.index(conf) - drop)]
            notes.append(f"최저가 매물이 {age:.0f}일 전 등록이라 신뢰도 {drop}단계 하향")
    return {"status": "ok", "a": chosen["amount"], "c": chosen["currency"], "n": valid_n,
            "confidence": conf, "skipped": skipped,
            "age": None if age is None else round(age, 1), "reason": "; ".join(notes)}


# ---------------------------------------------------------------- 출력
def describe(spec, sockets):
    ilvl = (f">={spec['ilvl_min']}" if spec["ilvl_max"] is None
            else str(spec["ilvl_min"]) if spec["ilvl_min"] == spec["ilvl_max"]
            else f"{spec['ilvl_min']}~{spec['ilvl_max']}")
    qual = (f">={spec['q_min']}" if spec["q_max"] is None
            else str(spec["q_min"]) if spec["q_min"] == spec["q_max"]
            else f"{spec['q_min']}~{spec['q_max']}")
    return f"{spec['label']}  ilvl{ilvl}, Quality{qual}, 소켓={sockets}"


CONF_KO = {"high": "신뢰 높음", "medium": "신뢰 보통", "low": "신뢰 낮음"}


def show(spec, sockets, total, rows, fair):
    print(f"\n  {describe(spec, sockets)}  (전체 {total}건)")
    if not rows:
        print("    결과 없음")
    bad = 0
    for r in rows:
        v = r["ilvl"]
        if v is None:
            continue
        if v < spec["ilvl_min"] or (spec["ilvl_max"] is not None and v > spec["ilvl_max"]):
            bad += 1
    if bad:
        print(f"    ⚠ ilvl 조건에 맞지 않는 매물 {bad}건 -> 필터 ID가 맞는지 확인 필요")

    for i, r in enumerate(rows, 1):
        a = age_days(r)
        print(f"    {i:2}. {r['amount']} {r['currency']}  | ilvl {r['ilvl']} | {r['name']} | {r['seller']}"
              + (f" | {a:.1f}일 전" if a is not None else ""))

    if fair["status"] == "insufficient":
        print(f"    -> 적정 최저가: 데이터 부족 ({fair['reason']})")
    else:
        print(f"    -> 적정 최저가: {fair['a']} {fair['c']}  [{CONF_KO[fair['confidence']]}] {fair['reason']}")


# ---------------------------------------------------------------- 저장 (index.html 이 읽는 prices.json)
def side_payload(total, rows, fair):
    return {
        "total": total,
        "listings": [{"a": r["amount"], "c": r["currency"]} for r in rows if r["amount"] is not None],
        "fair": fair,
    }


def load_stopped(path, league):
    """prices.json 에 기록된 '수집 중지' 항목 {"베이스slug:ilvl": {since, reason}}."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)["leagues"].get(league, {}).get("stopped", {})
    except (OSError, ValueError, KeyError, AttributeError):
        return {}
    out = {}
    for key, info in raw.items():
        if ":" in key:
            out[key] = info
        else:                                    # 이전 버전(베이스 단위) 형식 -> ilvl 별로 펼친다
            for v in ILVLS:
                out[f"{key}:{v}"] = info
    return out


def load_order(path):
    """prices.json 의 시즌 리그 순서 ["최신", "직전"] (html 이 최신/직전을 구분하는 데 사용)."""
    try:
        with open(path, encoding="utf-8") as f:
            order = json.load(f).get("order")
    except (OSError, ValueError, AttributeError):
        return []
    return [x for x in order if isinstance(x, str)] if isinstance(order, list) else []


def merge_order(path, seasonal, has_latest):
    """이번 실행에서 확인한 시즌 리그를 앞에 두고, 기존 순서의 나머지를 이어 붙여 KEEP_LEAGUES 개까지 유지.
    latest 를 조회하지 않은 실행(previous 단독 등)은 기존 순서를 바꾸지 않는다."""
    old = load_order(path)
    if old and not has_latest:
        return old[:KEEP_LEAGUES]
    return (seasonal + [x for x in old if x not in seasonal])[:KEEP_LEAGUES]


def save_prices(path, league, entries, stopped=None, order=None):
    """기존 파일이 있으면 같은 리그의 (base, ilvl) 항목만 갈아끼우고 나머지는 보존한다.
    stopped 가 주어지면 리그의 '수집 중지' 목록 전체를 그 값으로 바꾼다 (비어 있으면 항목 삭제)."""
    data = {"version": 1, "leagues": {}}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded.get("leagues"), dict):
                data = loaded
        except (OSError, ValueError):
            print(f"  ⚠ 기존 {path} 를 읽지 못해 새로 만듭니다")
    now = utc_stamp()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if order:
        data["order"] = list(order)
    lg = data["leagues"].setdefault(league, {"entries": []})
    merged = {(e["base"], e["ilvl"]): e for e in lg.get("entries", [])}
    for e in entries:
        e["collectedAt"] = now
        merged[(e["base"], e["ilvl"])] = e
    lg["entries"] = list(merged.values())
    lg["collectedAt"] = now
    if stopped is not None:
        if stopped:
            lg["stopped"] = dict(stopped)
        else:
            lg.pop("stopped", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def omitted_payload():
    """30% 매물이 부족해 0% 검색을 생략했을 때 저장하는 buy0 (index.html 은 '-', '-개' 로 표시)."""
    return {"total": None, "listings": [], "omitted": True,
            "fair": {"status": "omitted", "a": None, "c": None, "n": 0, "confidence": None,
                     "skipped": 0, "reason": "30% 매물 데이터 부족으로 0% 조회 생략"}}


def run(league, base_name, sockets, ilvls):
    """베이스 하나를 조회하고 prices.json 용 entries 를 반환 (ilvls 에 든 항목만).
    SEARCHES 는 ilvl 마다 30%(A) -> 0%(B) 순서라, 30% 가 데이터 부족이면 같은 ilvl 의 0% 검색은 생략한다."""
    print(f"\n=== {base_name} (소켓 {sockets}, ilvl {'/'.join(map(str, ilvls))}) ===")
    by_ilvl = {}
    sell_short = {}                      # entry_ilvl -> 30% 매물이 데이터 부족인지
    for spec in SEARCHES:
        if spec["entry_ilvl"] not in ilvls:
            continue
        e = by_ilvl.setdefault(spec["entry_ilvl"], {
            "base": slug(base_name), "ilvl": spec["entry_ilvl"], "sockets": sockets})
        if spec["side"] == "buy0" and sell_short.get(spec["entry_ilvl"]):
            print(f"\n  {describe(spec, sockets)}  -> 30% 매물 데이터 부족으로 조회 생략")
            e["buy0"] = omitted_payload()
            continue
        total, rows = cheapest(league, base_name, spec, sockets)
        fair = fair_price(rows)
        show(spec, sockets, total, rows, fair)
        e[spec["side"]] = side_payload(total, rows, fair)
        if spec["side"] == "sell30":
            sell_short[spec["entry_ilvl"]] = fair["status"] == "insufficient"
    return list(by_ilvl.values())


def plan_requests(targets, stopped, force):
    """실행 전에 조회할 (베이스, ilvl)과 최대 요청 수를 계산한다.
    반환: ({베이스: [ilvl...]}, 건너뛴 수집 중지 항목 이름들, 최대 검색 수, 최대 fetch 수)"""
    active, held = {}, []
    for name, _ in targets:
        keep = []
        for v in ILVLS:
            if not force and f"{slug(name)}:{v}" in stopped:
                held.append(f"{name} ilvl {v}")
            else:
                keep.append(v)
        active[name] = keep
    searches = 2 * sum(len(v) for v in active.values())      # ilvl 마다 30% + 0% (30% 부족이면 0% 생략으로 줄어듦)
    return active, held, searches, searches                  # fetch 는 검색마다 최대 1회


def collect(league, stopped, active, todo, out, order):
    """리그 하나를 수집해 저장하고 실패한 베이스 이름 목록을 반환."""
    failed = []
    use_cmp_rates(out, league)                  # 이 리그의 poe.ninja 환율로 이상치 판정 (환율 갱신은 main 에서 먼저 끝난 상태)
    for name, sockets in todo:
        sl = slug(name)
        try:
            entries = run(league, name, sockets, active[name])
        except (RuntimeError, requests.RequestException) as e:
            print(f"  ✗ {name} 조회 실패: {str(e)[:300]}")
            failed.append(name)
            continue
        now = utc_stamp()
        for e in entries:                       # 수집 중지는 베이스+ilvl 별로 각각 관리
            key = f"{sl}:{e['ilvl']}"
            if e["sell30"]["fair"]["status"] == "insufficient":
                stopped[key] = {"since": stopped.get(key, {}).get("since", now),
                                "reason": "30% 매물 데이터 부족 (정상 매물 2개 미만)"}
            else:
                stopped.pop(key, None)
        save_prices(out, league, entries, stopped, order)     # 베이스마다 저장 -> 중간에 끊겨도 진행분 보존
        newly = [f"ilvl {e['ilvl']}" for e in entries if f"{sl}:{e['ilvl']}" in stopped]
        print(f"  -> {out} 저장 ({league} / {name})" + (f"  [수집 중지: {', '.join(newly)}]" if newly else ""))
    return failed


def main():
    ap = argparse.ArgumentParser(description="PoE2 trade2 베이스별 최저가 조회")
    ap.add_argument("target", nargs="?", default="all",
                    help='베이스 이름 또는 "all" = 전체 13종 (기본: %(default)s)')
    ap.add_argument("--league", default="latest",
                    help="latest | 리그 이름 직접 지정. 쉼표로 여러 개. standard, previous 는 수집하지 않음 (기본: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="결과 저장 경로 (기본: 스크립트 옆 out/prices.json, 기존 파일이 있으면 병합)")
    ap.add_argument("--retry-stopped", action="store_true",
                    help="all 실행에서도 '수집 중지'된 항목(베이스+ilvl)을 다시 조회")
    ap.add_argument("--no-rates", action="store_true", help="poe.ninja 환율 갱신을 건너뜀")
    ap.add_argument("--rates-only", action="store_true", help="poe.ninja 환율만 갱신하고 끝냄 (GGG 검색 없음)")
    args = ap.parse_args()

    explicit = args.target.lower() != "all"
    if not explicit:
        targets = [(n, BASES[n]) for n in QUERY_BASES]
    else:
        match = {k.lower(): k for k in BASES}.get(args.target.strip().lower())
        if not match:
            sys.exit(f"알 수 없는 베이스: {args.target}\n사용 가능: {', '.join(BASES)}")
        targets = [(match, BASES[match])]

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
    force = explicit or args.retry_stopped
    plans, n_search, n_fetch = [], 0, 0
    print(f"리그: {', '.join(leagues)}")
    for league in leagues:
        stopped = load_stopped(args.out, league)
        active, held, ns, nf = plan_requests(targets, stopped, force)
        todo = [(n, k) for n, k in targets if active[n]]
        print(f"[{league}] 조회 대상 {len(todo)}종 / {sum(len(active[n]) for n, _ in todo)}개 항목")
        if held:
            print(f"  수집 중지 {len(held)}건 건너뜀: {', '.join(held)}  (다시 조회: --retry-stopped)")
        if todo:
            plans.append((league, stopped, active, todo))
            n_search += ns
            n_fetch += nf
    if not plans:
        return
    est = estimate_seconds(n_search, n_fetch)
    print(f"요청 최대 {n_search + n_fetch}회 (검색 {n_search} + fetch {n_fetch}) · 레이트리밋 기준 최단 약 {est / 60:.1f}분"
          f"  (30% 매물이 부족하면 0% 검색을 생략해 줄어듭니다)")

    started = time.monotonic()
    failed = []
    for league, stopped, active, todo in plans:
        print(f"\n######## 리그: {league} ########")
        failed += [f"{league}/{n}" for n in collect(league, stopped, active, todo, args.out, order)]
    print(f"\n완료: 요청 {limiter.count}회, 소요 {(time.monotonic() - started) / 60:.1f}분"
          + (f", 실패 {len(failed)}건: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
