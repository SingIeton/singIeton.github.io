#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poe2_highend_margin_item_parser.py
===================
PoE2 장비 아이템 텍스트(한글/영문, Ctrl+Alt+C 상세 복사 형식)를 파싱해서
트레이드 API 쿼리용 JSON 파일로 저장한다.

사용법
------
  python poe2_highend_margin_item_parser.py item.txt -o items.json     # 파일에서 읽기
  python poe2_highend_margin_item_parser.py -c -o items.json           # 클립보드에서 읽기
  python poe2_highend_margin_item_parser.py -o items.json              # 직접 붙여넣기 (마지막 줄에 END 입력)
  python poe2_highend_margin_item_parser.py item.txt -o items.json -a  # 기존 파일에 추가
  python poe2_highend_margin_item_parser.py item.txt -o -              # 파일 대신 stdout 출력
  python poe2_highend_margin_item_parser.py item.txt --stats stats.json
                                                                       # 트레이드 stats 사전으로 stat id 채우기
  python poe2_highend_margin_item_parser.py item.txt --stats stats_ko.json --stats stats.json
                                                                       # 한글/영문 사전 둘 다 (언어별로 자동 선택)

  * 한 번에 여러 아이템을 붙여넣어도 된다 (한글/영문 혼합 가능).
  * 클립보드 복사는 반드시 Ctrl+Alt+C(상세 속성 포함)로 할 것.
    일반 Ctrl+C 에는 접두/접미 구분, 등급, 롤 범위가 없다.

다른 스크립트에서 import
------------------------
  from poe2_highend_margin_item_parser import parse_items, make_match_key
  items = parse_items(text)

JSON 구조 (요약, schema_version 3)
----------------------------------
  {
    "schema_version": 2,
    "items": [{
      "language": "ko" | "en",
      "item_class": {"raw", "en", "trade_category"},
      "rarity": {"raw", "en"},
      "name",            # 고유(Unique) 아이템만. 희귀/마법의 랜덤 생성 이름은 저장 안 함 (null)
      "base_type", "item_level", "quality",
      "requirements": {"level","str","dex","int"},
      "sockets": {"count","raw"},
      "flags": {"fractured","desecrated","corrupted","mirrored","unidentified"},
      "weapon":   {physical_damage, elemental_damage[], chaos_damage,
                   critical_hit_chance, attacks_per_second, reload_time} | null,
      "defences": {armour, evasion, energy_shield, block_chance} | null,
      "granted_skills": [],
      "mods":  [...],    # 고정/접두/접미 등 속성 (헤더 정보 + 줄별 문구 template). 룬 등 augment 는 제외
      "stats": [...],    # mods 를 줄 단위로 편 리스트 (trade_id 도 여기에 채워짐)
      "query": {...},    # <- 트레이드 쿼리 스크립트는 이것만 보면 된다 (아래 참고)
      "unparsed": [...],
      "warnings": [...]
    }]
  }

저장 정책
---------
  저장 안 함 : dps 등 파생 정보 / 희귀·마법 아이템의 랜덤 이름 /
               룬 등 augment 정보 (줄 끝 "(rune)") / "(augmented)" 표기 /
               모드의 roll 값, value 수치 (원문 text, values, ranges 전부).
               모드는 "종류(source/affix) + 문구 template + tier" 만 남긴다.
  저장하되 쿼리에선 거의 안 씀 : 이름~요구사항 사이 정보 (quality, weapon, defences ...).
               단 퀄리티는 QUALITY_QUERY_MIN 기준 이상이면 쿼리에 사용.
  분열(fractured) 모드 : mods/stats 에는 fractured 로 저장하지만,
               쿼리에서는 일반(explicit) 모드와 똑같이 취급한다.

stats[] 한 줄 (수치는 저장하지 않는다):
  {"source": explicit|implicit|enchant|fractured|desecrated|crafted|unknown,
   "affix": prefix|suffix|null, "tier": 1, "name": "...",
   "template": "Adds # to # Cold Damage",      # 수치 자리는 전부 '#'
   "match_key": 비교용 정규화 문자열,
   "trade_id": "explicit.stat_..." | null,     # resolve_trade_stats()/--stats 가 채움
   "trade_source": 실제로 찾은 사전 그룹,
   "trade_id_alt": [...],                      # (선택) 문구가 같은 다른 stat id 가 있을 때만
   "trade_id_via": "en_twin"}                  # (선택) 한글 사전 없이 영문 복사본으로 채운 경우

