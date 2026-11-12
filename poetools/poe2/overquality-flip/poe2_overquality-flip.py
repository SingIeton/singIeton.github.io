"""PoE2 trade2: 베이스별 최저가 조회 + 적정 최저가 계산 (basequality.txt 명세 기준).

공통 조건 : Instant Buyout(securable), Rarity=Normal, NOT corrupted/mirrored/fractured
4-A : ilvl >= 82, Quality >= 30  -> 최저가 TOP_N   (index.html: ilvl 82 행의 최대 오버퀄리티 시장가)
4-B : ilvl >= 82, Quality 제한 없음 -> 최저가 TOP_N_BUY0 (index.html: ilvl 82 행의 베이스)
5-A : ilvl  = 81, Quality >= 30  -> 최저가 TOP_N   (index.html: ilvl 81 행의 최대 오버퀄리티 시장가)
5-B : ilvl  = 81, Quality 제한 없음 -> 최저가 TOP_N_BUY0 (index.html: ilvl 81 행의 베이스)
소켓 수는 베이스별로 다르다 (WEAPONS / BODY_ARMOURS 참고). 방어구의 방어 타입(AR/EV/ES)은 BODY_ARMOUR_TYPES 에 보관한다.
방어구(현재 갑옷만)는 ilvl 82 이상(4-A / 4-B)만 조사하고 ilvl 81(5-A / 5-B)은 조사하지 않는다. 갑옷 소켓은 3.

후처리:
  1) 정상 매물(가격·통화를 알 수 있는 매물)이 2개 미만이면 '데이터 부족'
  2) 유효 매물 수(같은 판매자 매물은 1, 0.5, 0.33 ... 으로 줄여 센다. SELLER_* 참고)와 가격 분포로 신뢰도를 매기고
     적정 최저가를 고른다. high: 유효 매물 5 이상 & 최저가/중앙값 75% 이상, medium: 3 이상 & 65% 이상, 그 외 low.
     Instant Buyout은 허위 매물이 드물어 최저가가 시장 최저가에 가깝다고 보되,
     중앙값보다 지나치게 싼 고립 매물(시세를 모르거나 급처)은 제외한다.
     단, 제외 대상은 '최근 등록된' 매물뿐이다. 싸게 나온 매물은 금방 팔려야 정상이므로, 오래 안 팔리고
     남아 있는 저가 매물은 '급처'가 아니라 그 가격이 실제로는 거래되지 않는다(허위·비활성 판매자·시세 오기 등)는
     증거다. 이런 매물은 제외하지 않고 최저가로 남겨, 아래 4)의 경과일 규칙으로 신뢰도를 깎는다.
  3) (최대 오버퀄리티 시장가만) 고른 최저가가 다음 매물보다 ISOLATED_RATIO(10%) 넘게 싸게 혼자 떨어져 있으면, 그 가격은 '싸게 나온
     물건 하나'로 보고 적정 시장가를 윗 매물층 쪽으로 끌어올리며(최저가와 윗층 대표값의 중간, ISOLATED_BLEND) 신뢰도를
     한 단계 낮춘다. 베이스는 실제로 사야 하는 값이라 이 보정을 하지 않는다.
  4) 고른 최저가 매물이 오래됐으면(listing.indexed 기준 STALE_DAYS(3일) 이상 한 단계, OLD_DAYS(7일) 이상 두 단계) 신뢰도를 낮춘다.
     최저가 한 개만 보면 오래 안 팔리던 매물층에서 재등록한 매물이 '방금 등록'으로 통과하므로, 최저가 근처 매물층
     (AGE_GROUP_N 개)의 나이 중앙값과 최저가 나이 중 더 오래된 쪽으로 판정한다.
     오래된 최저가는 이미 시세와 어긋났을 가능성이 크기 때문이다. 등록 시각을 알 수 없으면 보정하지 않는다.

요청 절약 규칙:
  - 최대 오버퀄리티 매물(4-A / 5-A)이 데이터 부족(정상 매물 1개 이하)이면 같은 ilvl 의 베이스 검색(4-B / 5-B)은 생략한다.
    생략된 항목은 overquality-flip-prices.json 에 buy0.omitted = true 로 저장되고, index.html 은 '-', '-개' 로 표시한다.
  - 최대 오버퀄리티 매물이 데이터 부족인 '베이스+ilvl' 은 각각 '수집 중지'로 overquality-flip-prices.json (리그 항목의 stopped, 키 "베이스:ilvl")에
    기록하고, 이후 실행에서는 그 항목만 건너뛴다 (예: Siege Crossbow ilvl 82 만 중지, 81 은 계속 조회).
    index.html 은 해당 ilvl 행을 '수집 중지'로 표시한다. 마지막 확인(checkedAt) 후 재조회 간격이 지나면
    다음 실행에서 자동으로 다시 조회한다 (그 리그가 수집되는 실행에서). 재조회 간격은 --stopped-retry 로 리그별 지정
    (예: latest:1,previous:3,standard:10 = 최신 1일 / 직전 3일 / Standard 10일), 지정하지 않은 리그는 STOPPED_RETRY_DAYS(1일).
    즉 중지 항목은 '그 리그의 수집 주기'와 '재조회 간격' 중 덜 자주 조회된다. 그 전에 다시 조회하려면 --retry-stopped 를 쓰거나 베이스 이름을 직접 지정한다.
    조회 결과 최대 오버퀄리티 매물이 생기면 자동으로 해제되고, 여전히 부족하면 중지가 유지되며 마지막 확인 시각만 갱신된다.

레이트리밋:
  - 실행 전에 조회할 항목으로 최대 요청 수와 최단 소요 시간을 계산해 출력한다.
  - 보낸 시각을 기록하는 슬라이딩 윈도우 방식으로 모든 규칙(5:10, 15:60, 30:300 ...)을 한도 미만으로 유지한다.
    한도 직전까지 몰아 보내고 기간 전체(301초)를 쉬던 이전 방식보다 짧고, 한도 초과로 인한 차단이 걸리지 않는다.
    규칙은 응답 헤더로 매번 갱신하고, 서버가 센 횟수가 더 많으면(브라우저·다른 프로그램 사용분) 그만큼 더 기다린다.

화폐 환율 (poe.ninja):
  - 실행할 때마다 리그별로 Divine, Chaos, 바알 대장장이/방어구 장인의 주입기, 대장장이의 숫돌·방어구 장인의 고철 가격을 poe.ninja 의 PoE2 화폐 거래소
    집계(Exalted 기준, 약 1시간 단위 갱신)에서 읽어 overquality-flip-prices.json 의 리그 항목 "rates" 에 저장한다.
    poe.ninja 가 기본으로 주는 primaryValue 는 리그·시점에 따라 바뀌는 기준 화폐(core.primary, adaptive)로 매긴 값이라 싼 화폐는 오차가 크다.
    그래서 항목별로 '그 화폐로 매겨진 실제 시세'(거래량이 가장 많은 상대 화폐 maxVolumeCurrency 와, 그 화폐 1개로 살 수 있는 개수 maxVolumeRate -> 가격 = 1 / maxVolumeRate)를 읽는다.
      · 바알 주입기·퀄리티 화폐(숫돌·고철): 읽은 값을 Exalted 로 환산하지 않고 그대로 {"v": 값, "u": 단위} 로 저장한다 (u = e Exalted / d Divine / c Chaos).
        maxVolumeCurrency 가 Exalted·Divine·Chaos 중 하나면 그 화폐 값을 쓰고, 아니면 Exalted -> Divine -> Chaos 순서로 찾는다. 저장은 읽은 단위 그대로지만, 화면(overquality-flip.html)은 1 Divine 이상이면 d, 그보다 작으면 읽은 단위와 무관하게 Exalted(e)로 환산해 보여준다
      · Divine·Chaos 자체: 항상 Exalted 기준 숫자 (Exalted 시세를 먼저 보고, 없으면 서로를 거쳐 환산)
    overquality-flip.html 이 이 값을 리그별 기본 환율로 쓴다. 모든 리그는 소프트코어(하드코어 제외)다.
  - 일부 항목을 찾지 못하면 그 항목은 이전 값을 유지하고, poe.ninja 접속에 실패해도 GGG 가격 수집은 계속한다.
  - --no-rates 로 건너뛰고, --rates-only 로 환율만 갱신할 수 있다 (GGG 검색 없이 몇 초).

결과는 이 스크립트 옆의 out/overquality-flip-prices.json 에 저장된다 (index.html 이 같은 out/ 에서 읽음, 기존 파일이 있으면 병합).

실행:
  python poe2_basequality.py                          # 기본: 전체 23종 (무기 13 + 갑옷 10, QUERY_BASES = BASES), 최신 리그만,
                                                      # 수집 중지 항목은 STOPPED_RETRY_DAYS(1일)마다 자동 재조회 (--stopped-retry 로 리그별 지정 가능)
  python poe2_basequality.py "Warmonger Bow"          # 지정한 베이스 하나 (수집 중지여도 조회)
  python poe2_basequality.py all                      # 전체 23종 (요청 최대: 무기 베이스당 10회, 갑옷 베이스당 5회)
  python poe2_basequality.py all --retry-stopped      # 수집 중지된 항목도 다시 조회
  python poe2_basequality.py all --league "latest,previous:6,standard:24" --stopped-retry "latest:1,previous:3,standard:10"
      # 수집 중지 항목 재조회: 최신 1일 / 직전 3일 / Standard 10일마다
  python poe2_basequality.py all --league latest      # 최신 리그만 (기본값)
  python poe2_basequality.py all --league "이름"       # 리그 이름 직접 지정
  python poe2_basequality.py all --league all         # 거래소에 있는 모든 소프트코어 리그 (시즌 리그 전부 + Standard)
  python poe2_basequality.py all --league all:6       # 위와 같되, 리그마다 마지막 수집 후 6시간이 지났을 때만 수집
  python poe2_basequality.py all --league "latest,previous:6,standard:24"
      # 최신 리그는 매번, 직전(second latest) 리그는 마지막 수집 후 6시간이 지났을 때만, Standard 는 24시간이 지났을 때만 수집.
      # 리그 뒤의 ":시간" 은 최소 수집 간격이다 (생략하면 매번 수집). 실행 소요 시간·지연을 감안해 1.5시간 일찍 도래한 것으로 본다 (INTERVAL_MARGIN_H).
  python poe2_basequality.py all --out other/overquality-flip-prices.json   # 저장 위치 지정 (기본: out/overquality-flip-prices.json)
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
DEFAULT_OUT = os.path.join(OUT_DIR, "overquality-flip-prices.json")
KEEP_LEAGUES = 2               # 수집·표시할 시즌 리그 수 (최신 + 직전)
INTERVAL_MARGIN_H = 1.5        # '--league 이름:N' 의 N시간 간격을 판단할 때 앞당겨 보는 시간.
                               # 수집 시각은 그 리그 수집이 끝난 뒤에 찍히고, 직전 리그·Standard 는 최신 리그 뒤에 수집되므로
                               # 한 번의 실행이 이 시간보다 오래 걸리면 다음 주기를 한 번 건너뛰게 된다. 크론 주기(2시간)보다는 작아야 함
UA = "poe2-price-test/0.1 (contact: augustusminu@hotmail.com)"

FETCH_MAX = 10                 # fetch 한 번에 가져올 수 있는 최대 개수 (GGG API 한계). 그보다 많이 보려면 나눠서 여러 번 fetch 한다
TOP_N = 10                     # 최대 오버퀄리티 시장가(4-A/5-A) 검색에서 보는 최저가 매물 수 (fetch 1회)
TOP_N_BUY0 = 20                # 베이스(4-B/5-B) 검색에서 보는 최저가 매물 수 (fetch 2회: 10 + 10, 21개 이상이면 fetch 3회)
                               # index.html 은 '필요 베이스 수(약 9.1 -> 10개)'만큼 싼 순으로 평균을 내므로, 이상치 제외 후에도 10개가 남도록 여유를 둔다


def utc_stamp():
    """수집 시각: 실행 환경(PC=KST, Actions=UTC)과 무관하게 항상 UTC ISO 형식 (예: 2026-11-08T12:21:00Z).
    index.html 이 시간대가 붙은 값을 Date 로 비교하고 사용자 로컬 시간으로 보여준다."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- 적정 최저가 판정 파라미터 -------------------------------------------
