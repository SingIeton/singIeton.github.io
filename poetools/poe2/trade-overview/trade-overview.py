"""PoE2 trade2: 장비 종류별 경매장 매물 수집 -> trade-overview.html 용 데이터(js) 생성.

사용자가 TARGETS 에 적어 둔 경매장 링크(또는 검색 설정)를 GGG trade2 API 로 검색해, 가격 오름차순 최저가 매물을
html 이 쓰기 좋은 형태로 정리해 js 파일로 저장한다.

[의도적으로 구현하지 않은 것]
  '시장가 추정' 로직은 poe2_overquality-flip.py 에서 나중에 옮겨 올 예정이라 여기에는 없다 (estimate_market() 이 빈 자리).
  그 로직이 쓰던 poe.ninja 환율 수집도 같은 이유로 넣지 않았다. 지금은 RATES 에 직접 적은 환율을 출력에 그대로 실어 줄 뿐이다.
  지금 이 파일이 하는 일은 '검색 -> 매물 정규화 -> 한글 표기 -> 저장' 까지다.

------------------------------------------------------------------------------------------------
사용자가 손댈 곳 (이 파일 위쪽)
  1) TARGETS : 표시할 장비 종류 목록. 항목 하나 = 화면의 한 줄.
        "url"   : PoE2 경매장 링크. 주소창의 링크를 그대로 붙여 넣으면 된다.
                  - 긴 압축 문자열(H4sI...)이 든 링크: 링크 안의 검색 조건을 직접 풀어 읽는다 (서버 조회 없음)
                  - '?q={...}' 링크: 마찬가지로 서버 조회 없음
                  - 짧은 저장 검색 링크(.../<리그>/<id>): 서버에서 조건을 한 번만 읽어 와 out/ 에 캐시한다
                  링크의 리그는 검색 조건을 읽어 오는 용도일 뿐이고, 실제로 조회하는 리그는 --league 가 정한다
                  (같은 조건을 최신 리그 / 직전 리그 / Standard 에 모두 쓸 수 있다).
        "query" : 링크 대신 검색 설정을 직접 적는다 (trade2 검색 요청의 "query" 부분, 또는 {"query":..} 전체).
        url / query 중 정확히 하나만 적는다.
        id 가 "0" 인 항목은 생략된다 (검색도 출력도 하지 않으므로 잠시 빼 두고 싶을 때 id 만 "0" 으로 바꾸면 된다).
        "comment": (선택) 이 줄에 붙일 메모 (예: "스킬 소켓 2개 이상 / 부패 제외"). 번역 없이 적은 그대로
                  targets / entries 의 "comment" 로 출력되어 html 이 표시할 수 있다. 적지 않으면 null.
  2) KO      : 한글 표기. 영어 -> 한글. 비워 두면 영어로 보인다. 섹션:
        name     TARGETS 의 name            category  TARGETS 의 category
        currency GGG 화폐 id (divine ...)   item      베이스 타입 / 유니크 이름
        mods     옵션 문구. 숫자를 #로 바꾼 영문 -> 한글 템플릿 (예: "+# to Level of all Spell Skills": "모든 주문 스킬 레벨 +#")
        py 안의 KO 에 적거나, 이 파일 옆 trade-overview-ko.json 에 같은 구조로 적어도 된다 (json 쪽이 우선).
        TARGETS 항목에 "ko": "..." 를 직접 적는 것이 name 보다 우선한다.
        실행이 끝나면 한글 표기가 없는 문구를 콘솔과 out/trade-overview-missing-ko.json 에 모아 준다
        (그 파일에 값만 채워 trade-overview-ko.json 으로 합치면 된다).
  3) RATES   : (선택) 리그별 환율을 직접 적는다. 출력의 leagues.<리그>.rates 로 그대로 들어간다.
  4) 빈 카드 : TARGETS 에 {"id": "5", "name": "", "url": ""} 처럼 name / url (/ query) 을 비워 둔 항목은 빈 카드다.
        검색하지 않고 status "blank" 항목으로 저장되며, 제목 배경색만 보인다 (카드 번호별 색은 html 의 COLORS 에서 정한다). 채우려면 name 과 url 에 값을 적으면 된다 (둘 다 필요).

출력: out/trade-overview.js  ->  window.TRADE_OVERVIEW_SKILL_AMULET = { ... };
  html 은 <script src="out/trade-overview.js"></script> 로 읽으면 된다 (file:// 로 열어도 동작). 구조:
  {
   "version": 1, "page": "skill-amulet", "generatedAt": "2026-11-21T03:00:00Z",
   "order": ["최신 시즌 리그", "직전 시즌 리그"],            # 시즌 리그 순서 (Standard 는 여기에 없음)
   "targets": [                                            # TARGETS 순서 그대로 = 화면에 보일 줄 (수집 전이어도 있음)
     {"id", "name"(영어), "ko"(한글 또는 null), "category", "categoryKo", "comment"(메모 또는 null)}, ...],
   "i18n": {"currency": {"divine": "...", ...}, "category": {"Amulet": "...", ...}},   # 값이 있는 것만
   "leagues": {
     "<리그 이름>": {
       "collectedAt": "...Z" | null,                       # 이 리그에서 마지막으로 수집에 성공한 시각 (성공이 한 번도 없으면 null)
       "rates": {"div": 646.2, "chaos": 60.96, "source": "manual"},   # RATES 에 적은 경우만. 1개 = Exalted 몇 개
       "entries": [{                                       # TARGETS 순서
         "id", "name", "ko", "category", "categoryKo", "comment",
         "status": "ok" | "empty"(검색 결과 없음) | "error"(수집 실패, 이전 값도 없음) | "blank"(name/url/query 없이 id 만 적은 빈 카드),
         "link": "https://www.pathofexile.com/trade2/search/poe2/<리그>/<검색id>",   # 경매장에서 같은 검색을 여는 링크
         "total": 123,                                     # 검색에 걸린 전체 매물 수
         "fetched": 10,                                    # listings 에 담긴 매물 수
         "listings": [{                                    # 가격 오름차순 최저가 매물
            "id", "a": 12, "c": "divine",                  #   가격 (원래 금액, 통화)
            "indexed": "...Z", "seller": "계정명",          #   등록(마지막 갱신) 시각, 판매자
            "item": {"base", "baseKo", "rarity", "name", "nameKo", "ilvl", "corrupted",
                     "mods": {"implicit"|"explicit"|"rune"|"enchant"|"fractured"|"desecrated": [{"en", "ko", "id", "tier", "affix"}, ...]}}}, ...],
                                                           #   ko / id / tier / affix 는 있을 때만
         "fair": {...},                                    # estimate_market() 이 값을 돌려준 경우만 (지금은 없음)
         "stale": true, "error": "...",                    # 이번 수집이 실패해 이전 값을 유지하는 경우만
         "collectedAt": "...Z"}]}}}
  결과는 기존 파일에 병합된다 (같은 리그의 같은 id 만 갈아끼움, TARGETS 에서 지운 항목은 저장할 때 정리).
  수집에 실패한 항목: 이전 값이 있으면 그 값에 stale/error 를 붙여 유지하고, 없으면 status "error" 항목을 만든다.

레이트리밋: 슬라이딩 윈도우 방식. 실행 전에 최대 요청 수와 최단 소요 시간을 출력한다.

실행:
  python trade-overview.py                       # TARGETS 전체, 최신 리그만
  python trade-overview.py "skill-amulet"        # id 또는 이름이 맞는 항목 하나만
  python trade-overview.py --dry-run             # 네트워크 없이 어떤 검색을 할지만 출력 (링크 해석 확인용)
  python trade-overview.py --league "latest,previous:6,standard:24"
      # 최신 리그는 매번, 직전 리그는 마지막 수집 후 6시간이 지났을 때만, Standard 는 24시간이 지났을 때만 ('이름:시간' = 최소 수집 간격)
  python trade-overview.py --league all          # 거래소에 있는 모든 소프트코어 리그
  python trade-overview.py --league "이름"        # 리그 이름 직접 지정
  python trade-overview.py --out other/data.js   # 저장 위치 지정 (기본: out/trade-overview.js)
  python trade-overview.py --ko my-ko.json       # 한글 표기 파일 지정 (기본: trade-overview-ko.json)

필요: pip install requests     (로그인이 필요한 경우 환경변수 POESESSID 에 세션 쿠키 값을 넣는다)
"""
import argparse
import base64
import copy
import gzip
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

