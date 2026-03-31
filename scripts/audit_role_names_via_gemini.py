#!/usr/bin/env python3
"""Gemini-powered boundary review of canonical role names.

Sends all current role names from unified_knowledge.json to Gemini and asks
it to classify each as: genuine character, likely noise, or uncertain.

This is a **quality gate** — meant to be run after rule-based pruning to catch
cases that pattern matching cannot detect.  Results are written to a JSON
report; any flagged names should be reviewed and, if confirmed, added to
swordcoming_manual_overrides.json → blocked_aliases before the next rebuild.

Usage:
    python scripts/audit_role_names_via_gemini.py [--kb data/unified_knowledge.json]

Requires GEMINI_API_KEY environment variable.
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

from swordcoming_pipeline.llm_json import extract_json_from_response

DEFAULT_MODEL = "gemini-2.5-flash-preview-05-20"

SYSTEM_PROMPT = textwrap.dedent("""\
你是中国网络小说《剑来》（烽火戏诸侯 著）的角色名专家审计员。

你的任务是审阅一份从小说文本中自动提取出的"角色名"列表，判断每一个名字是否
是**真实存在于小说中的角色名**。

常见噪音类型（需要识别出来）：
1. **语音/动作描写词** — 如"沙哑""低沉"是形容嗓音的词，不是人名
2. **人名+动作后缀粘连** — 如"俞真意冷"是"俞真意"+"冷（冷漠）"的断句错误
3. **纯称谓/头衔** — 如"白衣少年""中年儒士"是泛称，不是专有名
4. **叙述残片** — 如"管狮子""后笑眯眯"是从句子中截断出来的
5. **同一角色的错误别名** — 如将不存在的拼接结果当作独立角色

对于每个名字，给出以下分类之一：
- "genuine" — 确认是小说中的真实角色名
- "noise" — 确认不是角色名，是提取噪音
- "uncertain" — 无法确定，需要人工复核

你必须返回严格 JSON，格式如下：
{
  "audit_results": [
    {"name": "陈平安", "verdict": "genuine", "reason": "主角"},
    {"name": "沙哑", "verdict": "noise", "reason": "语音描写词，不是人名"},
    ...
  ],
  "noise_count": 2,
  "uncertain_count": 0
}

注意事项：
- 《剑来》角色名通常为 2-4 个汉字的中文人名
- 小说中确实存在一些不常见的角色名，不要仅因为"不像人名"就判定为噪音
- 优先保守：如果不确定，标记为 "uncertain" 而非 "noise"
""")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_user_prompt(role_names: List[str]) -> str:
    names_text = "\n".join(f"  {i+1}. {name}" for i, name in enumerate(role_names))
    return textwrap.dedent(f"""\
请审阅以下从《剑来》自动提取的 {len(role_names)} 个角色名，判断每个是否是真实角色名：

{names_text}

请按照 system prompt 指定的 JSON 格式返回审计结果。
""")


def run_audit(
    *,
    kb_path: Path,
    output_path: Path,
    model_name: str,
    api_key: str,
) -> Dict[str, Any]:
    """Run Gemini boundary review on all role names in the KB."""
    kb = _load_json(kb_path)
    role_names = sorted(kb.get("roles", {}).keys())
    print(f"Loaded {len(role_names)} role names from {kb_path}")

    # Lazy import to avoid requiring google-genai for tests
    from google import genai

    client = genai.Client(api_key=api_key)
    user_prompt = _build_user_prompt(role_names)

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
    audit_results = result.get("audit_results", [])

    # Summarize
    noise = [r for r in audit_results if r.get("verdict") == "noise"]
    uncertain = [r for r in audit_results if r.get("verdict") == "uncertain"]
    genuine = [r for r in audit_results if r.get("verdict") == "genuine"]

    report = {
        "metadata": {
            "model": model_name,
            "kb_path": str(kb_path),
            "total_roles": len(role_names),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "summary": {
            "genuine_count": len(genuine),
            "noise_count": len(noise),
            "uncertain_count": len(uncertain),
        },
        "noise": noise,
        "uncertain": uncertain,
        "all_results": audit_results,
    }

    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nAudit report written to {output_path}")
    print(f"  Genuine:   {len(genuine)}")
    print(f"  Noise:     {len(noise)}")
    print(f"  Uncertain: {len(uncertain)}")

    if noise:
        print("\n⚠️  Flagged as NOISE:")
        for item in noise:
            print(f"    - {item['name']}: {item.get('reason', '')}")

    if uncertain:
        print("\n⚠️  Flagged as UNCERTAIN:")
        for item in uncertain:
            print(f"    - {item['name']}: {item.get('reason', '')}")

    if not noise and not uncertain:
        print("\n✅ All role names confirmed as genuine characters.")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gemini boundary review of canonical role names."
    )
    parser.add_argument("--kb", default="data/unified_knowledge.json", help="Unified knowledge JSON.")
    parser.add_argument("--output", default="data/role_name_audit_report.json", help="Output report path.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model name.")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        return 1

    report = run_audit(
        kb_path=Path(args.kb),
        output_path=Path(args.output),
        model_name=args.model,
        api_key=api_key,
    )

    # Non-zero exit if noise or uncertain items found
    if report["summary"]["noise_count"] > 0 or report["summary"]["uncertain_count"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