MIN_LISTINGS = 2               # 정상 매물이 이보다 적으면 '데이터 부족'
OUTLIER_MIN_N = 4              # 이상치 판정은 매물이 이 수 이상일 때만 (그 미만이면 비교 기준이 부족)
OUTLIER_RATIO = 0.5            # 중앙값의 이 비율 미만이면 '너무 싼' 매물
STALE_DAYS = 3                 # 적정 최저가로 고른 매물이 이 일수 이상 오래되면 신뢰도를 한 단계 낮춘다 (이전 7일)
OLD_DAYS = 7                   # 이 일수 이상이면 두 단계 낮춘다 (시세와 어긋났을 가능성이 큼) (이전 30일)
# 신뢰도 등급 기준 (유효 매물 수 n_eff 와 최저가/중앙값 비율 rel)
CONF_HIGH_N, CONF_HIGH_REL = 5, 0.75      # high  : n_eff >= 5, rel >= 75%
CONF_MED_N, CONF_MED_REL = 3, 0.65        # medium: n_eff >= 3, rel >= 65% (그 외 low)
# 같은 판매자 매물의 신뢰도 반영 (유효 매물 수 n_eff 계산).
# 한 판매자의 첫 매물 = 1, 두 번째 = SELLER_W2, 세 번째부터는 직전 가치 x SELLER_RATIO 로 지수적으로 줄어든다.
# SELLER_RATIO 는 몇 개를 올리든 그 판매자의 가치 합이 SELLER_CAP 을 넘지 않도록 자동 계산된다
# (기본: 1, 0.5, 0.33, 0.22, 0.15 ... -> 합의 한계 2.5). SELLER_CAP 은 1 + SELLER_W2 이상이어야 한다.
SELLER_W2 = 0.5
SELLER_CAP = 2.5
SELLER_RATIO = 1 - SELLER_W2 / (SELLER_CAP - 1)
ISOLATED_RATIO = 1.10           # (최대 오버퀄리티 시장가만) 바로 다음 매물이 최저가의 이 배수보다 비싸면 '고립된 최저가'로 본다
ISOLATED_MIN_N = 4              # 고립 보정은 (최저가 + 그 위 매물 3개 이상), 즉 정상 매물이 이 수 이상일 때만 (위가 한두 개면 '매물층'이라 볼 수 없음)
AGE_GROUP_N = 3                # 경과일 판정에 쓰는 '최저가 매물층' 크기: 적정 최저가부터 싼 순으로 이 개수의 매물 (1 이면 최저가 한 개만 본다)
ISOLATED_REF_N = 3              # 고립된 최저가일 때 윗 매물층의 대표값 = 최저가 다음 매물 최대 이 개수의 중앙값
ISOLATED_BLEND = 0.5            # 적정 시장가 = 최저가 + 이 비율 × (윗 매물층 대표값 − 최저가).  0 이면 최저가 그대로, 1 이면 윗 매물층 가격
MAX_SKIP = 2                   # 고립된 저가 매물로 보고 제외할 최대 개수 (그 이상 몰려 있으면 실제 시세)
OUTLIER_MAX_AGE_DAYS = 2            # 이상치로 제외할 수 있는 저가 매물의 최대 경과 일수. 이보다 오래된 저가 매물은 '안 팔리는 가격'이라 제외하지 않는다
STOPPED_RETRY_DAYS = 1             # 수집 중지 항목을 이 일수마다 자동으로 다시 조회한다 (마지막 확인 시각 기준, 0 이하면 자동 재조회 안 함).
                                   # 이 값은 기본값이다. --stopped-retry "latest:1,previous:3,standard:10" 처럼 리그별로 지정하면 그 값이 우선한다.
                                   # 재조회는 그 리그가 수집되는 실행에서만 일어나므로, 리그 수집 주기가 이 일수보다 길면 그 주기를 따른다.
                                   # (중지 목록은 리그별로 관리되고, 그 리그가 수집되는 실행에서 확인한다)
