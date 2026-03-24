from pathlib import Path

from model.action import Action
from model.event import Event
from entity_resolution import EntityResolver
from scripts import build_swordcoming_book


def test_build_book_orders_seasons_and_generates_ranges(tmp_path, monkeypatch):
    files = [
        tmp_path / '剑来第三季原著.docx',
        tmp_path / '剑来第一季原著.doc',
        tmp_path / '剑来第二季原著.docx',
    ]
    for file in files:
        file.write_text('', encoding='utf-8')

    fixture_data = {
        '剑来第一季原著.doc': [
            '《剑来》',
            '第一卷笼中雀 第一章 惊蛰',
            '陈平安在泥瓶巷守夜。',
            '第一卷笼中雀 第二章 开门',
            '宋集薪站在墙头说话。',
        ],
        '剑来第二季原著.docx': [
            '第二卷山水郎 第八十六章 同道中人',
            '崔瀺在袁家祖宅等待杨老头。',
        ],
        '剑来第三季原著.docx': [
            '第三卷金错刀 第两百零六章 月儿圆月儿弯',
            '陆沉在龙泉等候大骊皇帝。',
        ],
    }

    def fake_extract(path: Path):
        return fixture_data[path.name]

    monkeypatch.setattr(build_swordcoming_book, 'extract_paragraphs', fake_extract)

    units, index_payload, config_payload = build_swordcoming_book.build_book(tmp_path, max_sentences=6, max_chars=600)

    assert [unit['season_name'] for unit in units] == ['第一季', '第一季', '第二季', '第三季']
    assert units[0]['unit_title'] == '第一卷笼中雀 第一章 惊蛰'
    assert units[1]['progress_start'] > units[0]['progress_end']
    assert index_payload['total_units'] == 4
    assert config_payload['quick_filters'][0]['label'] == '第一季'
    assert config_payload['quick_filters'][-1]['label'] == '全部'


def test_split_sentences_preserves_long_sentence_with_commas():
    paragraph = '当了一段时间飘来荡去的孤魂野鬼，少年实在找不到挣钱的营生，靠着那点微薄积蓄。'
    result = build_swordcoming_book.split_sentences(paragraph)

    assert result == [paragraph]


def test_entity_resolver_populates_progress_fields():
    resolver = EntityResolver()
    resolver.set_book_metadata(book_id='swordcoming', unit_label='章节', progress_label='叙事进度')
    resolver.set_segment_progress_index({'1-1': 10, '1-2': 11}, {'1-1': '第一章 · 段1', '1-2': '第一章 · 段2'})

    event = Event(
        name='泥瓶巷夜谈',
        time=None,
        location='泥瓶巷',
        participants=['陈平安', '宋集薪'],
        description='陈平安与宋集薪在泥瓶巷发生对话。',
        significance='奠定二人早期关系。',
    )
    resolver.add_event(event, juan_index=1, segment_index=1)
    resolver.add_event(event, juan_index=1, segment_index=2)

    resolver.add_relation(
        Action(
            time=None,
            from_roles=['宋集薪'],
            to_roles=['陈平安'],
            action='讥讽',
            context='宋集薪在墙头奚落陈平安。',
            result=None,
            event_name='泥瓶巷夜谈',
            location='泥瓶巷',
            juan_index=1,
            segment_index=1,
        )
    )

    kb = resolver.build_knowledge_base()
    event_out = kb.events['泥瓶巷夜谈']
    relation_out = kb.relations['宋集薪->陈平安']

    assert kb.book_id == 'swordcoming'
    assert kb.unit_label == '章节'
    assert event_out.progress_start == 10
    assert event_out.progress_end == 11
    assert event_out.progress_label == '第一章 · 段1'
    assert relation_out.progress_start == 10
    assert relation_out.progress_label == '第一章 · 段1'