query (아이템별 검색 조건):
  "filters": {각 항목: {"mode": "exact", "value": ...} | {"mode": "min", "value": ...}
                      | {"mode": "any"}  (= 조건 없음)}
  "stats":   [{"source", "sources", "origin", "tier", "match_key", "template", "count",
               "trade_id", "trade_id_alt"}]      # 수치 조건 없음: 어떤 옵션이 붙어 있는지만 검색
  - flags: fractured / desecrated 는 항상 any (훼손 아이템이어도 조건 없음), mirrored 는 입력과 동일(true/false).
  - stats.sources: 트레이드 stats 사전에서 찾을 그룹 순서. 분열 모드는 ["explicit"], 훼손 모드는
    ["explicit", "desecrated"] (같은 문구의 일반 옵션이 있으면 일반 옵션으로 검색).
    resolve_trade_stats()/--stats 로 trade_id 와 실제 사용된 source 가 채워진다.
  - 같은 조건이 겹치는 옵션(일반 + 훼손이 똑같은 경우 등)은 하나로 합치고 count 에 개수를 남긴다.
  - filters 의 기본은 exact. 예외(any/min 등)는 아래 정책 상수에서 한 곳에서 바꾼다.
  - 무기/방어구는 "(Local)" 이 붙은 stat 를, 장신구는 붙지 않은 stat 를 우선 사용한다
    (아이템 문구에는 (Local) 표기가 없어서 사전에서 구분해 줘야 한다).
  - template/match_key 는 트레이드 사이트 stats 문구('#')와 매칭하는 용도다.
    매칭 시 stats 쪽 문구에도 make_match_key() 를 똑같이 적용할 것.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 3

# ---------------------------------------------------------------------------
# 저장/쿼리 정책 (바꾸고 싶으면 여기만 수정)
# ---------------------------------------------------------------------------

# 저장하지 않을 출처 태그 (줄 끝 "(rune)"). 소울 코어 등 소켓 augment 도 (rune) 로 표기된다.
IGNORED_SOURCE_TAGS = {"rune"}

# 아이템 상태 플래그별 쿼리 모드. 기본은 exact.
#  - fractured : 분열 아이템이어도 any (분열 모드는 그냥 그 옵션으로 검색)
#  - desecrated: 훼손된 아이템이어도 any (훼손 여부는 조건에 넣지 않음)
#  - mirrored  : exact = 입력과 동일 (미러된 아이템이면 true, 아니면 false 로 검색)
FLAG_QUERY_MODE: dict[str, str] = {
    "fractured": "any",
    "desecrated": "any",
    "corrupted": "exact",
    "mirrored": "exact",
    "unidentified": "exact",
}

# 모드 출처별로 트레이드 stats 사전(explicit/desecrated ...)에서 찾아볼 그룹과 순서.
#  - fractured : 일반(explicit) 모드와 똑같이 취급
#  - desecrated: 같은 문구의 일반(explicit) 옵션이 사전에 있으면 그것으로, 없을 때만 desecrated 옵션으로 검색
STAT_SOURCE_ORDER: dict[str, list[str]] = {
    "fractured": ["explicit"],
    "desecrated": ["explicit", "desecrated"],
}

# 퀄리티를 쿼리에 쓸 최소값 (trade_category 앞부분 기준). None 이면 쿼리에 안 씀.
# 장신구 기준값은 요청 문장이 끊겨 있어서 비워 둠 -> 숫자를 정하면 여기에 넣을 것.
QUALITY_QUERY_MIN: dict[str, Optional[int]] = {
    "weapon": 30,
    "armour": 30,
    "accessory": None,
}

# ---------------------------------------------------------------------------
# 용어 사전 (한글/영문). 새 용어가 나오면 여기에만 추가하면 된다.
# 해석 못한 줄은 item["unparsed"], 모르는 헤더는 item["warnings"] 에 남는다.
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip()).casefold()


# 속성 이름 -> 내부 키
PROPERTY_ALIASES: dict[str, list[str]] = {
    "item_class": ["Item Class", "아이템 종류"],
    "rarity": ["Rarity", "아이템 희귀도"],
    "quality": ["Quality", "퀄리티"],
    "physical_damage": ["Physical Damage", "물리 피해"],
    "elemental_damage": ["Elemental Damage", "원소 피해"],
    "chaos_damage": ["Chaos Damage", "카오스 피해"],
    "critical_hit_chance": ["Critical Hit Chance", "치명타 명중 확률"],
    "attacks_per_second": ["Attacks per Second", "초당 공격 횟수"],
    "reload_time": ["Reload Time", "재장전 시간"],
    "block_chance": ["Block chance", "막기 확률"],
    "armour": ["Armour", "방어도"],
    "evasion": ["Evasion Rating", "Evasion", "회피", "회피 수치"],
    "energy_shield": ["Energy Shield", "에너지 보호막"],
    "requires": ["Requires", "요구 사항"],
    "sockets": ["Sockets", "홈"],
    "item_level": ["Item Level", "아이템 레벨"],
    "granted_skill": ["Grants Skill", "스킬 부여"],
}
KEY_LOOKUP = {_norm(a): k for k, v in PROPERTY_ALIASES.items() for a in v}

RARITY_MAP = {
    "normal": "Normal", "일반": "Normal",
    "magic": "Magic", "마법": "Magic",
    "rare": "Rare", "희귀": "Rare",
    "unique": "Unique", "고유": "Unique",
}