# 서로 다른 통화의 매물을 비교하기 위한 환율(Exalted 기준). 이상치 판정과 정렬에만 쓰이고, 저장되는 가격은 매물 원래의 (금액, 통화)다.
# 실제 값은 리그 수집을 시작할 때 overquality-flip-prices.json 의 그 리그 poe.ninja 환율(rates)로 덮어쓴다 (use_cmp_rates).
# 아래 기본값은 poe.ninja 환율이 없을 때(--no-rates 이고 저장된 값도 없음, 조회 실패)만 쓰인다.
DEFAULT_CMP_RATES = {"exalted": 1.0, "chaos": 67.0, "divine": 515.0}
CMP_RATES = dict(DEFAULT_CMP_RATES)

# 검색 조건 (basequality.txt 4-A, 4-B, 5-A, 5-B)
# ilvl_max / q_max 가 None 이면 "이상(>=)", 값이 있으면 min~max 범위(같으면 정확히 일치)
# q_min 이 None 이면 퀄리티 필터를 검색 조건에 넣지 않음(퀄리티 제한 없음)
# entry_ilvl : overquality-flip-prices.json 에서 이 결과가 들어갈 행 / side : sell30(최대 오버퀄리티 시장가) 또는 buy0(베이스, 퀄리티 제한 없음)
SEARCHES = [
    {"label": "4-A", "ilvl_min": 82, "ilvl_max": None, "q_min": 30, "q_max": None, "entry_ilvl": 82, "side": "sell30"},
    {"label": "4-B", "ilvl_min": 82, "ilvl_max": None, "q_min": None, "q_max": None, "entry_ilvl": 82, "side": "buy0"},
    {"label": "5-A", "ilvl_min": 81, "ilvl_max": 81,   "q_min": 30, "q_max": None, "entry_ilvl": 81, "side": "sell30"},
    {"label": "5-B", "ilvl_min": 81, "ilvl_max": 81,   "q_min": None, "q_max": None, "entry_ilvl": 81, "side": "buy0"},
]
ILVLS = sorted({sp["entry_ilvl"] for sp in SEARCHES}, reverse=True)   # overquality-flip-prices.json 의 ilvl 행 (82, 81)

# 베이스 이름 -> 증강 가능 소켓 수 (정확히 이 값)
WEAPONS = {
    "Obliterator Bow": 3, "Warmonger Bow": 3,                                       # 활
    "Siege Crossbow": 3, "Gemini Crossbow": 3, "Desolate Crossbow": 3,              # 석궁
    "Sinister Quarterstaff": 3, "Bolting Quarterstaff": 3,                          # 육척봉
    "Soaring Spear": 2, "Akoyan Spear": 2, "Flying Spear": 2,                       # 창
    "Spiny Talisman": 3,                                                            # 부적
    "Massive Greathammer": 3, "Ironwood Greathammer": 3,                            # 양손 철퇴
}
# 방어구: 부위별로 오버소켓 수가 다르다 (갑옷 = 3). 방어구는 ilvl 82 이상만 조사한다 (ilvl 81 행 없음).
# 방어력 종류(AR/EV/ES 조합)는 검색 조건에 쓰이지 않으므로 구분하지 않는다. 베이스 이름 -> 소켓 수.
# 방어 타입은 검색 조건에 쓰이지 않지만, 나중에 타입별 분류·집계에 쓸 수 있도록 데이터로 보관한다 (overquality-flip.html 의 bases[].def 와 같은 값).
#   AR = 방어도(Armour), EV = 회피(Evasion), ES = 에너지 보호막(Energy Shield), 복합 타입은 '/' 로 연결
DEFENCE_TYPES = ("AR", "EV", "ES", "AR/EV", "AR/ES", "EV/ES", "AR/EV/ES")
BODY_ARMOUR_SOCKETS = 3
BODY_ARMOUR_TYPES = {                                                               # 베이스 이름 -> 방어 타입
    "Warlord Cuirass": "AR", "Ornate Plate": "AR",
    "Slipstrike Vest": "EV",
    "Feathered Raiment": "ES", "Vile Robe": "ES",
    "Death Mail": "AR/EV", "Dastard Armour": "AR/EV",
    "Sleek Jacket": "EV/ES", "Falconer's Jacket": "EV/ES",
    "Sacrificial Regalia": "AR/EV/ES",
}
assert set(BODY_ARMOUR_TYPES.values()) <= set(DEFENCE_TYPES)
BODY_ARMOURS = {name: BODY_ARMOUR_SOCKETS for name in BODY_ARMOUR_TYPES}
BASES = {**WEAPONS, **BODY_ARMOURS}
# 기본 조회 대상 (all 과 같음): BASES 전체 (무기 + 갑옷).
# 조회에서 빼려면 WEAPONS / BODY_ARMOURS 에서 지우거나, 데이터 부족이면 아래 '수집 중지' 기능이 자동으로 막는다.
QUERY_BASES = list(BASES)
ARMOUR_ILVLS = (82,)           # 방어구는 82 이상만 조사


def ilvls_for(name):
    """이 베이스에서 조사하는 ilvl 행. 무기는 ILVLS (82, 81), 방어구는 ARMOUR_ILVLS (82)."""
    return ARMOUR_ILVLS if name in BODY_ARMOURS else tuple(ILVLS)


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
# overquality-flip-prices.json 의 리그 항목 "rates" 에 저장한다.
#   - div, chaos: '1개 = Exalted 몇 개' (항상 Exalted 기준 숫자)
#   - inf.*, q.*: poe.ninja 가 그 화폐로 매겨 준 값을 환산하지 않고 그대로 {"v": 값, "u": 단위} 로 저장한다.
#     단위 u 는 e = Exalted, d = Divine, c = Chaos. (예: {"v": 0.1364, "u": "d"} = 1개 = 0.1364 Divine)
#     화면(overquality-flip.html)은 1 Divine 이상이면 d, 그보다 작으면 읽은 단위(d / c / e)와 무관하게 e 로 환산해 보여주고, 계산은 항상 div / chaos 환율로 Exalted 로 환산한 값으로 한다.
# overquality-flip.html 이 같은 키(div, chaos, inf.blacksmith/armourer, q.whetstone/scrap)로 읽는다 (키를 바꾸면 html 도 같이 바꿀 것).
#   "rates": {"div": 646.2, "chaos": 60.96, "inf": {"blacksmith": {"v": 0.1364, "u": "d"}, "armourer": {"v": 1.273, "u": "d"}},
#             "q": {"whetstone": {"v": 0.01042, "u": "d"}, "scrap": {"v": 0.0139, "u": "d"}},
#             "source": "poe.ninja", "updatedAt": "2026-11-12T12:41:26Z"}
NINJA = "https://poe.ninja/poe2/api/economy"
# rates 키 -> (표시 이름, 매칭 후보). id·이름·detailsId 에서 영숫자만 남겨 소문자로 만든 값과 비교하므로
# "vaal-blacksmith-s-infuser", "Vaal Blacksmith's Infuser" 같은 표기 차이는 문제되지 않는다.
RATE_ITEMS = {
    "div": ("Divine Orb", ("divine", "divineorb")),
    "chaos": ("Chaos Orb", ("chaos", "chaosorb")),
    "inf.blacksmith": ("Vaal Blacksmith's Infuser", ("vaalblacksmithsinfuser", "vaalblacksmithinfuser")),
    "q.whetstone": ("Blacksmith's Whetstone", ("blacksmithswhetstone", "blacksmithwhetstone", "whetstone")),
    # 방어구용 (무기는 위의 대장장이 계열)
    "inf.armourer": ("Vaal Armourer's Infuser", ("vaalarmourersinfuser", "vaalarmourerinfuser")),
    "q.scrap": ("Armourer's Scrap", ("armourersscrap", "armourerscrap")),
}
EXALTED_KEYS = ("exalted", "exaltedorb")
# 가격을 환산할 때 기준으로 삼는 세 화폐 (poe.ninja 응답에서 찾는 이름)
ANCHORS = {"exalted": EXALTED_KEYS, "divine": ("divine", "divineorb"), "chaos": ("chaos", "chaosorb")}
ANCHOR_KEYS = {"div": "divine", "chaos": "chaos"}       # rates 키 -> ANCHORS 이름 (Divine / Chaos 자체의 Exalted 가격)
# 항목별로 '어떤 화폐로 매겨진 시세'를 읽을지, 그리고 그 우선순위.
#   poe.ninja 의 기준 화폐(core.primary, adaptive)로 환산한 primaryValue 는 싼 화폐일수록 오차가 커서 쓰지 않는다.
#   퀄리티 화폐·바알 주입기(q.*, inf.*)는 거래량이 가장 많은 상대 화폐(maxVolumeCurrency)가 Exalted / Divine / Chaos 중 하나면 그 화폐로 매겨진 값을
#   환산 없이 그대로 쓰고(단위 e / d / c 와 함께 저장), 아니면 Exalted -> Divine -> Chaos 순서로 찾는다.
#   Divine·Chaos 자체의 가격은 이전처럼 Exalted 시세를 먼저 보고, 없으면 서로를 거쳐 Exalted 로 환산한다 (항상 Exalted 기준 숫자).
RATE_CHAINS = {k: ("exalted", "divine", "chaos") for k in RATE_ITEMS}
UNIT_SHORT = {"exalted": "e", "divine": "d", "chaos": "c"}   # rates 에 저장하는 단위 표기
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


