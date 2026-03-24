import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile
from xml.etree import ElementTree as ET


TITLE_WINDOW = 40
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


def extract_docx_paragraphs(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        texts = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
        text = "".join(texts).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def extract_doc_paragraphs(path: Path) -> list[str]:
    try:
        import win32com.client as win32
        import pywintypes
    except ImportError as exc:  # pragma: no cover - Windows-only path
        raise RuntimeError("Reading .doc files requires pywin32 on Windows.") from exc

    working_path = path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if not str(path).isascii():
        temp_dir = tempfile.TemporaryDirectory(prefix="swordcoming-doc-")
        working_path = Path(temp_dir.name) / f"input{path.suffix.lower()}"
        shutil.copy2(path, working_path)

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = None
    try:
        document = word.Documents.Open(
            str(working_path),
            ReadOnly=True,
            AddToRecentFiles=False,
            ConfirmConversions=False,
            OpenAndRepair=True,
            NoEncodingDialog=True,
        )
        try:
            content = str(document.Content.Text)
        except pywintypes.com_error as exc:
            raise RuntimeError(f"Failed to read {path}") from exc

        paragraphs = []
        for chunk in re.split(r"\r+", content):
            normalized = chunk.replace("\x07", "").strip()
            if normalized:
                paragraphs.append(normalized)
        return paragraphs
    finally:  # pragma: no cover - Windows-only path
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        try:
            word.Quit()
        except Exception:
            pass
        if temp_dir is not None:
            temp_dir.cleanup()


def extract_paragraphs(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx_paragraphs(path)
    if suffix == ".doc":
        return extract_doc_paragraphs(path)
    raise ValueError(f"Unsupported file type: {path}")


def infer_season_name(path: Path) -> str:
    match = re.search(r"(第[一二三四五六七八九十百千万两0-9]+季)", path.stem)
    return match.group(1) if match else path.stem


def chinese_numeral_to_int(text: str) -> int:
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}

    if text.isdigit():
        return int(text)

    total = 0
    current = 0
    for char in text:
        if char in digits:
            current = digits[char]
            continue
        if char in units:
            multiplier = units[char]
            total += (current or 1) * multiplier
            current = 0
    return total + current


def season_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"第([一二三四五六七八九十百千万两0-9]+)季", path.stem)
    if not match:
        return (10_000, path.name)
    return (chinese_numeral_to_int(match.group(1)), path.name)


def is_unit_title(text: str) -> bool:
    if not text.startswith("第"):
        return False
    window = text[:TITLE_WINDOW]
    return "章" in window or "回" in window


def split_sentences(paragraph: str) -> list[str]:
    normalized = re.sub(r"\s+", "", paragraph)
    if not normalized:
        return []

    return [part.strip() for part in SENTENCE_SPLIT_RE.split(normalized) if part.strip()]