# (영문 Item Class, [한글 후보], 트레이드 category 값)
# ※ 한글명은 '육척봉', '방패'만 실제 확인됨. 나머지는 추정이므로 틀리면 고쳐 쓸 것.
# ※ trade_category 는 pathofexile.com/trade2 의 category 필터 값 기준 (best-effort).
ITEM_CLASSES: list[tuple[str, list[str], str]] = [
    ("Quarterstaves", ["육척봉"], "weapon.warstaff"),
    ("Staves", ["스태프", "지팡이"], "weapon.staff"),
    ("Wands", ["완드"], "weapon.wand"),
    ("Sceptres", ["셉터"], "weapon.sceptre"),
    ("Bows", ["활"], "weapon.bow"),
    ("Crossbows", ["석궁"], "weapon.crossbow"),
    ("Spears", ["창"], "weapon.spear"),
    ("Flails", ["플레일"], "weapon.flail"),
    ("One Hand Maces", ["한손 철퇴"], "weapon.onemace"),
    ("Two Hand Maces", ["양손 철퇴"], "weapon.twomace"),
    ("Shields", ["방패"], "armour.shield"),
    ("Bucklers", ["버클러"], "armour.buckler"),
    ("Foci", ["초점", "포커스"], "armour.focus"),
    ("Helmets", ["투구"], "armour.helmet"),
    ("Body Armours", ["갑옷"], "armour.chest"),
    ("Gloves", ["장갑"], "armour.gloves"),
    ("Boots", ["신발"], "armour.boots"),
    ("Quivers", ["화살통"], "armour.quiver"),
    ("Rings", ["반지"], "accessory.ring"),
    ("Amulets", ["목걸이"], "accessory.amulet"),
    ("Belts", ["허리띠"], "accessory.belt"),
]
CLASS_LOOKUP: dict[str, tuple[str, str]] = {}
for _en, _kos, _cat in ITEM_CLASSES:
    CLASS_LOOKUP[_norm(_en)] = (_en, _cat)
    for _ko in _kos:
        CLASS_LOOKUP[_norm(_ko)] = (_en, _cat)

# 속성 헤더 { Fractured Suffix Modifier "of Unmaking" (Tier: 1) — Attack, Critical }
KIND_WORDS: list[tuple[str, list[str]]] = [
    ("prefix", ["prefix", "접두어"]),
    ("suffix", ["suffix", "접미어"]),
    ("implicit", ["implicit", "고정", "암시"]),      # 한글 implicit 표기는 추정
    ("enchant", ["enchant", "인챈트"]),              # 추정
    ("unique", ["unique", "고유"]),                  # 추정
]
MOD_FLAG_WORDS: dict[str, list[str]] = {
    "fractured": ["fractured", "분열된"],
    "desecrated": ["desecrated", "훼손된"],
    "crafted": ["crafted", "제작된"],                # 한글 표기는 추정
}

# 아이템 전체 상태 줄 ("Fractured Item" 등)
ITEM_FLAG_LINES: dict[str, str] = {
    "fractured item": "fractured", "분열된 아이템": "fractured",
    "desecrated item": "desecrated", "훼손된 아이템": "desecrated",      # 한글 추정
    "corrupted": "corrupted", "타락": "corrupted", "타락함": "corrupted",  # 한글 추정
    "mirrored": "mirrored", "미러": "mirrored", "미러링": "mirrored",      # 한글 추정
    "unidentified": "unidentified", "미확인": "unidentified",              # 한글 추정
}
ITEM_FLAG_LOOKUP = {_norm(k): v for k, v in ITEM_FLAG_LINES.items()}

ELEMENT_MAP = {
    "fire": "fire", "화염": "fire",
    "cold": "cold", "냉기": "cold",
    "lightning": "lightning", "번개": "lightning",
    "chaos": "chaos", "카오스": "chaos",
}

# 줄 끝에 붙는 출처 태그: "... (rune)"
SOURCE_TAG_RE = re.compile(r"\s*\((rune|implicit|enchant|crafted)\)\s*$", re.I)
AUGMENTED_RE = re.compile(r"\s*\(augmented\)", re.I)

HEADER_RE = re.compile(r"^\{\s*(?P<body>.*?)\s*\}$")
NAME_RE = re.compile(r'["“”](.*?)["“”]')
TIER_RE = re.compile(r"\(\s*([^():]+?)\s*:\s*(\d+)\s*\)")
KV_RE = re.compile(r"^([^:：]+?)\s*[:：]\s*(.*)$")
ITEM_START_RE = re.compile(r"^\s*(?:Item Class|아이템 종류)\s*[:：]", re.I | re.M)

_NUM = r"-?\d+(?:\.\d+)?"
VALUE_RE = re.compile(
    rf"(?:(?<![\w)])(?P<neg>-))?(?P<val>\d+(?:\.\d+)?)"
    rf"(?:\((?P<lo>{_NUM})-(?P<hi>{_NUM})\))?"
)

# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------


def _num(s: str) -> int | float:
    return float(s) if "." in s else int(s)


