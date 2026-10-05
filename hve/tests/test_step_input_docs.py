"""FR-INPUT-06 — README/users-guide が4面と安全境界を説明する。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "users-guide" / "step-inputs.md"


def test_root_readme_links_step_input_guide() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "users-guide/step-inputs.md" in text


def test_guide_covers_all_surfaces_and_boundaries() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for word in (
        "Cloud", "GUI", "CLI", "Prompt", "複数", "MarkItDown",
        "docs-original", "MCP経由で情報を補填しますか?", "workiq", "ask",
        "Cloud upload unavailable", "branch-relative",
    ):
        assert word in text, word