BASE = "https://www.pathofexile.com"
POESESSID = os.environ.get("POESESSID", "")           # 선택. 코드에 직접 적지 말 것
PAGE = "skill-amulet"
JS_GLOBAL = "TRADE_OVERVIEW_SKILL_AMULET"          # html 이 읽는 전역 변수 이름 (바꾸면 html 도 같이 바꿀 것)
JS_PREFIX = f"window.{JS_GLOBAL} = "
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")
DEFAULT_OUT = os.path.join(OUT_DIR, "trade-overview.js")
QUERY_CACHE_FILE = os.path.join(OUT_DIR, "trade-overview-queries.json")   # 링크 -> 검색 조건 캐시
MISSING_KO_FILE = os.path.join(OUT_DIR, "trade-overview-missing-ko.json")  # 한글 표기가 없는 문구 목록
DEFAULT_KO_FILE = os.path.join(HERE, "trade-overview-ko.json")
KEEP_LEAGUES = 2               # 수집·표시할 시즌 리그 수 (최신 + 직전)
INTERVAL_MARGIN_H = 1.5        # '--league 이름:N' 의 N시간 간격을 판단할 때 앞당겨 보는 시간 (실행 시간·지연 보정)
UA = "poe2-price-test/0.1 (contact: augustusminu@hotmail.com)"

FETCH_MAX = 10                 # fetch 한 번에 가져올 수 있는 최대 개수 (GGG API 한계)
LIMIT = 10                     # 항목당 가져올 최저가 매물 수 (검색 1회 + fetch ceil(LIMIT/10)회). 항목별로 "limit" 으로 바꿀 수 있다
FORCE_SECURABLE = True         # 링크·설정의 거래 상태를 Instant Buyout(securable)로 고정한다.
                               # 나중에 붙일 시장가 판정이 '즉시 구매 매물은 허위가 드물다'는 가정 위에 있으므로 끄지 않는 것을 권장