def _num(x):
    """양수 숫자만 float 로 (bool·0·음수·문자열은 None)."""
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def ninja_parse(resp):
    """exchange overview 응답을 시세 계산용으로 정리한다.
      lines  : {화폐 id: line}
      keys   : {id / 이름 / detailsId 를 정규화한 값: 화폐 id}
      primary: core.primary (리그·시점에 따라 바뀌는 'adaptive' 기준 화폐 id. 이 화폐 자신의 line 은 없을 수 있다)
      anchor : {'exalted' | 'divine' | 'chaos': 화폐 id}  (응답에서 찾은 것만)"""
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
    """cid 1개를 cur 화폐로 나타낸 시세(cur 몇 개)를 poe.ninja 가 직접 준 값에서 읽는다. (값, 출처) 또는 None.
      pair   : 거래량이 가장 많은 상대 화폐(maxVolumeCurrency)가 cur 일 때.
               maxVolumeRate 는 '상대 화폐 1개로 살 수 있는 이 화폐의 개수'(예: Exalted 줄의 Divine 쌍 = 644.8 -> Divine 1개 = Exalted 644.8개)
               이므로 이 화폐 1개의 가격은 1 / maxVolumeRate 다. (실제 응답으로 확인한 방향. poe.ninja 는 항상 같은 방향으로 준다)
      primary: cur 이 core.primary 일 때의 primaryValue (primaryValue 는 가격 그대로)"""
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
    """cid 1개의 cur 화폐 기준 시세. (값, 출처) 또는 None. 자기 자신 = 1, 직접 시세가 없으면 반대쪽 line 의 역수."""
    if cid == cur:
        return 1.0, "자신"
    r = _direct(ov, cid, cur)
    if r:
        return r
    r = _direct(ov, cur, cid)                      # 예: Divine 이 core.primary 이면 Divine 자신의 line 은 없다 -> Exalted 쪽 시세의 역수
    return (1 / r[0], r[1] + " 역수") if r else None


def _ex_price(ov, cid, chain, per):
    """cid 1개의 Exalted 가격. chain(화폐 이름 순서)대로 '그 화폐로 매겨진 시세'를 찾아 Exalted 로 환산한다.
    첫 번째로 구해지는 것을 쓴다. 반환: (Ex 값, 쓴 화폐 이름, 출처) 또는 None.  per = {'exalted': 1, 'divine': .., 'chaos': ..} (1개 = Ex 몇 개)"""
    for name in chain:
        cur = ov["anchor"].get(name)
        if cur is None or per.get(name) is None:
            continue
        q = _quote(ov, cid, cur)
        if q:
            return q[0] * per[name], name, q[1]
    return None


def _native_price(ov, cid, chain, per):
    """cid 1개의 시세를 poe.ninja 가 매긴 화폐 단위 그대로 읽는다 (Exalted 로 환산하지 않음). 반환: (값, 화폐 이름, 출처) 또는 None.
    거래량이 가장 많은 상대 화폐(maxVolumeCurrency)가 chain 에 있는 화폐면 그것을 먼저 보고, 이어서 chain 순서로 찾는다.
    per(Exalted 환율)에 그 화폐가 없으면 화면에서 Exalted 로 환산할 수 없으므로 건너뛴다."""
    mv = _norm((ov["lines"].get(cid) or {}).get("maxVolumeCurrency"))
    first = [n for n, c in ov["anchor"].items() if mv and _norm(c) == mv and n in chain]
    for name in first + [n for n in chain if n not in first]:
        cur = ov["anchor"].get(name)
        if cur is None or per.get(name) is None:
            continue
        q = _quote(ov, cid, cur)
        if q:
            return q[0], name, q[1]
    return None


def ninja_ex_per(ov):
    """Divine / Chaos 1개 = Exalted 몇 개 -> ({'exalted': 1.0, 'divine': .., 'chaos': ..}, {이름: 출처}).
    먼저 Exalted 로 매겨진 시세를 읽고, 못 구한 쪽만 다른 쪽(Divine <-> Chaos)을 거쳐 환산한다. Exalted 를 찾지 못하면 ({}, {})."""
    if "exalted" not in ov["anchor"]:
        return {}, {}
    per, src = {"exalted": 1.0}, {}
    for fallback in (False, True):
        for name, other in (("divine", "chaos"), ("chaos", "divine")):
            cid = ov["anchor"].get(name)
            if cid is None or name in per:
                continue
            r = _ex_price(ov, cid, (other,) if fallback else ("exalted",), per)
            if r:
                per[name], src[name] = r[0], f"{r[1].title()}·{r[2]}"
    return per, src


def ninja_league_id(league, ninja_leagues):
    """우리 리그 이름(trade2 기준)에 해당하는 poe.ninja 리그 id. 정규화한 id/이름이 정확히 같은 것만 인정하므로
    'Hardcore ...' 같은 다른 리그와 섞이지 않는다 (소프트코어만 사용)."""
    key = _norm(league)
    for lg in ninja_leagues:
        if key in (_norm(lg.get("id")), _norm(lg.get("name"))):
            return lg.get("id")
    return None