def chunk_sentences(
    sentences: Iterable[str],
    max_sentences: int,
    max_chars: int,
) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0

    for sentence in sentences:
        if not sentence:
            continue
        next_chars = current_chars + len(sentence)
        if current and (len(current) >= max_sentences or next_chars > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(sentence)
        current_chars += len(sentence)

    if current:
        chunks.append(current)
    return chunks


def build_book(
    source_dir: Path,
    max_sentences: int,
    max_chars: int,
) -> tuple[list[dict], dict, dict]:
    units: list[dict] = []
    progress_index = 1
    unit_index = 1
    season_filters: list[dict] = []

    for season_index, path in enumerate(sorted(source_dir.iterdir(), key=season_sort_key), start=1):
        if path.suffix.lower() not in {".doc", ".docx"}:
            continue
        paragraphs = extract_paragraphs(path)
        season_name = infer_season_name(path)

        current_title: str | None = None
        current_body: list[str] = []
        season_unit_start: int | None = None
        season_progress_start: int | None = None
        season_unit_end: int | None = None
        season_progress_end: int | None = None

        def flush_unit() -> None:
            nonlocal current_title
            nonlocal current_body
            nonlocal progress_index
            nonlocal unit_index
            nonlocal season_unit_start
            nonlocal season_progress_start
            nonlocal season_unit_end
            nonlocal season_progress_end

            if not current_title or not current_body:
                return

            sentences: list[str] = []
            for paragraph in current_body:
                sentences.extend(split_sentences(paragraph))

            if not sentences:
                return

            segments = []
            start_progress = progress_index
            for segment_index, chunk in enumerate(
                chunk_sentences(sentences, max_sentences=max_sentences, max_chars=max_chars),
                start=1,
            ):
                segments.append(
                    {
                        "segment_index": segment_index,
                        "segment_start_time": current_title,
                        "progress_index": progress_index,
                        "progress_label": f"{current_title} · 段{segment_index}",
                        "sentences": chunk,
                    }
                )
                progress_index += 1

            end_progress = progress_index - 1
            if season_unit_start is None:
                season_unit_start = unit_index
                season_progress_start = start_progress
            season_unit_end = unit_index
            season_progress_end = end_progress

            units.append(
                {
                    "juan_index": unit_index,
                    "juan_title": current_title,
                    "unit_index": unit_index,
                    "unit_title": current_title,
                    "season_index": season_index,
                    "season_name": season_name,
                    "progress_start": start_progress,
                    "progress_end": end_progress,
                    "segments": segments,
                }
            )
            unit_index += 1

        for paragraph in paragraphs:
            if paragraph == "《剑来》":
                continue
            if is_unit_title(paragraph):
                flush_unit()
                current_title = paragraph
                current_body = []
            elif current_title:
                current_body.append(paragraph)
        flush_unit()

        if season_unit_start is not None and season_progress_start is not None:
            season_filters.append(
                {
                    "label": season_name,
                    "unit_range": [season_unit_start, season_unit_end],
                    "progress_range": [season_progress_start, season_progress_end],
                }
            )

        current_title = None
        current_body = []

    generated_at = datetime.now().isoformat()

    unit_index_payload = {
        "version": "v1",
        "generated_at": generated_at,
        "book_id": "swordcoming",
        "unit_label": "章节",
        "progress_label": "叙事进度",
        "total_units": len(units),
        "total_progress_points": progress_index - 1,
        "units": {
            str(unit["unit_index"]): {
                "unit_index": unit["unit_index"],
                "unit_title": unit["unit_title"],
                "season_index": unit["season_index"],
                "season_name": unit["season_name"],
                "progress_start": unit["progress_start"],
                "progress_end": unit["progress_end"],
            }
            for unit in units
        },
        "segments": {
            f"{unit['unit_index']}-{segment['segment_index']}": {
                "unit_index": unit["unit_index"],
                "segment_index": segment["segment_index"],
                "progress_index": segment["progress_index"],
                "progress_label": segment["progress_label"],
            }
            for unit in units
            for segment in unit["segments"]
        },
    }

    config_payload = {
        "book_id": "swordcoming",
        "title": "剑来",
        "subtitle": "原著内容可视化试点",
        "unit_label": "章节",
        "progress_label": "叙事进度",
        "has_geo_coordinates": False,
        "default_tab": "timeline",
        "quick_filters": [
            *season_filters,
            {
                "label": "全部",
                "unit_range": [1, len(units)],
                "progress_range": [1, progress_index - 1],
            },
        ],
    }

    return units, unit_index_payload, config_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Sword Coming book artifacts.")
    parser.add_argument(
        "--source-dir",
        default=".",
        help="Directory containing Sword Coming .doc/.docx files.",
    )
    parser.add_argument(
        "--output",
        default="data/swordcoming_book.json",
        help="Book JSON output path.",
    )
    parser.add_argument(
        "--index-output",
        default="data/unit_progress_index.json",
        help="Unit-progress index JSON output path.",
    )
    parser.add_argument(
        "--config-output",
        default="data/book_config.json",
        help="Book config JSON output path.",
    )
    parser.add_argument("--max-sentences", type=int, default=6, help="Max sentences per segment.")
    parser.add_argument("--max-chars", type=int, default=600, help="Max characters per segment.")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}", file=sys.stderr)
        return 1

    book, index_payload, config_payload = build_book(
        source_dir=source_dir,
        max_sentences=args.max_sentences,
        max_chars=args.max_chars,
    )

    output_path = Path(args.output)
    index_path = Path(args.index_output)
    config_path = Path(args.config_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Built Sword Coming units: {len(book)}")
    print(f"Total progress points: {index_payload['total_progress_points']}")
    print(f"Wrote {output_path}")
    print(f"Wrote {index_path}")
    print(f"Wrote {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
