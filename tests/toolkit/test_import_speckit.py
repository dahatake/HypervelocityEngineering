import json

SPEC = """# Feature Specification: 写真アルバム

**Feature Branch**: `001-photo-albums`
**Created**: 2026-10-01
**Status**: Draft
**Input**: User description: "photo organizer"

## Clarifications

### Session 2026-10-02

- Q: アルバムの並び順は？ → A: 撮影日の新しい順

## User Scenarios & Testing *(mandatory)*

<!-- IMPORTANT: comment that must be ignored. **FR-999**: System MUST not appear -->

### User Story 1 - 日付ごとのアルバム (Priority: P1)

利用者は、写真が撮影日ごとのアルバムにまとめられていることを確認できる。

**Why this priority**: 主要な価値だから

**Independent Test**: 写真を 3 枚取り込み、アルバムが日付ごとにできることを確認する

**Acceptance Scenarios**:

1. **Given** 撮影日の異なる写真が 2 枚ある, **When** 取り込む, **Then** アルバムが 2 つできる
2. **Given** アルバムがある, **When** 開く, **Then** タイル表示でプレビューされる

---

### User Story 2 - アルバムの並べ替え (Priority: P3)

利用者は、アルバムをドラッグで並べ替えられる。

**Acceptance Scenarios**:

1. **Given** アルバムが 2 つある, **When** ドラッグする, **Then** 順序が保存される

### Edge Cases

- 撮影日がない写真はどうなるか？
- 同じ写真を 2 回取り込んだときは重複させない

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST group photos by capture date
- **FR-002**: System SHOULD show a tile preview of each album
- **FR-003**: System MUST retain deleted photos for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities

- **Album**: 撮影日でまとめた写真の集合
- **Photo**: 1 枚の画像と撮影日

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 1,000 枚の取り込みが 1 分以内に終わる

## Assumptions

- 写真はローカルに保存する
"""

CONSTITUTION = """# Photo Constitution

## Core Principles

### I. Library-First
Every feature starts as a standalone library.

### II. Test-First (NON-NEGOTIABLE)
Tests are written before implementation.

## Governance

Amendments need approval.
"""


def make_speckit(repo):
    repo.write("specs/001-photo-albums/spec.md", SPEC)
    repo.write("specs/001-photo-albums/plan.md", "# Plan\nVite + SQLite\n")
    repo.write("specs/002-sharing/spec.md", "# Feature Specification: [FEATURE NAME]\n\n## Requirements\n\n### Functional Requirements\n\n- **FR-001**: System MUST share albums\n")
    repo.write(".specify/memory/constitution.md", CONSTITUTION)


def test_json_mapping(repo):
    make_speckit(repo)
    out = repo.py("import-speckit.py", "--json", check=True).stdout
    data = json.loads(out)
    f1 = next(f for f in data["features"] if f["name"] == "001-photo-albums")
    refs = {i["ref"]: i for i in f1["items"]}
    assert refs["speckit:001-photo-albums/US1"]["priority"] == "MUST"
    assert refs["speckit:001-photo-albums/US2"]["priority"] == "MAY"
    assert "US1-AS2" in " ".join(refs)
    assert refs["speckit:001-photo-albums/US1-AS1"]["kind"] == "受入シナリオ"
    assert refs["speckit:001-photo-albums/FR-002"]["priority"] == "SHOULD"
    assert refs["speckit:001-photo-albums/FR-003"]["clarifications"] == ["retention period not specified"]
    assert refs["speckit:001-photo-albums/SC-001"]["kind"] == "成功基準"
    assert refs["speckit:001-photo-albums/EC1"]["target"].startswith("質問票")
    assert refs["speckit:001-photo-albums/EC2"]["target"] == "受入基準（AC）"
    assert refs["speckit:001-photo-albums/CL1"]["kind"] == "確認済みの回答"
    assert "speckit:001-photo-albums/ENT-Album" in refs
    assert "speckit:001-photo-albums/AS1" in refs
    assert not any("FR-999" in r for r in refs), "HTML comments must be ignored"
    assert f1["references"] and f1["references"][0].endswith("plan.md")
    f2 = next(f for f in data["features"] if f["name"] == "002-sharing")
    assert "[FEATURE NAME]" in f2["placeholders"]
    names = [c["text"] for c in data["constitution"]]
    assert names[0].startswith("Library-First") and len(names) == 2


def test_writes_request_without_touching_docs(repo):
    make_speckit(repo)
    before = repo.read("docs/requirements-definition.md")
    proc = repo.py("import-speckit.py", "--feature", "001", "--out", "work/import/t.md", check=True)
    assert "features=1" in proc.stdout
    text = repo.read("work/import/t.md")
    assert '<pasted_content id="speckit-001-photo-albums">' in text
    assert '</pasted_content id="speckit-constitution">' in text
    assert "scope: なし" in text and "<references>" in text
    assert "specs/001-photo-albums/plan.md" in text
    assert "| `speckit:001-photo-albums/FR-003` |" in text
    assert repo.read("docs/requirements-definition.md") == before
    assert "FR-001" not in repo.read("docs/id-registry.md")


def test_implement_and_stdout(repo):
    make_speckit(repo)
    out = repo.py("import-speckit.py", "--feature", "001", "--implement", "--no-constitution", "--stdout", check=True).stdout
    assert out.startswith("<request>")
    assert "scope: なし" not in out and "speckit-constitution" not in out


def test_coexists_with_speckit_files(repo):
    # Spec Kit numbers its own FR-001... in specs/ and .specify/templates; they must not trip CHK-19
    make_speckit(repo)
    repo.write(".specify/templates/spec-template.md", "- **FR-001**: System MUST [capability]\n")
    repo.write("specs/tests/test_feature.py", "# AC-999 is a real test reference\n")
    repo.write("docs-images/flow.svg", "<svg><text>FR-777 example</text></svg>\n")
    repo.commit("add speckit")
    proc = repo.py("verify.py", "--docs-only")
    assert proc.returncode == 1 and "specs/tests/test_feature.py" in proc.stdout  # non-Markdown files are still scanned
    (repo.path / "specs/tests/test_feature.py").unlink()
    repo.commit("remove")
    proc = repo.py("verify.py", "--docs-only")
    assert proc.returncode == 0, proc.stdout
    sel = repo.py("select-tests.py", "--base", "HEAD~2", check=True).stdout
    assert "specs/001-photo-albums" not in sel and ".specify" not in sel
    req_line = next(l for l in sel.splitlines() if l.startswith("REQ"))
    assert not any(f"FR-00{i}" in req_line for i in (1, 2, 3))  # Spec Kit's own numbers are not harvested as toolkit IDs


def test_placeholder_warning_and_missing(repo):
    make_speckit(repo)
    proc = repo.py("import-speckit.py", "--feature", "002", "--out", "work/import/w.md", check=True)
    assert "WARN" in proc.stdout
    proc = repo.py("import-speckit.py", "--feature", "999")
    assert proc.returncode == 2
