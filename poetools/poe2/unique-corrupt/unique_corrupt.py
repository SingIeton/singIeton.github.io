"""PoE2 고유 장비 타락 플리핑 데이터 수집 (결과: uniques/장비명.js + uniques/index.js 목록 -> unique-corrupt.html 이 읽음).

타락 결과 4종은 각 25% (poe2wiki 기준). 고유 장비 하나당 아래를 계산해 window.UC_DATA.push({...}) 형식으로 저장한다.
  1) 변화 없음   : 검색 (인챈트 없음: 인챈트 옵션 전체를 NOT 그룹으로 제외). 검색 실패 시 베이스 가격 x NO_CHANGE_RATIO 로 대체
  2) 수치 변동   : 굴린 뒤 나올 수 있는 값(예: -3/-4/-5)별 확률을 계산(배율 0.78~1.22, 0.01 단위)하고, 값별 가격은 검색(실패 시 ratio) 또는 '변화 없음' 가치로 정함
  3) 바알 인챈트 : 인챈트별로 (검색) 또는 (베이스 x ratio). 검색으로 가격을 못 구하면 ratio 로 대체
  4) 소켓 추가   : 검색 (socket_search 가 None 이면 장신구처럼 변화 없음으로 합산)
가격 판정(최저가, 이상치 제외)·레이트리밋·poe.ninja 환율을 사용한다. 가격 단위는 Divine.

실행:
  python unique_corrupt.py                      # UNIQUES 전체, 최신 리그
  python unique_corrupt.py "Viper Cap"          # 하나만
  python unique_corrupt.py --league "리그이름"   # latest | previous | standard | 이름
  python unique_corrupt.py --out other_dir      # 저장 폴더 (기본: 스크립트 옆 uniques/)
  (실행하면 캐시 사용 여부를 묻는다: 1 = yes, 2 = no(전체 검색). --use-cache 를 주면 묻지 않고 사용)
  python unique_corrupt.py --use-cache          # 같은 리그로 저장된 js 의 검색 결과 중 검색 조건이 같은 것은 재사용 (거래소 검색 생략)
"""
import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from urllib.parse import quote

import requests

# ================================================================ 설정
BASE = "https://www.pathofexile.com"
POESESSID = ""                          # 선택
UA = "poe2-price-test/0.1 (contact: augustusminu@hotmail.com)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uniques")

NO_CHANGE_RATIO = 0.5        # X: '변화 없음' 검색으로 가격을 못 구했을 때만 쓰는 대체값 = 베이스 가격 x X
ROUND_MODE = "round"         # 수치 변동 반올림: "round" = 일반 반올림 / "trunc" = trunc(값+0.5) (wiki 가설. 음수 옵션이 0 쪽으로 쏠려 -5 같은 값은 나오지 않음)
VAAL_COST_DIV = None         # 바알 오브 가격(Divine). None 이면 poe.ninja 에서 읽음
QUALITY_MIN = 20             # 타락(corrupted) 검색 전체에 거는 최소 퀄리티 기본값. None 이면 퀄리티 조건 없음. 검색 명세에 "quality_min" 을 넣으면 그 검색만 덮어씀
CORRUPT_FILTERS = {          # 타락(corrupted) 검색 전체에 추가하는 misc 필터. 키 = 거래소 필터 id, 값 = 옵션 (Twice Corrupted = No, Sanctified = No)
    "twice_corrupted": {"option": "false"},
    "sanctified": {"option": "false"},
}
OUTCOME_P = 0.25             # 타락 결과 1종의 확률

TOP_N = 10                   # 검색당 가져올 최저가 매물 수 (fetch 1회)
FETCH_MAX = 10


def M(stat, min=None, max=None, id=None):
    """검색 옵션 하나. stat 은 거래소 옵션 문구(예: '# to maximum Life'), 스탯 id 를 알면 id 로 직접 지정 가능."""
    return {"stat": stat, "min": min, "max": max, "id": id}


# 검색 명세: corrupted(True/False), sockets=(min, max) 증강 가능 소켓(None=제한 없음), mods=[M(...)]
# 바알 인챈트 정보: 장비 부위(slot)별 고정 목록. en = 영문명, ko = 한글명, range = 수치 범위, mod = 거래소 인챈트 옵션 문구.
# 어떤 인챈트를 검색/ratio 로 평가할지와 ratio 값은 개별 장비의 "enchants" 에서 설정한다.
ENCHANTS = {
    "helmet": [
        {"en": "Increased Energy Shield",         "ko": "에너지 보호막 % 증가",    "range": "15—25",  "mod": "#% increased Energy Shield"},
        {"en": "Reduced Attribute Requirements",  "ko": "능력치 요구사항 감소",     "range": "10—20",  "mod": "#% increased Attribute Requirements"},
        {"en": "Maximum Cold Resistance",         "ko": "냉기 저항 최대치 +%",     "range": "1—3",    "mod": "+#% to Maximum Cold Resistance"},
        {"en": "Spirit",                          "ko": "정신력",                "range": "20—30",  "mod": "# to Spirit"},
        {"en": "Maximum Power Charges +1",        "ko": "권능 충전 최대치 +1",     "range": "1",      "mod": "# to Maximum Power Charges"},
        {"en": "Accuracy Rating",                 "ko": "정확도",                "range": "50—100", "mod": "+# to Accuracy Rating"},
        {"en": "Life Regeneration rate",          "ko": "생명력 재생 속도 % 증가",   "range": "15—25",  "mod": "#% increased Life Regeneration rate"},
        {"en": "Mana Regeneration Rate",          "ko": "마나 재생 속도 % 증가",    "range": "20—30",  "mod": "#% increased Mana Regeneration Rate"},
        {"en": "Level of all Minion Skills +1",   "ko": "모든 소환수 스켈 레벨 +1",  "range": "1",      "mod": "# to Level of all Minion Skills"},
    ],
    "shield": [
        {"en": "Increased Armour",                "ko": "방어도 % 증가",           "range": "15—25",  "mod": "#% increased Armour (Local)"},
        {"en": "Reduced Attribute Requirements",  "ko": "능력치 요구사항 감소",     "range": "10—20",  "mod": "#% increased Attribute Requirements"},
        {"en": "Increased Thorns Damage",         "ko": "가시 피해 % 증가",        "range": "40—50",  "mod": "#% increased Thorns damage"},
        {"en": "Increased Block Chance",          "ko": "막기 확률 % 증가",        "range": "10—15",  "mod": "#% increased Block chance"},
        {"en": "Maximum Block Chance",            "ko": "최대 막기 확률 +%",       "range": "3",      "mod": "+#% to maximum Block chance"},
        {"en": "Life on Block",                   "ko": "막아낼 시 생명력 획득",    "range": "20—25",  "mod": "# Life gained when you Block"},
        {"en": "Mana on Block",                   "ko": "막아낼 시 마나 획득",      "range": "10—15",  "mod": "# Mana gained when you Block"},
    ],
}


