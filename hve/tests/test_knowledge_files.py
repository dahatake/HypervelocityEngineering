"""FR-KD-05 / NFR-KD-01: qa/ と knowledge/ への並行実行に安全なファイル操作。"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from hve import knowledge_files as kf
from hve.qa_merger import QAMerger

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATOR = _REPO_ROOT / ".github" / "scripts" / "validate-knowledge-files.py"


def _qa_text(count: int = 3) -> str:
    rows = "\n".join(
        f"| {n} | 質問{n} | A) はい / B) いいえ | A) はい | 理由{n} |  |" for n in range(1, count + 1)
    )
    return (
        "# 事前 QA\n\n**状態**: 回答待ち\n\n---\n\n## 質問項目\n\n"
        "| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | ユーザー回答 |\n"
        "|-----|------|--------|-----------|----------------|------------|\n"
        f"{rows}\n"
    )


def _valid_d_doc(nn: str = "01") -> str:
    sections = "\n\n".join(
        f"## {title}\n\n内容"
        for title in (
            "1. 目的と背景", "2. 要求項目（Confirmed）", "3. 要求項目（Tentative — 推論・仮定を含む）",
            "4. 未確定事項（Unknown）", "5. 最低内容カバー状況", "6. 不足判定・推奨アクション",
            "7. 状態サマリー", "8. 関連文書",
        )
    )
    return (
        f"# D{nn}: 事業意図・成功条件定義書\n\n**D クラス**: D{nn}\n**文書名**: 事業意図\n**必須度**: Core\n"
        "**総合状態**: Tentative\n**Prompt投入可否**: No\n**関連 ADR / 未解決論点**: なし\n\n---\n\n"
        f"{sections}\n"
    )


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_knowledge_files_for_test", _VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- paths


@pytest.mark.parametrize(
    "raw",
    ["/qa/a.md", "C:/qa/a.md", "qa/../knowledge/D01-x.md", "qa/a.txt", "", "qa/", "other/a.md"],
)
def test_qa_path_denied(tmp_path: Path, raw: str) -> None:
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.resolve_path(tmp_path, raw, "qa")
    assert err.value.code == "path-denied"


def test_backslash_is_normalized(tmp_path: Path) -> None:
    rel, path = kf.resolve_path(tmp_path, "qa\\sub\\a.md", "qa")
    assert rel == "qa/sub/a.md"
    assert path == tmp_path / "qa" / "sub" / "a.md"


@pytest.mark.parametrize(
    "raw,ok",
    [
        ("knowledge/D01-事業意図.md", True),
        ("knowledge/business-requirement-document-status.md", True),
        ("knowledge/D01-事業意図-ChangeLog.md", False),
        ("knowledge/D1-x.md", False),
        ("knowledge/sub/D01-x.md", False),
        ("knowledge/readme.md", False),
    ],
)
def test_knowledge_path_rules(tmp_path: Path, raw: str, ok: bool) -> None:
    if ok:
        assert kf.resolve_path(tmp_path, raw, "knowledge")[0] == raw
    else:
        with pytest.raises(kf.KnowledgeFileError) as err:
            kf.resolve_path(tmp_path, raw, "knowledge")
        assert err.value.code == "path-denied"


def test_symlink_component_is_denied(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    try:
        (tmp_path / "qa").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink を作成できない環境")
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.resolve_path(tmp_path, "qa/a.md", "qa")
    assert err.value.code == "path-denied"


# --------------------------------------------------------------------------- lock


def test_lock_file_contains_only_owner_metadata(tmp_path: Path) -> None:
    lock = kf.FileLock(tmp_path, "qa/a.md")
    with lock:
        assert lock.lock_path.parent == tmp_path / ".hve" / "locks"
    data = json.loads(lock.lock_path.read_text(encoding="utf-8"))
    assert set(data) == {"pid", "host", "token", "created_at"}
    assert data["pid"] == os.getpid() and data["host"] == socket.gethostname()


def test_lock_timeout_within_process(tmp_path: Path) -> None:
    with kf.FileLock(tmp_path, "qa/a.md"):
        with pytest.raises(kf.KnowledgeFileError) as err:
            kf.FileLock(tmp_path, "qa/a.md", timeout=0.3).acquire()
    assert err.value.code == "lock-timeout"


_HOLDER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from hve import knowledge_files as kf
lock = kf.FileLock(Path(sys.argv[2]), "qa/a.md")
lock.acquire()
print("held", flush=True)
if sys.argv[3] == "hold":
    time.sleep(30)
else:
    import os
    os._exit(1)  # 解放せずに異常終了する
"""


def _spawn_holder(tmp_path: Path, mode: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(_REPO_ROOT), str(tmp_path), mode],
        stdout=subprocess.PIPE, text=True,
    )
    assert proc.stdout is not None and proc.stdout.readline().strip() == "held"
    return proc