def first_number(s: str) -> Optional[int | float]:
    m = re.search(_NUM, s)
    return _num(m.group()) if m else None


def make_match_key(template: str) -> str:
    """트레이드 stats 문구와 비교하기 위한 정규화: '+#' -> '#', 공백 정리, 소문자."""
    t = re.sub(r"\[(?:[^\]|]*\|)?([^\]]*)\]", r"\1", template)  # "[a|b]" -> "b", "[a]" -> "a"
    t = re.sub(r"\+(?=#)", "", t)
    return re.sub(r"\s+", " ", t).strip().casefold()


def detect_language(text: str) -> str:
    return "ko" if re.search(r"[\uac00-\ud7a3]", text) else "en"


def parse_stat_line(text: str) -> dict[str, Any]:
    """'Adds 18(1-19) to 332(310-358) Lightning Damage' -> 수치를 전부 '#' 로 바꾼 문구만 남긴다.

    roll 값 / value 수치 / 롤 범위는 저장하지 않는다 (원문 text 에도 들어 있으므로 text 도 저장 안 함)."""
    template = VALUE_RE.sub("#", AUGMENTED_RE.sub("", text)).strip()
    return {
        "template": template,
        "match_key": make_match_key(template),
    }


def parse_mod_header(line: str) -> Optional[dict[str, Any]]:
    m = HEADER_RE.match(line)
    if not m:
        return None
    body = m.group("body")

    name = None
    nm = NAME_RE.search(body)
    if nm:
        name = nm.group(1).strip()
        body = body[: nm.start()] + " " + body[nm.end():]

    parts = re.split(r"\s*[—–]\s*", body, maxsplit=1)
    left = parts[0]
    tags = [t.strip() for t in parts[1].split(",") if t.strip()] if len(parts) > 1 else []

    tier = None
    tm = TIER_RE.search(left)
    if tm:
        tier = int(tm.group(2))
        left = left[: tm.start()] + " " + left[tm.end():]

    words = _norm(left)
    kind = "unknown"
    for k, kws in KIND_WORDS:
        if any(kw in words for kw in kws):
            kind = k
            break
    flags = {f: any(kw in words for kw in kws) for f, kws in MOD_FLAG_WORDS.items()}

    return {
        "kind": kind,
        "fractured": flags["fractured"],
        "desecrated": flags["desecrated"],
        "crafted": flags["crafted"],
        "name": name,
        "tier": tier,
        "tags": tags,
        "raw_header": line,
        "lines": [],
    }


def stat_source(mod: dict[str, Any]) -> str:
    for f in ("fractured", "desecrated", "crafted"):
        if mod.get(f):
            return f
    if mod["kind"] in ("prefix", "suffix", "unique"):
        return "explicit"
    return mod["kind"]


def parse_requirements(value: str) -> dict[str, Optional[int]]:
    req: dict[str, Optional[int]] = {"level": None, "str": None, "dex": None, "int": None}
    m = re.search(r"(?:Level|레벨)\s*(\d+)", value, re.I)
    if m:
        req["level"] = int(m.group(1))
    attr_map = {"str": "str", "힘": "str", "dex": "dex", "민첩": "dex", "int": "int", "지능": "int"}
    for m in re.finditer(r"(\d+)\s*(?:\([^)]*\)\s*)?(Str|Dex|Int|힘|민첩|지능)(?![A-Za-z])", value, re.I):
        req[attr_map[m.group(2).casefold()]] = int(m.group(1))
    return req


def _range(s: str) -> Optional[dict[str, int | float]]:
    m = re.search(rf"({_NUM})\s*-\s*({_NUM})", s)
    return {"min": _num(m.group(1)), "max": _num(m.group(2))} if m else None


# ---------------------------------------------------------------------------
# 쿼리 조건 생성
# ---------------------------------------------------------------------------


