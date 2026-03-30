from pathlib import Path


def _read_app_tsx() -> str:
    app_path = Path(__file__).resolve().parents[1] / "visualization" / "src" / "App.tsx"
    return app_path.read_text(encoding="utf-8")


def test_detail_panels_entity_click_opens_role_detail():
    content = _read_app_tsx()

    expected = "onEntityClick={(entityName) => openRoleDetail(entityName, activeTab, { pushCurrent: true })}"
    assert content.count(expected) >= 4


def test_spotlight_role_name_is_clickable():
    content = _read_app_tsx()

    assert "onClick={() => openRoleDetail(spotlightArc.role_name, 'writerArcs')}" in content
    assert "<strong className=\"hero-side-value\">{spotlightArc.role_name}</strong>" not in content
