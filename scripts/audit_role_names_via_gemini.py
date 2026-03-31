#!/usr/bin/env python3
"""Gemini-powered boundary review of stable role designators.

Sends all current role names from unified_knowledge.json to Gemini and asks it
to classify each name by *how it functions in the imported corpus*:

- canonical_name: standard canonical role id
- stable_designator: not necessarily a legal name, but a stable / single-target
  role designator in the current text (e.g. 杨老头, 火龙真人)
- alias_of: a stable designator that should merge into a canonical role
- noise: extraction noise, narration fragment, voice/action descriptor, etc.
- uncertain: genuinely ambiguous and needs review

This is a **quality gate** — meant to be run after rule-based pruning to catch
cases that pattern matching cannot detect. Results are written to a JSON
report. Noise or uncertain items should be reviewed before the next rebuild.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.character_quality import build_allowed_special_designator_map
from swordcoming_pipeline.llm_json import extract_json_from_response

DEFAULT_MODEL = "gemini-2.5-flash-preview-05-20"
VALID_VERDICTS = {"genuine", "stable_designator", "alias_of", "noise", "uncertain"}

SYSTEM_PROMPT = textwrap.dedent("""\
你是中国网络小说《剑来》（烽火戏诸侯 著）的角色名专家审计员。

你的任务是审阅一份从小说文本中自动提取出的“角色指称”列表，判断每一个名字在
**当前已导入文本**中，是否构成一个稳定且单义地指向同一个角色的指称。

你不是在判断“它是不是身份证式本名”，而是在判断：
- 它是不是一个可以稳定保留的角色指称
- 或者它是否应该合并到某个既有 canonical role
- 或者它根本就是提取噪音

常见噪音类型（需要识别出来）：
1. **语音/动作描写词** — 如"沙哑""低沉"是形容嗓音的词，不是人名
2. **人名+动作后缀粘连** — 如"俞真意冷"是"俞真意"+"冷（冷漠）"的断句错误
3. **泛称且不单义** — 如"白衣少年""中年儒士""老人""女子"是泛称，不是稳定单义角色指称
4. **叙述残片** — 如"管狮子""后笑眯眯"是从句子中截断出来的
5. **同一角色的错误别名** — 如将不存在的拼接结果当作独立角色

对于每个名字，给出以下分类之一：
- "genuine" — 确认是 canonical role 名或可直接保留的正式角色名
- "stable_designator" — 不是本名，但在当前语料中稳定且单义地指向同一个角色，应保留
- "alias_of" — 稳定指向某个既有 canonical role，应合并；同时提供 canonical_target
- "noise" — 确认不是角色指称，是提取噪音
- "uncertain" — 无法确定，需要人工复核

你必须返回严格 JSON，格式如下：
{
  "audit_results": [
    {"name": "陈平安", "verdict": "genuine", "reason": "主角"},
    {"name": "杨老头", "verdict": "stable_designator", "reason": "书内稳定单义称谓"},
    {"name": "桂姨", "verdict": "alias_of", "canonical_target": "桂夫人", "reason": "稳定称谓，应合并"},
    {"name": "沙哑", "verdict": "noise", "reason": "语音描写词，不是人名"},
    ...
  ],
  "noise_count": 2,
  "uncertain_count": 0
}