def utc_stamp():
    """수집 시각: 실행 환경과 무관하게 항상 UTC ISO 형식 (예: 2026-11-08T12:21:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ================================================================ 사용자 설정: 장비 종류(TARGETS)
# 아래는 '예시'다. 실제로 보고 싶은 장비 종류의 링크/검색 설정으로 바꿔 쓴다.
#   id       : 영문 소문자·숫자·'-' (생략하면 name 에서 만든다). 데이터 파일과 html 에서 항목을 구분하는 키라 한 번 정하면 바꾸지 않는 것이 좋다
#   name     : 영어 표시 이름 (KO["name"] 의 키이기도 하다)
#   category : 묶음 이름 (선택, 예: "Amulet"). KO["category"] 의 키
#   ko       : 한글 이름 (선택, 가장 우선)
#   comment  : 이 줄에 붙일 메모 (선택). 번역 없이 그대로 출력에 실린다 (targets / entries 의 "comment")
#   url | query : 둘 중 정확히 하나
#   limit    : 선택, 기본 LIMIT
TARGETS = [
    {"id": "1", "name": "Absent Amulet (Melee, Trinity)", "category": "",
     "url": "https://www.pathofexile.com/trade2/search/poe2/Forbidden%20Rites/H4sIAAAAAAAACq1X2Y7bIBT9F56jiM0s-ZVqhBiMO2gwjgBPpxrl3ytn2onrmHhpn5IA59yFc2-4HyBlnfsETh-gO2fXBXACyZo-6mdvweVw3U_g9O0D5J9nC05AhxocQON8tvFzw9XgBM7J9nV3_PxQoW-fbVRdo3TTuHfVdnUCB_CmfW8HW61-Byd0OYDapcFSDU6N9sleni6HL0um60Oes5VenfdHo1NWXVAmuuyM9irl6F4tGJPm2NuBcQZWd_X3xcOpb9suqPjSadX-duchQEfz0upl4hxdcPknmCzbbGPQXsUVFH8Csd62NmTtlXZ--LYE_NH5Rp21eb0_-DS-IxeGO1p_ITfeicFn78KrijbZ-KavIlvw8BaS6ULj-_fFe9ImusaZxaS1bkitGq7JxqXDjY3aKxfeOlNw-2m6si9_9v3snXH5OFSbkkhwKjGYcpEr1wwAYYgJRIyTOw83cFBEkCBwPwVGDEPJaYW3cDRRm9xHW0-D38uwLxt3JDvSMeHYlo-dpTf1G3FOIWWVKIt76qZgjDBE8XKsFD4IFjLCqooMhtejqMCiwpWQW1CECskFhvC-Rjgqo7CUhHJIl3WBcNm4FIRTWUm2yMLL6oIVRLCihC67wqpy9jgVjFUM0X_wBUtOKeKIykUS_CnT_9_xRqot9ZZ9Ip02qFUanYDWSfRv0EqF1jZZE3X-kmgFJWEY8gfVO8UgJCuCJIMPMBPnNhQCLIa4vg5GAp5c-84ymFzQ-iooc6wvAlokIVIgTCHn9ylZLhs8Lpsf1n1_ycvP7NwNb6Tbayna5FLWwQxP9wcI86K7ND498ua37RM60lKgleCUIMareRwuJqiqmMBUIrkVKBGnQiKK54D4WFYY4ZIiJAjbCORCIsTlTFHN8MAjKwpr4BEUy1VEeEV_xXsa7F_SnOh5c1MP3TaLBSneZsRbS1Opv82L924NK192B9eSUaPfzXgrxi4OuNFgex0xh6HWdDH251zaTjqY7BpX2v_6B1Uu23buzMxkewA56toW_D3HYXj5k-7Qe3_4HJIpPNzYa_fmwpT-mpjL5RedHSKdyw8AAA"},

    {"id": "2", "name": "Absent Amulet (Melee, Eternal)", "category": "",
     "url": "https://www.pathofexile.com/trade2/search/poe2/Forbidden%20Rites/H4sIAAAAAAAACq1X247bIBD9F56jiJu55FeqFWIx7qLFOAK83WqVf6-ctInrmNhO-5TEcM7czkw8XyBlnfsEDl-gO2bXBXAAyZo-6ldvwWl3Pk_g8O0L5J9HCw5AhxrsQON8tvFy4GpwAMdk-7rbXz5U6NtXG1XXKN007lO1XZ3ADnxo39vBVqs_wQGddqB2abBUg0OjfbKnl9Puasl0fchzttK7835vdMqqC8pEl53RXqUc3bsFY9IcezswzsDqrv6-eDn1bdsFFd86rdrf7jwE6GjeWr1MnKMLLv9cumazjUF7FaeUl2zNR2a9bW3I2ivt_PBtycqPzjfqqM37_cWXcdFcGIq2vkI33onBV-_Cu4o22fihz6pbysM1JNOFxvefi4XTJrrGmcVCtG7IrRrqZuPS5cZG7ZULH50puP0yffJc_uzn0Tvj8n5oPyWR4FRiMOUiZ64ZAMIQE4gYJ3cebuCgiCBB4PMUGDEMJacV3sLRRG1yH209Df5ZhueycUfyRDomHNvy8WTrTf1GnFNIWSXK4p66KRgjDFG8HCuFD4KFjLCqIoPh9SgqsKhwJeQWFKFCcoEhvO8RjsooLCWhHNJlXSBcNi4F4VRWki2y8LK6YAURrCihy66wqpw9TgVjFUP0H3zBklOKOKJykQRfZPr_J95ItaXZ8pxIpwNqlUYnoHUS_Ru0UqG1TdZEna8SraAkDEP-oHunGIRkRZBk8AFm4tyGRoDFENf3wUjAk7I_2QaTAq3vgjLH-iagRRIiBcIUcn6fkuW2weO2-WHd97e8_N6du-Ed6fa2FG1yKetghnf5Bwjzprs0vj3y5rftA9rTUqCV4JQgxqt5HC4mqKqYwFQiuRUoEadCIorngHhfVhjhkiIkCNsI5EIixOVMU83wwD0rCmvgERTLVUR4xXzFzwzYv6Q50fPmoR66bRYLUrwtjbeRplJ_WyDv3RqeXO0OriWjRr-b8VGMXRxwo033vEUNW67pYuyPuXScdDDZNa50fv0HVS7bdu7OzKq7Aznq2hb8PcZhefmT7tB7v7tszRTubuy1-3BhSn9OzOn0C5vRHSHcDwAA"},
     
     {"id": "3", "name": "", "url": ""},

    {"id": "4", "name": "Res, Recycle", "category": "",
     "url": "https://www.pathofexile.com/trade2/search/poe2/Forbidden%20Rites/H4sIAAAAAAAACrVX226jMBD9Fz9HkT2-8yurClEwXSQCyDZVo4h_X5F2N1xicFn1KRdzZnzOnBmbG3I-871DyQ21na_aBiXImby32Wtt0HC6rzuU_Lohf-0MSlDWFOiEyqr2xn4uVAVKkPno6iqv_HkEpKAx0UpIjtEJvWd1b8YMl6pBCYFhOH2BOmf6oj1_fqS-9VmdmtpcTDN-s8ZVzmdNbtAJFZUbt1SgxNverIIS_ohaXaZbIYoLrrGkahUlsI-mv7wam7Zlai6dv6adNWX1kV7awqFIiOvLB-RlBH2pl7d945_pN980YKoVAFPqkXH-BNVEMqUJgzCtBYJK4MCAyVgEA8AYpAYWiyBCEioFjc8xcUrwCaBMCeA6NqZWVDLNtQiGlEwJwQVhaN81oSRcCS0IfbKrl5U9hxgLzFtoVq55OPYZ7wloVrFY0KxosaDIDl-CgqVcBgEcCkKlUkQSysN2WCqpqQBFZTyCCY4BlCJHZ8Z0AEQmJZhjgjmj625bKSx4UGKlCVEMtNqXmAxrq8L_WnU7Z6R1jwbZmD8Hrb1TiEkdSpvlvrem2O1fqoKojQbeQG108AZqq4VZHK94ibd4Ho5ysNxbOuzUe6KLafLfWfPXeJJwqRgWG7eMpZCgNWUSM7qWH-Mw54NjYpl9en9Ywu5zYSf2kTmhBYBU-D6bFmOHBluaS0oolmKfL4jQJXBi2n1qh0YgaCK4wvczJpYaw0JiMW4r4jg8B8lNeulnyAFQQrigmH6nbpIzxjjnYp8cC5ObtPjPkJv5K-ynjcptVWpDk2cafK_tmva7TRd3-3l4OXRCPgwxBJ4gjBENmPMnZRv_-bfrkZjL08nv2ZK1rR1xk_fTMqvd_d00b63tOx9adlmT-6qsnq8Pw-muYyBznnnz1trrDJrluXGutdezrZq3McYw_AFl05Z5Qw8AAA"},
     
     

    # 빈 카드 (검색 없음, 제목 색은 html 의 COLORS). 채우려면 name 과 url 에 값을 적는다. id "0" 은 생략된다
    {"id": "5", "name": "", "url": ""},
    {"id": "6", "name": "", "url": ""},
    {"id": "7", "name": "", "url": ""},
    {"id": "8", "name": "", "url": ""},
    {"id": "9", "name": "", "url": ""},
    {"id": "10", "name": "", "url": ""},
    {"id": "11", "name": "", "url": ""},
    {"id": "12", "name": "", "url": ""},
    {"id": "13", "name": "", "url": ""},
    {"id": "14", "name": "", "url": ""},
    {"id": "15", "name": "", "url": ""},
    {"id": "16", "name": "", "url": ""},
    {"id": "17", "name": "", "url": ""},
    {"id": "18", "name": "", "url": ""},
    {"id": "19", "name": "", "url": ""},
    {"id": "20", "name": "", "url": ""},
    {"id": "21", "name": "", "url": ""},
    {"id": "22", "name": "", "url": ""},
    {"id": "23", "name": "", "url": ""},
    {"id": "24", "name": "", "url": ""},
    {"id": "25", "name": "", "url": ""},
]

# ================================================================ 사용자 설정: 한글 표기 (영어 -> 한글)
# 비워 두면(또는 키가 없으면) 영어 그대로 보인다. 값은 직접 채운다.
KO = {
    "name": {                       # TARGETS 의 name -> 한글 이름
        # "Skill Amulet": "",
    },
    "category": {                   # TARGETS 의 category -> 한글 묶음 이름
        # "Amulet": "",
    },
    "currency": {                   # GGG 가격 통화 키 -> 한글 화폐 이름 (가격 표시에 쓰임)
        # "exalted": "", "divine": "", "chaos": "",
    },
    "item": {                       # 매물의 베이스 타입 / 유니크 이름 -> 한글 (영문 그대로, 대소문자 포함)
        # "Stellar Amulet": "",
    },
    "mods": {                       # 옵션 문구: 숫자를 # 로 바꾼 영문 -> 한글. # 자리에는 원문의 숫자가 순서대로 들어간다 (부호는 템플릿에 직접 적을 것)
        # "+# to Level of all Spell Skills": "모든 주문 스킬 레벨 +#",
    },
}
KO_SECTIONS = ("name", "category", "currency", "item", "mods")

# ================================================================ 사용자 설정: 환율 (선택)
# 리그 이름 -> {"div": 1 Divine 가 몇 Exalted, "chaos": 1 Chaos 가 몇 Exalted}. "*" 는 모든 리그에 쓰는 기본값.
# 출력의 leagues.<리그>.rates 로 그대로 들어간다 (source: "manual"). 이 파일은 이 값을 쓰지 않는다 — html 이나 나중에 붙일 시장가 로직용이다.
RATES = {
    # "*": {"div": 646.2, "chaos": 60.96},
}


# ================================================================ 시장가 추정 (비워 둠)
def estimate_market(listings, target, league):
    """시장가 추정 자리. poe2_overquality-flip.py 의 로직을 나중에 여기로 옮겨 온다 (지금은 의도적으로 구현하지 않음).

    listings : 가격 오름차순 매물 목록. 원소는 {"id", "a": 금액, "c": 통화, "indexed": ISO 시각, "seller": 계정명, "item": {...}}.
               overquality-flip 의 rows 는 {"amount", "currency", "seller", "indexed", ...} 형태이므로 옮길 때
               rows = [{"amount": l["a"], "currency": l["c"], "seller": l["seller"], "indexed": l["indexed"]} for l in listings]
               처럼 바꿔 주면 된다.
    target   : TARGETS 항목 (id, name, category, limit, ...). 항목별 설정(예: "market")을 더 쓰고 싶으면 TARGETS 에 키를 추가하면
               normalize_targets() 가 그대로 넘겨 준다.
    league   : 수집 중인 리그 이름. 환율이 필요하면 RATES 나 (옮겨 올) poe.ninja 수집 코드를 쓴다.

    반환: dict 면 그대로 entries[].fair 에 저장되고, None 이면 fair 는 출력되지 않는다.
    예외가 나도 수집한 매물은 fair 없이 저장된다.
    """
    return None


session = requests.Session()
session.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
if POESESSID:
    session.cookies.set("POESESSID", POESESSID, domain="www.pathofexile.com")

_printed_headers = False


def slug(name):
    """'Skill Amulet' -> 'skill-amulet'"""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


# ---------------------------------------------------------------- 레이트리밋: 슬라이딩 윈도우 스케줄러
# 응답 헤더(X-Rate-Limit-Ip 등)는 "허용횟수:기간(초):초과 시 차단(초)" 규칙의 목록이다. 예) 30:300:1800 = 300초 동안 30회까지, 넘기면 1800초 차단.
# 보낸 시각을 모두 기록해 두고, 모든 규칙에서 '가장 오래된 요청이 윈도우 밖으로 나가는 순간' 바로 다음 요청을 보낸다. 한도는 절대 넘기지 않는다.
RATE_MARGIN = 1        # 한도보다 이만큼 적게만 쓴다 (초과하면 최대 30분 차단이라 여유를 둔다)
RATE_PAD = 0.5         # 윈도우가 풀리는 시각에 더하는 여유(초)
MIN_GAP = 0.3          # 요청 사이 최소 간격(초)
RATE_HEADERS = ("X-Rate-Limit-Ip", "X-Rate-Limit-Account")
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


# ---------------------------------------------------------------- 데이터 파일 (out/trade-overview.js)
_ACTIVE = []          # main 이 정규화해 둔 TARGETS 전체 (저장할 때 항목 정리·순서·메타에 사용)
_BLANK = []           # TARGETS 에서 id 만 적은 빈 카드 (검색하지 않고 제목 색만 가진 채 저장)
_ALL = []             # TARGETS 순서 그대로의 전체 (검색할 항목 + 빈 카드)


def load_data(path):
    """js 파일에서 'window.X = {...};' 의 JSON 부분을 읽는다. 파일이 없거나 읽지 못하면 빈 구조."""
    data = {"version": 1, "page": PAGE, "leagues": {}}
    if not os.path.exists(path):
        return data
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        start = text.index(JS_PREFIX) + len(JS_PREFIX)
        loaded = json.loads(text[start:].strip().rstrip(";"))
        if isinstance(loaded.get("leagues"), dict):
            data = loaded
    except (OSError, ValueError):
        print(f"  ⚠ 기존 {path} 를 읽지 못해 새로 만듭니다")
    return data


def build_i18n():
    """html 이 화폐·묶음 이름을 번역할 때 쓰는 표 (값이 있는 것만)."""
    return {sec: {k: v for k, v in KO[sec].items() if v} for sec in ("currency", "category")}


def entry_meta(t):
    return {"id": t["id"], "name": t["name"], "ko": ko_name(t),
            "category": t.get("category"), "categoryKo": ko_category(t.get("category")),
            "comment": (t.get("comment") or "").strip() or None}


def make_blank_entry(t):
    return {**entry_meta(t), "status": "blank", "link": None, "total": 0, "fetched": 0, "listings": [], "collectedAt": None}


def target_meta():
    return [entry_meta(t) for t in _ALL]


def sort_entries(entries):
    """TARGETS 에 있는 항목(빈 카드 포함)만, TARGETS 순서대로."""
    pos = {t["id"]: i for i, t in enumerate(_ALL)}
    return sorted((e for e in entries if e.get("id") in pos), key=lambda e: pos[e["id"]])


def save_data(path, data):
    data["version"] = 1
    data["page"] = PAGE
    data["generatedAt"] = utc_stamp()
    if _ACTIVE:
        data["targets"] = target_meta()
    data["i18n"] = build_i18n()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"                                   # html 이 읽는 도중에 깨진 파일을 보지 않도록 임시 파일 -> 교체
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"// {PAGE} 데이터: {os.path.basename(__file__)} 가 생성합니다. 직접 수정하지 마세요.\n")
        f.write(JS_PREFIX)
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write(";\n")
    os.replace(tmp, path)


def manual_rates(league):
    """RATES 에 적은 이 리그(또는 '*')의 환율을 출력용으로. 없으면 None."""
    r = RATES.get(league) or RATES.get("*")
    return {**r, "source": "manual"} if r else None


def store_entry(path, league, entry, order=None, collected=True):
    """같은 리그의 같은 id 항목만 갈아끼우고 나머지는 보존한다 (TARGETS 에서 사라진 항목은 정리).
    collected=False(수집 실패)면 리그의 collectedAt 을 갱신하지 않는다."""
    data = load_data(path)
    if order:
        data["order"] = list(order)
    lg = data["leagues"].setdefault(league, {"entries": [], "collectedAt": None})
    merged = {e["id"]: e for e in lg.get("entries", []) if isinstance(e, dict) and "id" in e}
    merged[entry["id"]] = entry
    lg["entries"] = sort_entries(merged.values()) if _ACTIVE else list(merged.values())
    if collected:
        lg["collectedAt"] = entry["collectedAt"]
    rates = manual_rates(league)
    if rates:
        lg["rates"] = rates
    save_data(path, data)


def store_blanks(path, league, order=None):
    """빈 카드 항목을 리그 데이터에 한 번에 저장한다 (같은 id 의 이전 빈 항목은 갈아끼움)."""
    if not _BLANK:
        return
    data = load_data(path)
    if order:
        data["order"] = list(order)
    lg = data["leagues"].setdefault(league, {"entries": [], "collectedAt": None})
    merged = {e["id"]: e for e in lg.get("entries", []) if isinstance(e, dict) and "id" in e}
    for t in _BLANK:
        merged[t["id"]] = make_blank_entry(t)
    lg["entries"] = sort_entries(merged.values())
    rates = manual_rates(league)
    if rates:
        lg["rates"] = rates
    save_data(path, data)


def store_failure(path, league, t, msg, order=None):
    """수집에 실패한 항목: 이전 값이 있으면 stale/error 를 붙여 유지하고, 없으면 status 'error' 항목을 만든다."""
    lg = load_data(path).get("leagues", {}).get(league) or {}
    old = next((e for e in lg.get("entries", []) if isinstance(e, dict) and e.get("id") == t["id"] and e.get("status") != "blank"), None)
    if old:
        entry = dict(old, **entry_meta(t), stale=True, error=msg)
    else:
        entry = {**entry_meta(t), "status": "error", "error": msg, "link": None, "total": None, "fetched": 0, "listings": []}
    store_entry(path, league, entry, order, collected=False)


def load_order(path):
    """시즌 리그 순서 ["최신", "직전"]."""
    order = load_data(path).get("order")
    return [x for x in order if isinstance(x, str)] if isinstance(order, list) else []


def merge_order(path, seasonal, has_latest, keep=KEEP_LEAGUES):
    """이번 실행에서 확인한 시즌 리그를 앞에 두고, 기존 순서의 나머지를 이어 붙여 keep 개까지 유지.
    latest 를 조회하지 않은 실행(previous 단독 등)은 기존 순서를 바꾸지 않는다."""
    old = load_order(path)
    if old and not has_latest:
        return old[:keep]
    return (seasonal + [x for x in old if x not in seasonal])[:keep]


# ---------------------------------------------------------------- 한글 표기
_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_MISSING = {"item": set(), "mods": set()}       # 이번 실행에서 만난, 한글 표기가 없는 문구


def load_ko_file(path):
    """trade-overview-ko.json 을 KO 에 병합한다 (파일 쪽이 우선). 없으면 조용히 건너뛴다."""
    if not path or not os.path.exists(path):
        if path and path != DEFAULT_KO_FILE:
            print(f"  ⚠ 한글 표기 파일 {path} 가 없습니다")
        return
    try:
        with open(path, encoding="utf-8") as f:
            extra = json.load(f)
        for sec in KO_SECTIONS:
            if isinstance(extra.get(sec), dict):
                KO[sec].update({k: v for k, v in extra[sec].items() if isinstance(v, str) and v})
        print(f"한글 표기 파일: {path}")
    except (OSError, ValueError, AttributeError) as e:
        print(f"  ⚠ 한글 표기 파일 {path} 를 읽지 못함 ({str(e)[:200]})")


def ko_name(t):
    return t.get("ko") or KO["name"].get(t["name"]) or None


def ko_category(cat):
    return (KO["category"].get(cat) or None) if cat else None


def ko_item(en):
    """베이스 타입 / 유니크 이름의 한글. 없으면 None 이고 누락 목록에 기록한다."""
    if not en:
        return None
    ko = KO["item"].get(en)
    if not ko:
        _MISSING["item"].add(en)
    return ko or None


def clean_markup(s):
    """PoE2 API 옵션 문구의 [키워드|표시문구] / [키워드] 표기를 표시문구로 바꾼다."""
    s = re.sub(r"\[([^\]|]*)\|([^\]]*)\]", r"\2", s)
    return re.sub(r"\[([^\]]*)\]", r"\1", s)


def ko_mod(text):
    """옵션 문구(영어)의 한글. 숫자를 #로 바꾼 템플릿으로 KO['mods'] 를 찾고, # 자리에 원문 숫자를 순서대로 채운다."""
    tpl = _DIGITS.sub("#", text)
    ko_tpl = KO["mods"].get(tpl)
    if not ko_tpl:
        _MISSING["mods"].add(tpl)
        return None
    nums = iter(_DIGITS.findall(text))
    return re.sub("#", lambda _m: next(nums, "#"), ko_tpl)


