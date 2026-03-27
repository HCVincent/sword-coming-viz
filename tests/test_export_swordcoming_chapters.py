import json
from pathlib import Path

from scripts.export_swordcoming_chapters import export_chapters, render_unit_markdown, split_volume_and_chapter


def test_split_volume_and_chapter_splits_title():
    volume_title, chapter_title = split_volume_and_chapter("第一卷笼中雀 第一章 惊蛰")
    assert volume_title == "第一卷笼中雀"
    assert chapter_title == "第一章 惊蛰"


def test_render_unit_markdown_contains_segment_anchor_and_metadata():
    unit = {
        "unit_index": 1,
        "juan_index": 1,
        "unit_title": "第一卷笼中雀 第一章 惊蛰",
        "season_index": 1,
        "season_name": "第一季",
        "progress_start": 1,
        "progress_end": 3,
        "segments": [
            {
                "segment_index": 1,
                "progress_index": 1,
                "progress_label": "第一卷笼中雀 第一章 惊蛰 · 段1",
                "sentences": ["二月二，龙抬头。", "少年姓陈，名平安。"],
            }
        ],
    }

    markdown = render_unit_markdown(unit)
    assert "# 第一卷笼中雀 第一章 惊蛰" in markdown
    assert "来源文档：剑来第一季原著.doc" in markdown
    assert '<a id="seg-001"></a>' in markdown
    assert "二月二，龙抬头。少年姓陈，名平安。" in markdown


def test_export_chapters_writes_markdown_and_index(tmp_path):
    book_path = tmp_path / "swordcoming_book.json"
    output_dir = tmp_path / "chapters"
    index_output = tmp_path / "chapter_index.json"

    book_path.write_text(
        json.dumps(
            [
                {
                    "unit_index": 1,
                    "juan_index": 1,
                    "unit_title": "第一卷笼中雀 第一章 惊蛰",
                    "season_index": 1,
                    "season_name": "第一季",
                    "progress_start": 1,
                    "progress_end": 2,
                    "segments": [
                        {
                            "segment_index": 1,
                            "progress_index": 1,
                            "progress_label": "第一卷笼中雀 第一章 惊蛰 · 段1",
                            "sentences": ["二月二，龙抬头。"],
                        }
                    ],
                },
                {
                    "unit_index": 2,
                    "juan_index": 2,
                    "unit_title": "第一卷笼中雀 第二章 稚子",
                    "season_index": 1,
                    "season_name": "第一季",
                    "progress_start": 3,
                    "progress_end": 4,
                    "segments": [
                        {
                            "segment_index": 1,
                            "progress_index": 3,
                            "progress_label": "第一卷笼中雀 第二章 稚子 · 段1",
                            "sentences": ["巷子里风大。"],
                        }
                    ],
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    stats = export_chapters(book_path=book_path, output_dir=output_dir, index_output=index_output, sync_public_data_dir=None)

    assert stats["volumes"] == 1
    assert stats["chapters"] == 2
    assert (output_dir / "001_第一卷笼中雀" / "001_第一章_惊蛰.md").exists()
    assert (output_dir / "001_第一卷笼中雀" / "002_第二章_稚子.md").exists()

    index_payload = json.loads(index_output.read_text(encoding="utf-8"))
    assert index_payload["unit_count"] == 2
    assert index_payload["units"][0]["relative_path"] == "001_第一卷笼中雀/001_第一章_惊蛰.md"
    assert index_payload["units"][0]["segments"][0]["anchor"] == "seg-001"
