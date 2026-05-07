import pytest
from pydantic import ValidationError

import utils.prompts as prompts_mod
from utils.prompts import get_prompt

_VALID_FM = (
    "---\n"
    "id: test-prompt\n"
    "version: \"2026-05-07\"\n"
    "model: gemini-3-flash-preview\n"
    "role: user\n"
    "inputs: [patient_yaml]\n"
    "---\n"
)


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    """Leert den Modul-Cache vor jedem Test."""
    prompts_mod._PROMPT_CACHE.clear()
    yield
    prompts_mod._PROMPT_CACHE.clear()


def test_get_prompt_strips_frontmatter(tmp_path):
    (tmp_path / "with_fm.md").write_text(_VALID_FM + "Das ist der Body.\n", encoding="utf-8")
    result = get_prompt("with_fm", tmp_path)
    assert result == "Das ist der Body.\n"
    assert "---" not in result
    assert "id:" not in result


def test_get_prompt_validates_frontmatter(tmp_path):
    (tmp_path / "bad_fm.md").write_text(
        "---\nid: bad-prompt\n# version, model, role, inputs fehlen\n---\nBody.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        get_prompt("bad_fm", tmp_path)


def test_get_prompt_raises_on_missing_frontmatter(tmp_path):
    (tmp_path / "no_fm.md").write_text("Kein Frontmatter hier.", encoding="utf-8")
    with pytest.raises(ValueError, match="kein Frontmatter"):
        get_prompt("no_fm", tmp_path)


def test_get_prompt_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_prompt("nichtvorhanden", tmp_path)


def test_get_prompt_caches_result(tmp_path):
    p = tmp_path / "cached.md"
    p.write_text(_VALID_FM + "Original", encoding="utf-8")
    first = get_prompt("cached", tmp_path)
    p.write_text(_VALID_FM + "Geändert", encoding="utf-8")
    second = get_prompt("cached", tmp_path)
    assert first == second == "Original"