def build_query(item: dict[str, Any]) -> dict[str, Any]:
    """저장된 아이템 정보에서 검색 조건을 만든다. 기본은 전부 exact."""
    filters: dict[str, Any] = {}

    def exact(key: str, value: Any, target: Optional[dict] = None) -> None:
        if value is not None:
            (filters if target is None else target)[key] = {"mode": "exact", "value": value}

    cls = item["item_class"] or {}
    cat = cls.get("trade_category")
    exact("category", cat)
    exact("rarity", (item["rarity"] or {}).get("en"))
    exact("name", item["name"])              # 고유 아이템만 값이 있음
    exact("base_type", item["base_type"])
    exact("item_level", item["item_level"])
    if item["sockets"]:
        exact("sockets", item["sockets"]["count"])

    reqs: dict[str, Any] = {}
    for k, v in item["requirements"].items():
        exact(k, v, reqs)
    if reqs:
        filters["requirements"] = reqs

    # 퀄리티: 기준 이상일 때만 쿼리에 사용
    q = item["quality"]
    qmin = QUALITY_QUERY_MIN.get(cat.split(".")[0]) if cat else None
    if q is not None and qmin is not None and q >= qmin:
        filters["quality"] = {"mode": "min", "value": qmin}

    # 상태 플래그 (fractured 는 any)
    for flag, value in item["flags"].items():
        if FLAG_QUERY_MODE.get(flag, "exact") == "any":
            filters[flag] = {"mode": "any"}
        else:
            filters[flag] = {"mode": "exact", "value": bool(value)}

    # 모드: 분열 모드는 일반 모드와 똑같이, 훼손 모드는 같은 일반 옵션이 있으면 일반 옵션으로 검색.
    # 수치(value/roll)는 쓰지 않는다. 같은 stat(trade_id, 아직 없으면 첫 그룹 + 문구)이 겹치면 하나로 합친다
    # (예: 아이템에 일반 옵션과 똑같은 훼손 옵션이 있는 경우 -> 일반 옵션 하나로).
    stats: list[dict[str, Any]] = []
    seen: dict[tuple, dict[str, Any]] = {}
    for st in item["stats"]:
        sources = STAT_SOURCE_ORDER.get(st["source"], [st["source"]])
        tid = st.get("trade_id")
        key = ("id", tid) if tid else ("key", sources[0], st["match_key"])
        if key in seen:
            seen[key]["count"] += 1
            continue
        q = {
            "source": st.get("trade_source") or sources[0],   # 사전에서 실제로 쓴 그룹 (resolve 후)
            "sources": sources,          # 사전에서 찾아볼 그룹 순서
            "origin": st["source"],      # 아이템에 표시된 원래 출처
            "tier": st["tier"],
            "match_key": st["match_key"],
            "template": st["template"],
            "count": 1,
            "trade_id": tid,             # resolve_trade_stats 가 채움
        }
        if st.get("trade_id_alt"):
            q["trade_id_alt"] = st["trade_id_alt"]
        stats.append(q)
        seen[key] = q
    return {"filters": filters, "stats": stats}


# ---------------------------------------------------------------------------
# 트레이드 stats 사전 연결 (선택)
# ---------------------------------------------------------------------------


_LOCAL_RE = re.compile(r"\s*\(local\)", re.I)


def load_stats_catalog(data: dict[str, Any]) -> dict[str, Any]:
    """/api/trade2/data/stats 응답 -> {"language", "groups": {그룹: {match_key: [{"id", "local"}, ...]}}}

    사전 문구의 "(Local)" 은 떼고 키를 만든다 (아이템 문구에는 (Local) 표기가 없다).
    같은 키에 local / non-local 이 같이 있으면 둘 다 후보로 남기고, 고르는 건 resolve_trade_stats 가 한다."""
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    sample = ""
    for grp in data.get("result", []):
        g = _norm(grp.get("id") or grp.get("label") or "")
        for e in grp.get("entries", []):
            text = e.get("text") or ""
            sample += text
            key = make_match_key(_LOCAL_RE.sub("", text))
            groups.setdefault(g, {}).setdefault(key, []).append(
                {"id": e["id"], "local": bool(_LOCAL_RE.search(text))})
    return {"language": detect_language(sample), "groups": groups}


def _is_gear(item: dict[str, Any]) -> bool:
    """무기/방어구는 (Local) stat, 장신구는 일반 stat 를 우선한다."""
    cat = (item.get("item_class") or {}).get("trade_category") or ""
    return cat.startswith(("weapon", "armour"))


def _pick_stat(cands: list[dict[str, Any]], prefer_local: bool) -> tuple[str, list[str]]:
    pool = [c for c in cands if c["local"] == prefer_local] or cands
    return pool[0]["id"], [c["id"] for c in pool[1:]]


def _twin_signature(it: dict[str, Any]) -> tuple:
    return ((it.get("item_class") or {}).get("trade_category"), it.get("item_level"),
            it.get("quality"), (it.get("sockets") or {}).get("count"), len(it["stats"]))