注意事项：
- 《剑来》中存在不少不是身份证式本名、但在书内稳定单指某一角色的称谓
- 像“杨老头”“火龙真人”“大骊皇帝”“于夫人”“桂夫人”这种，如果在当前语料中稳定单指同一人，不应判为 noise
- 像“桂姨”这种，如果在当前语料中稳定指向“桂夫人”，应判为 alias_of
- 不要仅因为“像称谓、不像本名”就判为噪音
- 优先保守：如果不确定，标记为 "uncertain" 而非 "noise"
""")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_user_prompt(
    role_names: List[str],
    allowed_special_designators: Dict[str, Dict[str, str]] | None = None,
) -> str:
    names_text = "\n".join(f"  {i+1}. {name}" for i, name in enumerate(role_names))
    allowlist_lines = ""
    if allowed_special_designators:
        rendered = []
        for name, entry in sorted(allowed_special_designators.items()):
            resolution = entry.get("resolution", "keep_as_canonical")
            target = entry.get("canonical_target", name)
            kind = entry.get("kind", "honorific")
            if resolution == "merge_to_canonical":
                rendered.append(f"- {name}: stable_designator/alias_of 候选，通常应合并到 {target}（{kind}）")
            else:
                rendered.append(f"- {name}: stable_designator 候选，应优先视为可保留的稳定称谓（{kind}）")
        allowlist_lines = "\n\n以下是当前项目已知的“特殊但稳定的角色指称”样例，请不要误判为 noise：\n" + "\n".join(rendered)
    return textwrap.dedent(f"""\
请审阅以下从《剑来》自动提取的 {len(role_names)} 个角色指称，判断每个是否属于：
- genuine
- stable_designator
- alias_of
- noise
- uncertain

判断标准是：它在当前已导入文本中，是否构成一个稳定且单义的角色指称，而不是“是不是本名”。

{names_text}
{allowlist_lines}