def enchants_of(u):
    """장비의 enchants 설정에 ENCHANTS[slot] 의 en/ko/range/mod 를 합쳐서 반환."""
    if u.get("slot") not in ENCHANTS:
        sys.exit(f"{u['name']}: slot 이 없거나 ENCHANTS 에 없는 부위입니다 (사용 가능: {', '.join(ENCHANTS)})")
    base = {e["en"]: e for e in ENCHANTS[u["slot"]]}
    out = []
    for c in u["enchants"]:
        if c["en"] not in base:
            sys.exit(f"{u['name']}: ENCHANTS['{u['slot']}'] 에 없는 인챈트입니다: {c['en']}")
        e = {**base[c["en"]], **c}
        if e.get("search") and not e.get("mod"):
            sys.exit(f"{u['name']}: '{e['en']}' 은 검색하도록 설정됐지만 ENCHANTS 에 mod 가 없습니다")
        if not e.get("search") and e.get("ratio") is None:
            sys.exit(f"{u['name']}: '{e['en']}' 은 search 도 ratio 도 설정되지 않았습니다")
        out.append(e)
    return out


def no_enchant_mods(u):
    """'변화 없음' 검색용: 부위의 인챈트 옵션 전체를 NOT 그룹(하나도 없음)으로 제외. mod 가 있는 인챈트만 포함."""
    return [{**M(e["mod"]), "group": "enchant"} for e in ENCHANTS[u["slot"]] if e.get("mod")]


SVALINN_ENCHANTS = [
    {"en": "Increased Armour",               "ratio": 1.00},
    {"en": "Reduced Attribute Requirements", "ratio": 1.00},
    {"en": "Increased Thorns Damage",        "ratio": 1.00},
    {"en": "Increased Block Chance",         "ratio": 1.00},
    {"en": "Maximum Block Chance",           "ratio": 1.00},
    {"en": "Life on Block",                  "ratio": 1.00},
    {"en": "Mana on Block",                  "ratio": 1.00},
]

