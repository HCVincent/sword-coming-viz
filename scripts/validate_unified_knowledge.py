#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, List


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
    return collect_suspicious_paths(payload)


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