请按照 system prompt 指定的 JSON 格式返回审计结果。
""")


def _normalize_verdict(raw: Any) -> str:
    verdict = str(raw or "").strip()
    return verdict if verdict in VALID_VERDICTS else "uncertain"


def _postprocess_audit_results(
    audit_results: List[Dict[str, Any]],
    allowed_special_designators: Dict[str, Dict[str, str]] | None = None,
    audited_names: set[str] | None = None,
) -> List[Dict[str, Any]]:
    allowed_special_designators = allowed_special_designators or {}
    audited_names = audited_names or set()
    by_name: Dict[str, Dict[str, Any]] = {}

    for item in audit_results:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized = dict(item)
        normalized["name"] = name
        normalized["verdict"] = _normalize_verdict(item.get("verdict"))
        reason = str(item.get("reason", "")).strip()
        if reason:
            normalized["reason"] = reason
        else:
            normalized["reason"] = ""
        canonical_target = str(item.get("canonical_target", "")).strip()
        if canonical_target:
            normalized["canonical_target"] = canonical_target

        override = allowed_special_designators.get(name)
        if override:
            target = override.get("canonical_target", name) or name
            kind = override.get("kind", "honorific")
            if override.get("resolution") == "merge_to_canonical":
                normalized["verdict"] = "alias_of"
                normalized["canonical_target"] = target
                normalized["reason"] = normalized["reason"] or f"当前语料中的稳定单义称谓，应合并到 {target}（{kind}）"
            else:
                normalized["verdict"] = "stable_designator"
                normalized["canonical_target"] = target
                normalized["reason"] = normalized["reason"] or f"当前语料中的稳定单义角色称谓（{kind}）"
        elif normalized["verdict"] == "alias_of" and not normalized.get("canonical_target"):
            normalized["verdict"] = "uncertain"
            normalized["reason"] = normalized["reason"] or "模型判断为 alias_of，但缺少 canonical_target"

        by_name[name] = normalized

    for name, override in allowed_special_designators.items():
        if audited_names and name not in audited_names:
            continue
        if name in by_name:
            continue
        target = override.get("canonical_target", name) or name
        kind = override.get("kind", "honorific")
        resolution = override.get("resolution", "keep_as_canonical")
        if resolution == "merge_to_canonical":
            by_name[name] = {
                "name": name,
                "verdict": "alias_of",
                "canonical_target": target,
                "reason": f"当前语料中的稳定单义称谓，应合并到 {target}（{kind}）",
            }
        else:
            by_name[name] = {
                "name": name,
                "verdict": "stable_designator",
                "canonical_target": target,
                "reason": f"当前语料中的稳定单义角色称谓（{kind}）",
            }

    return [by_name[name] for name in sorted(by_name.keys())]


def run_audit(
    *,
    kb_path: Path,
    output_path: Path,
    manual_overrides_path: Path,
    model_name: str,
    api_key: str,
) -> Dict[str, Any]:
    """Run Gemini boundary review on all role names in the KB."""
    kb = _load_json(kb_path)
    manual_overrides = _load_json(manual_overrides_path)
    allowed_special_designators = build_allowed_special_designator_map(
        manual_overrides.get("allowed_special_designators", [])
    )
    role_names = sorted(kb.get("roles", {}).keys())
    print(f"Loaded {len(role_names)} role names from {kb_path}")

    # Lazy import to avoid requiring google-genai for tests
    from google import genai

    client = genai.Client(api_key=api_key)
    user_prompt = _build_user_prompt(role_names, allowed_special_designators)

    print(f"Sending {len(role_names)} names to Gemini ({model_name}) for boundary review...")
    response = client.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config={"system_instruction": SYSTEM_PROMPT},
    )

    text = ""
    if response.candidates:
        for part in response.candidates[0].content.parts:
            text += part.text or ""
    if not text:
        raise RuntimeError("Gemini returned empty response")

    result = extract_json_from_response(text)
    audit_results = _postprocess_audit_results(
        result.get("audit_results", []),
        allowed_special_designators=allowed_special_designators,
        audited_names=set(role_names),
    )

    # Summarize
    noise = [r for r in audit_results if r.get("verdict") == "noise"]
    uncertain = [r for r in audit_results if r.get("verdict") == "uncertain"]
    genuine = [r for r in audit_results if r.get("verdict") == "genuine"]
    stable_designator = [r for r in audit_results if r.get("verdict") == "stable_designator"]
    alias_of = [r for r in audit_results if r.get("verdict") == "alias_of"]

    report = {
        "metadata": {
            "model": model_name,
            "kb_path": str(kb_path),
            "manual_overrides_path": str(manual_overrides_path),
            "total_roles": len(role_names),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "summary": {
            "genuine_count": len(genuine),
            "stable_designator_count": len(stable_designator),
            "alias_of_count": len(alias_of),
            "noise_count": len(noise),
            "uncertain_count": len(uncertain),
        },
        "stable_designator": stable_designator,
        "alias_of": alias_of,
        "noise": noise,
        "uncertain": uncertain,
        "all_results": audit_results,
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAudit report written to {output_path}")
    print(f"  Genuine:   {len(genuine)}")
    print(f"  Stable:    {len(stable_designator)}")
    print(f"  Alias:     {len(alias_of)}")
    print(f"  Noise:     {len(noise)}")
    print(f"  Uncertain: {len(uncertain)}")

    if noise:
        print("\nFlagged as NOISE:")
        for item in noise:
            print(f"    - {item['name']}: {item.get('reason', '')}")

    if uncertain:
        print("\nFlagged as UNCERTAIN:")
        for item in uncertain:
            print(f"    - {item['name']}: {item.get('reason', '')}")

    if not noise and not uncertain:
        print("\nAll reviewed role names were classified as genuine, stable_designator, or alias_of.")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gemini boundary review of canonical role names."
    )
    parser.add_argument("--kb", default="data/unified_knowledge.json", help="Unified knowledge JSON.")
    parser.add_argument(
        "--manual-overrides",
        default="data/swordcoming_manual_overrides.json",
        help="Manual overrides JSON.",
    )
    parser.add_argument("--output", default="data/role_name_audit_report.json", help="Output report path.")
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        help="Gemini model name.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        return 1

    report = run_audit(
        kb_path=Path(args.kb),
        output_path=Path(args.output),
        manual_overrides_path=Path(args.manual_overrides),
        model_name=args.model,
        api_key=api_key,
    )

    # Non-zero exit if noise or uncertain items found
    if report["summary"]["noise_count"] > 0 or report["summary"]["uncertain_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