UNIQUES = [
    {
        "name": "Constricting Command",      # 거래소 검색에 쓰는 이름
        "file": "Constricting_Command_Oversocket",   # 저장 파일명 (uniques/<file>.js). 없으면 name 사용
        "title": "Constricting Command (Oversocket)",   # html 에 표시할 이름 (없으면 name)
        "ko": "목 죄이는 명령 (오버소켓)",              # 한글 이름 (비우면 영문만 표시)
        "type": "Viper Cap",             # 베이스 타입(선택). 이름만으로 검색이 안 되면 지정
        "slot": "helmet",                # 장비 부위 -> 바알 인챈트 목록은 파일 상단 ENCHANTS[slot] 사용
        "base": "",                      # html 목록에 작게 표시할 문구 (영문 기본, 한글은 "base_ko" 로 추가 가능)
        # 모든 표시 문구는 영문이 기본(label/name/base). 한글 번역이 있을 때만 "ko"(base 는 "base_ko") 를 추가 -> 화면이 한글일 때 사용, 없으면 영문 그대로
        # root 노드(베이스) 아래에 표시할 문구. 직접 수정. 한글은 root_text_ko (비우면 영문 표시)
        "root_text": ["Sockets ≥2", "Surrounded =-4"],
        "root_text_ko": ["소켓 = 2", "포위 수 = -4"],
        # 기본 검색 값: 아래 모든 검색(base/enchant/socket/reroll)이 이 값을 바탕으로 한다.
        #   각 검색에는 기본값과 다른 항목만 적는다. corrupted / sockets 는 적으면 덮어쓰고,
        #   mods 는 같은 옵션(stat)이면 해당 옵션만 교체, 없는 옵션은 추가한다 (기본 옵션은 그대로 유지).
        "default_search": {"corrupted": True, "sockets": (2, 2), "mods": [
            M("# to maximum Life", min=110),
            M("# to all Attributes"),
            M("# Life Regeneration per second"),
            M("Require # additional enemies to be Surrounded", min=-4, max=-4),
        ]},
        # [0] 베이스 구매가
        "base_search": {"corrupted": False, "sockets": (2, None)},
        # [2] 바알 인챈트 검색 (타락 + 소켓 변화 없음) = 기본 검색 그대로
        "enchant_search": {},
        # [3] 소켓 +1 검색. 장신구처럼 소켓이 안 늘어나면 None
        "socket_search": {"sockets": (3, None), "mods": [
            M("# to maximum Life", min=108),
        ]},
        # 바알 인챈트 설정 (en = 상단 ENCHANTS[slot] 의 영문명). 이 목록의 인챈트가 타락 결과로 계산된다.
        #   "search": True -> 거래소에서 해당 인챈트 매물 검색. 검색 실패(정상 매물 < MIN_LISTINGS)일 때만 ratio 사용: ratio 가 있으면 베이스 가격 x ratio, 없으면 변화 없음 가치
        #   "ratio": 베이스 가격 x ratio 로 평가 (search 가 없을 때 사용). "w" = 확률 가중치(선택, 기본 1)
        "enchants": [
            {"en": "Increased Energy Shield",        "ratio": 0.85},
            {"en": "Reduced Attribute Requirements", "ratio": 0.70},
            {"en": "Maximum Cold Resistance",        "ratio": 1.15},
            {"en": "Spirit",                         "search": True, "ratio": 1.00},
            {"en": "Maximum Power Charges +1",       "search": True, "ratio": 1.00},
            {"en": "Accuracy Rating",                "ratio": 1.10},
            {"en": "Life Regeneration rate",         "ratio": 1.05},
            {"en": "Mana Regeneration Rate",         "ratio": 0.85},
            {"en": "Level of all Minion Skills +1",  "search": True, "ratio": 1.00},
        ],
        # [1] 수치 변동. roll = 구매하는 베이스의 해당 옵션 수치. 굴린 뒤 나올 수 있는 값(-3, -4, -5)이 각각 동등한 결과이고, 확률은 roll 에서 계산한다.
        #   outcomes 에는 나올 수 있는 값을 전부 적어야 한다 (빠지면 오류).
        #   "search" 가 있으면 거래소 검색으로 가격을 구하고, 없으면 '변화 없음' 검색 가격을 그대로 쓴다 (값이 그대로인 경우).
        #   "suffix" / "suffix_ko" (선택): 화면 라벨 뒤에 붙는 문구 (예: " 이상"). "ratio" (선택): 검색 실패(정상 매물 < MIN_LISTINGS)일 때 베이스 가격 x ratio 로 대체. 없으면 변화 없음 가치로 대체.
        "reroll": {
            "label": "Surround", "ko": "포위", "roll": -4,
            "outcomes": [
                {"value": -5, "suffix": " or lower", "suffix_ko": " 이상", "ratio": 8.0, "search": {"mods": [
                    M("# to maximum Life", min=105),
                    M("Require # additional enemies to be Surrounded", max=-5),
                ]}},
                {"value": -4, "suffix": "", "suffix_ko": "", "ratio": 1.0, "search": {"mods": [
                    M("# to maximum Life", min=105),
                    M("Require # additional enemies to be Surrounded", min=-4, max=-4),
                ]}},
                {"value": -3, "suffix": " or higher", "suffix_ko": " 이하", "ratio": 1.0, "search": {"mods": [
                    M("# to maximum Life", min=105),
                    M("Require # additional enemies to be Surrounded", min=-3),
                ]}},
            ],
        },
    },
    {
        "name": "Constricting Command",
        "file": "Constricting_Command",
        "ko": "목 죄이는 명령",
        "type": "Viper Cap",
        "slot": "helmet",
        "base": "",
        "root_text": ["Sockets =1", "Surrounded =-4"],
        "root_text_ko": ["소켓 = 1", "포위 수 = -4"],
        "default_search": {"corrupted": True, "sockets": (1, 1), "mods": [
            M("# to maximum Life", min=110),
            M("# to all Attributes"),
            M("# Life Regeneration per second"),
            M("Require # additional enemies to be Surrounded", min=-4, max=-4),
        ]},
        # [0] 베이스 구매가 (미타락, 소켓 1)
        "base_search": {"corrupted": False, "sockets": None},   # 최대 소켓이 1 이므로 소켓 조건 없이 검색
        # [2] 바알 인챈트 검색 = 기본 검색 그대로
        "enchant_search": {},
        # [3] 소켓 +1 검색 (1 -> 2소켓)
        "socket_search": {"sockets": (2, None), "mods": [
            M("# to maximum Life", min=108),
        ]},
        "enchants": [
            {"en": "Increased Energy Shield",        "ratio": 0.85},
            {"en": "Reduced Attribute Requirements", "ratio": 0.70},
            {"en": "Maximum Cold Resistance",        "ratio": 1.15},
            {"en": "Spirit",                         "search": True, "ratio": 1.00},
            {"en": "Maximum Power Charges +1",       "search": True, "ratio": 1.00},
            {"en": "Accuracy Rating",                "ratio": 1.10},
            {"en": "Life Regeneration rate",         "ratio": 1.05},
            {"en": "Mana Regeneration Rate",         "ratio": 0.85},
            {"en": "Level of all Minion Skills +1",  "search": True, "ratio": 1.00},
        ],
        "reroll": {
            "label": "Surround", "ko": "포위", "roll": -4,
            "outcomes": [
                {"value": -5, "suffix": " or lower", "suffix_ko": " 이상", "ratio": 8.0, "search": {"mods": [
                    M("# to maximum Life", min=105),
                    M("Require # additional enemies to be Surrounded", max=-5),
                ]}},
                {"value": -4, "suffix": "", "suffix_ko": "", "ratio": 1.0, "search": {"mods": [
                    M("# to maximum Life", min=105),
                    M("Require # additional enemies to be Surrounded", min=-4, max=-4),
                ]}},
                {"value": -3, "suffix": " or higher", "suffix_ko": " 이하", "ratio": 1.0, "search": {"mods": [
                    M("# to maximum Life", min=105),
                    M("Require # additional enemies to be Surrounded", min=-3),
                ]}},
            ],
        },
    },
    {
        "name": "Svalinn",
        "file": "Svalinn_0-1",
        "title": "Svalinn (0~1)",
        "ko": "스발린 (0~1)",
        "type": "Crucible Tower Shield",
        "slot": "shield",
        "base": "",
        "root_text": ["Sockets =1", "Armour ≥250%", "Blocked Hits ≤1%"],
        "root_text_ko": ["소켓 = 1", "방어도 ≥ 250%", "막기 피격 피해 ≤ 1%"],
        # 0~1 은 바알 수치 변동을 해도 0 은 0, 1 은 1 로 그대로 -> 수치 변동 = 변화 없음과 동일 취급
        "default_search": {"corrupted": True, "sockets": (1, 1), "mods": [
            M("#% increased Armour (Local)", min=250),
            M("You take #% of damage from Blocked Hits", max=1),
        ]},
        "base_search": {"corrupted": False, "sockets": None},   # 최대 소켓이 1 이므로 소켓 조건 없이 검색
        "enchant_search": {},
        "socket_search": {"sockets": (2, None)},
        "enchants": SVALINN_ENCHANTS,
        "reroll": {
            "label": "Blocked Dmg", "ko": "막기 피해", "roll": 1,
            "outcomes": [
                {"value": 1, "text": "1", "text_ko": "1"},      # search 없음 = 변화 없음 가격
            ],
        },
    },
    {
        "name": "Svalinn",
        "file": "Svalinn_2-5",
        "title": "Svalinn (2~5)",
        "ko": "스발린 (2~5)",
        "type": "Crucible Tower Shield",
        "slot": "shield",
        "base": "",
        "root_text": ["Sockets =1", "Armour ≥250%", "Blocked Hits 2—5%"],
        "root_text_ko": ["소켓 = 1", "방어도 ≥ 250%", "막기 피격 피해 2—5%"],
        "default_search": {"corrupted": True, "sockets": (1, 1), "mods": [
            M("#% increased Armour (Local)", min=250),
            M("You take #% of damage from Blocked Hits", min=2, max=5),
        ]},
        "base_search": {"corrupted": False, "sockets": None},   # 최대 소켓이 1 이므로 소켓 조건 없이 검색
        "enchant_search": {},
        "socket_search": {"sockets": (2, None)},
        "enchants": SVALINN_ENCHANTS,
        # 수치 변동: 구매 베이스의 수치(roll) 기준. 기본 검색 범위(2~5) 안이면 변화 없음과 같은 가격, 벗어나면 별도 검색
        "reroll": {
            "label": "Blocked Dmg", "ko": "막기 피해", "roll": 3.5,
            "outcomes": [
                {"range": (None, 1), "text": "≤1", "text_ko": "≤ 1", "search": {"mods": [
                    M("You take #% of damage from Blocked Hits", max=1),
                ]}},
                {"range": (2, 5), "text": "2—5", "text_ko": "2—5"},
                {"range": (6, None), "text": "6+", "text_ko": "6 이상", "search": {"mods": [
                    M("You take #% of damage from Blocked Hits", min=6),
                ]}},
            ],
        },
    },
]