def _twin_aligned(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """한글/영문 복사본은 모드 순서·종류·티어가 똑같다."""
    return all((x["source"], x["affix"], x["tier"]) == (y["source"], y["affix"], y["tier"])
               for x, y in zip(a["stats"], b["stats"]))


def resolve_trade_stats(items: list[dict[str, Any]], catalogs: list[dict[str, Any]]) -> int:
    """item["stats"][i]["trade_id"] 를 채우고 query 를 다시 만든다. 못 찾은 stat 개수를 반환.

    1) 아이템과 같은 언어의 사전으로 찾는다. sources 순서대로: 훼손 옵션은 같은 문구의 explicit 이 있으면
       그것을, 없을 때만 desecrated 를 쓴다. 문구가 같은 (Local)/일반 stat 가 둘 다 있으면
       무기/방어구는 (Local), 장신구는 일반 stat 를 쓴다.
    2) 같은 언어 사전이 없는 아이템(예: 한글 아이템 + 영문 stats.json)은, 같은 입력 안에 있는
       영문 복사본(분류/아이템 레벨/퀄리티/홈/모드 순서·티어가 같은 것)에서 trade_id 를 그대로 가져온다.
       (stat id 는 언어와 상관없이 같다.)"""
    by_lang = {c["language"]: c for c in catalogs}
    pending: list[dict[str, Any]] = []   # 같은 언어 사전이 없는 아이템
    for it in items:
        cat = by_lang.get(it["language"])
        if cat is None:
            pending.append(it)
            continue
        gear = _is_gear(it)
        for st in it["stats"]:
            st["trade_id"] = st["trade_source"] = None
            st.pop("trade_id_alt", None)
            for src in STAT_SOURCE_ORDER.get(st["source"], [st["source"]]):
                cands = cat["groups"].get(src, {}).get(st["match_key"])
                if cands:
                    st["trade_id"], alt = _pick_stat(cands, gear)
                    st["trade_source"] = src
                    if alt:
                        st["trade_id_alt"] = alt
                    break

    for it in pending:
        for st in it["stats"]:
            st["trade_id"] = st["trade_source"] = None
        twin = next((o for o in items if o is not it and o["language"] != it["language"]
                     and o["language"] in by_lang
                     and _twin_signature(o) == _twin_signature(it) and _twin_aligned(o, it)), None)
        if twin is None:
            it["warnings"].append(
                f"{it['language']} stats 사전이 없고 같은 아이템의 다른 언어 복사본도 없어 trade_id 를 채우지 못함 "
                f"(--stats 로 {it['language']} 사전을 추가하거나, 같은 아이템을 영문으로도 같이 입력할 것)")
            continue
        for st, ts in zip(it["stats"], twin["stats"]):
            for k in ("trade_id", "trade_source", "trade_id_alt"):
                if k in ts:
                    st[k] = ts[k]
            if st["trade_id"]:
                st["trade_id_via"] = "en_twin"

    missing = 0
    for it in items:
        unresolved = [st for st in it["stats"] if not st.get("trade_id")]
        missing += len(unresolved)
        has_dict = it["language"] in by_lang or any(st.get("trade_id") for st in it["stats"])
        if has_dict:   # 사전 자체가 없던 아이템은 위에서 경고 한 줄을 이미 남겼다
            for st in unresolved:
                it["warnings"].append(f"stats 사전에 없는 옵션: {st['template']}")
        it["query"] = build_query(it)
    return missing


# ---------------------------------------------------------------------------
# 아이템 1개 파싱
# ---------------------------------------------------------------------------


def split_sections(text: str) -> list[list[str]]:
    sections: list[list[str]] = []
    cur: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if re.fullmatch(r"-{3,}", s):
            sections.append(cur)
            cur = []
        elif s:
            cur.append(s)
    sections.append(cur)
    return [s for s in sections if s]


def parse_item_text(text: str, keep_raw: bool = False) -> dict[str, Any]:
    sections = split_sections(text)
    warnings: list[str] = []
    unparsed: list[str] = []

    item: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "language": detect_language(text),
        "item_class": None,
        "rarity": None,
        "name": None,
        "base_type": None,
        "item_level": None,
        "quality": None,
        "requirements": {"level": None, "str": None, "dex": None, "int": None},
        "sockets": None,
        "flags": {"fractured": False, "desecrated": False, "corrupted": False,
                  "mirrored": False, "unidentified": False},
        "weapon": None,
        "defences": None,
        "granted_skills": [],
        "mods": [],
        "stats": [],
        "query": None,
        "unparsed": unparsed,
        "warnings": warnings,
    }
    if not sections:
        warnings.append("빈 입력")
        return item

    # ---- 헤더 섹션: Item Class / Rarity / 이름 ----
    name_lines: list[str] = []
    for line in sections[0]:
        kv = KV_RE.match(line)
        key = KEY_LOOKUP.get(_norm(kv.group(1))) if kv else None
        if key == "item_class":
            raw = kv.group(2).strip()
            en, cat = CLASS_LOOKUP.get(_norm(raw), (None, None))
            item["item_class"] = {"raw": raw, "en": en, "trade_category": cat}
            if en is None:
                warnings.append(f"알 수 없는 아이템 종류: {raw!r} (ITEM_CLASSES 에 추가 필요)")
        elif key == "rarity":
            raw = kv.group(2).strip()
            item["rarity"] = {"raw": raw, "en": RARITY_MAP.get(_norm(raw))}
        else:
            name_lines.append(line)

    rarity_en = (item["rarity"] or {}).get("en")
    # 이름은 고유(Unique)만 저장. 희귀/마법의 랜덤 생성 이름은 버린다.
    if rarity_en in ("Rare", "Unique") and len(name_lines) >= 2:
        if rarity_en == "Unique":
            item["name"] = name_lines[0]
        item["base_type"] = name_lines[1]
    elif rarity_en == "Magic":
        warnings.append("마법 아이템: base_type 은 이름에서 직접 분리해야 함")
    elif name_lines:
        item["base_type"] = name_lines[-1]

    # ---- 나머지 섹션 ----
    mods: list[dict[str, Any]] = []
    warnings_header_set: set[str] = set()
    weapon: dict[str, Any] = {}
    defences: dict[str, Any] = {}

    def handle_property(key: str, raw_value: str) -> None:
        value = AUGMENTED_RE.sub("", raw_value).strip()  # "(augmented)" 표기는 버린다

        if key == "quality":
            item["quality"] = first_number(value)
        elif key == "item_level":
            item["item_level"] = first_number(value)
        elif key == "requires":
            item["requirements"] = parse_requirements(value)
        elif key == "sockets":
            item["sockets"] = {"count": len(value.split()), "raw": value}
        elif key == "granted_skill":
            item["granted_skills"].append(value)
        elif key == "physical_damage":
            weapon["physical_damage"] = _range(value)
        elif key == "chaos_damage":
            weapon["chaos_damage"] = _range(value)
        elif key == "elemental_damage":
            elems = []
            for m in re.finditer(rf"({_NUM})\s*-\s*({_NUM})\s*\(([^)]+)\)", value):
                tag = m.group(3).strip()
                etype = ELEMENT_MAP.get(tag.casefold())
                if etype is None:
                    warnings.append(f"알 수 없는 원소 표기: {tag!r}")
                    etype = tag
                elems.append({"type": etype, "min": _num(m.group(1)), "max": _num(m.group(2))})
            weapon["elemental_damage"] = elems
        elif key == "critical_hit_chance":
            weapon["critical_hit_chance"] = first_number(value)
        elif key == "attacks_per_second":
            weapon["attacks_per_second"] = first_number(value)
        elif key == "reload_time":
            weapon["reload_time"] = first_number(value)
        elif key in ("armour", "evasion", "energy_shield", "block_chance"):
            defences[key] = first_number(value)

    for sec in sections[1:]:
        cur_mod: Optional[dict[str, Any]] = None
        for line in sec:
            # 1) { ... } 속성 헤더
            hdr = parse_mod_header(line)
            if hdr is not None:
                if hdr["kind"] == "unknown":
                    warnings.append(f"알 수 없는 속성 헤더: {line}")
                    warnings_header_set.add(line)
                mods.append(hdr)
                cur_mod = hdr
                continue
            # 2) 아이템 상태 줄 (Fractured Item 등)
            flag = ITEM_FLAG_LOOKUP.get(_norm(line))
            if flag:
                item["flags"][flag] = True
                cur_mod = None
                continue
            # 3) 헤더 아래 속성 본문
            if cur_mod is not None:
                tm = SOURCE_TAG_RE.search(line)
                if tm:
                    tag = tm.group(1).lower()
                    if tag in IGNORED_SOURCE_TAGS:
                        continue  # 룬 등 augment 줄은 저장하지 않음
                    line = SOURCE_TAG_RE.sub("", line)
                    if cur_mod["kind"] == "unknown":   # 헤더에서 종류를 못 읽었으면 줄 끝 태그로 보충
                        cur_mod["kind"] = tag
                        cur_mod["crafted"] = cur_mod["crafted"] or tag == "crafted"
                        if cur_mod["raw_header"] in warnings_header_set:
                            warnings.remove(f"알 수 없는 속성 헤더: {cur_mod['raw_header']}")
                            warnings_header_set.discard(cur_mod["raw_header"])
                cur_mod["lines"].append(parse_stat_line(line))
                continue
            # 4) 줄 끝 (rune) 등 출처 태그가 붙은 줄
            tm = SOURCE_TAG_RE.search(line)
            if tm:
                kind = tm.group(1).lower()
                if kind in IGNORED_SOURCE_TAGS:
                    continue  # 룬 등 augment 정보는 저장하지 않음
                mods.append({
                    "kind": kind, "fractured": False, "desecrated": False,
                    "crafted": kind == "crafted", "name": None, "tier": None,
                    "tags": [], "raw_header": None,
                    "lines": [parse_stat_line(SOURCE_TAG_RE.sub("", line))],
                })
                continue
            # 5) "키: 값" 속성
            kv = KV_RE.match(line)
            key = KEY_LOOKUP.get(_norm(kv.group(1))) if kv else None
            if key:
                handle_property(key, kv.group(2).strip())
                continue
            unparsed.append(line)

    # ---- 후처리 ----
    mods = [m for m in mods if m["lines"]]
    for mod in mods:
        if mod["fractured"]:
            item["flags"]["fractured"] = True
        if mod["desecrated"]:
            item["flags"]["desecrated"] = True
        src = stat_source(mod)
        affix = mod["kind"] if mod["kind"] in ("prefix", "suffix") else None
        for ln in mod["lines"]:
            item["stats"].append({
                "source": src, "affix": affix, "tier": mod["tier"], "name": mod["name"], **ln,
                "trade_id": None,
            })
    item["mods"] = mods

    if weapon:
        weapon.setdefault("physical_damage", None)
        weapon.setdefault("elemental_damage", [])
        weapon.setdefault("chaos_damage", None)
        weapon.setdefault("critical_hit_chance", None)
        weapon.setdefault("attacks_per_second", None)
        weapon.setdefault("reload_time", None)
        item["weapon"] = weapon
    if defences:
        for k in ("armour", "evasion", "energy_shield", "block_chance"):
            defences.setdefault(k, None)
        item["defences"] = defences

    if not any(m["raw_header"] for m in mods):
        warnings.append("{...} 속성 헤더가 없음: Ctrl+Alt+C(상세 복사)로 복사했는지 확인")
    if unparsed:
        warnings.append(f"해석하지 못한 줄 {len(unparsed)}개 (unparsed 참고)")
    item["query"] = build_query(item)
    if keep_raw:
        item["raw_text"] = text.strip()
    return item


