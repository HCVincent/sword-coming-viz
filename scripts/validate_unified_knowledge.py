#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.character_quality import audit_role_name


def is_suspicious_placeholder(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return False
    if set(stripped) == {"?"}:
        return True
    return "??" in stripped


def collect_suspicious_paths(node: Any, path: str = "$") -> List[str]:
    hits: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            hits.extend(collect_suspicious_paths(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            hits.extend(collect_suspicious_paths(value, f"{path}[{index}]"))
    elif isinstance(node, str) and is_suspicious_placeholder(node):
        hits.append(path)
    return hits


def validate_unified_knowledge(path: Path) -> List[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    suspicious = collect_suspicious_paths(payload)
    roles = payload.get("roles") if isinstance(payload, dict) else None
    if isinstance(roles, dict):
        for role_id, role_payload in roles.items():
            reasons = audit_role_name(str(role_id))
            if reasons:
                suspicious.append(f"$.roles.{role_id} [{'；'.join(reasons)}]")
            if isinstance(role_payload, dict):
                canonical_name = role_payload.get("canonical_name")
                if isinstance(canonical_name, str):
                    canonical_reasons = audit_role_name(canonical_name)
                    if canonical_reasons:
                        suspicious.append(
                            f"$.roles.{role_id}.canonical_name [{'；'.join(canonical_reasons)}]"
                        )
    return suspicious


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate unified_knowledge.json for placeholder question marks.")
    parser.add_argument("input", nargs="?", default="data/unified_knowledge.json", help="Path to unified_knowledge.json")
    args = parser.parse_args()

    path = Path(args.input)
    suspicious = validate_unified_knowledge(path)
    if suspicious:
        print(f"Found suspicious placeholder strings in {path}:")
        for item in suspicious[:50]:
            print(f"  - {item}")
        if len(suspicious) > 50:
            print(f"  ... and {len(suspicious) - 50} more")
        return 1

    print(f"{path} passed placeholder validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