def _mod_key(m):
    return m.get("id") or m["stat"]


def fname(u):
    """저장 파일명(확장자 제외): file 이 있으면 file, 없으면 name."""
    return u.get("file") or u["name"]


def apply_defaults(u):
    """각 검색 명세에 u['default_search'] 를 적용 (corrupted/sockets 는 덮어쓰기, mods 는 옵션 단위로 교체·추가)."""
    d = u.get("default_search") or {}

    def merge(spec):
        over = {_mod_key(m): m for m in spec.get("mods") or []}
        drop = set(spec.get("drop_mods") or [])
        mods = [over.pop(_mod_key(m), m) for m in d.get("mods") or [] if _mod_key(m) not in drop] + list(over.values())
        return {**d, **spec, "mods": mods}

    for k in ("base_search", "enchant_search", "socket_search"):
        if u.get(k) is not None:
            u[k] = merge(u[k])
    for o in u["reroll"]["outcomes"]:
        if o.get("search") is not None:
            o["search"] = merge(o["search"])


for _u in UNIQUES:
    apply_defaults(_u)

# ================================================================ 적정 최저가 판정 파라미터
MIN_LISTINGS = 2             # 검색 실패 = 가격·통화를 확인할 수 있는 정상 매물이 이 값 미만 (price_search 가 None 반환). 실패 시 대체값: 베이스 구매가=장비 제외, 변화 없음=베이스 x NO_CHANGE_RATIO, 인챈트=ratio(없으면 변화 없음 가치)
OUTLIER_MIN_N = 4
OUTLIER_RATIO = 0.5
MAX_SKIP = 2
OUTLIER_MAX_AGE_DAYS = 2
DEFAULT_CMP_RATES = {"exalted": 1.0, "chaos": 67.0, "divine": 515.0}   # poe.ninja 실패 시에만 사용
CMP_RATES = dict(DEFAULT_CMP_RATES)    # 통화 -> Exalted 환산값 (실행 시 poe.ninja 값으로 덮어씀)

session = requests.Session()
session.headers.update({"User-Agent": UA, "Content-Type": "application/json"})
if POESESSID:
    session.cookies.set("POESESSID", POESESSID, domain="www.pathofexile.com")
_printed_headers = False

# ================================================================ 레이트리밋 (슬라이딩 윈도우)
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
        if not _printed_headers and "X-Rate-Limit-Ip" in r.headers:
            for h in ("X-Rate-Limit-Ip", "X-Rate-Limit-Ip-State"):
                if h in r.headers:
                    print(f"  {h}: {r.headers[h]}")
            _printed_headers = True
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60)) + 1
            print(f"  429 -> {wait}초 대기")
            limiter.block[kind] = max(limiter.block.get(kind, 0), time.monotonic() + wait)
            continue
        if not r.ok:
            raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
        return r.json()


# ================================================================ poe.ninja 환율 (Divine / Chaos / Vaal Orb 의 Exalted 가격)
NINJA = "https://poe.ninja/poe2/api/economy"
ANCHORS = {"exalted": ("exalted", "exaltedorb"), "divine": ("divine", "divineorb"), "chaos": ("chaos", "chaosorb")}
VAAL_KEYS = ("vaalorb", "vaal")
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


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def ninja_parse(resp):
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
    r = _direct(ov, cur, cid)
    return (1 / r[0], r[1] + " 역수") if r else None


def _ex_price(ov, cid, chain, per):
    """cid 1개의 Exalted 가격. chain(화폐 이름 순서)대로 '그 화폐로 매겨진 시세'를 찾아 환산. (Ex 값, 화폐, 출처) 또는 None"""
    for name in chain:
        cur = ov["anchor"].get(name)
        if cur is None or per.get(name) is None:
            continue
        q = _quote(ov, cid, cur)
        if q:
            return q[0] * per[name], name, q[1]
    return None


def ninja_ex_per(ov):
    """Divine / Chaos 1개 = Exalted 몇 개 -> {'exalted': 1.0, 'divine': .., 'chaos': ..}"""
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