def missing_ko(currencies):
    """한글 표기가 없는 문구를 종류별로 모은다 (실행이 끝난 뒤 사용자에게 알려 줄 용도)."""
    miss = {"name": [t["name"] for t in _ACTIVE if not ko_name(t)],
            "category": sorted({t["category"] for t in _ACTIVE if t.get("category") and not ko_category(t["category"])}),
            "currency": sorted(c for c in currencies if c and not KO["currency"].get(c)),
            "item": sorted(_MISSING["item"]),
            "mods": sorted(_MISSING["mods"])}
    return {k: v for k, v in miss.items() if v}


# ---------------------------------------------------------------- 장비 종류(TARGETS) -> 검색 조건
def normalize_targets():
    """TARGETS 를 검사하고 id 를 채운 복사본을 반환한다 -> (검색할 항목, 빈 카드, TARGETS 순서 전체). 잘못된 항목이 있으면 이유를 알리고 종료."""
    out, blank, allt, seen = [], [], [], set()
    for i, raw in enumerate(TARGETS, 1):
        if str(raw.get("id", "")).strip() == "0":          # id 가 0 인 항목은 건너뜀 (수집·출력 안 함, 검사도 안 함)
            continue
        t = dict(raw)
        if not t.get("name") and not t.get("url") and not t.get("query"):   # id 만 있는 빈 카드
            t["id"] = str(t.get("id") or "").strip()
            if not t["id"]:
                sys.exit(f"TARGETS {i}번째 항목: name / url / query 가 모두 없으면 빈 카드로 보는데, 그러려면 id 가 필요합니다")
            if t["id"] in seen:
                sys.exit(f"TARGETS 의 id 가 겹칩니다: {t['id']}")
            seen.add(t["id"])
            t["name"] = ""
            blank.append(t)
            allt.append(t)
            continue
        if not t.get("name"):
            sys.exit(f"TARGETS {i}번째 항목에 name 이 없습니다")
        t["id"] = t.get("id") or slug(t["name"])
        if not t["id"]:
            sys.exit(f"TARGETS '{t['name']}' 의 id 를 만들 수 없습니다. id 를 영문으로 직접 적어 주세요")
        if t["id"] in seen:
            sys.exit(f"TARGETS 의 id 가 겹칩니다: {t['id']}")
        seen.add(t["id"])
        if bool(t.get("url")) == bool(t.get("query")):
            sys.exit(f"TARGETS '{t['id']}': url 과 query 중 정확히 하나만 적어 주세요")
        limit = t.get("limit", LIMIT)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            sys.exit(f"TARGETS '{t['id']}': limit 은 1 이상의 정수여야 합니다")
        t["limit"] = limit
        if t.get("comment") is not None and not isinstance(t["comment"], str):
            sys.exit(f"TARGETS '{t['id']}': comment 는 문자열이어야 합니다")
        if t.get("url"):
            try:
                parse_trade_url(t["url"])
            except ValueError as e:
                sys.exit(f"TARGETS '{t['id']}': {e}")
        out.append(t)
        allt.append(t)
    return out, blank, allt


