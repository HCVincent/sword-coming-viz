#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from entity_resolution import load_and_resolve, save_unified_knowledge_base
from knowledge_store import ChunkExtraction
from model.action import Action
from model.event import Event
from model.location import Location
from model.role import Role
from scripts.character_quality import audit_role_name, is_pseudo_role_name
from scripts.build_chapter_synopses import build_chapter_synopses_file
from scripts.build_key_events_index import build_key_events_index_file
from scripts.build_season_overview_audit import build_audit
from scripts.build_swordcoming_writer_insights import build_writer_insights_file
from scripts.validate_unified_knowledge import validate_unified_knowledge


DEFAULT_SYNC_FILES = [
    "book_config.json",
    "chapter_index.json",
    "chapter_synopses.json",
    "key_events_index.json",
    "unit_progress_index.json",
    "unified_knowledge.json",
    "writer_insights.json",
    "swordcoming_book.json",
]

SYMMETRIC_ACTIONS = {"对话", "会见", "冲突", "同行"}

COMMON_SURNAME_CHARS = set(
    "赵钱孙李周吴郑王冯陈卫蒋沈韩杨朱秦许何吕张孔曹严华金魏陶姜戚谢邹喻柏窦章云苏潘葛范彭郎鲁韦马苗凤方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝安常乐于傅卞齐康伍余元顾孟黄穆萧尹姚邵汪祁毛禹狄贝明伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季贾路江童颜郭梅盛林刁钟徐邱高夏蔡田樊胡凌霍虞万支柯昝管卢莫房裘缪应宗丁宣邓郁杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊惠甄曲封芮储靳汲松段富巫乌焦巴弓牧车侯宓全班仰秋仲伊宫宁栾甘厉戎祖武符刘景詹龙叶司韶黎蓟薄印白蒲邰从鄂索赖卓蔺屠蒙池乔阴闻党翟谭贡劳姬申扶堵冉宰郦雍桑桂牛寿通边扈燕冀郏浦尚温别庄晏柴瞿阎充慕连茹习艾鱼向古易慎戈廖终暨居衡步都耿弘匡国文寇广禄东欧沃利蔚越夔隆师巩聂晁勾敖融冷辛阚那简饶曾沙养鞠须丰关蒯相查后荆红游竺权盖益桓公"
)
COMMON_NAME_PREFIXES = set()
LEADING_NOISE_TOKENS = (
    "于是",
    "然后",
    "只是",
    "若是",
    "如果",
    "这个",
    "那个",
    "这么",
    "那么",
    "便是",
    "还是",
)
TRAILING_NOISE_CHARS = set("的了着呢啊呀嘛吧么")
NON_PERSON_CANDIDATES = {
    "小镇",
    "大骊",
    "山上",
    "山下",
    "少年",
    "少女",
    "老人",
    "男人",
    "女人",
    "先生",
    "掌教",
    "真人",
    "道人",
    "修士",
    "武夫",
    "剑修",
    "书生",
    "国师",
    "皇帝",
    "山君",
    "君子",
    "圣人",
    "祖师",
    "天君",
    "公子",
    "夫人",
    "小姐",
    "孩子",
    "婢女",
    "丫鬟",
    "城头",
    "街巷",
    "泥瓶",
    "骑龙",
    "龙泉",
    "书院",
    "长城",
    "落魄",
    "正阳",
    "白帝",
    "风雪",
    "老龙",
    "落魄山",
    "剑气长城",
}
NON_PERSON_SUBSTRINGS = (
    "少年",
    "少女",
    "老人",
    "女子",
    "男子",
    "书生",
    "掌柜",
    "祖宅",
    "老祖",
    "岛上",
    "岛中",
    "京城",
    "朝廷",
    "皇帝",
    "王朝",
    "藩王",
    "铺子",
    "店里",
    "城里",
    "城中",
    "城头",
    "巷口",
    "路上",
    "山上",
    "山下",
    "楼上",
    "楼下",
    "时候",
    "地方",
    "东西",
    "事情",
    "一个",
    "一种",
    "一些",
    "这些",
    "那些",
    "于是",
    "然后",
    "最后",
    "只是",
    "后者",
    "前者",
    "那人",
    "仰头",
    "转头",
    "低头",
    "抬头",
    "点头",
    "摇头",
    "轻声",
    "沉声",
    "小声",
    "冷冷",
    "微微",
    "静静",
    "哈哈",
    "好奇",
    "忍不住",
    "试探性",
    "毕恭毕敬",
    "小心翼翼",
    "边跑一边",
)
ALLOWED_TITLED_CANDIDATES = {
}
CONTEXT_DENY_NEXT_PHRASES = (
    "大开口",
    "笑眯眯",
    "笑呵呵",
    "笑吟吟",
    "慢悠悠",
    "慢吞吞",
)
LOCATION_POWER_HINTS = {
    "泥瓶巷": "小镇",
    "骑龙巷": "小镇",
    "小镇": "小镇",
    "龙泉": "龙泉",
    "龙泉郡": "龙泉",
    "骊珠洞天": "骊珠洞天",
    "大骊": "大骊",
    "大隋": "山崖书院",
    "山崖书院": "山崖书院",
    "老龙城": "老龙城",
    "落魄山": "落魄山",
    "剑气长城": "剑气长城",
}
MINED_CHARACTER_PATTERNS = [
    ("intro", re.compile(r"姓([\u4e00-\u9fff])，名([\u4e00-\u9fff]{1,2})")),
    ("intro", re.compile(r"(?:名叫|叫做|唤作|唤做|自称)([\u4e00-\u9fff]{2,4})")),
    (
        "dialogue",
        re.compile(
            r"([\u4e00-\u9fff]{2,4})(?=说道|问道|笑道|答道|冷笑道|怒道|喝道|骂道|轻声道|沉声道|开口道|开口说道|开口问道|开口答道)"
        ),
    ),
]
MANUAL_EXTRA_CHARACTERS = [
    {"name": "陆台", "aliases": [], "power": "道家", "description": "与陈平安有稳定交集的重要人物，能补足前三季山上与命运分叉线。"},
    {"name": "吴鸢", "aliases": [], "power": "大骊", "description": "大骊体系中的重要官面人物，补强王朝与地方秩序线。"},
    {"name": "茅小冬", "aliases": [], "power": "山崖书院", "description": "书院线关键人物，能把李宝瓶一行与更高层儒家视角串起来。"},
    {"name": "曹峻", "aliases": [], "power": "山上", "description": "山上人物，适合补强前三季外围修士群像与冲突关系。"},
    {"name": "徐远霞", "aliases": [], "power": "江湖", "description": "江湖线人物，可补足陈平安早期外部同行与见闻线。"},
    {"name": "张山峰", "aliases": [], "power": "道家", "description": "道门支线人物，能扩展前三季陈平安外部世界的接触面。"},
    {"name": "范二", "aliases": [], "power": "老龙城", "description": "老龙城支线的重要人物，适合补足城池与家族关系网。"},
    {"name": "杨花", "aliases": [], "power": "小镇", "description": "小镇旧线人物，可补齐街巷人情与早期命运分流。"},
    {"name": "柳赤诚", "aliases": [], "power": "山上", "description": "山上高位人物，适合扩展外围强者关系与更大格局。"},
    {"name": "桂姨", "aliases": [], "power": "老龙城", "description": "老龙城线中的重要女性角色，可补强城池人情与势力关系。"},
    {"name": "刘太守", "aliases": [], "power": "大骊", "description": "地方官面人物，能增强大骊王朝线与地方秩序线。（含郡城治理线）"},
    {"name": "范峻茂", "aliases": [], "power": "老龙城", "description": "老龙城家族线兼山上修士背景人物，适合补足家族利益网络与外围宗门关系。"},
    {"name": "曹慈", "aliases": [], "power": "武道", "description": "武道线代表人物，适合补足前三季高水平对照线。"},
    {"name": "丁婴", "aliases": [], "power": "武道", "description": "高强度冲突线人物，可强化外围强者与江湖武道层面的关系。"},
    {"name": "许甲", "aliases": [], "power": "山上", "description": "山上支线人物，适合补足修士群像。"},
    {"name": "贺小凉", "aliases": [], "power": "山上", "description": "山上女性人物，可补足外围修士关系链。"},
    {"name": "傅玉", "aliases": [], "power": "山上", "description": "山上人物，适合增强外围势力和人物关系层次。"},
    {"name": "陈真容", "aliases": [], "power": "大骊", "description": "大骊相关人物，可补足王朝支线与官面网络。"},
    {"name": "李侯", "aliases": [], "power": "龙泉", "description": "龙泉地界人物，适合增强地方秩序与山水网络。"},
    {"name": "黄尚", "aliases": [], "power": "山上", "description": "山上人物，适合扩展外围修士节点。"},
    {"name": "陆舫", "aliases": [], "power": "山上", "description": "山上人物，适合补强高位修士群像。"},
    {"name": "崔明皇", "aliases": [], "power": "大骊", "description": "大骊支线人物，适合加强王朝线的层次。"},
    {"name": "金粟", "aliases": [], "power": "老龙城", "description": "老龙城与渡船线的重要女性人物，可补足陈平安外出途中结识的支线关系。"},
    {"name": "王毅甫", "aliases": [], "power": "大骊", "description": "大骊官面与调查线人物，可补足王朝视角中的执行层关系。"},
    {"name": "李长英", "aliases": [], "power": "山崖书院", "description": "书院求学线的重要人物，适合补强李宝瓶一行相关的人物网络。"},
    {"name": "刘幽州", "aliases": [], "power": "大骊", "description": "与陈平安有直接交集的年轻人物，可扩充大骊支线与同行线。"},
    {"name": "周姝真", "aliases": [], "power": "山上", "description": "外围修士与高位布局线人物，适合补足山上势力层次。"},
    {"name": "魏衍", "aliases": [], "power": "江湖", "description": "江湖与朝局交叉线人物，可补足支线冲突与地方秩序网络。"},
    {"name": "樊莞尔", "aliases": [], "power": "老龙城", "description": "老龙城相关的重要女性人物，适合补充城池与家族支线。"},
    {"name": "刘宗", "aliases": [], "power": "武道", "description": "武道支线人物，能补足高强度对峙与外部强者关系。"},
    {"name": "姜北海", "aliases": [], "power": "山上", "description": "高位修士支线人物，适合补强外围宗门与强者网络。"},
    {"name": "石春嘉", "aliases": [], "power": "小镇", "description": "小镇旧人旧事中的稳定角色，可补足街巷人情与日常关系层。"},
    {"name": "沈温", "aliases": [], "power": "山上", "description": "山水与庙堂边缘的支线人物，适合补足外围山上关系。"},
    {"name": "李抟景", "aliases": [], "power": "山上", "description": "山上剑修线人物，可增强外部强者与宗门关系层次。"},
    {"name": "周肥", "aliases": [], "power": "山上", "description": "高位修士支线人物，适合扩充外围势力与家族博弈线。"},
    {"name": "高稹", "aliases": [], "power": "大骊", "description": "大骊宗室相关人物，可补足王朝内部关系与身份错位线。"},
    {"name": "曹曦", "aliases": [], "power": "山上", "description": "山上强者支线人物，可补足正阳山等外围宗门关系。"},
    {"name": "马致", "aliases": [], "power": "山上", "description": "外围修士人物，适合增加山上群像与冲突节点。"},
    {"name": "苏琅", "aliases": [], "power": "山上", "description": "山上支线人物，适合补足高位修士与对战网络。"},
    {"name": "秋实", "aliases": [], "power": "老龙城", "description": "渡船与老龙城支线女性人物，可补足陈平安外出途中人际网络。"},
    {"name": "沈霖", "aliases": [], "power": "山水", "description": "山水神灵相关人物，适合补强地方山水与秩序网络。"},
    {"name": "周矩", "aliases": [], "power": "山上", "description": "外围修士与谋划线人物，可扩展山上冲突关系链。"},
    {"name": "刘高华", "aliases": [], "power": "江湖", "description": "江湖同行线人物，可补足陈平安早期外出见闻与同伴网络。"},
    {"name": "吴懿", "aliases": [], "power": "山水", "description": "山水与地方势力交叉线人物，适合扩充场域相关关系。"},
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unique_names(names: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for name in names:
        normalized = str(name).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def build_matchers(items: Sequence[dict], aliases_key: str = "aliases") -> List[Tuple[str, str]]:
    matchers: List[Tuple[str, str]] = []
    for item in items:
        canonical = str(item["name"]).strip()
        aliases = unique_names([canonical, *item.get(aliases_key, [])])
        for alias in aliases:
            matchers.append((alias, canonical))
    return sorted(matchers, key=lambda item: (-len(item[0]), item[0]))


def match_entities(text: str, matchers: Sequence[Tuple[str, str]]) -> List[Tuple[str, str, int, int]]:
    matches: List[Tuple[str, str, int, int]] = []
    occupied: List[Tuple[int, int]] = []

    for alias, canonical in matchers:
        start = 0
        while True:
            index = text.find(alias, start)
            if index < 0:
                break
            end = index + len(alias)
            overlaps = any(not (end <= left or index >= right) for left, right in occupied)
            if not overlaps:
                matches.append((canonical, alias, index, end))
                occupied.append((index, end))
            start = index + len(alias)

    return sorted(matches, key=lambda item: item[2])


def build_sentence_mentions(
    sentences: Sequence[str],
    character_matchers: Sequence[Tuple[str, str]],
    location_matchers: Sequence[Tuple[str, str]],
) -> Tuple[List[List[str]], List[List[str]]]:
    sentence_characters: List[List[str]] = []
    sentence_locations: List[List[str]] = []

    for sentence in sentences:
        character_matches = match_entities(sentence, character_matchers)
        location_matches = match_entities(sentence, location_matchers)
        sentence_characters.append(unique_names(match[0] for match in character_matches))
        sentence_locations.append(unique_names(match[0] for match in location_matches))

    return sentence_characters, sentence_locations


def all_cjk(text: str) -> bool:
    return bool(text) and all("\u4e00" <= char <= "\u9fff" for char in text)


def trim_candidate_noise(name: str) -> str:
    candidate = str(name).strip().strip("“”‘’『』「」《》〈〉【】（）()，。！？；：、 ")
    for token in LEADING_NOISE_TOKENS:
        if candidate.startswith(token) and len(candidate) - len(token) >= 2:
            candidate = candidate[len(token) :]
            break
    while candidate and candidate[-1] in TRAILING_NOISE_CHARS:
        candidate = candidate[:-1]
    return candidate


def normalize_mined_candidate(
    raw_name: str,
    *,
    blocked_names: set[str],
    known_names: set[str],
    location_names: set[str],
    sentence_text: str = "",
    source: str = "",
    match_start: int = -1,
    match_end: int = -1,
) -> Optional[str]:
    candidate = trim_candidate_noise(raw_name)
    if len(candidate) < 2 or len(candidate) > 4:
        return None
    if not all_cjk(candidate):
        return None
    if candidate in blocked_names or candidate in known_names or candidate in location_names:
        return None
    if candidate in NON_PERSON_CANDIDATES:
        return None
    if any(part in candidate for part in NON_PERSON_SUBSTRINGS):
        return None
    if is_pseudo_role_name(candidate, blocked_names=blocked_names):
        return None
    if any(known == candidate or known.startswith(candidate) or candidate.startswith(known) for known in known_names):
        return None

    first_char = candidate[0]
    if first_char not in COMMON_SURNAME_CHARS and first_char not in COMMON_NAME_PREFIXES:
        return None
    if first_char in COMMON_NAME_PREFIXES and candidate not in ALLOWED_TITLED_CANDIDATES:
        return None
    if source == "dialogue" and sentence_text and match_end >= 0:
        trailing_text = sentence_text[match_end : match_end + 6]
        if any(trailing_text.startswith(phrase) for phrase in CONTEXT_DENY_NEXT_PHRASES):
            return None
    return candidate


def audit_mined_candidate(
    candidate: str,
    *,
    evidence_item: dict,
    blocked_names: set[str],
) -> List[str]:
    reasons = audit_role_name(candidate, blocked_names=blocked_names)
    intro_hits = int(evidence_item["pattern_hits"].get("intro", 0))
    dialogue_hits = int(evidence_item["pattern_hits"].get("dialogue", 0))
    unit_count = len(evidence_item["units"])
    co_character_count = len(evidence_item["co_characters"])
    co_location_count = len(evidence_item["co_locations"])

    if dialogue_hits > 0 and intro_hits == 0 and int(evidence_item["sentence_count"]) <= 1:
        reasons.append("仅单次对话模式命中")
    if intro_hits == 0 and co_character_count == 0:
        reasons.append("缺少稳定人物共现")
    if intro_hits == 0 and unit_count < 3:
        reasons.append("跨章节单元覆盖不足")
    if intro_hits == 0 and co_character_count < 2 and not (co_character_count >= 1 and co_location_count >= 1):
        reasons.append("缺少稳定人物或地点牵连")

    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def infer_candidate_power(
    *,
    co_character_names: Iterable[str],
    character_config: Dict[str, dict],
    location_names: Iterable[str],
) -> str:
    power_counts = Counter(
        str(character_config[name].get("power", "")).strip()
        for name in co_character_names
        if name in character_config and str(character_config[name].get("power", "")).strip()
    )
    if power_counts:
        return power_counts.most_common(1)[0][0]

    for location_name in location_names:
        if location_name in LOCATION_POWER_HINTS:
            return LOCATION_POWER_HINTS[location_name]

    return "未归类"


def build_candidate_description(
    *,
    candidate_name: str,
    co_character_names: Sequence[str],
    location_names: Sequence[str],
    sample_sentences: Sequence[str],
) -> str:
    partners = "、".join(co_character_names[:2])
    locations = "、".join(location_names[:2])

    if partners and locations:
        return f"前三季叙事中多次出现，常与{partners}同场，主要活动于{locations}。"
    if partners:
        return f"前三季叙事中多次出现，常与{partners}同场，推动相关支线发展。"
    if locations:
        return f"前三季叙事中多次出现，主要活动于{locations}等场域。"
    if sample_sentences:
        return f"前三季叙事中多次出现，相关语境包括：{sample_sentences[0][:28]}。"
    return f"{candidate_name}在前三季叙事中多次出现，是可继续补充整理的重要支线人物。"


def mine_character_candidates(
    *,
    book: Sequence[dict],
    core_cast: dict,
    manual_overrides: dict,
) -> List[dict]:
    seed_characters = core_cast.get("characters", [])
    seed_names = {str(item["name"]).strip() for item in seed_characters if str(item.get("name", "")).strip()}
    known_names = set(seed_names)
    location_names = {
        str(item["name"]).strip()
        for item in core_cast.get("locations", [])
        if str(item.get("name", "")).strip()
    }
    blocked_names = {
        str(name).strip()
        for name in manual_overrides.get("blocked_aliases", [])
        if str(name).strip()
    }

    for item in seed_characters:
        known_names.update(unique_names(item.get("aliases", [])))
    for item in core_cast.get("locations", []):
        location_names.update(unique_names(item.get("aliases", [])))

    target_total = max(int(core_cast.get("candidate_target_total_roles", 160)), len(seed_characters))
    max_new_characters = max(0, target_total - len(seed_characters))
    if max_new_characters <= 0:
        return []

    evidence: Dict[str, dict] = {}

    for unit in book:
        unit_index = int(unit["juan_index"])
        for segment in unit.get("segments", []):
            for sentence in segment.get("sentences", []):
                sentence_text = str(sentence).strip()
                if not sentence_text:
                    continue

                co_characters = sorted(name for name in seed_names if name in sentence_text)
                co_locations = sorted(name for name in location_names if name in sentence_text)

                for source, pattern in MINED_CHARACTER_PATTERNS:
                    for match in pattern.finditer(sentence_text):
                        raw_name = match.group(1) + match.group(2) if source == "intro" and match.lastindex == 2 else match.group(1)
                        candidate = normalize_mined_candidate(
                            raw_name,
                            blocked_names=blocked_names,
                            known_names=known_names,
                            location_names=location_names,
                            sentence_text=sentence_text,
                            source=source,
                            match_start=match.start(),
                            match_end=match.end(),
                        )
                        if not candidate:
                            continue

                        entry = evidence.setdefault(
                            candidate,
                            {
                                "units": set(),
                                "sentence_count": 0,
                                "co_characters": Counter(),
                                "co_locations": Counter(),
                                "pattern_hits": Counter(),
                                "samples": [],
                            },
                        )
                        entry["units"].add(unit_index)
                        entry["sentence_count"] += 1
                        entry["pattern_hits"][source] += 1
                        entry["co_characters"].update(co_characters)
                        entry["co_locations"].update(co_locations)
                        if len(entry["samples"]) < 3 and sentence_text not in entry["samples"]:
                            entry["samples"].append(sentence_text)

    character_config = {str(item["name"]).strip(): item for item in seed_characters}
    selected: List[Tuple[int, str, dict]] = []
    rejected_audits: List[Tuple[str, List[str]]] = []

    for candidate, item in evidence.items():
        unit_count = len(item["units"])
        co_character_count = len(item["co_characters"])
        co_location_count = len(item["co_locations"])
        audit_reasons = audit_mined_candidate(candidate, evidence_item=item, blocked_names=blocked_names)
        if audit_reasons:
            rejected_audits.append((candidate, audit_reasons))
            continue

        if unit_count < 3:
            continue
        if not (co_character_count >= 2 or (co_character_count >= 1 and co_location_count >= 1)):
            continue

        intro_hits = int(item["pattern_hits"].get("intro", 0))
        dialogue_hits = int(item["pattern_hits"].get("dialogue", 0))
        if intro_hits == 0 and dialogue_hits < 2:
            continue
        if intro_hits == 0 and int(item["sentence_count"]) < 2:
            continue

        score = unit_count * 8 + co_character_count * 5 + co_location_count * 3 + intro_hits * 7 + dialogue_hits * 4 + int(item["sentence_count"])
        selected.append((score, candidate, item))

    selected.sort(key=lambda value: (-value[0], value[1]))

    if rejected_audits:
        print("Rejected suspicious mined role candidates:")
        for candidate, reasons in rejected_audits[:20]:
            print(f"  - {candidate}: {'；'.join(reasons)}")
        if len(rejected_audits) > 20:
            print(f"  ... and {len(rejected_audits) - 20} more")

    mined_characters: List[dict] = []
    for _, candidate, item in selected[:max_new_characters]:
        co_character_names = [name for name, _ in item["co_characters"].most_common(4)]
        location_names_sorted = [name for name, _ in item["co_locations"].most_common(3)]
        mined_characters.append(
            {
                "name": candidate,
                "aliases": [],
                "power": infer_candidate_power(
                    co_character_names=co_character_names,
                    character_config=character_config,
                    location_names=location_names_sorted,
                ),
                "description": build_candidate_description(
                    candidate_name=candidate,
                    co_character_names=co_character_names,
                    location_names=location_names_sorted,
                    sample_sentences=item["samples"],
                ),
                "mined": True,
                "source_units": sorted(item["units"]),
            }
        )

    return mined_characters


def choose_summary_sentences(
    sentences: Sequence[str],
    sentence_characters: Sequence[Sequence[str]],
    sentence_locations: Sequence[Sequence[str]],
    limit: int = 3,
) -> List[str]:
    prioritized: List[str] = []
    fallback: List[str] = []

    for sentence, characters, locations in zip(sentences, sentence_characters, sentence_locations):
        if characters or locations:
            prioritized.append(sentence)
        elif sentence:
            fallback.append(sentence)

    selected = prioritized[:limit]
    if len(selected) < limit:
        selected.extend(fallback[: limit - len(selected)])
    return selected


def classify_relation_action(sentence: str, relation_keywords: Sequence[dict]) -> Optional[str]:
    best_action: Optional[str] = None
    best_hits = 0
    for item in relation_keywords:
        keywords = [str(keyword).strip() for keyword in item.get("keywords", []) if str(keyword).strip()]
        hits = sum(1 for keyword in keywords if keyword in sentence)
        if hits > best_hits:
            best_hits = hits
            best_action = str(item["action"])
    return best_action


def orient_relation(characters: Sequence[str], sentence: str, action: str) -> List[Tuple[str, str]]:
    if len(characters) < 2:
        return []

    positions = sorted((sentence.find(name), name) for name in characters)
    ordered_names = unique_names(name for position, name in positions if position >= 0)
    if len(ordered_names) < 2:
        ordered_names = unique_names(characters)

    if action in SYMMETRIC_ACTIONS:
        limited = ordered_names[:4]
        return [(left, right) for left, right in combinations(limited, 2)]

    source = ordered_names[0]
    targets = ordered_names[1:4]
    return [(source, target) for target in targets if target != source]


def classify_event_type(
    unit_title: str,
    sentences: Sequence[str],
    event_type_rules: Sequence[dict],
    relation_actions: Sequence[Action],
) -> str:
    haystack = "\n".join([unit_title, *sentences])
    best_type = ""
    best_score = 0

    for rule in event_type_rules:
        event_type = str(rule.get("type", "")).strip()
        if not event_type:
            continue
        keywords = [str(keyword).strip() for keyword in rule.get("keywords", []) if str(keyword).strip()]
        hits = sum(1 for keyword in keywords if keyword in haystack)
        if hits > best_score:
            best_score = hits
            best_type = event_type

    if best_type:
        return best_type
    if relation_actions:
        return relation_actions[0].action
    return "剧情推进"


def match_event_rule(unit_title: str, sentences: Sequence[str], rules: Sequence[dict]) -> Optional[dict]:
    haystack = "\n".join([unit_title, *sentences])
    best_rule: Optional[dict] = None
    best_score = 0

    for rule in rules:
        keywords = rule.get("keywords", [])
        hits = sum(1 for keyword in keywords if keyword and keyword in haystack)
        min_keywords = int(rule.get("min_keywords", len(keywords) or 1))
        if hits >= min_keywords and hits > best_score:
            best_rule = rule
            best_score = hits

    return best_rule


def build_event_name(
    *,
    unit_title: str,
    event_type: str,
    participants: Sequence[str],
    location: Optional[str],
) -> str:
    if len(participants) >= 2 and location:
        base = f"{participants[0]}与{participants[1]}在{location}{event_type}"
    elif len(participants) >= 2:
        base = f"{participants[0]}与{participants[1]}{event_type}"
    elif participants and location:
        base = f"{participants[0]}在{location}{event_type}"
    elif participants:
        base = f"{participants[0]}{event_type}"
    elif location:
        base = f"{location}{event_type}"
    else:
        base = event_type or "关键场景"
    return f"{unit_title} · {base}"


def infer_significance(
    *,
    event_type: str,
    participants: Sequence[str],
    location: Optional[str],
) -> str:
    if len(participants) >= 2 and location:
        return f"在{location}推动{participants[0]}与{participants[1]}之间的{event_type}线。"
    if len(participants) >= 2:
        return f"推动{participants[0]}与{participants[1]}之间的{event_type}关系。"
    if participants:
        return f"对应{participants[0]}在叙事中的关键{event_type}节点。"
    if location:
        return f"对应{location}相关的关键{event_type}场景。"
    return f"对应当前章节中的关键{event_type}节点。"


def select_event_participants(
    *,
    sentence_characters: Sequence[Sequence[str]],
    relation_actions: Sequence[Action],
    rule: Optional[dict],
) -> List[str]:
    seeded = unique_names(rule.get("participants", []) if rule else [])
    if relation_actions:
        relation_participants = unique_names(
            name
            for relation in relation_actions
            for name in [*relation.from_roles, *relation.to_roles]
        )
        participants = unique_names([*seeded, *relation_participants])
        if participants:
            return participants[:4]

    counts = Counter(name for names in sentence_characters for name in names)
    ranked = [name for name, _ in counts.most_common(4)]
    return unique_names([*seeded, *ranked])[:4]


def build_event(
    *,
    unit: dict,
    segment: dict,
    sentences: Sequence[str],
    sentence_characters: Sequence[Sequence[str]],
    sentence_locations: Sequence[Sequence[str]],
    relation_actions: Sequence[Action],
    event_rules: Sequence[dict],
    event_type_rules: Sequence[dict],
) -> Optional[Event]:
    characters = unique_names(name for items in sentence_characters for name in items)
    locations = unique_names(name for items in sentence_locations for name in items)
    unit_title = str(unit["unit_title"])
    rule = match_event_rule(unit_title, sentences, event_rules)

    if not characters and not locations and not rule:
        return None

    participants = select_event_participants(
        sentence_characters=sentence_characters,
        relation_actions=relation_actions,
        rule=rule,
    )
    location = (rule.get("location") if rule and rule.get("location") else None) or (locations[0] if locations else None)
    description = " ".join(choose_summary_sentences(sentences, sentence_characters, sentence_locations))
    event_type = str(rule.get("event_type", "")) if rule else ""
    if not event_type:
        event_type = classify_event_type(unit_title, sentences, event_type_rules, relation_actions)
    name = str(rule["name"]) if rule else build_event_name(
        unit_title=unit_title,
        event_type=event_type,
        participants=participants,
        location=location,
    )
    background = str(rule.get("background", "")) if rule else ""
    significance = (
        str(rule["significance"])
        if rule and rule.get("significance")
        else infer_significance(event_type=event_type, participants=participants, location=location)
    )

    return Event(
        name=name,
        time=None,
        location=location,
        participants=participants,
        description=description or unit_title,
        background=background,
        significance=significance,
        related_action_indices=list(range(len(relation_actions))),
        source=f"{unit_title} · 段{int(segment['segment_index'])}",
        sentence_indexes_in_segment=list(range(len(sentences))),
        juan_index=int(unit["juan_index"]),
        segment_index=int(segment["segment_index"]),
    )


def build_segment_chunk(
    unit: dict,
    segment: dict,
    character_config: Dict[str, dict],
    location_config: Dict[str, dict],
    character_matchers: Sequence[Tuple[str, str]],
    location_matchers: Sequence[Tuple[str, str]],
    relation_keywords: Sequence[dict],
    event_rules: Sequence[dict],
    event_type_rules: Sequence[dict],
) -> Optional[ChunkExtraction]:
    sentences = [str(sentence).strip() for sentence in segment.get("sentences", []) if str(sentence).strip()]
    if not sentences:
        return None

    sentence_characters, sentence_locations = build_sentence_mentions(sentences, character_matchers, location_matchers)
    segment_characters = unique_names(name for items in sentence_characters for name in items)
    segment_locations = unique_names(name for items in sentence_locations for name in items)

    roles: List[Role] = []
    for name in segment_characters:
        config = character_config[name]
        indexes = [index for index, names in enumerate(sentence_characters) if name in names]
        description = " ".join(sentences[index] for index in indexes[:2])
        roles.append(
            Role(
                entity_type="person",
                name=name,
                alias=[alias for alias in config.get("aliases", []) if alias != name],
                original_description_in_book=description,
                description=str(config.get("description", "")),
                power=config.get("power"),
                sentence_indexes_in_segment=indexes,
                juan_index=int(unit["juan_index"]),
                segment_index=int(segment["segment_index"]),
            )
        )

    locations: List[Location] = []
    for name in segment_locations:
        config = location_config[name]
        indexes = [index for index, names in enumerate(sentence_locations) if name in names]
        associated = unique_names(character for index in indexes for character in sentence_characters[index])
        locations.append(
            Location(
                name=name,
                alias=[alias for alias in config.get("aliases", []) if alias != name],
                type=str(config.get("type", "")),
                description=str(config.get("description", "")),
                modern_name=str(config.get("modern_name", "")),
                coordinates=None,
                related_entities=associated,
                sentence_indexes_in_segment=indexes,
                juan_index=int(unit["juan_index"]),
                segment_index=int(segment["segment_index"]),
            )
        )

    relations: List[Action] = []
    seen_relations = set()
    for index, sentence in enumerate(sentences):
        characters = sentence_characters[index]
        if len(characters) < 2:
            continue
        action_name = classify_relation_action(sentence, relation_keywords)
        if not action_name:
            continue
        relation_location = sentence_locations[index][0] if sentence_locations[index] else (segment_locations[0] if segment_locations else None)
        for source, target in orient_relation(characters, sentence, action_name):
            key = (source, target, action_name, sentence)
            if key in seen_relations:
                continue
            seen_relations.add(key)
            relations.append(
                Action(
                    time=None,
                    from_roles=[source],
                    to_roles=[target],
                    action=action_name,
                    context=sentence,
                    result=None,
                    event_name=None,
                    location=relation_location,
                    is_commentary=False,
                    sentence_indexes_in_segment=[index],
                    juan_index=int(unit["juan_index"]),
                    segment_index=int(segment["segment_index"]),
                )
            )

    if not relations and len(segment_characters) == 2:
        combined_text = " ".join(sentences)
        action_name = classify_relation_action(combined_text, relation_keywords)
        if action_name:
            source, target = orient_relation(segment_characters, combined_text, action_name)[0]
            relations.append(
                Action(
                    time=None,
                    from_roles=[source],
                    to_roles=[target],
                    action=action_name,
                    context=combined_text,
                    result=None,
                    event_name=None,
                    location=segment_locations[0] if segment_locations else None,
                    is_commentary=False,
                    sentence_indexes_in_segment=list(range(len(sentences))),
                    juan_index=int(unit["juan_index"]),
                    segment_index=int(segment["segment_index"]),
                )
            )

    event = build_event(
        unit=unit,
        segment=segment,
        sentences=sentences,
        sentence_characters=sentence_characters,
        sentence_locations=sentence_locations,
        relation_actions=relations,
        event_rules=event_rules,
        event_type_rules=event_type_rules,
    )

    if event:
        for relation in relations:
            relation.event_name = event.name

    if not roles and not locations and not relations and not event:
        return None

    return ChunkExtraction(
        juan_index=int(unit["juan_index"]),
        segment_index=int(segment["segment_index"]),
        chunk_start_index=0,
        chunk_end_index=len(sentences),
        segment_start_time=str(segment.get("segment_start_time") or unit["unit_title"]),
        source_sentences=sentences,
        entities=roles,
        locations=locations,
        events=[event] if event else [],
        relations=relations,
        model_name="offline-rules-v2",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )


def write_store(chunks_by_juan: Dict[int, Dict[str, dict]], store_dir: Path) -> None:
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)

    last_juan = 0
    last_segment = 0
    total_chunks = 0

    for juan_index, chunks in sorted(chunks_by_juan.items()):
        if not chunks:
            continue
        path = store_dir / f"juan_{juan_index}.json"
        path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        total_chunks += len(chunks)
        last_juan = juan_index
        last_segment = max(item["segment_index"] for item in chunks.values())

    metadata = {
        "created_at": datetime.now().isoformat(),
        "version": "swordcoming-offline-v2",
        "progress": {
            "last_juan": last_juan,
            "last_segment": last_segment,
            "last_chunk": 0,
            "total_chunks_processed": total_chunks,
        },
    }
    (store_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def prune_suspicious_roles_from_knowledge_base(kb: Any, blocked_names: set[str]) -> List[Tuple[str, List[str]]]:
    suspicious_roles = [
        (role_id, audit_role_name(role.canonical_name, blocked_names=blocked_names))
        for role_id, role in kb.roles.items()
    ]
    suspicious_roles = [(role_id, reasons) for role_id, reasons in suspicious_roles if reasons]
    if not suspicious_roles:
        return []

    blocked_role_ids = {role_id for role_id, _ in suspicious_roles}
    kb.roles = {role_id: role for role_id, role in kb.roles.items() if role_id not in blocked_role_ids}
    kb.relations = {
        relation_id: relation
        for relation_id, relation in kb.relations.items()
        if relation.from_entity not in blocked_role_ids and relation.to_entity not in blocked_role_ids
    }
    kb.name_to_role_id = {
        name: role_id
        for name, role_id in kb.name_to_role_id.items()
        if role_id not in blocked_role_ids and not is_pseudo_role_name(name, blocked_names=blocked_names)
    }
    kb.power_to_roles = {
        power: [role_id for role_id in role_ids if role_id not in blocked_role_ids]
        for power, role_ids in kb.power_to_roles.items()
        if [role_id for role_id in role_ids if role_id not in blocked_role_ids]
    }
    kb.juan_to_roles = {
        juan: [role_id for role_id in role_ids if role_id not in blocked_role_ids]
        for juan, role_ids in kb.juan_to_roles.items()
    }
    kb.unit_to_roles = {
        unit: [role_id for role_id in role_ids if role_id not in blocked_role_ids]
        for unit, role_ids in kb.unit_to_roles.items()
    }
    for event in kb.events.values():
        event.participants = {participant for participant in event.participants if participant not in blocked_role_ids}
    kb.total_roles = len(kb.roles)
    kb.total_relations = len(kb.relations)
    return suspicious_roles


def sync_public_files(source_dir: Path, target_dir: Path, files: Sequence[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in files:
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, target_dir / name)
            print(f"Copied {source} -> {target_dir / name}")


def build_offline_data(
    book_path: Path,
    core_cast_path: Path,
    store_dir: Path,
    kb_output: Path,
    writer_output: Path,
    unit_progress_index_path: Path,
    book_config_path: Path,
    manual_overrides_path: Path,
    sync_output: bool = False,
    public_data_dir: Optional[Path] = None,
    max_units: Optional[int] = None,
    synopses_output: Optional[Path] = None,
    key_events_output: Optional[Path] = None,
) -> dict:
    book = load_json(book_path)
    core_cast = load_json(core_cast_path)
    manual_overrides = load_json(manual_overrides_path)

    if max_units is not None:
        book = book[:max_units]

    base_characters = core_cast.get("characters", [])
    base_character_names = {item["name"] for item in base_characters}
    curated_extra_characters = [
        item for item in MANUAL_EXTRA_CHARACTERS if item["name"] not in base_character_names
    ]
    character_seeds = [*base_characters, *curated_extra_characters]
    core_cast_for_extraction = {**core_cast, "characters": character_seeds}

    mined_characters = mine_character_candidates(
        book=book,
        core_cast=core_cast_for_extraction,
        manual_overrides=manual_overrides,
    )
    augmented_characters = [
        *character_seeds,
        *[item for item in mined_characters if item["name"] not in {character["name"] for character in character_seeds}],
    ]

    character_config = {item["name"]: item for item in augmented_characters}
    location_config = {item["name"]: item for item in core_cast.get("locations", [])}
    character_matchers = build_matchers(augmented_characters)
    location_matchers = build_matchers(core_cast.get("locations", []))

    chunks_by_juan: Dict[int, Dict[str, dict]] = defaultdict(dict)
    extracted_roles = 0
    extracted_locations = 0
    extracted_events = 0
    extracted_relations = 0

    for unit in book:
        for segment in unit.get("segments", []):
            chunk = build_segment_chunk(
                unit=unit,
                segment=segment,
                character_config=character_config,
                location_config=location_config,
                character_matchers=character_matchers,
                location_matchers=location_matchers,
                relation_keywords=core_cast.get("relation_keywords", []),
                event_rules=core_cast.get("event_rules", []),
                event_type_rules=core_cast.get("event_type_rules", []),
            )
            if chunk is None:
                continue

            key = f"{chunk.juan_index}-{chunk.segment_index}-{chunk.chunk_start_index}"
            chunks_by_juan[chunk.juan_index][key] = chunk.model_dump()
            extracted_roles += len(chunk.entities)
            extracted_locations += len(chunk.locations)
            extracted_events += len(chunk.events)
            extracted_relations += len(chunk.relations)

    write_store(chunks_by_juan, store_dir)

    kb = load_and_resolve(
        str(store_dir),
        unit_progress_index_path=str(unit_progress_index_path),
        book_config_path=str(book_config_path),
        manual_overrides_path=str(manual_overrides_path),
    )
    blocked_role_names = {
        str(name).strip()
        for name in manual_overrides.get("blocked_aliases", [])
        if str(name).strip()
    }
    pruned_roles = prune_suspicious_roles_from_knowledge_base(kb, blocked_role_names)
    if pruned_roles:
        print("Pruned suspicious roles from unified knowledge base:")
        for role_id, reasons in pruned_roles[:20]:
            print(f"  - {role_id}: {'；'.join(reasons)}")
        if len(pruned_roles) > 20:
            print(f"  ... and {len(pruned_roles) - 20} more")
    save_unified_knowledge_base(kb, str(kb_output))

    suspicious = validate_unified_knowledge(kb_output)
    if suspicious:
        raise ValueError(f"Unified knowledge output still contains placeholder question marks: {suspicious[:5]}")

    writer_payload = build_writer_insights_file(
        kb=kb,
        unit_progress_index_path=unit_progress_index_path,
        core_cast_path=core_cast_path,
        output_path=writer_output,
    )
    writer_suspicious = validate_unified_knowledge(writer_output)
    if writer_suspicious:
        raise ValueError(f"Writer insights output still contains placeholder question marks: {writer_suspicious[:5]}")

    # --- Season overview audit ---
    upi = load_json(unit_progress_index_path)
    audit = build_audit(writer_payload, upi)
    audit_output = kb_output.parent / "season_overview_audit.json"
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Season overview audit → {audit_output}")
    if not audit.get("all_seasons_roles_evidence_backed"):
        raise ValueError("Season overview audit FAILED: some priority_roles lack chapter evidence")
    if not audit.get("all_seasons_beats_in_range"):
        raise ValueError("Season overview audit FAILED: some story beats are out of season range")
    if not audit.get("all_seasons_beats_unique_names"):
        raise ValueError("Season overview audit FAILED: duplicate beat names detected")
    if not audit.get("all_seasons_template_names_backed"):
        raise ValueError("Season overview audit FAILED: some template-injected role names lack chapter evidence")

    # --- Chapter synopses ---
    _synopses_path = synopses_output or (kb_output.parent / "chapter_synopses.json")
    chapter_synopses = build_chapter_synopses_file(
        kb=kb,
        unit_progress_index_path=unit_progress_index_path,
        core_cast_path=core_cast_path,
        output_path=_synopses_path,
    )

    # --- Key events index ---
    _key_events_path = key_events_output or (kb_output.parent / "key_events_index.json")
    key_events_chapters = build_key_events_index_file(
        kb=kb,
        unit_progress_index_path=unit_progress_index_path,
        core_cast_path=core_cast_path,
        output_path=_key_events_path,
    )

    if sync_output and public_data_dir is not None:
        sync_public_files(book_path.parent, public_data_dir, DEFAULT_SYNC_FILES)

    return {
        "chunks": sum(len(chunks) for chunks in chunks_by_juan.values()),
        "roles": kb.total_roles,
        "locations": kb.total_locations,
        "events": kb.total_events,
        "relations": kb.total_relations,
        "raw_roles": extracted_roles,
        "raw_locations": extracted_locations,
        "raw_events": extracted_events,
        "raw_relations": extracted_relations,
        "seed_roles": len(base_characters),
        "curated_extra_seed_roles": len(curated_extra_characters),
        "mined_roles": len(mined_characters),
        "augmented_role_seeds": len(augmented_characters),
        "pruned_suspicious_roles": len(pruned_roles),
        "writer_character_arcs": writer_payload["summary"]["character_arc_count"],
        "writer_season_overviews": writer_payload["summary"]["season_overview_count"],
        "writer_curated_relationships": writer_payload["summary"]["curated_relationship_count"],
        "writer_conflict_chains": writer_payload["summary"]["conflict_chain_count"],
        "writer_foreshadowing_threads": writer_payload["summary"]["foreshadowing_thread_count"],
        "audit_roles_evidence_backed": audit.get("all_seasons_roles_evidence_backed", False),
        "audit_beats_in_range": audit.get("all_seasons_beats_in_range", False),
        "audit_beats_unique_names": audit.get("all_seasons_beats_unique_names", False),
        "chapter_synopses_count": len(chapter_synopses),
        "key_events_chapters": len(key_events_chapters),
        "key_events_total": sum(len(ch["key_events"]) for ch in key_events_chapters),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Sword Coming offline knowledge data without model APIs.")
    parser.add_argument("--book", default="data/swordcoming_book.json", help="Input Sword Coming book JSON.")
    parser.add_argument("--core-cast", default="data/swordcoming_core_cast.json", help="Core cast/location config.")
    parser.add_argument("--store-dir", default="data/swordcoming_offline_store", help="Offline extraction store output dir.")
    parser.add_argument("--kb-output", default="data/unified_knowledge.json", help="Unified knowledge output path.")
    parser.add_argument("--writer-output", default="data/writer_insights.json", help="Writer insights output path.")
    parser.add_argument("--unit-progress-index", default="data/unit_progress_index.json", help="Unit progress index path.")
    parser.add_argument("--book-config", default="data/book_config.json", help="Book config path.")
    parser.add_argument("--manual-overrides", default="data/swordcoming_manual_overrides.json", help="Manual overrides path.")
    parser.add_argument("--no-sync", action="store_true", help="Skip syncing output files into visualization/public/data.")
    parser.add_argument("--public-data-dir", default="visualization/public/data", help="Vite public/data directory.")
    parser.add_argument("--synopses-output", default="data/chapter_synopses.json", help="Chapter synopses output path.")
    parser.add_argument("--key-events-output", default="data/key_events_index.json", help="Key events index output path.")
    parser.add_argument("--max-units", type=int, default=None, help="Optional limit for quick iteration.")
    args = parser.parse_args()

    stats = build_offline_data(
        book_path=Path(args.book),
        core_cast_path=Path(args.core_cast),
        store_dir=Path(args.store_dir),
        kb_output=Path(args.kb_output),
        writer_output=Path(args.writer_output),
        unit_progress_index_path=Path(args.unit_progress_index),
        book_config_path=Path(args.book_config),
        manual_overrides_path=Path(args.manual_overrides),
        sync_output=not args.no_sync,
        public_data_dir=Path(args.public_data_dir),
        max_units=args.max_units,
        synopses_output=Path(args.synopses_output),
        key_events_output=Path(args.key_events_output),
    )

    print("Built Sword Coming offline data:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