# ---------------------------------------------------------------------------
# 여러 아이템 / 입출력
# ---------------------------------------------------------------------------


def split_items(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    starts = [m.start() for m in ITEM_START_RE.finditer(text)]
    if not starts:
        return [text] if text.strip() else []
    return [text[s: (starts[i + 1] if i + 1 < len(starts) else len(text))] for i, s in enumerate(starts)]


def parse_items(text: str, keep_raw: bool = False) -> list[dict[str, Any]]:
    return [parse_item_text(chunk, keep_raw) for chunk in split_items(text)]


def read_clipboard() -> str:
    try:
        import pyperclip  # type: ignore
        return pyperclip.paste()
    except ImportError:
        pass
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        try:
            return root.clipboard_get()
        finally:
            root.destroy()
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"클립보드를 읽을 수 없음 ({e}). `pip install pyperclip` 후 다시 시도하세요.")


def read_input(args: argparse.Namespace) -> str:
    if args.clipboard:
        return read_clipboard()
    if args.input:
        return Path(args.input).read_text(encoding="utf-8-sig")
    if sys.stdin.isatty():
        print("아이템 정보를 붙여넣은 뒤, 새 줄에 END 를 입력하고 Enter (또는 Ctrl+Z / Ctrl+D):",
              file=sys.stderr)
        buf = []
        for line in sys.stdin:
            if line.strip().upper() == "END":
                break
            buf.append(line)
        return "".join(buf)
    return sys.stdin.read()


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="PoE2 아이템 텍스트(한글/영문) -> JSON 변환기")
    ap.add_argument("input", nargs="?", help="아이템 텍스트 파일 (생략 시 stdin/붙여넣기)")
    ap.add_argument("-o", "--output", default="items.json", help="출력 JSON 경로 ('-' = stdout)")
    ap.add_argument("-c", "--clipboard", action="store_true", help="클립보드에서 읽기")
    ap.add_argument("-a", "--append", action="store_true", help="기존 출력 파일의 items 뒤에 추가")
    ap.add_argument("--stats", action="append", default=[], metavar="JSON",
                    help="trade2 stats 사전(/api/trade2/data/stats 응답) 파일. 언어별로 여러 번 지정 가능. stats[].trade_id / query.stats[].trade_id 를 채움. "
                         "한글 아이템은 한글 사전이 없으면 같은 입력 안의 영문 복사본에서 가져옴")
    ap.add_argument("--keep-raw", action="store_true", help="원문 텍스트를 raw_text 로 같이 저장")
    args = ap.parse_args(argv)

    text = read_input(args)
    items = parse_items(text, keep_raw=args.keep_raw)
    if not items:
        print("파싱할 아이템이 없습니다.", file=sys.stderr)
        return 1

    if args.stats:
        cats = [load_stats_catalog(json.loads(Path(f).read_text(encoding="utf-8-sig"))) for f in args.stats]
        miss = resolve_trade_stats(items, cats)
        if miss:
            print(f"stats 사전에서 못 찾은 옵션 {miss}개", file=sys.stderr)

    for i, it in enumerate(items, 1):
        cls = (it["item_class"] or {}).get("en") or (it["item_class"] or {}).get("raw")
        found = sum(1 for st in it["stats"] if st.get("trade_id"))
        print(f"[{i}] {it['name'] or it['base_type']} ({it['rarity'] and it['rarity']['en']}, {cls}, "
              f"{it['language']}) stats={len(it['stats'])}"
              + (f" trade_id={found}/{len(it['stats'])}" if args.stats else ""), file=sys.stderr)
        for w in it["warnings"]:
            print(f"    ! {w}", file=sys.stderr)

    if args.output == "-":
        print(json.dumps({"schema_version": SCHEMA_VERSION, "items": items}, ensure_ascii=False, indent=2))
        return 0

    out = Path(args.output)
    existing: list[dict] = []
    if args.append and out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        if old.get("schema_version") != SCHEMA_VERSION:
            raise SystemExit(f"기존 파일의 schema_version={old.get('schema_version')} (현재 {SCHEMA_VERSION}). "
                             "섞어 쓸 수 없으니 새 파일로 저장하세요.")
        existing = old.get("items", [])
    out.write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "items": existing + items},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"저장 완료: {out} (총 {len(existing) + len(items)}개)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