_URL_PATH = re.compile(r"/trade2/search/(?:poe2/)?(?P<league>[^/?#]+)(?:/(?P<id>[^/?#]+))?")


def parse_trade_url(url):
    """경매장 링크 -> (링크의 리그, 저장된 검색 id 또는 None, 링크 안의 검색 조건 또는 None).
    지원: .../trade2/search/poe2/<리그>/<id>   .../trade2/search/poe2/<리그>?q={...}   .../trade2/search/poe2/<리그>/H4sI...(압축)"""
    u = urlparse(str(url).strip())
    m = _URL_PATH.search(u.path)
    if not m:
        raise ValueError(f"PoE2 경매장 링크가 아닙니다 (…/trade2/search/poe2/<리그>/<id> 형식): {url}")
    q = None
    qs = parse_qs(u.query)
    if qs.get("q"):
        try:
            q = json.loads(qs["q"][0])
        except ValueError:
            raise ValueError(f"링크의 q= 값이 JSON 이 아닙니다: {url}")
        if not isinstance(q, dict):
            raise ValueError(f"링크의 q= 값이 검색 조건이 아닙니다: {url}")
    sid = m.group("id")
    if q is None and sid and sid.startswith("H4sI"):    # 검색 조건이 링크 안에 gzip+base64url 로 들어 있는 형식 (서버 조회 불필요)
        try:
            q = json.loads(gzip.decompress(base64.urlsafe_b64decode(sid + "=" * (-len(sid) % 4))))
        except (ValueError, OSError, EOFError):
            raise ValueError(f"링크에 들어 있는 압축된 검색 조건을 풀지 못했습니다: {url}")
        if not isinstance(q, dict):
            raise ValueError(f"링크에 들어 있는 검색 조건 형식이 이상합니다: {url}")
        sid = None
    if q is None and not sid:
        raise ValueError(f"링크에 저장된 검색 id 도 q= 도 없습니다: {url}")
    return unquote(m.group("league")), sid, q