def fetch_ninja_rates(league, ninja_leagues):
    """리그 하나의 환율을 읽어 {"div": (값, "exalted"), "chaos": (값, "exalted"), "inf.blacksmith": (값, "divine"), "q.whetstone": (값, "exalted"), ..} 로 반환 (찾은 것만).
    div / chaos 는 Exalted 기준 값이고, 나머지는 poe.ninja 가 그 화폐로 매겨 준 값을 환산하지 않고 단위(화폐 이름)와 함께 돌려준다.
    poe.ninja 의 기준 화폐(core.primary, 'adaptive')로 환산하지 않고 '그 화폐로 매겨진 시세'를 읽는다
    (maxVolumeCurrency 우선, 이어서 Exalted -> Divine -> Chaos). 아무것도 못 얻거나 값이 비정상이면 None."""
    lid = ninja_league_id(league, ninja_leagues)
    if lid is None:
        names = ", ".join(str(x.get("id")) for x in ninja_leagues) or "없음"
        print(f"  [{league}] poe.ninja 에서 같은 이름의 리그를 찾지 못함 (poe.ninja 리그: {names})")
        return None
    found, how, quoteless, sample = {}, {}, {}, []
    for typ in NINJA_TYPES:
        want = [k for k in RATE_ITEMS if k not in found]
        if not want:
            break
        try:
            ov = ninja_parse(ninja_get("exchange/current/overview", {"league": lid, "type": typ}))
        except (requests.RequestException, ValueError, AttributeError) as e:
            print(f"  [{league}] poe.ninja {typ} 조회 실패 ({str(e)[:200]})")
            if typ == "Currency":
                return None                         # 첫 요청부터 실패하면 나머지 카테고리도 소용없다
            continue
        if not sample:
            sample = sorted(ov["keys"])[:25]
        per, per_src = ninja_ex_per(ov)
        for k in want:
            if k in ANCHOR_KEYS:                    # Divine / Chaos 자체의 Exalted 가격
                name = ANCHOR_KEYS[k]
                if name in per:
                    found[k], how[k] = (per[name], "exalted"), per_src.get(name, "")
                continue
            cid = next((ov["keys"][c] for c in RATE_ITEMS[k][1] if c in ov["keys"]), None)
            if cid is None or not per:
                continue
            r = _native_price(ov, cid, RATE_CHAINS[k], per)
            if r:
                found[k], how[k] = (r[0], r[1]), r[2]
            else:
                ln = ov["lines"].get(cid) or {}     # 이 카테고리에는 있으나 허용된 화폐(Exalted 등)로 매겨진 시세가 없음 -> 원인 확인용으로 원본 필드를 남긴다
                quoteless[k] = (f"{RATE_ITEMS[k][0]}: " + (f"primary={ov['primary']}, primaryValue={ln.get('primaryValue')}, "
                                f"maxVolumeCurrency={ln.get('maxVolumeCurrency')}, maxVolumeRate={ln.get('maxVolumeRate')}"
                                if ln else f"line 없음 (primary={ov['primary']})"))
        time.sleep(0.5)
    missing = [RATE_ITEMS[k][0] for k in RATE_ITEMS if k not in found]
    if "div" in found and "chaos" in found and found["div"][0] <= found["chaos"][0]:
        print(f"  [{league}] 값이 비정상(Divine {found['div'][0]:.1f} <= Chaos {found['chaos'][0]:.1f} Ex)이라 저장하지 않음")
        return None
    shown = ", ".join(f"{RATE_ITEMS[k][0]} {found[k][0]:.4g} {UNIT_SHORT[found[k][1]]}" + (f" ({how[k]})" if how.get(k) else "")
                      for k in RATE_ITEMS if k in found)
    print(f"  [{league}] {shown or '찾은 항목 없음'}")
    if missing:
        print(f"    찾지 못함 (이전 값 유지): {', '.join(missing)}")
        nq = [quoteless[k] for k in RATE_ITEMS if k in quoteless and k not in found]
        if nq:
            print("    └ 항목은 있으나 Exalted / Divine / Chaos 로 매겨진 시세가 없음:")
            for line in nq:
                print(f"      {line}")
        print(f"    poe.ninja Currency 응답의 키 예시: {', '.join(sample) or '(비어 있음)'}")
    return found or None


def save_rates(path, league, found, order=None):
    """found({키: (값, 화폐 이름)})를 overquality-flip-prices.json 의 league.rates 에 병합 저장 (찾지 못한 항목은 이전 값 유지)."""
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
        val, unit = v
        if key in ANCHOR_KEYS:                      # div / chaos: Exalted 기준 숫자 (이상치 판정·환산 기준이라 형식 유지)
            t[parts[-1]] = round(val, 2) if val >= 1 else round(val, 4)
        else:                                       # 읽은 값 그대로 + 단위. 작은 값(0.01042 d)이 0 으로 사라지지 않게 유효숫자 4자리로 저장
            t[parts[-1]] = {"v": float(f"{val:.4g}"), "u": UNIT_SHORT.get(unit, "e")}
    rates["source"] = "poe.ninja"
    rates["updatedAt"] = utc_stamp()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def update_rates(leagues, out, order=None):
    """모든 리그의 환율을 poe.ninja 에서 읽어 저장한다. 실패해도 예외를 내지 않는다 (GGG 가격 수집은 계속)."""
    print("\n== poe.ninja 환율 (읽은 단위 그대로: e=Exalted, d=Divine, c=Chaos / Divine·Chaos 자체는 Ex) ==")
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
    """이 리그의 poe.ninja 환율(overquality-flip-prices.json 의 rates.chaos / rates.div)을 CMP_RATES 에 반영한다.
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


_LEAGUE_NAMES = None


def fetch_leagues():
    """trade2 리그 목록에서 poe2 리그 이름들을 API가 주는 순서대로 반환 (한 번 받으면 재사용)."""
    global _LEAGUE_NAMES
    if _LEAGUE_NAMES is not None:
        return _LEAGUE_NAMES
    data = call("GET", f"{BASE}/api/trade2/data/leagues")
    names = []
    for lg in data.get("result", []):
        if lg.get("realm") not in (None, "poe2"):
            continue
        name = lg.get("id") or lg.get("text")
        if name:
            names.append(name)
    _LEAGUE_NAMES = names
    return names


def all_leagues(out_path):
    """--league all: 거래소 목록의 모든 소프트코어 리그. 시즌 리그(API 순서 = 최신 순)를 앞에, Standard 를 뒤에 둔다.
    Hardcore / SSF / Ruthless 등은 제외 (_EXCLUDE). 목록 조회가 실패하면 저장된 데이터의 리그 순서 + Standard 로 대체."""
    names = None
    try:
        names = fetch_leagues()
    except Exception as e:
        print(f"  리그 목록 조회 실패 ({e})")

    if names is not None:
        softcore = [n for n in names if not _EXCLUDE.search(n)]
        seasonal = [n for n in softcore if n.lower() != "standard"]
        standard = [n for n in softcore if n.lower() == "standard"] or ["Standard"]
        found = seasonal + standard
        print(f"  감지된 전체 리그(API 순서): {found}")
        return found

    saved = [x for x in load_order(out_path) if x.lower() != "standard"] + ["Standard"]
    print(f"  -> 저장된 데이터의 리그 {saved} 사용")
    return saved


def known_season(path, idx):
    """리그 목록 조회가 실패했을 때의 대체값: overquality-flip-prices.json 에 기록된 시즌 리그 순서(order)의 idx 번째 (0=최신, 1=직전).
    order 가 없으면 Standard 아닌 리그를 수집 시각이 최근인 순으로 놓고 idx 번째."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        leagues = data["leagues"]
        order = [x for x in (data.get("order") or []) if isinstance(x, str) and x in leagues]
        if len(order) > idx:
            return order[idx]
        found = sorted(((str(v.get("collectedAt", "")), k) for k, v in leagues.items() if k.lower() != "standard"), reverse=True)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return found[idx][1] if len(found) > idx else None


def hours_since_collected(path, league):
    """overquality-flip-prices.json 에서 이 리그를 마지막으로 수집한 뒤 지난 시간(시). 기록이 없거나 시각 형식을 읽지 못하면 None (= 수집해야 함)."""
    try:
        with open(path, encoding="utf-8") as f:
            ts = json.load(f)["leagues"][league]["collectedAt"]
        last = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def resolve_league(choice, out_path):
    """choice: latest | previous(직전 시즌 리그) | standard | 리그 이름 직접 지정. 확인하지 못하면 None."""
    key = choice.strip().lower()
    if key == "standard":
        return "Standard"
    if key not in ("latest", "previous"):
        return choice.strip()
    idx = 0 if key == "latest" else 1

    names = None
    try:
        names = fetch_leagues()
    except Exception as e:
        print(f"  리그 목록 조회 실패 ({e})")

    if names is not None:
        # 일반 소프트코어 시즌 리그만 (Standard / Hardcore / SSF / Ruthless 제외)
        current = [n for n in names if n.lower() != "standard" and not _EXCLUDE.search(n)]
        print(f"  감지된 리그(API 순서): {current}  (첫 번째=latest, 두 번째=previous)")
        if len(current) > idx:
            return current[idx]
        print(f"  '{choice}' 리그를 찾지 못함 (종료된 리그는 거래소 목록에서 사라질 수 있음)")
        return None                              # 목록 조회에 성공했는데 없으면 저장된 값으로 대체하지 않음

    saved = known_season(out_path, idx)
    if saved:
        print(f"  -> 저장된 데이터의 {'최신' if idx == 0 else '직전'} 리그 '{saved}' 사용")
        return saved
    return None


