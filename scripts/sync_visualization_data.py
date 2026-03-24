import argparse
import shutil
from pathlib import Path


DEFAULT_FILES = [
    "book_config.json",
    "unit_progress_index.json",
    "unified_knowledge.json",
    "writer_insights.json",
    "swordcoming_book.json",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync canonical data files into Vite public/data.")
    parser.add_argument("--source-dir", default="data", help="Canonical data directory.")
    parser.add_argument(
        "--target-dir",
        default="visualization/public/data",
        help="Destination directory served by Vite.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=DEFAULT_FILES,
        help="Specific files to sync.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    target_dir = Path(args.target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for name in args.files:
        source = source_dir / name
        if not source.exists():
            print(f"Skip missing file: {source}")
            continue
        shutil.copy2(source, target_dir / name)
        copied += 1
        print(f"Copied {source} -> {target_dir / name}")

    print(f"Synced {copied} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