def load_query_cache():
    try:
        with open(QUERY_CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def save_query_cache(cache):
    os.makedirs(os.path.dirname(QUERY_CACHE_FILE), exist_ok=True)
    with open(QUERY_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def needs_query_fetch(t, cache):
    """이 항목이 저장된 검색 조건을 서버에서 읽어 와야 하는지 (링크이고, 링크 안에 조건이 없고 검색 id 만 있고, 캐시에 없을 때)."""
    if not t.get("url"):
        return False
    _lg, sid, q = parse_trade_url(t["url"])
    return q is None and sid not in cache


def _as_body(q):
    """{"query": {...}} 전체이든 query 부분만이든 요청 본문 형태로 맞춘다."""
    q = copy.deepcopy(q)
    return q if isinstance(q.get("query"), dict) else {"query": q}


def resolve_body(t, cache):
    """항목 -> trade2 검색 요청 본문. 가격 오름차순 정렬로 고정하고, FORCE_SECURABLE 이면 Instant Buyout 로 고정한다.
    저장된 검색 링크는 GET /api/trade2/search/poe2/<리그>/<id> 의 응답 query 를 쓰고 캐시한다 (조건은 리그와 무관하게 다른 리그에도 쓴다)."""
    if t.get("query"):
        body = _as_body(t["query"])
    else:
        lg, sid, q = parse_trade_url(t["url"])
        if q is not None:
            body = _as_body(q)
        elif sid in cache:
            body = {"query": copy.deepcopy(cache[sid])}
        else:
            s = call("GET", f"{BASE}/api/trade2/search/poe2/{quote(lg, safe='')}/{sid}")
            found = s.get("query") if isinstance(s, dict) else None
            if not isinstance(found, dict):
                raise RuntimeError(f"링크 {t['url']} 에서 검색 조건을 읽지 못했습니다. 링크가 만료됐다면 경매장에서 다시 검색한 링크를 쓰거나 "
                                   f"'?q=' 링크 / query 설정으로 바꿔 주세요")
            cache[sid] = found
            save_query_cache(cache)
            body = {"query": copy.deepcopy(found)}
    body["sort"] = {"price": "asc"}
    if FORCE_SECURABLE:
        body["query"]["status"] = {"option": "securable"}
    return body


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
    목록 조회가 실패하면 저장된 데이터의 리그 순서 + Standard 로 대체."""
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
    """리그 목록 조회가 실패했을 때의 대체값: 저장된 시즌 리그 순서(order)의 idx 번째 (0=최신, 1=직전).
    order 가 없으면 Standard 아닌 리그를 수집 시각이 최근인 순으로 놓고 idx 번째."""
    data = load_data(path)
    leagues = data.get("leagues") or {}
    order = [x for x in (data.get("order") or []) if isinstance(x, str) and x in leagues]
    if len(order) > idx:
        return order[idx]
    found = sorted(((str(v.get("collectedAt") or ""), k) for k, v in leagues.items() if k.lower() != "standard"), reverse=True)
    return found[idx][1] if len(found) > idx else None


def hours_since_collected(path, league):
    """이 리그를 마지막으로 수집한 뒤 지난 시간(시). 기록이 없거나 시각 형식을 읽지 못하면 None (= 수집해야 함)."""
    try:
        ts = load_data(path)["leagues"][league]["collectedAt"]
        last = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError, AttributeError):
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


# ---------------------------------------------------------------- 검색 + 매물 정규화
MOD_KEYS = [
    ("implicit", "implicitMods"),
    ("explicit", "explicitMods"),
    ("rune", "runeMods"),
    ("enchant", "enchantMods"),
    ("fractured", "fracturedMods"),
    ("desecrated", "desecratedMods"),
]


def mod_entry(line):
    """옵션 한 줄 -> {"en", ("ko"), ("id", "tier", "affix")}. 문구를 찾지 못하면 None.
    API 는 한 줄을 문자열로 주기도 하고, 객체 {"description", "hash", "mods": [{"name", "tier", "level", "magnitudes"}]} 로 주기도 한다.
    (객체를 str() 로 바꾸면 clean_markup 이 그 안의 [ ] 까지 망가뜨리므로, 문구(description)만 꺼내 clean_markup 에 넣는다.)
      id    : 옵션 고유 id (hash)       tier : 티어 (예: "S1")       affix : 접두/접미 이름 (예: "of Battle")"""
    meta = {}
    if isinstance(line, dict):
        text = line.get("description") or line.get("text")
        if line.get("hash"):
            meta["id"] = line["hash"]
        sub = line.get("mods")
        for x in (sub if isinstance(sub, list) else [sub]):
            if isinstance(x, dict):
                if x.get("tier") and "tier" not in meta:
                    meta["tier"] = x["tier"]
                if x.get("name") and "affix" not in meta:
                    meta["affix"] = x["name"]
    else:
        text = line
    if not isinstance(text, str) or not text.strip():
        return None
    en = clean_markup(text.strip())
    m = {"en": en}
    ko = ko_mod(en)
    if ko:
        m["ko"] = ko
    m.update(meta)
    return m


def norm_item(it):
    """fetch 응답의 item -> html 이 쓰는 간단한 형태. 한글 표기가 있으면 *Ko / ko 를 붙인다."""
    base = it.get("baseType") or it.get("typeLine") or ""
    rarity = it.get("rarity")
    o = {"base": base}
    k = ko_item(base)
    if k:
        o["baseKo"] = k
    if rarity:
        o["rarity"] = rarity
    nm = (it.get("name") or "").strip()
    if nm:
        o["name"] = nm
        if rarity == "Unique":                      # 레어/매직의 이름은 무작위 생성이라 번역 대상이 아님
            k = ko_item(nm)
            if k:
                o["nameKo"] = k
    if it.get("ilvl") is not None:
        o["ilvl"] = it["ilvl"]
    if it.get("corrupted"):
        o["corrupted"] = True
    mods = {}
    for out_key, api_key in MOD_KEYS:
        row = [m for m in (mod_entry(x) for x in (it.get(api_key) or [])) if m]
        if row:
            mods[out_key] = row
    if mods:
        o["mods"] = mods
    return o


def norm_listing(r):
    """fetch 응답 한 건 -> {"id", "a", "c", "indexed", "seller", "item"}. 가격(금액·통화)을 알 수 없는 매물은 None."""
    lst = r.get("listing") or {}
    price = lst.get("price") or {}
    if price.get("amount") is None or not price.get("currency"):
        return None
    return {
        "id": r.get("id"),
        "a": price["amount"],
        "c": price["currency"],                      # exalted / chaos / divine / ...
        "indexed": lst.get("indexed"),               # 등록(마지막 갱신) 시각, ISO 8601
        "seller": (lst.get("account") or {}).get("name"),
        "item": norm_item(r.get("item") or {}),
    }


def fetch_calls(limit):
    """limit 개를 가져오는 데 필요한 fetch 요청 수 (FETCH_MAX 개씩 나눠서)."""
    return -(-limit // FETCH_MAX)


def search_listings(league, body, limit):
    """(검색 id, 총 매물 수, 정규화한 최저가 매물 리스트) 반환. 요청 = 검색 1회 + fetch fetch_calls(limit)회."""
    s = call("POST", f"{BASE}/api/trade2/search/poe2/{quote(league, safe='')}", json=body)
    sid = s.get("id")
    total = s.get("total", 0)
    ids = (s.get("result") or [])[:limit]
    rows = []
    for i in range(0, len(ids), FETCH_MAX):          # fetch 는 한 번에 최대 FETCH_MAX 개 -> 가격순 그대로 나눠서 가져온다
        chunk = ids[i:i + FETCH_MAX]
        f = call("GET", f"{BASE}/api/trade2/fetch/{','.join(chunk)}", params={"query": sid, "realm": "poe2"})
        rows.extend(r for r in (f.get("result") or []) if r)
    listings = [x for x in (norm_listing(r) for r in rows) if x]
    return sid, total, listings


# ---------------------------------------------------------------- 출력 / 항목 만들기
def show(t, entry):
    print(f"\n  {t['name']}  (전체 {entry['total']}건, {entry['fetched']}건 조회)")
    if not entry["listings"]:
        print("    결과 없음")
    for i, l in enumerate(entry["listings"], 1):
        it = l["item"]
        title = f"{it.get('name', '')} {it.get('base', '')}".strip()
        print(f"    {i:2}. {l['a']} {l['c']}  | ilvl {it.get('ilvl')} | {title} | {l['seller'] or '?'} | {l['indexed'] or '-'}")


def make_entry(t, league, search_id, total, listings):
    return {
        **entry_meta(t),
        "status": "ok" if listings else "empty",
        "link": f"{BASE}/trade2/search/poe2/{quote(league, safe='')}/{search_id}" if search_id else None,
        "total": total,
        "fetched": len(listings),
        "listings": listings,
        "collectedAt": utc_stamp(),
    }


def attach_fair(entry, listings, t, league):
    """estimate_market() 훅을 부른다. 값이 있으면 entry['fair'] 로 저장. 훅이 예외를 내도 수집한 매물은 보존한다."""
    try:
        fair = estimate_market(listings, t, league)
    except Exception as e:
        print(f"  ⚠ estimate_market 오류 ({e!r}) -> fair 없이 저장")
        return
    if fair is not None:
        entry["fair"] = fair


def collect(league, todo, cache, out, order, seen_currencies):
    """리그 하나를 수집해 항목마다 저장하고 실패한 항목 id 목록을 반환."""
    failed = []
    store_blanks(out, league, order)                          # 빈 카드 항목 (검색 없음)
    for t in todo:
        print(f"\n=== {t['name']} ({t['id']}) ===")
        try:
            body = resolve_body(t, cache)
            search_id, total, listings = search_listings(league, body, t["limit"])
        except (RuntimeError, ValueError, requests.RequestException) as e:
            msg = str(e)[:300]
            print(f"  ✗ {t['name']} 조회 실패: {msg}")
            failed.append(t["id"])
            store_failure(out, league, t, msg, order)         # 이전 값은 stale 로 유지, 없으면 error 항목
            continue
        entry = make_entry(t, league, search_id, total, listings)
        attach_fair(entry, listings, t, league)
        show(t, entry)
        seen_currencies.update(l["c"] for l in listings)
        store_entry(out, league, entry, order)                # 항목마다 저장 -> 중간에 끊겨도 진행분 보존
        print(f"  -> {out} 저장 ({league} / {t['id']})")
    return failed


def dry_run(targets, cache, league_arg):
    """네트워크 없이 각 항목이 어떤 검색을 하게 되는지 보여 준다 (링크 해석 확인용)."""
    print(f"[dry-run] 리그 지정: {league_arg}  (latest/previous 는 실행할 때 거래소 목록에서 확인합니다)")
    print(f"[dry-run] 빈 카드 {len(_BLANK)}개 (번호 {', '.join(t['id'] for t in _BLANK) or '-'}) 는 검색 없이 제목 색만 저장합니다")
    for t in targets:
        print(f"\n- {t['id']}  ({t['name']})  limit={t['limit']}  요청: 검색 1 + fetch {fetch_calls(t['limit'])} (리그마다)")
        if t.get("query"):
            print("  입력: query (직접 적은 검색 설정)")
        else:
            lg, sid, q = parse_trade_url(t["url"])
            if q is not None:
                print(f"  입력: 링크 (검색 조건이 링크 안에 있음 -> 서버 조회 없음, 링크의 리그 '{lg}' 는 조건 읽기용)")
            else:
                state = "캐시에 있음" if sid in cache else "서버에서 한 번 읽어 옴(GET 1회) 후 캐시"
                print(f"  입력: 저장된 검색 링크 id={sid} -> {state}")
        if needs_query_fetch(t, cache):
            print("  검색 조건: (서버에서 읽어 와야 해서 dry-run 에서는 표시하지 않음)")
            continue
        body = resolve_body(t, cache)
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        print(f"  검색 조건: {text[:700]}{' ...' if len(text) > 700 else ''}")


def main():
    global _ACTIVE, _BLANK, _ALL
    ap = argparse.ArgumentParser(description="PoE2 trade2 장비 종류별 경매장 매물 수집 (trade-overview.html 용 데이터)")
    ap.add_argument("target", nargs="?", default="all",
                    help='TARGETS 의 id 또는 이름, 또는 "all" = 전체 (기본: %(default)s)')
    ap.add_argument("--league", default="latest",
                    help="latest | previous(직전 리그) | standard | all(모든 소프트코어 리그) | 리그 이름 직접 지정. 쉼표로 여러 개. "
                         "'이름:시간' 으로 최소 수집 간격 지정 (예: latest,previous:6,standard:24 / all:6) (기본: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="결과 저장 경로 (기본: 스크립트 옆 out/trade-overview.js, 기존 파일이 있으면 병합)")
    ap.add_argument("--ko", default=DEFAULT_KO_FILE,
                    help="한글 표기 json 경로 (기본: 스크립트 옆 trade-overview-ko.json, 없으면 무시). py 안의 KO 와 같은 구조")
    ap.add_argument("--dry-run", action="store_true", help="네트워크 요청 없이 어떤 검색을 할지만 출력")
    args = ap.parse_args()

    load_ko_file(args.ko)
    _ACTIVE, _BLANK, _ALL = normalize_targets()
    if not _ACTIVE:
        sys.exit("TARGETS 가 비어 있습니다. 이 파일 위쪽의 TARGETS 에 경매장 링크나 검색 설정을 추가하세요")
    if args.target.lower() == "all":
        targets = list(_ACTIVE)
    else:
        key = args.target.strip().lower()
        targets = [t for t in _ACTIVE if key in (t["id"].lower(), t["name"].lower())]
        if not targets:
            sys.exit(f"알 수 없는 항목: {args.target}\n사용 가능: {', '.join(t['id'] for t in _ACTIVE)}")

    cache = load_query_cache()
    if args.dry_run:
        dry_run(targets, cache, args.league)
        return

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

    n_query = sum(1 for t in targets if needs_query_fetch(t, cache))      # 저장된 검색 조건을 읽는 GET (한 번만, 이후 캐시)
    n_search = len(leagues) * len(targets) + n_query
    n_fetch = len(leagues) * sum(fetch_calls(t["limit"]) for t in targets)
    print(f"리그: {', '.join(leagues)} / 장비 종류 {len(targets)}종")
    est = estimate_seconds(n_search, n_fetch)
    print(f"요청 최대 {n_search + n_fetch}회 (검색 {n_search} + fetch {n_fetch}) · 레이트리밋 기준 최단 약 {est / 60:.1f}분")

    started = time.monotonic()
    failed, seen_currencies = [], set()
    for league in leagues:
        print(f"\n######## 리그: {league} ########")
        failed += [f"{league}/{i}" for i in collect(league, targets, cache, args.out, order, seen_currencies)]
    print(f"\n완료: 요청 {limiter.count}회, 소요 {(time.monotonic() - started) / 60:.1f}분"
          + (f", 실패 {len(failed)}건: {', '.join(failed)}" if failed else ""))

    miss = missing_ko(seen_currencies)
    if miss:
        print("\n한글 표기가 없어 영어로 보이는 문구 (KO 또는 trade-overview-ko.json 에 추가하세요):")
        for sec, names in miss.items():
            shown = ", ".join(names[:12]) + (f" ... 외 {len(names) - 12}개" if len(names) > 12 else "")
            print(f"  {sec} ({len(names)}개): {shown}")
        os.makedirs(os.path.dirname(MISSING_KO_FILE), exist_ok=True)
        with open(MISSING_KO_FILE, "w", encoding="utf-8") as f:
            json.dump({sec: {n: "" for n in names} for sec, names in miss.items()}, f, ensure_ascii=False, indent=1)
        print(f"  -> 전체 목록: {MISSING_KO_FILE} (값을 채워 trade-overview-ko.json 에 합치면 됩니다)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