# ---------------------------------------------------------------- 검색
def _range(lo, hi):
    r = {"min": lo}
    if hi is not None:
        r["max"] = hi
    return r


def build_query(base_name, spec, sockets):
    misc = {"ilvl": _range(spec["ilvl_min"], spec["ilvl_max"])}
    if spec["q_min"] is not None:                       # q_min 이 None 이면 퀄리티 제한 없음 (필터 생략)
        misc["quality"] = _range(spec["q_min"], spec["q_max"])
    misc.update({
        "corrupted": {"option": "false"},
        "mirrored": {"option": "false"},
        "fractured_item": {"option": "false"},
    })
    return {
        "query": {
            "status": {"option": "securable"},
            "type": base_name,
            "filters": {
                "type_filters": {"filters": {"rarity": {"option": "normal"}}},
                "misc_filters": {"filters": misc},
                "equipment_filters": {
                    "filters": {"rune_sockets": {"min": sockets, "max": sockets}}
                },
            },
        },
        "sort": {"price": "asc"},
    }


def top_n_for(spec):
    """검색 종류별로 볼 최저가 매물 수: 베이스는 TOP_N_BUY0, 최대 오버퀄리티 시장가는 TOP_N."""
    return TOP_N_BUY0 if spec["side"] == "buy0" else TOP_N


