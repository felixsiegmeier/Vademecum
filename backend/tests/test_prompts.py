import pytest
from pydantic import ValidationError

import utils.prompts as prompts_mod
from utils.prompts import get_prompt


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    """Leert den Modul-Cache vor jedem Test."""
    prompts_mod._PROMPT_CACHE.clear()
    yield
    prompts_mod._PROMPT_CACHE.clear()


def test_get_prompt_no_frontmatter_returns_raw(tmp_path):
    p = tmp_path / "simple.txt"
    p.write_text("Nur Text.", encoding="utf-8")
    assert get_prompt("simple.txt", tmp_path) == "Nur Text."


def test_get_prompt_strips_frontmatter(tmp_path):
    p = tmp_path / "with_fm.md"
    p.write_text(
        "---\n"
        "id: test-prompt\n"
        "version: 2026-05-07\n"
        "model: gemini-2.0-flash\n"
        "role: user\n"
        "inputs: [patient_yaml]\n"
        "---\n"
        "Das ist der Body.\n",
        encoding="utf-8",
    )
    result = get_prompt("with_fm.md", tmp_path)
    assert result == "Das ist der Body.\n"
    assert "---" not in result
    assert "id:" not in result


def test_get_prompt_validates_frontmatter(tmp_path):
    p = tmp_path / "bad_fm.md"
    p.write_text(
        "---\n"
        "id: bad-prompt\n"
        # version, model, role, inputs fehlen
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        get_prompt("bad_fm.md", tmp_path)


def test_get_prompt_prefers_md_over_txt(tmp_path):
    (tmp_path / "prompt.txt").write_text("txt-Version", encoding="utf-8")
    (tmp_path / "prompt.md").write_text("md-Version", encoding="utf-8")
    assert get_prompt("prompt.txt", tmp_path) == "md-Version"


def test_get_prompt_caches_result(tmp_path):
    p = tmp_path / "cached.txt"
    p.write_text("Original", encoding="utf-8")
    first = get_prompt("cached.txt", tmp_path)
    p.write_text("Geändert", encoding="utf-8")
    second = get_prompt("cached.txt", tmp_path)
    assert first == second == "Original"