def load_rates(league):
    """CMP_RATES(통화 -> Exalted)를 poe.ninja 값으로 갱신하고 Vaal Orb 의 Exalted 가격을 반환 (못 구하면 None)."""
    print("\n== poe.ninja 환율 ==")
    try:
        nl = ninja_get("leagues")
        if isinstance(nl, dict):
            nl = nl.get("leagues") or []
        key = _norm(league)
        lid = next((x.get("id") for x in nl if isinstance(x, dict) and key in (_norm(x.get("id")), _norm(x.get("name")))), None)
        if lid is None:
            raise ValueError(f"poe.ninja 에 '{league}' 리그 없음")
        ov = ninja_parse(ninja_get("exchange/current/overview", {"league": lid, "type": "Currency"}))
        per = ninja_ex_per(ov)
        if "divine" not in per or "chaos" not in per or per["divine"] <= per["chaos"]:
            raise ValueError("Divine / Chaos 환율을 구하지 못함")
    except (requests.RequestException, ValueError, AttributeError) as e:
        print(f"  환율 조회 실패 ({str(e)[:200]}) -> 기본값 사용: {DEFAULT_CMP_RATES}")
        return None
    CMP_RATES.update(per)
    print(f"  Chaos = {per['chaos']:.2f} Ex, Divine = {per['divine']:.2f} Ex")
    cid = next((ov["keys"][k] for k in VAAL_KEYS if k in ov["keys"]), None)
    r = _ex_price(ov, cid, ("exalted", "divine", "chaos"), per) if cid else None
    if r:
        print(f"  Vaal Orb = {r[0]:.2f} Ex")
    return r[0] if r else None


# ================================================================ 리그
_EXCLUDE = re.compile(r"\b(hc|ssf|hardcore|ruthless|solo)\b", re.IGNORECASE)


def resolve_league(choice):
    key = choice.strip().lower()
    if key == "standard":
        return "Standard"
    if key not in ("latest", "previous"):
        return choice.strip()
    data = call("GET", f"{BASE}/api/trade2/data/leagues")
    names = [lg.get("id") or lg.get("text") for lg in data.get("result", []) if lg.get("realm") in (None, "poe2")]
    current = [n for n in names if n and n.lower() != "standard" and not _EXCLUDE.search(n)]
    idx = 0 if key == "latest" else 1
    if len(current) <= idx:
        sys.exit(f"'{choice}' 리그를 찾지 못했습니다. --league \"이름\" 으로 직접 지정하세요. (감지: {current})")
    return current[idx]


# ================================================================ 옵션(stat) id 해석
def norm_stat(t):
    t = re.sub(r"\(local\)", "", str(t or "").lower())
    return re.sub(r"\s+", " ", t.replace("+", "")).strip()


def raw_stat(t):
    """(Local) 표기를 유지한 정규화 문구. M('... (Local)') 처럼 로컬 옵션을 지정할 때 사용."""
    return re.sub(r"\s+", " ", str(t or "").lower().replace("+", "")).strip()


def load_stats():
    """trade2 옵션 목록 -> {그룹(explicit/enchant/..): {정규화 문구: [id, ...]}}"""
    data = call("GET", f"{BASE}/api/trade2/data/stats")
    idx = {}
    for grp in data.get("result", []):
        gid = str(grp.get("id") or grp.get("label") or "").lower()
        for e in grp.get("entries", []):
            if e.get("id"):
                idx.setdefault(gid, {}).setdefault(norm_stat(e.get("text")), []).append(e["id"])
                if "(local)" in str(e.get("text") or "").lower():
                    idx[gid].setdefault(raw_stat(e.get("text")), []).append(e["id"])
    return idx


STATS = {}


def stat_id(text, group="explicit"):
    if not STATS:                      # 옵션 목록은 실제로 필요할 때(검색/링크 생성)만 로드
        STATS.update(load_stats())
    pool = STATS.get(group, {})
    ids = pool.get(raw_stat(text)) if "(local)" in str(text).lower() else None
    ids = ids or pool.get(norm_stat(text))
    if ids:
        if len(ids) > 1:
            print(f"  ⚠ '{text}' 와 일치하는 옵션이 {len(ids)}개라 첫 번째({ids[0]}) 사용")
        return ids[0]
    words = [w for w in norm_stat(text).split() if w != "#"]
    near = [k for k in pool if words and all(w in k for w in words)][:8]
    sys.exit(f"옵션 문구를 찾지 못했습니다: '{text}' (그룹 {group}).\n비슷한 문구: {near or '없음'}\n"
             f"정확한 문구로 고치거나 M(..., id='explicit.stat_...') 로 id 를 직접 지정하세요.")


# ================================================================ 검색
def _range(lo, hi):
    r = {}
    if lo is not None:
        r["min"] = lo
    if hi is not None:
        r["max"] = hi
    return r


def build_query(u, spec, extra_mods=()):
    def to_filters(mods):
        out = []
        for m in mods:
            f = {"id": m.get("id") or stat_id(m["stat"], m.get("group", "explicit"))}
            v = _range(m.get("min"), m.get("max"))
            if v:
                f["value"] = v
            out.append(f)
        return out

    filters = to_filters(list(spec.get("mods") or []) + list(extra_mods))
    q = {
        "status": {"option": "securable"},
        "name": u["name"],
        "stats": [{"type": "and", "filters": filters}]
                 + ([{"type": "not", "filters": to_filters(spec["not_mods"])}] if spec.get("not_mods") else []),
        "filters": {
            "type_filters": {"filters": {"rarity": {"option": "unique"}}},
            "misc_filters": {"filters": {
                "corrupted": {"option": "true" if spec["corrupted"] else "false"},
                "mirrored": {"option": "false"},
            }},
        },
    }
    if spec["corrupted"]:
        q["filters"]["misc_filters"]["filters"].update(CORRUPT_FILTERS)
    qmin = spec.get("quality_min", QUALITY_MIN) if spec["corrupted"] else None
    if qmin is not None:
        q["filters"]["misc_filters"]["filters"]["quality"] = {"min": qmin}
    if u.get("type"):
        q["type"] = u["type"]
    lo, hi = spec.get("sockets") or (None, None)
    if lo is not None or hi is not None:
        q["filters"]["equipment_filters"] = {"filters": {"rune_sockets": _range(lo, hi)}}
    return {"query": q, "sort": {"price": "asc"}}


