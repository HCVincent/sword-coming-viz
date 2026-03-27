#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEASON_SOURCE_DOCUMENTS = {
    "第一季": "剑来第一季原著.doc",
    "第二季": "剑来第二季原著.docx",
    "第三季": "剑来第三季原著.docx",
}

INVALID_FILENAME_CHARS = '<>:"/\\|?*'


@dataclass(frozen=True)
class UnitMeta:
    unit_index: int
    volume_index: int
    volume_title: str
    chapter_title: str
    relative_path: str


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sanitize_filename(name: str) -> str:
    sanitized = str(name).strip()
    for char in INVALID_FILENAME_CHARS:
        sanitized = sanitized.replace(char, " ")
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized.replace(" ", "_")


def split_volume_and_chapter(title: str) -> tuple[str, str]:
    parts = re.split(r"\s+", str(title).strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return str(title).strip(), str(title).strip()


def render_front_matter(unit: dict, volume_title: str, chapter_title: str) -> str:
    source_document = SEASON_SOURCE_DOCUMENTS.get(str(unit.get("season_name", "")), "")
    lines = [
        "---",
        "book_id: swordcoming",
        f"unit_index: {int(unit['unit_index'])}",
        f"juan_index: {int(unit['juan_index'])}",
        f"season_index: {int(unit.get('season_index', 0))}",
        f"season_name: {unit.get('season_name', '')}",
        f"volume_title: {volume_title}",
        f"chapter_title: {chapter_title}",
        f"progress_start: {int(unit.get('progress_start', 0))}",
        f"progress_end: {int(unit.get('progress_end', 0))}",
        f"source_document: {source_document}",
        "---",
        "",
    ]
    return "\n".join(lines)


def render_segment(segment: dict) -> str:
    segment_index = int(segment["segment_index"])
    progress_index = int(segment.get("progress_index", 0))
    progress_label = str(segment.get("progress_label") or "")
    body = "".join(str(sentence) for sentence in segment.get("sentences", [])).strip()
    lines = [
        f'<a id="seg-{segment_index:03d}"></a>',
        f"### 段 {segment_index} · 进度 {progress_index}",
    ]
    if progress_label:
        lines.append(f"- 段落标签：{progress_label}")
    lines.extend(["", body, ""])
    return "\n".join(lines)


def render_unit_markdown(unit: dict) -> str:
    volume_title, chapter_title = split_volume_and_chapter(str(unit["unit_title"]))
    source_document = SEASON_SOURCE_DOCUMENTS.get(str(unit.get("season_name", "")), "")
    header_lines = [
        render_front_matter(unit, volume_title, chapter_title),
        f"# {unit['unit_title']}",
        "",
        f"- 季别：{unit.get('season_name', '')}",
        f"- 卷名：{volume_title}",
        f"- 章名：{chapter_title}",
        f"- 全书章节序号：{int(unit['unit_index'])}",
        f"- 卷内序号：{int(unit['juan_index'])}",
        f"- 叙事进度：{int(unit.get('progress_start', 0))} - {int(unit.get('progress_end', 0))}",
        f"- 来源文档：{source_document}",
        "",
        "## 正文",
        "",
    ]
    segment_blocks = [render_segment(segment) for segment in unit.get("segments", [])]
    return "\n".join(header_lines + segment_blocks).strip() + "\n"


def build_volume_readme(volume_title: str, units: Sequence[dict]) -> str:
    lines = [
        f"# {volume_title}",
        "",
        f"- 章节数：{len(units)}",
        "",
        "## 章节目录",
        "",
    ]
    for unit in units:
        _, chapter_title = split_volume_and_chapter(str(unit["unit_title"]))
        file_name = f"{int(unit['unit_index']):03d}_{sanitize_filename(chapter_title)}.md"
        lines.append(f"- [{unit['unit_title']}](./{file_name})")
    lines.append("")
    return "\n".join(lines)


def build_root_readme(volume_groups: Sequence[tuple[str, Sequence[dict], str]]) -> str:
    total_units = sum(len(units) for _, units, _ in volume_groups)
    lines = [
        "# 剑来章节导出",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 卷数：{len(volume_groups)}",
        f"- 章节数：{total_units}",
        "",
        "## 卷目录",
        "",
    ]
    for volume_title, units, directory_name in volume_groups:
        lines.append(f"- [{volume_title}](./{directory_name}/README.md) · {len(units)} 章")
    lines.append("")
    return "\n".join(lines)


def build_index_entry(unit: dict, meta: UnitMeta) -> dict:
    source_document = SEASON_SOURCE_DOCUMENTS.get(str(unit.get("season_name", "")), "")
    return {
        "unit_index": int(unit["unit_index"]),
        "juan_index": int(unit["juan_index"]),
        "season_index": int(unit.get("season_index", 0)),
        "season_name": str(unit.get("season_name", "")),
        "title": str(unit["unit_title"]),
        "volume_index": meta.volume_index,
        "volume_title": meta.volume_title,
        "chapter_title": meta.chapter_title,
        "relative_path": meta.relative_path.replace("\\", "/"),
        "progress_start": int(unit.get("progress_start", 0)),
        "progress_end": int(unit.get("progress_end", 0)),
        "source_document": source_document,
        "segments": [
            {
                "segment_index": int(segment["segment_index"]),
                "progress_index": int(segment.get("progress_index", 0)),
                "progress_label": str(segment.get("progress_label") or ""),
                "anchor": f"seg-{int(segment['segment_index']):03d}",
            }
            for segment in unit.get("segments", [])
        ],
    }


def write_index(path: Path, entries: Sequence[dict]) -> None:
    payload = {
        "book_id": "swordcoming",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "unit_count": len(entries),
        "units": list(entries),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_chapters(
    *,
    book_path: Path,
    output_dir: Path,
    index_output: Path | None = None,
    sync_public_data_dir: Path | None = None,
    sync_public_chapters_dir: Path | None = None,
) -> dict:
    book = load_json(book_path)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped_units: list[tuple[str, list[dict], str]] = []
    index_entries: list[dict] = []
    volume_index_by_title: dict[str, int] = {}

    for unit in book:
        volume_title, _ = split_volume_and_chapter(str(unit["unit_title"]))
        if volume_title not in volume_index_by_title:
            volume_index_by_title[volume_title] = len(volume_index_by_title) + 1
            directory_name = f"{volume_index_by_title[volume_title]:03d}_{sanitize_filename(volume_title)}"
            grouped_units.append((volume_title, [], directory_name))
        for idx, (group_title, units, directory_name) in enumerate(grouped_units):
            if group_title == volume_title:
                units.append(unit)
                grouped_units[idx] = (group_title, units, directory_name)
                break

    for volume_title, units, directory_name in grouped_units:
        volume_index = volume_index_by_title[volume_title]
        volume_dir = output_dir / directory_name
        volume_dir.mkdir(parents=True, exist_ok=True)
        for unit in units:
            _, chapter_title = split_volume_and_chapter(str(unit["unit_title"]))
            file_name = f"{int(unit['unit_index']):03d}_{sanitize_filename(chapter_title)}.md"
            unit_path = volume_dir / file_name
            unit_path.write_text(render_unit_markdown(unit), encoding="utf-8")
            meta = UnitMeta(
                unit_index=int(unit["unit_index"]),
                volume_index=volume_index,
                volume_title=volume_title,
                chapter_title=chapter_title,
                relative_path=str(Path(directory_name) / file_name),
            )
            index_entries.append(build_index_entry(unit, meta))

        (volume_dir / "README.md").write_text(build_volume_readme(volume_title, units), encoding="utf-8")

    (output_dir / "README.md").write_text(build_root_readme(grouped_units), encoding="utf-8")

    if index_output is not None:
        write_index(index_output, index_entries)
        if sync_public_data_dir is not None:
            sync_public_data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(index_output, sync_public_data_dir / index_output.name)

    if sync_public_chapters_dir is not None:
        if sync_public_chapters_dir.exists():
            shutil.rmtree(sync_public_chapters_dir)
        shutil.copytree(output_dir, sync_public_chapters_dir)

    return {
        "volumes": len(grouped_units),
        "chapters": len(index_entries),
        "output_dir": str(output_dir),
        "index_output": str(index_output) if index_output else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Sword Coming source text into volume/chapter markdown files.")
    parser.add_argument("--book", default="data/swordcoming_book.json", help="Input normalized book JSON.")
    parser.add_argument("--output-dir", default="chapters", help="Output directory for chapter markdown files.")
    parser.add_argument("--index-output", default="data/chapter_index.json", help="Output JSON index for chapter paths and segment anchors.")
    parser.add_argument(
        "--public-data-dir",
        default="visualization/public/data",
        help="Optional public data directory for syncing chapter_index.json.",
    )
    parser.add_argument(
        "--public-chapters-dir",
        default="visualization/public/chapters",
        help="Optional public chapters directory for syncing chapter markdown files.",
    )
    parser.add_argument("--skip-sync", action="store_true", help="Do not sync the chapter index into visualization/public/data.")
    args = parser.parse_args()

    stats = export_chapters(
        book_path=PROJECT_ROOT / args.book,
        output_dir=PROJECT_ROOT / args.output_dir,
        index_output=PROJECT_ROOT / args.index_output,
        sync_public_data_dir=None if args.skip_sync else PROJECT_ROOT / args.public_data_dir,
        sync_public_chapters_dir=None if args.skip_sync else PROJECT_ROOT / args.public_chapters_dir,
    )

    print("Exported Sword Coming chapters:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