def test_live_foreign_lock_times_out(tmp_path: Path) -> None:
    proc = _spawn_holder(tmp_path, "hold")
    try:
        with pytest.raises(kf.KnowledgeFileError) as err:
            kf.FileLock(tmp_path, "qa/a.md", timeout=0.5).acquire()
        assert err.value.code == "lock-timeout"
    finally:
        proc.kill()
        proc.wait()


def test_lock_of_crashed_process_is_released_by_os(tmp_path: Path) -> None:
    proc = _spawn_holder(tmp_path, "crash")
    proc.wait(timeout=30)
    with kf.FileLock(tmp_path, "qa/a.md", timeout=5):
        pass


# --------------------------------------------------------------------------- optimistic write


def test_create_update_and_conflict(tmp_path: Path) -> None:
    sha1 = kf.write_file(tmp_path, "qa/a.md", "one\n", base_sha256=None, kind="qa")
    assert sha1 == kf.sha256_text("one\n")
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.write_file(tmp_path, "qa/a.md", "dup\n", base_sha256=None, kind="qa")
    assert err.value.code == "conflict" and err.value.current_sha256 == sha1
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.write_file(tmp_path, "qa/a.md", "two\n", base_sha256="0" * 64, kind="qa")
    assert err.value.code == "conflict" and err.value.current_sha256 == sha1
    assert (tmp_path / "qa" / "a.md").read_text(encoding="utf-8") == "one\n"
    sha2 = kf.write_file(tmp_path, "qa/a.md", "two\n", base_sha256=sha1, kind="qa")
    assert sha2 == kf.sha256_text("two\n")


def test_failed_replace_keeps_original_and_cleans_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sha = kf.write_file(tmp_path, "qa/a.md", "keep\n", base_sha256=None, kind="qa")

    def _boom(src: str, dst: str) -> None:
        raise OSError("disk")

    monkeypatch.setattr(kf.os, "replace", _boom)
    with pytest.raises(OSError):
        kf.write_file(tmp_path, "qa/a.md", "new\n", base_sha256=sha, kind="qa")
    assert (tmp_path / "qa" / "a.md").read_text(encoding="utf-8") == "keep\n"
    assert [p.name for p in (tmp_path / "qa").iterdir()] == ["a.md"]


def test_read_file_returns_sha(tmp_path: Path) -> None:
    assert kf.read_file(tmp_path, "qa/none.md")["exists"] is False
    kf.write_file(tmp_path, "qa/a.md", "x\n", base_sha256=None, kind="qa")
    result = kf.read_file(tmp_path, "qa/a.md")
    assert result == {"path": "qa/a.md", "exists": True, "sha256": kf.sha256_text("x\n"), "content": "x\n"}


# --------------------------------------------------------------------------- QA


def test_create_qa_allocates_suffix(tmp_path: Path) -> None:
    rel1, _ = kf.create_qa_document(tmp_path, run_id="20261001T000000-abcdef", label="akm", text=_qa_text())
    rel2, _ = kf.create_qa_document(tmp_path, run_id="20261001T000000-abcdef", label="akm", text=_qa_text())
    assert rel1 == "qa/20261001T000000-abcdef-akm-knowledge-discovery-qa.md"
    assert rel2 == "qa/20261001T000000-abcdef-akm-knowledge-discovery-qa-2.md"


def test_label_is_sanitized(tmp_path: Path) -> None:
    rel, _ = kf.create_qa_document(tmp_path, run_id="r1", label="1/D01 x", text=_qa_text())
    assert rel == "qa/r1-1-D01-x-knowledge-discovery-qa.md"


def test_update_qa_research_updates_only_given_question(tmp_path: Path) -> None:
    sha = kf.write_file(tmp_path, "qa/a.md", _qa_text(), base_sha256=None, kind="qa")
    result = kf.update_qa_research(
        tmp_path,
        "qa/a.md",
        base_sha256=sha,
        answers=[kf.ResearchAnswer(no=2, answer="A) はい", status="Confirmed", source_ids=("L1",))],
        sources=[kf.SourceEntry(id="L1", kind="repo", server="", tool="", locator="docs-original/a.md", summary="要約|x")],
    )
    assert result["updated"] == [2] and result["source_id_map"] == {"L1": "S1"}
    doc = QAMerger.parse_qa_file(tmp_path / "qa" / "a.md")
    by_no = {q.no: q for q in doc.questions}
    assert by_no[2].research_answer == "A) はい"
    assert by_no[2].research_status == "Confirmed"
    assert by_no[2].research_sources == "S1"
    assert by_no[1].research_status == "" and by_no[3].research_status == ""
    assert "| S1 | repo |  |  | docs-original/a.md | 要約&#124;x |" in doc.raw_sections["調査出典"]
    second = kf.update_qa_research(
        tmp_path, "qa/a.md", base_sha256=result["sha256"],
        answers=[kf.ResearchAnswer(no=1, answer="", status="Unknown", source_ids=("L1",))],
        sources=[kf.SourceEntry(id="L1", kind="repo", server="", tool="", locator="qa/a.md", summary="b")],
    )
    assert second["source_id_map"] == {"L1": "S2"}