def search_url(u, league, spec, extra_mods=()):
    """검색 요청 없이 조건만 담은 경매장 링크 (?q=) 생성."""
    q = json.dumps(build_query(u, spec, extra_mods), separators=(",", ":"), ensure_ascii=False)
    return f"{BASE}/trade2/search/poe2/{quote(league)}?q={quote(q)}"


def cheapest(u, league, spec, extra_mods=()):
    s = call("POST", f"{BASE}/api/trade2/search/poe2/{league}", json=build_query(u, spec, extra_mods))
    total = s.get("total", 0)
    ids = s.get("result", [])[:TOP_N]
    rows = []
    for i in range(0, len(ids), FETCH_MAX):
        f = call("GET", f"{BASE}/api/trade2/fetch/{','.join(ids[i:i + FETCH_MAX])}", params={"query": s["id"]})
        for e in f.get("result", []):
            listing = e.get("listing") or {}
            price = listing.get("price") or {}
            rows.append({
                "amount": price.get("amount"), "currency": price.get("currency"),
                "indexed": listing.get("indexed"),
            })
    return total, rows, s.get("id")


# ================================================================ 적정 최저가
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


def fair_price(rows):
    """적정 최저가: 가격을 확인할 수 있는 매물 중 최저가. 중앙값의 OUTLIER_RATIO 미만인 최근 저가 매물은 이상치로 최대 MAX_SKIP개 제외."""
    usable = sorted((r for r in rows if _ex(r) is not None), key=_ex)
    n = len(usable)
    if n < MIN_LISTINGS:
        return {"status": "insufficient", "n": n, "reason": f"정상 매물 {n}개 < 최소 {MIN_LISTINGS}개"}

    vals = [_ex(r) for r in usable]
    skipped = 0
    if n >= OUTLIER_MIN_N:
        med = statistics.median(vals)
        cheap = 0
        while cheap < n and vals[cheap] < med * OUTLIER_RATIO:
            a = age_days(usable[cheap])
            if a is not None and a >= OUTLIER_MAX_AGE_DAYS:
                break
            cheap += 1
        if 0 < cheap <= min(MAX_SKIP, n // 3):
            skipped = cheap

    chosen = usable[skipped]
    return {"status": "ok", "a": chosen["amount"], "c": chosen["currency"], "n": n - skipped}


# ================================================================ 계산
def rnd(x):
    return float(f"{x:.4g}") if x < 1 else round(x, 2)


def to_div(f):
    return f["a"] * CMP_RATES[f["c"]] / CMP_RATES["divine"]


# ---------------------------------------------------------------- 검색 결과 캐시 (--use-cache)
CACHE_IN = {}      # 현재 장비의 기존 js 에 저장된 {검색 지문: [가격, 매물 수, 링크]}
CACHE_OUT = {}     # 이번 실행에서 쓴 결과 (js 의 "searches" 로 저장)
ONLINE = {"done": False, "vaal": None}


def search_fp(u, spec, kind="price"):
    """검색 조건 지문. 거래소 검색에 영향을 주는 값만 포함 (root_text, ko, ratio, NO_CHANGE_RATIO 등은 제외)."""
    mods = [[m.get("id") or m["stat"], m.get("group", "explicit"), m.get("min"), m.get("max")] for m in spec.get("mods") or []]
    corrupted = bool(spec["corrupted"])
    nots = [[m.get("id") or m["stat"], m.get("group", "explicit")] for m in spec.get("not_mods") or []]
    key = [u["name"], u.get("type"), mods, nots, corrupted, CORRUPT_FILTERS if corrupted else None, spec.get("quality_min", QUALITY_MIN) if corrupted else None,
           list(spec.get("sockets") or (None, None)), kind, TOP_N]
    return hashlib.sha1(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def search_specs(u):
    """장비 하나가 거래소 검색에 쓰는 명세 목록. analyze 의 price_search 호출과 같아야 한다."""
    es = u["enchant_search"]
    out = [u["base_search"], {**es, "not_mods": no_enchant_mods(u)}]
    out += [{**es, "mods": list(es["mods"]) + [{**M(e["mod"]), "group": "enchant"}]} for e in enchants_of(u) if e.get("search")]
    if u.get("socket_search") is not None:
        out.append(u["socket_search"])
    out += [reroll_spec(u, o) for o in u["reroll"]["outcomes"] if o.get("search")]
    return out


def reroll_spec(u, o):
    """수치 변동 검색: 변화 없음 검색처럼 인챈트 옵션 전체를 NOT 그룹으로 제외 (인챈트가 붙은 매물 배제)."""
    return {**o["search"], "not_mods": no_enchant_mods(u) + list(o["search"].get("not_mods") or [])}


def ensure_online(league):
    """환율(poe.ninja)과 바알 가격을 처음 필요할 때 한 번만 조회."""
    if ONLINE["done"]:
        return
    ONLINE["done"] = True
    vaal_ex = load_rates(league)
    if VAAL_COST_DIV is not None:
        ONLINE["vaal"] = VAAL_COST_DIV
    elif vaal_ex:
        ONLINE["vaal"] = rnd(vaal_ex / CMP_RATES["divine"])
    else:
        ONLINE["vaal"] = 0.0
        print("  ⚠ Vaal Orb 가격을 구하지 못해 vaalCost=0 으로 계산합니다 (VAAL_COST_DIV 로 직접 지정 가능)")


def link_url(u, league, spec, extra):
    """검색 없이 만드는 경매장 링크. 조건이 같으면 캐시된 링크 재사용 (옵션 목록 로드 생략)."""
    fp = search_fp(u, {**spec, "mods": list(spec.get("mods") or []) + list(extra)}, "link")
    if fp in CACHE_IN:
        CACHE_OUT[fp] = CACHE_IN[fp]
        return CACHE_IN[fp][2]
    url = search_url(u, league, spec, extra)
    CACHE_OUT[fp] = [None, None, url]
    return url


def price_search(u, league, spec, tag):
    """검색 -> (Divine 가격, 매물 수, 링크). 데이터 부족이면 (None, n, 링크)."""
    fp = search_fp(u, spec)
    if fp in CACHE_IN:
        price, n, url = CACHE_IN[fp]
        CACHE_OUT[fp] = CACHE_IN[fp]
        print(f"  [{tag}] 캐시 사용 -> " + (f"{price} div" if price is not None else "데이터 부족"))
        return price, n, url
    ensure_online(league)
    price, n, url = _price_search(u, league, spec, tag)
    CACHE_OUT[fp] = [price, n, url]
    return price, n, url


def _price_search(u, league, spec, tag):
    total, rows, sid = cheapest(u, league, spec)
    url = f"{BASE}/trade2/search/poe2/{quote(league)}/{sid}" if sid else None  # 가격 유무와 관계없이 항상 링크 생성
    f = fair_price(rows)
    if f["status"] != "ok":
        print(f"  [{tag}] 검색 {total}건, 데이터 부족 ({f['reason']})")
        return None, total, url          # n = 거래소 검색 전체 매물 수 (가격 판정에 쓴 상위 10건 중 정상 매물 수가 아님)
    p = to_div(f)
    print(f"  [{tag}] 검색 {total}건 -> {rnd(p)} div")
    return rnd(p), total, url


def roll_dist(roll):
    """수치 변동 배율 0.78~1.22(0.01 단위, 45가지 균등)를 적용한 결과값의 확률분포 {값: 확률}."""
    dist = Counter()
    for mi in range(78, 123):
        v = Fraction(str(roll)) * mi / 100
        if ROUND_MODE == "trunc":
            r = math.trunc(v + Fraction(1, 2))
        else:
            r = int(math.floor(abs(v) + Fraction(1, 2))) * (1 if v >= 0 else -1)
        dist[r] += 1
    return {k: c / 45 for k, c in dist.items()}


def reroll_outcomes(u, league, cost, nc):
    """수치 변동: 굴린 뒤 나올 수 있는 값마다 동등한 결과 1개 (확률 = OUTCOME_P x 그 값이 나올 확률)."""
    R = u["reroll"]
    dist = roll_dist(R["roll"])
    print(f"  [{R['label']}] 변동 후 값 분포: " + ", ".join(f"{v}:{p * 100:.0f}%" for v, p in sorted(dist.items())))
    def bounds(o):
        return o["range"] if "range" in o else (o["value"], o["value"])

    def covers(o, v):
        lo, hi = bounds(o)
        return (lo is None or v >= lo) and (hi is None or v <= hi)

    missing = sorted(v for v in dist if not any(covers(o, v) for o in R["outcomes"]))
    if missing:
        sys.exit(f"{u['name']}: reroll.outcomes 에 없는 값이 나올 수 있습니다: {missing}")
    outs = []
    for o in R["outcomes"]:
        pv = sum(p for v, p in dist.items() if covers(o, v))
        txt = o["text"] if "text" in o else f"{o['value']}{o.get('suffix', '')}"
        txt_ko = o["text_ko"] if "text_ko" in o else f"{o['value']}{o.get('suffix_ko', '')}"
        if pv == 0:
            print(f"  ⚠ {R['label']} {txt}: 확률 0 (ROUND_MODE={ROUND_MODE}) -> 제외")
            continue
        out = {"group": "reroll", "label": f"{R['label']} {txt}", "p": OUTCOME_P * pv}
        if R.get("ko"):
            out["ko"] = f"{R['ko']} {txt_ko}"
        low = False
        if o.get("search"):
            price, n, url = price_search(u, league, reroll_spec(u, o), f"수치 변동 {txt}")
            if price is None:    # 검색 실패 -> ratio (없으면 변화 없음 가치) 로 대체, html 에서 매물 건 텍스트를 붉게 표시
                price, low = (rnd(cost * o["ratio"]) if o.get("ratio") is not None else nc["price"]), True
        else:                    # 값 그대로 = 변화 없음 검색 가격
            price, n, url, low = nc["price"], nc["n"], nc["url"], nc["low"]
        out.update({"price": price, "n": n})
        if low:
            out["low"] = True
        if url:
            out["url"] = url
        outs.append(out)
    return outs


def analyze(u, league, old=None):
    print(f"\n######## {u['name']} ########")
    CACHE_IN.clear()
    CACHE_OUT.clear()
    if old:
        CACHE_IN.update(old["data"].get("searches") or {})
        print(f"  기존 데이터 사용 가능 (수집 {old['stamp']}) · 검색 조건이 같은 항목은 검색 생략")
    cost, n_base, base_url = price_search(u, league, u["base_search"], "베이스 구매가")
    if cost is None:
        print("  베이스 시세를 알 수 없어 건너뜁니다.")
        return None
    nc_spec = {**u["enchant_search"], "not_mods": no_enchant_mods(u)}
    nochange, nc_n, nc_url = price_search(u, league, nc_spec, "변화 없음")
    nc_low = nochange is None            # 검색 실패 -> 베이스 x NO_CHANGE_RATIO 로 대체, 매물 건 텍스트 붉게 표시
    if nc_low:
        nochange = rnd(cost * NO_CHANGE_RATIO)
    nc = {"price": nochange, "n": nc_n, "url": nc_url, "low": nc_low}

    outcomes = []
    socket_ok = u.get("socket_search") is not None
    o = {"group": "none", "label": "No change", "ko": "변화 없음", "p": OUTCOME_P * (1 if socket_ok else 2), "price": nochange, "n": nc_n, "url": nc_url}
    if nc_low:
        o["low"] = True
    outcomes.append(o)

    ENCH = enchants_of(u)
    ws = sum(e.get("w", 1) for e in ENCH) or 1
    for e in ENCH:
        p = OUTCOME_P * e.get("w", 1) / ws
        label, n, url, low = e["en"], None, None, False
        ratio = e.get("ratio")
        if e.get("search"):
            price, n, url = price_search(u, league, {**u["enchant_search"], "mods": list(u["enchant_search"]["mods"])
                                                  + [{**M(e["mod"]), "group": "enchant"}]}, "인챈트 " + e["en"])
            if price is None:    # 검색으로 가격을 못 구함 -> ratio (없으면 변화 없음 가치) 로 대체, html 에서 매물 건 텍스트를 붉게 표시
                price, low = (rnd(cost * ratio) if ratio is not None else nochange), True
        else:
            price = rnd(cost * ratio)
            url = link_url(u, league, u["enchant_search"], [{**M(e["mod"]), "group": "enchant"}] if e.get("mod") else [])
        o = {"group": "vaal", "label": label, "p": p, "price": price, "n": n}
        if e.get("ko"):
            o["ko"] = e["ko"]
        if low:
            o["low"] = True
        if url:
            o["url"] = url
        if e.get("range"):
            o["range"] = e["range"]
        outcomes.append(o)

    if socket_ok:
        price, n, url = price_search(u, league, u["socket_search"], "소켓 +1")
        est = price is None
        if est:
            price = nochange
        o = {"group": "socket", "label": "Socket +1", "ko": "소켓 +1", "p": OUTCOME_P, "price": price, "n": n, "url": url}
        if est:
            o["est"] = True
        outcomes.append(o)

    outcomes += reroll_outcomes(u, league, cost, nc)
    if ONLINE["done"] or not old or old["data"].get("vaalCost") is None:
        ensure_online(league)
        vaal_div = ONLINE["vaal"]
    else:
        vaal_div = old["data"]["vaalCost"]       # 이번 실행에서 거래소 조회가 없었으면 기존 값 유지
    data = {"name": u.get("title") or u["name"], "base": u.get("base", ""), "unit": "d", "cost": cost,
            "vaalCost": vaal_div, "rootText": u.get("root_text", []),
            "outcomes": outcomes, "searches": dict(CACHE_OUT)}
    if base_url:
        data["baseUrl"] = base_url
    if u.get("root_text_ko"):
        data["rootTextKo"] = u["root_text_ko"]
    if u.get("ko"):
        data["ko"] = u["ko"]
    if u.get("base_ko"):
        data["baseKo"] = u["base_ko"]
    return data


def count_requests(u, old=None):
    """검색 요청 수 (기존 데이터에 같은 조건의 결과가 있으면 제외)."""
    cached = (old["data"].get("searches") or {}) if old else {}
    return sum(1 for spec in search_specs(u) if search_fp(u, spec) not in cached)


def load_old(name, league, out_dir):
    """uniques/장비명.js 헤더의 리그가 같으면 {"data": ..., "stamp": 수집 시각}, 아니면 None."""
    path = os.path.join(out_dir, f"{name}.js")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.match(r"/\* .*? / 리그: (.*) / 수집: (\S+) \*/", text.split("\n", 1)[0])
        if not m or m.group(1) != league:
            return None
        body = text.split("window.UC_DATA.push(", 1)[1].rsplit(");", 1)[0]
        return {"data": json.loads(body), "stamp": m.group(2)}
    except (OSError, IndexError, ValueError):
        return None


def save(data, league, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.js")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"/* {name} / 리그: {league} / 수집: {stamp} */\n")
        f.write("window.UC_DATA.push(" + json.dumps(data, ensure_ascii=False, indent=1) + ");\n")
    # html 이 읽을 목록 파일: 폴더 안의 데이터 js 전체 (index.js 제외)
    files = sorted(x for x in os.listdir(out_dir) if x.lower().endswith(".js") and x.lower() != "index.js")
    with open(os.path.join(out_dir, "index.js"), "w", encoding="utf-8") as f:
        f.write("window.UC_FILES = " + json.dumps(files, ensure_ascii=False) + ";\n")
    return path


def main():
    ap = argparse.ArgumentParser(description="PoE2 고유 장비 타락 플리핑 데이터 수집")
    ap.add_argument("target", nargs="?", default="all", help='고유 장비 이름 또는 "all" (기본: %(default)s)')
    ap.add_argument("--league", default="latest", help="latest | previous | standard | 리그 이름 (기본: %(default)s)")
    ap.add_argument("--out", default=OUT_DIR, help="저장 폴더 (기본: 스크립트 옆 uniques/)")
    ap.add_argument("--use-cache", action="store_true", help="같은 리그로 저장된 js 의 검색 결과 중 검색 조건이 같은 것은 재사용")
    args = ap.parse_args()
    if not args.use_cache and sys.stdin.isatty():      # --use-cache 를 주지 않으면 실행 시 물어봄
        while True:
            ans = input("캐시를 사용하시겠습니까? 1 = yes, 2 = no (full query): ").strip()
            if ans in ("1", "2"):
                args.use_cache = ans == "1"
                break
            print("1 또는 2 를 입력하세요.")

    if args.target.lower() == "all":
        targets = UNIQUES
    else:
        t = args.target.strip().lower()
        targets = [u for u in UNIQUES if t in (u["name"].lower(), fname(u).lower())]
        if not targets:
            sys.exit(f"UNIQUES 에 없는 장비: {args.target} (사용 가능: {', '.join(fname(u) for u in UNIQUES)})")

    league = resolve_league(args.league)
    olds = {fname(u): load_old(fname(u), league, args.out) if args.use_cache else None for u in targets}
    n_search = sum(count_requests(u, olds[fname(u)]) for u in targets)
    est = estimate_seconds(n_search, n_search)
    print(f"리그: {league}\n요청 최대 {2 * n_search}회 (검색 {n_search} + fetch {n_search}) · 레이트리밋 기준 최단 약 {est / 60:.1f}분")

    if args.use_cache and n_search == 0:
        print("모든 검색이 기존 데이터와 조건이 같아 거래소 검색 없이 js 를 다시 만듭니다.")
    started = time.monotonic()
    saved = []
    for u in targets:
        data = analyze(u, league, olds[fname(u)])
        if data:
            path = save(data, league, args.out, fname(u))
            saved.append(os.path.basename(path))
            print(f"  -> {path} 저장")
    print(f"\n완료: 요청 {limiter.count}회, 소요 {(time.monotonic() - started) / 60:.1f}분")
    if saved:
        print("저장 완료 (uniques/index.js 목록 갱신됨):", ", ".join(saved))


if __name__ == "__main__":
    main()