def fetch_calls(top_n):
    """top_n 개를 가져오는 데 필요한 fetch 요청 수 (FETCH_MAX 개씩 나눠서)."""
    return -(-top_n // FETCH_MAX)


def cheapest(league, base_name, spec, sockets):
    """(총 매물 수, 최저가 행 리스트) 반환. 요청 = 검색 1회 + fetch fetch_calls(top_n)회."""
    s = call("POST", f"{BASE}/api/trade2/search/poe2/{league}",
             json=build_query(base_name, spec, sockets))
    total = s.get("total", 0)
    ids = s.get("result", [])[:top_n_for(spec)]
    if not ids:
        return total, []
    results = []
    for i in range(0, len(ids), FETCH_MAX):          # fetch 는 한 번에 최대 FETCH_MAX 개 -> 가격순 그대로 나눠서 가져온다
        chunk = ids[i:i + FETCH_MAX]
        f = call("GET", f"{BASE}/api/trade2/fetch/{','.join(chunk)}", params={"query": s["id"]})
        results.extend(f.get("result", []))
    rows = []
    for e in results:
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


def effective_count(rows):
    """신뢰도에 쓰는 유효 매물 수 n_eff. rows 는 가격 오름차순.
    같은 판매자의 매물은 싼 것부터 1, SELLER_W2, SELLER_W2*SELLER_RATIO, ... 로 셈 (판매자 한 명의 합은 SELLER_CAP 미만).
    판매자를 모르는 매물('?' 또는 없음)은 서로 다른 판매자로 보고 1로 센다."""
    seen = {}
    total = 0.0
    for r in rows:
        who = str(r.get("seller") or "?").strip().lower()
        if who == "?":
            total += 1.0
            continue
        k = seen.get(who, 0)                      # 이 판매자의 앞선(더 싼) 매물 수
        seen[who] = k + 1
        total += 1.0 if k == 0 else SELLER_W2 * SELLER_RATIO ** (k - 1)
    return total


def fair_price(rows, market=False):
    """적정 최저가 판정.

    반환 dict (overquality-flip-prices.json 의 sell30.fair / buy0.fair 로 그대로 저장됨):
      status     : "ok" | "insufficient"(데이터 부족)
      a, c       : 적정 최저가 (매물 원래의 금액, 통화). insufficient 면 None
      n          : 판정에 쓴 정상 매물 수
      n_eff      : 같은 판매자 매물을 줄여 센 유효 매물 수 (신뢰도 판정에 사용)
      confidence : "high" | "medium" | "low" | None
      skipped    : 너무 싸서 제외한 매물 수
      age        : 고른 최저가 매물의 경과 일수 (등록 시각을 모르면 None)
      group_age  : 최저가 근처 매물층(AGE_GROUP_N 개)의 경과 일수 중앙값 (경과일 신뢰도 보정은 age 와 이 값 중 큰 쪽 기준)
      reason     : 사람이 읽는 판정 사유
      raw        : (market 이고 고립 보정을 했을 때만) 보정 전 최저가 {"a", "c"}

    market=True 는 최대 오버퀄리티 시장가(적정 시장가) 판정이다. 이때는 최저가가 무리에서 혼자 떨어져 있으면 그 가격을 시장가로
    쓰지 않고 윗 매물층 쪽으로 끌어올린다(아래 '고립된 최저가' 참고). 베이스(buy0)는 실제로 사야 하는 값이므로
    최저가 그대로 둔다.
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

    n_eff = round(effective_count(usable[skipped:]), 6)    # 같은 판매자 매물을 줄여 센 유효 매물 수 (신뢰도 판정에만 사용)
    if n_eff >= CONF_HIGH_N and rel >= CONF_HIGH_REL:
        conf = "high"
    elif n_eff >= CONF_MED_N and rel >= CONF_MED_REL:
        conf = "medium"
    else:
        conf = "low"

    cnt = f"매물 {valid_n}개" + (f"(같은 판매자 보정 후 {n_eff:.1f}개 상당)" if abs(n_eff - valid_n) > 1e-9 else "")
    notes.insert(0, f"{cnt}, 최저가/중앙값 {rel:.0%}")

    # 고립된 최저가 (최대 오버퀄리티 시장가만): 최저가 바로 위에 받쳐 주는 매물이 없고 그 위에 정상 매물층이 따로 있으면,
    # 최저가는 '시세'가 아니라 '싸게 나온 물건 하나'다. 사람이 시세를 볼 때처럼 최저가와 윗 매물층의 중간보다
    # 약간 위를 적정 시장가로 본다. (예: 160, 180, 187, 199, 199, 199, 250 -> 윗층 대표 187, 적정 시장가 173.5)
    # 최저가/중앙값은 '무리 전체'와의 비교라 이런 경우를 못 잡으므로(위 예시는 80%) 신뢰도도 한 단계 낮춘다.
    raw = None
    a, c = chosen["amount"], chosen["currency"]
    if market and valid_n >= ISOLATED_MIN_N and round(valid[1] / valid[0], 6) > ISOLATED_RATIO:
        ref = statistics.median(valid[1:1 + ISOLATED_REF_N])
        rate = CMP_RATES.get(c)
        if rate:
            fair_ex = valid[0] + ISOLATED_BLEND * (ref - valid[0])
            raw = {"a": a, "c": c}
            a = round(fair_ex / rate, 1)
            notes.append(f"최저가 {raw['a']:g} {c}가 다음 매물보다 {valid[1] / valid[0] - 1:.0%} 싸게 혼자 떨어져 있어, "
                         f"윗 매물층({ref / rate:g} {c})과의 중간쪽인 {a:g} {c}를 적정 시장가로 사용")
        conf = _CONF_LEVELS[max(0, _CONF_LEVELS.index(conf) - 1)]
        notes.append("고립된 최저가라 신뢰도 1단계 하향")

    # 경과일 보정. 최저가 한 개의 등록 시각만 보면, 오래 안 팔리던 매물층에서 한 명이 내렸다가 다시 올린 순간
    # '방금 등록된 최저가'가 되어 통과해 버린다 (예: 지금 1개 + 5주 된 9개). 재등록은 indexed 를 새로 찍기 때문이다.
    # 그래서 최저가 근처 매물층(AGE_GROUP_N 개)의 나이 중앙값도 같이 보고, 둘 중 더 오래된 쪽으로 판정한다.
    # 중앙값(작은 쪽)이라 신선하게 싼 매물 하나가 오래된 매물 위에서 시세를 새로 잡은 경우(예: 0일, 2일, 40일)는 걸리지 않는다.
    age = age_days(chosen)
    grp = [x for x in (age_days(r) for r in usable[skipped:skipped + AGE_GROUP_N]) if x is not None]
    group_age = statistics.median_low(grp) if grp else None
    cands = [x for x in (age, group_age) if x is not None]
    eff_age = max(cands) if cands else None          # 등록 시각을 하나도 모르면 보정하지 않는다
    if eff_age is not None:
        drop = 2 if eff_age >= OLD_DAYS else 1 if eff_age >= STALE_DAYS else 0
        if drop:
            conf = _CONF_LEVELS[max(0, _CONF_LEVELS.index(conf) - drop)]
            if age is not None and eff_age <= age:
                notes.append(f"최저가 매물이 {age:.0f}일 전 등록이라 신뢰도 {drop}단계 하향")
            else:
                mine = f"최저가 매물은 {age:.0f}일 전이지만 " if age is not None else ""
                notes.append(f"{mine}최저가 근처 매물층(하위 {len(grp)}개)의 나이 중앙값이 {group_age:.0f}일이라 "
                             f"(재등록으로 새것처럼 보였을 수 있음) 신뢰도 {drop}단계 하향")
    out = {"status": "ok", "a": a, "c": c, "n": valid_n,
           "n_eff": round(n_eff, 2), "confidence": conf, "skipped": skipped,
           "age": None if age is None else round(age, 1),
           "group_age": None if group_age is None else round(group_age, 1), "reason": "; ".join(notes)}
    if raw:
        out["raw"] = raw
    return out


# ---------------------------------------------------------------- 출력
def describe(spec, sockets):
    ilvl = (f">={spec['ilvl_min']}" if spec["ilvl_max"] is None
            else str(spec["ilvl_min"]) if spec["ilvl_min"] == spec["ilvl_max"]
            else f"{spec['ilvl_min']}~{spec['ilvl_max']}")
    qual = ("제한 없음" if spec["q_min"] is None
            else f">={spec['q_min']}" if spec["q_max"] is None
            else str(spec["q_min"]) if spec["q_min"] == spec["q_max"]
            else f"{spec['q_min']}~{spec['q_max']}")
    return f"{spec['label']}  ilvl{ilvl}, Quality {qual}, 소켓={sockets}"


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


# ---------------------------------------------------------------- 저장 (index.html 이 읽는 overquality-flip-prices.json)
def side_payload(total, rows, fair):
    return {
        "total": total,
        "listings": [{"a": r["amount"], "c": r["currency"]} for r in rows if r["amount"] is not None],
        "fair": fair,
    }


def _parse_ts(t):
    """수집기가 저장한 시각(UTC ISO '...Z') 또는 이전 형식('2026-11-08 21:50', 시간대 없음 -> UTC 로 간주)을 datetime 으로. 해석 못 하면 None."""
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(str(t).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def retry_due(info, now=None, days=None):
    """수집 중지 항목을 자동으로 다시 조회할 때가 됐는지. 마지막 확인(checkedAt) 없으면 중지 시작(since) 기준.
    둘 다 없거나 해석하지 못하면 확인 기록이 없는 것이므로 다시 조회한다.
    days: 이 리그의 재조회 간격(일). 생략하면 STOPPED_RETRY_DAYS."""
    days = STOPPED_RETRY_DAYS if days is None else days
    if days <= 0:
        return False
    info = info if isinstance(info, dict) else {}
    last = _parse_ts(info.get("checkedAt")) or _parse_ts(info.get("since"))
    if last is None:
        return True
    now = now or datetime.now(timezone.utc)
    # 조회 계획은 실행 '시작'에 세우지만 checkedAt 은 수집 도중(Standard 는 맨 끝)에 찍힌다. 그 차이만큼 매번 조금 모자라
    # 간격이 실행 주기 단위로 한 칸씩 밀리므로(예: Standard 1일 -> 2일), 리그 수집 간격과 같은 INTERVAL_MARGIN_H 만큼 일찍 도래한 것으로 본다.
    return (now - last).total_seconds() >= days * 86400 - INTERVAL_MARGIN_H * 3600


def load_stopped(path, league):
    """overquality-flip-prices.json 에 기록된 '수집 중지' 항목 {"베이스slug:ilvl": {since(중지 시작), checkedAt(마지막 확인), reason}}."""
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
    """overquality-flip-prices.json 의 시즌 리그 순서 ["최신", "직전"] (html 이 최신/직전을 구분하는 데 사용)."""
    try:
        with open(path, encoding="utf-8") as f:
            order = json.load(f).get("order")
    except (OSError, ValueError, AttributeError):
        return []
    return [x for x in order if isinstance(x, str)] if isinstance(order, list) else []


def merge_order(path, seasonal, has_latest, keep=KEEP_LEAGUES):
    """이번 실행에서 확인한 시즌 리그를 앞에 두고, 기존 순서의 나머지를 이어 붙여 keep(기본 KEEP_LEAGUES) 개까지 유지.
    latest 를 조회하지 않은 실행(previous 단독 등)은 기존 순서를 바꾸지 않는다."""
    old = load_order(path)
    if old and not has_latest:
        return old[:keep]
    return (seasonal + [x for x in old if x not in seasonal])[:keep]


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
    """최대 오버퀄리티 매물이 부족해 베이스 검색을 생략했을 때 저장하는 buy0 (index.html 은 '-', '-개' 로 표시)."""
    return {"total": None, "listings": [], "omitted": True,
            "fair": {"status": "omitted", "a": None, "c": None, "n": 0, "confidence": None,
                     "skipped": 0, "reason": "최대 오버퀄리티 매물 데이터 부족으로 베이스 조회 생략"}}


def run(league, base_name, sockets, ilvls):
    """베이스 하나를 조회하고 overquality-flip-prices.json 용 entries 를 반환 (ilvls 에 든 항목만).
    SEARCHES 는 ilvl 마다 최대 오버퀄리티(A) -> 베이스(B) 순서라, 최대 오버퀄리티 매물이 데이터 부족이면 같은 ilvl 의 베이스 검색은 생략한다."""
    print(f"\n=== {base_name} (소켓 {sockets}, ilvl {'/'.join(map(str, ilvls))}) ===")
    by_ilvl = {}
    sell_short = {}                      # entry_ilvl -> 최대 오버퀄리티 매물이 데이터 부족인지
    for spec in SEARCHES:
        if spec["entry_ilvl"] not in ilvls:
            continue
        e = by_ilvl.setdefault(spec["entry_ilvl"], {
            "base": slug(base_name), "ilvl": spec["entry_ilvl"], "sockets": sockets})
        if spec["side"] == "buy0" and sell_short.get(spec["entry_ilvl"]):
            print(f"\n  {describe(spec, sockets)}  -> 최대 오버퀄리티 매물 데이터 부족으로 조회 생략")
            e["buy0"] = omitted_payload()
            continue
        total, rows = cheapest(league, base_name, spec, sockets)
        fair = fair_price(rows, market=spec["side"] == "sell30")
        show(spec, sockets, total, rows, fair)
        e[spec["side"]] = side_payload(total, rows, fair)
        if spec["side"] == "sell30":
            sell_short[spec["entry_ilvl"]] = fair["status"] == "insufficient"
    return list(by_ilvl.values())


def plan_requests(targets, stopped, force, days=None):
    """실행 전에 조회할 (베이스, ilvl)과 최대 요청 수를 계산한다.
    수집 중지 항목은 건너뛰되, 마지막 확인 후 days(리그별 재조회 일수, 생략하면 STOPPED_RETRY_DAYS)일이 지났으면 다시 조회한다 (force 면 전부 조회).
    반환: ({베이스: [ilvl...]}, 건너뛴 수집 중지 항목 이름들, 최대 검색 수, 최대 fetch 수, 기간이 지나 다시 조회하는 항목 이름들)"""
    active, held, due = {}, [], []
    now = datetime.now(timezone.utc)
    for name, _ in targets:
        keep = []
        for v in ilvls_for(name):                           # 무기 82/81, 방어구 82
            key = f"{slug(name)}:{v}"
            if not force and key in stopped:
                if retry_due(stopped[key], now, days):
                    due.append(f"{name} ilvl {v}")
                    keep.append(v)
                else:
                    held.append(f"{name} ilvl {v}")
            else:
                keep.append(v)
        active[name] = keep
    n_ilvl = sum(len(v) for v in active.values())
    searches = 2 * n_ilvl                                    # ilvl 마다 최대 오버퀄리티 + 베이스 (최대 오버퀄리티 매물이 부족하면 베이스 생략으로 줄어듦)
    fetches = n_ilvl * (fetch_calls(TOP_N) + fetch_calls(TOP_N_BUY0))   # 최대 오버퀄리티는 TOP_N, 베이스는 TOP_N_BUY0 개를 FETCH_MAX 개씩
    return active, held, searches, fetches, due


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
                stopped[key] = {"since": stopped.get(key, {}).get("since", now),     # 처음 중지된 시각 (재확인해도 유지)
                                "checkedAt": now,                                       # 마지막으로 다시 확인한 시각 (자동 재조회 주기의 기준)
                                "reason": "최대 오버퀄리티 매물 데이터 부족 (정상 매물 2개 미만)"}
            else:
                stopped.pop(key, None)
        save_prices(out, league, entries, stopped, order)     # 베이스마다 저장 -> 중간에 끊겨도 진행분 보존
        newly = [f"ilvl {e['ilvl']}" for e in entries if f"{sl}:{e['ilvl']}" in stopped]
        print(f"  -> {out} 저장 ({league} / {name})" + (f"  [수집 중지: {', '.join(newly)}]" if newly else ""))
    return failed


def parse_stopped_retry(text):
    """'--stopped-retry' 값 ('latest:1,previous:3,standard:10') -> {소문자 키: 일수}. 키는 latest / previous / standard / 리그 이름."""
    table = {}
    for token in (text or "").split(","):
        token = token.strip()
        if not token:
            continue
        m = re.fullmatch(r"(.+?):(\d+(?:\.\d+)?)", token)
        if not m:
            sys.exit(f"--stopped-retry 형식 오류: '{token}' (예: latest:1,previous:3,standard:10)")
        table[m.group(1).strip().lower()] = float(m.group(2))
    return table


def main():
    ap = argparse.ArgumentParser(description="PoE2 trade2 베이스별 최저가 조회")
    ap.add_argument("target", nargs="?", default="all",
                    help=f'베이스 이름 또는 "all" = 전체 {len(BASES)}종 (기본: %(default)s)')
    ap.add_argument("--league", default="latest",
                    help="latest | previous(직전 리그) | standard | all(모든 소프트코어 리그) | 리그 이름 직접 지정. 쉼표로 여러 개. "
                         "'이름:시간' 으로 최소 수집 간격 지정 (예: latest,previous:6,standard:24 / all:6) (기본: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="결과 저장 경로 (기본: 스크립트 옆 out/overquality-flip-prices.json, 기존 파일이 있으면 병합)")
    ap.add_argument("--retry-stopped", action="store_true",
                    help="all 실행에서도 '수집 중지'된 항목(베이스+ilvl)을 다시 조회")
    ap.add_argument("--stopped-retry", default="",
                    help="'수집 중지' 항목을 다시 조회하는 간격(일)을 리그별로 지정 (예: latest:1,previous:3,standard:10). "
                         f"지정하지 않은 리그는 {STOPPED_RETRY_DAYS}일 (STOPPED_RETRY_DAYS). 0 이하면 자동 재조회 안 함")
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

    stopped_retry = parse_stopped_retry(args.stopped_retry)
    retry_days = {}                                      # 리그 이름 -> 수집 중지 항목 재조회 간격(일)
    leagues, waiting, has_latest = [], [], False
    all_mode, seen_seasonal = False, []                  # --league all 사용 여부 / 이번에 확인한 시즌 리그(API 순서, 수집 간격으로 건너뛴 것 포함)
    for token in args.league.split(","):
        token = token.strip()
        if not token:
            continue
        m = re.fullmatch(r"(.+?):(\d+(?:\.\d+)?)", token)          # '이름:시간' -> 최소 수집 간격(시간)
        choice, every = (m.group(1).strip(), float(m.group(2))) if m else (token, None)
        from_all = choice.lower() == "all"
        if from_all:                                    # 모든 소프트코어 리그로 펼침 ('all:6' 이면 각 리그에 같은 간격 적용)
            all_mode = True
            picks = all_leagues(args.out)
        else:
            picks = [choice]
        for pick in picks:
            lg = resolve_league(pick, args.out)
            if lg is None:
                print(f"리그 '{pick}' 를 확인하지 못해 건너뜁니다")
                continue
            if from_all and lg.lower() != "standard" and lg not in seen_seasonal:
                seen_seasonal.append(lg)
            if lg in leagues or lg in waiting:
                continue
            if lg.lower() == "standard":                 # 리그 역할(latest / previous / standard) -> 재조회 간격
                role = "standard"
            elif pick.lower() in ("latest", "previous"):
                role = pick.lower()
            elif from_all and lg in seen_seasonal and seen_seasonal.index(lg) < 2:
                role = ("latest", "previous")[seen_seasonal.index(lg)]
            else:
                role = None
            d = stopped_retry.get(role) if role else None
            if d is None:
                d = stopped_retry.get(lg.lower())
            retry_days[lg] = STOPPED_RETRY_DAYS if d is None else d
            if every is not None:
                age = hours_since_collected(args.out, lg)
                if age is not None and age < every - INTERVAL_MARGIN_H:
                    print(f"[{lg}] 마지막 수집 {age:.1f}시간 전 (간격 {every:g}시간) -> 이번에는 건너뜁니다")
                    waiting.append(lg)
                    continue
            leagues.append(lg)
            if pick.lower() == "latest":
                has_latest = True
    if not leagues:
        if waiting:
            print("수집 주기가 아직 되지 않아 이번 실행은 할 일이 없습니다.")
            return
        sys.exit('수집할 리그를 확인하지 못했습니다. --league "이름" 으로 직접 지정하세요.')

    seasonal = [l for l in leagues if l.lower() != "standard"]
    if all_mode:                                        # all: 시즌 리그 전부(수집 간격으로 건너뛴 것 포함)를 표시 순서에 유지
        order = merge_order(args.out, seen_seasonal, True, keep=max(KEEP_LEAGUES, len(seen_seasonal)))
    else:
        order = merge_order(args.out, seasonal, has_latest)
    if not args.no_rates:
        update_rates(leagues, args.out, order)
        if args.rates_only:
            return
    force = explicit or args.retry_stopped
    plans, n_search, n_fetch = [], 0, 0
    print(f"리그: {', '.join(leagues)}")
    for league in leagues:
        stopped = load_stopped(args.out, league)
        days = retry_days.get(league, STOPPED_RETRY_DAYS)
        active, held, ns, nf, due = plan_requests(targets, stopped, force, days)
        todo = [(n, k) for n, k in targets if active[n]]
        print(f"[{league}] 조회 대상 {len(todo)}종 / {sum(len(active[n]) for n, _ in todo)}개 항목")
        if due:
            print(f"  수집 중지 {len(due)}건은 마지막 확인 후 {days:g}일이 지나 다시 조회: {', '.join(due)}")
        if held:
            print(f"  수집 중지 {len(held)}건 건너뜀 ({days:g}일마다 자동 재조회, 지금 전부 다시 조회: --retry-stopped): {', '.join(held)}")
        if todo:
            plans.append((league, stopped, active, todo))
            n_search += ns
            n_fetch += nf
    if not plans:
        return
    est = estimate_seconds(n_search, n_fetch)
    print(f"요청 최대 {n_search + n_fetch}회 (검색 {n_search} + fetch {n_fetch}) · 레이트리밋 기준 최단 약 {est / 60:.1f}분"
          f"  (최대 오버퀄리티 매물이 부족하면 베이스 검색을 생략해 줄어듭니다)")

    started = time.monotonic()
    failed = []
    for league, stopped, active, todo in plans:
        print(f"\n######## 리그: {league} ########")
        failed += [f"{league}/{n}" for n in collect(league, stopped, active, todo, args.out, order)]
    print(f"\n완료: 요청 {limiter.count}회, 소요 {(time.monotonic() - started) / 60:.1f}분"
          + (f", 실패 {len(failed)}건: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