def test_update_qa_research_rejects_unknown_question(tmp_path: Path) -> None:
    sha = kf.write_file(tmp_path, "qa/a.md", _qa_text(), base_sha256=None, kind="qa")
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.update_qa_research(
            tmp_path, "qa/a.md", base_sha256=sha,
            answers=[kf.ResearchAnswer(no=9, answer="x", status="Unknown", source_ids=())], sources=[],
        )
    assert err.value.code == "invalid-question"


_WORKER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from hve import knowledge_files as kf
root, rel, no = Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
for _ in range(200):
    sha = kf.read_file(root, rel)["sha256"]
    try:
        kf.update_qa_research(root, rel, base_sha256=sha, answers=[kf.ResearchAnswer(no=no, answer=f"answer-{no}", status="Tentative", source_ids=())], sources=[])
        break
    except kf.KnowledgeFileError as exc:
        if exc.code != "conflict":
            raise
        time.sleep(0.01)
else:
    raise SystemExit(3)
"""


def test_eight_processes_lose_no_update(tmp_path: Path) -> None:
    kf.write_file(tmp_path, "qa/a.md", _qa_text(8), base_sha256=None, kind="qa")
    procs = [
        subprocess.Popen([sys.executable, "-c", _WORKER, str(_REPO_ROOT), str(tmp_path), "qa/a.md", str(n)])
        for n in range(1, 9)
    ]
    assert [p.wait(timeout=120) for p in procs] == [0] * 8
    doc = QAMerger.parse_qa_file(tmp_path / "qa" / "a.md")
    assert sorted(q.research_answer for q in doc.questions) == sorted(f"answer-{n}" for n in range(1, 9))


# --------------------------------------------------------------------------- knowledge


def test_knowledge_write_validates_and_appends_changelog(tmp_path: Path) -> None:
    validator = _load_validator()
    rel = "knowledge/D01-事業意図.md"
    result = kf.write_knowledge(
        tmp_path, rel, _valid_d_doc(), base_sha256=None, run_id="run-1",
        summary="KPI を追記", locators=["qa/a.md", "https://example.com/x|y"],
        validator_path=_VALIDATOR,
    )
    changelog = tmp_path / "knowledge" / "D01-事業意図-ChangeLog.md"
    assert result["changelog_path"] == "knowledge/D01-事業意図-ChangeLog.md"
    text = changelog.read_text(encoding="utf-8")
    assert validator._validate_changelog(text) == []
    assert "## 知識探索による更新履歴" in text
    assert "| run-1 | KPI を追記 | qa/a.md<br>https://example.com/x&#124;y |" in text
    kf.write_knowledge(
        tmp_path, rel, _valid_d_doc() + "追記\n", base_sha256=result["sha256"], run_id="run-2",
        summary="2 回目", locators=["qa/b.md"], validator_path=_VALIDATOR,
    )
    text = changelog.read_text(encoding="utf-8")
    assert text.count("## 知識探索による更新履歴") == 1
    assert text.index("| run-1 |") < text.index("| run-2 |")


@pytest.mark.parametrize(
    "content",
    [_valid_d_doc("02"), _valid_d_doc().replace("## 8. 関連文書", "## 9. その他"), "   \n"],
)
def test_knowledge_write_rejects_invalid_document(tmp_path: Path, content: str) -> None:
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.write_knowledge(
            tmp_path, "knowledge/D01-事業意図.md", content, base_sha256=None, run_id="r",
            summary="s", locators=["qa/a.md"], validator_path=_VALIDATOR,
        )
    assert err.value.code == "invalid-content"
    assert not (tmp_path / "knowledge").exists() or not any((tmp_path / "knowledge").iterdir())


def test_knowledge_write_fails_closed_without_validator(tmp_path: Path) -> None:
    with pytest.raises(kf.KnowledgeFileError) as err:
        kf.write_knowledge(
            tmp_path, "knowledge/D01-事業意図.md", _valid_d_doc(), base_sha256=None, run_id="r",
            summary="s", locators=["qa/a.md"], validator_path=tmp_path / "missing.py",
        )
    assert err.value.code == "invalid-content"


def test_status_file_write_has_no_changelog(tmp_path: Path) -> None:
    result = kf.write_knowledge(
        tmp_path, kf.KNOWLEDGE_STATUS_FILE, "# status\n", base_sha256=None, run_id="r",
        summary="s", locators=["qa/a.md"], validator_path=_VALIDATOR,
    )
    assert result["changelog_path"] is None
    assert [p.name for p in (tmp_path / "knowledge").iterdir()] == ["business-requirement-document-status.md"]


def test_escape_table_cell() -> None:
    assert kf.escape_table_cell("a|b\r\nc\rd") == "a&#124;b<br>c<br>d"
