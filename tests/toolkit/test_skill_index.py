import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / ".github" / "skills"
PAIRS = (("implement-fr", "original-fr.md"), ("requirement-definition", "original.md"))


def _tags(text):
    out = {}
    for i, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^<([a-z_]+)>$", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = [i, None]
        m = re.match(r"^</([a-z_]+)>$", line)
        if m and m.group(1) in out and out[m.group(1)][1] is None:
            out[m.group(1)][1] = i
    return out


def test_skill_index_matches_original_tags():
    # 手順書の読み方の表（節 → 行範囲）が、原本のタグの位置と一致する
    for skill, original in PAIRS:
        text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        tags = _tags((SKILLS / skill / original).read_text(encoding="utf-8"))
        rows = re.findall(r"^\| `<([a-z_]+)>` \| (\d+)〜(\d+) 行 \|", text, flags=re.M)
        assert rows, skill
        for tag, a, b in rows:
            assert tags[tag] == [int(a), int(b)], f"{skill}: <{tag}> は {tags[tag]}（表は {a}〜{b}）"


def test_skill_files_stay_small_and_original_is_separate():
    # 作業役が起動のたびに読む手順書に、原本の全文を戻さない
    for skill, original in PAIRS:
        text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        assert len(text.encode("utf-8")) < 16_000, skill
        assert not re.search(r"^<(implementation|requirements_document)>$", text, flags=re.M)
        assert (SKILLS / skill / original).exists()
