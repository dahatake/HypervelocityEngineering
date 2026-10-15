"""Unit / integration tests for scripts/entities.py (FR-1020, FR-1023, FR-1024, NFR-COMPAT-003, NFR-SEC-023)."""
from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / "tests" / "system"))
sys.path.insert(0, str(SOURCE / "scripts"))
from entity_repo import CAT, DOC, SEP, make_other, make_standard, run_entities, snapshot  # noqa: E402

import entities as ent  # noqa: E402

CSV = "エンティティ名,説明\n注文,企業側の説明は転記されない\n顧客,x\n商品,y\n"


def set_source(repo: Path, source: str, **extra) -> None:
    p = repo / "scripts" / "ebak.config.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["enterprise_data_catalog"] = {"source": source, **extra}
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def rows(out: str, *needles: str):
    return [ln for ln in out.splitlines() if all(n in ln for n in needles)]


def rdcheck(repo: Path):
    return subprocess.run([sys.executable, "scripts/rdcheck.py", "check"], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


# FR-1020 AC-152 (optional fields may be omitted; invalid values are errors with a reason)
def test_ac152_optional_fields_omitted_is_not_an_error_and_valid_values_pass(tmp_path):
    repo = make_standard(tmp_path / "r")
    out = rdcheck(repo).stdout
    assert "エンティティの使い方" not in out and "利用シナリオ" not in out


@pytest.mark.parametrize("old,new,needle", [
    ("注文（作成）", "注文（廃棄）", "廃棄"),
    ("注文（作成）", "未定義（作成）", "未定義"),
    ("利用シナリオ: 1", "利用シナリオ: 9", "利用シナリオ 9"),
])
def test_ac152_invalid_optional_values_are_errors_with_location(tmp_path, old, new, needle):
    repo = make_standard(tmp_path / "r")
    p = repo / DOC
    p.write_text(p.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    r = rdcheck(repo)
    hit = rows(r.stdout, "ERROR", "FR-001", needle)
    assert hit and "docs/requirements-definition.md:" in hit[0], r.stdout


# FR-1020 AC-153
def test_ac153_missing_info_is_labelled_and_nothing_is_guessed(tmp_path):
    repo = make_standard(tmp_path / "r")
    out = run_entities(repo, "list").stdout
    cust = " ".join(rows(out, "顧客"))
    assert "説明未記載" in cust and "テーブル未記載" in cust and "使い方未記載" in cust
    stock = " ".join(rows(out, "在庫"))
    assert "テーブル未記載" in stock and "使い方未記載" in stock and "説明未記載" not in stock
    assert "説明未記載" not in " ".join(rows(out, "注文"))


# FR-1023 AC-160
def test_ac160_file_source_lists_match_only_sides_and_fuzzy(tmp_path):
    repo = make_standard(tmp_path / "r")
    (repo / "cat.csv").write_text("名前\n注文\n顧客\n在　庫（旧）\n商品\n", encoding="utf-8")
    set_source(repo, "cat.csv")
    out = run_entities(repo, "check").stdout
    assert rows(out, "注文 ⇔ 注文", "cat.csv:2", "docs/requirements-definition.md:")
    assert rows(out, "在庫 ≈ 在　庫（旧）", "cat.csv:4")  # 空白・全半角・括弧注記の違いは揺れ候補（一致ではない）
    assert not rows(out, "在庫 ⇔")
    assert rows(out, "商品", "企業カタログ: cat.csv:5")
    assert out.index("一致:") < out.index("EABK のみ")


def test_ac160_similarity_threshold_from_param(tmp_path):
    a = [("注文管理", "x:1")]
    assert ent.reconcile(a, [("注文管理表", "y:1")], 0.8)["fuzzy"]
    assert not ent.reconcile(a, [("注文管理表", "y:1")], 0.95)["fuzzy"]


@pytest.mark.parametrize("name,text", [
    ("c.json", json.dumps({"entities": [{"name": "注文"}, {"name": "顧客"}]}, ensure_ascii=False, indent=1)),
    ("c.md", "| エンティティ | 説明 |\n|---|---|\n| 注文 | a |\n| 顧客 | b |\n"),
    ("c.md", "# 一覧\n\n- 注文: a\n- 顧客: b\n"),
])
def test_ac160_json_and_markdown_sources(tmp_path, name, text):
    repo = make_standard(tmp_path / "r")
    (repo / name).write_text(text, encoding="utf-8")
    set_source(repo, name)
    out = run_entities(repo, "check").stdout
    assert rows(out, "注文 ⇔ 注文") and rows(out, "顧客 ⇔ 顧客")
    assert rows(out, "在庫", "EABK:")


class _Handler(http.server.BaseHTTPRequestHandler):
    log: list = []
    delay = 0.0

    def do_GET(self):  # noqa: N802
        _Handler.log.append(("GET", self.path))
        if self.path.startswith("/slow"):
            time.sleep(_Handler.delay)
        body = CSV.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_POST(self):  # noqa: N802
        _Handler.log.append(("POST", self.path))
        self.send_response(405)
        self.end_headers()

    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *a):  # noqa: D401
        pass


@pytest.fixture()
def server():
    _Handler.log = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


# FR-1023 AC-161 / AC-162
def test_ac161_url_source_same_result_and_ac162_only_get(tmp_path, server):
    repo = make_standard(tmp_path / "r")
    set_source(repo, server + "/c.csv")
    out = run_entities(repo, "check").stdout
    assert rows(out, "注文 ⇔ 注文") and rows(out, "顧客 ⇔ 顧客")
    assert _Handler.log and all(m == "GET" for m, _ in _Handler.log)


def test_ac161_timeout_reports_unusable_and_keeps_exit_code(tmp_path, server):
    repo = make_standard(tmp_path / "r")
    _Handler.delay = 6
    set_source(repo, server + "/slow.csv")
    cfg_p = repo / DOC
    tbl = "\n### 3.2 パラメータ（PARAM）\n\n| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |\n|---|---|---|---|---|---|\n| PARAM-016 | 待ち時間 | 1 | 秒 | t | 承認済み |\n\n## 5. 利用シナリオ"
    cfg_p.write_text(cfg_p.read_text(encoding="utf-8").replace("\n## 5. 利用シナリオ", tbl, 1), encoding="utf-8")
    t0 = time.monotonic()
    r = run_entities(repo, "check")
    assert time.monotonic() - t0 < 5.5
    assert r.returncode == 0 and "照合不能" in r.stdout
    assert "照合不能" not in rdcheck(repo).stdout


def test_ac161_unparsable_source_is_unusable(tmp_path):
    repo = make_standard(tmp_path / "r")
    (repo / "bad.json").write_text("{not json", encoding="utf-8")
    set_source(repo, "bad.json")
    r = run_entities(repo, "check")
    assert r.returncode == 0 and "照合不能" in r.stdout
    assert run_entities(repo, "check", "--strict").returncode == 1


def test_ac162_file_source_is_untouched(tmp_path):
    repo = make_standard(tmp_path / "r")
    f = repo / "cat.csv"
    f.write_text(CSV, encoding="utf-8")
    set_source(repo, "cat.csv")
    before = (f.read_bytes(), f.stat().st_mtime_ns)
    snap = snapshot(repo)
    for cmd in ("list", "check", "todo"):
        run_entities(repo, cmd)
    assert (f.read_bytes(), f.stat().st_mtime_ns) == before
    assert snapshot(repo) == snap


# NFR-SEC-023 AC-166
@pytest.mark.parametrize("src", ["ftp://example.com/c.csv", "file:///etc/passwd", "http://user:secret@127.0.0.1:9/c.csv"])
def test_ac166_forbidden_sources_are_not_fetched_and_no_credentials_in_output(tmp_path, src):
    repo = make_standard(tmp_path / "r")
    set_source(repo, src)
    r = run_entities(repo, "check")
    assert "照合不能" in r.stdout and "secret" not in r.stdout + r.stderr and r.returncode == 0
    assert "secret" not in run_entities(repo, "todo").stdout


def test_ac166_safe_display_drops_credentials_and_query():
    assert ent.safe_display("https://h.example/p/c.csv?token=abc#x") == "https://h.example/p/c.csv"


# NFR-SEC-023 AC-167
def test_ac167_body_is_not_cached_or_copied(tmp_path, server):
    repo = make_standard(tmp_path / "r")
    set_source(repo, server + "/c.csv")
    before = snapshot(repo)
    outs = "".join(run_entities(repo, c).stdout for c in ("list", "check", "todo"))
    assert "企業側の説明は転記されない" not in outs
    assert snapshot(repo) == before


# FR-1024 AC-164
def test_ac164_todo_reasons_by_catalog_content(tmp_path):
    repo = make_standard(tmp_path / "r")
    (repo / "cat.csv").write_text("名前\n注文\n在　庫（旧）\n", encoding="utf-8")
    set_source(repo, "cat.csv")
    out = run_entities(repo, "todo").stdout
    assert rows(out, "「顧客」", "企業カタログになし")
    assert rows(out, "「在庫」", "名称の確認")
    assert not rows(out, "「注文」")


# FR-1024 AC-165
def test_ac165_deterministic_and_deduplicated_against_open_questions(tmp_path):
    repo = make_standard(tmp_path / "r")
    set_source(repo, "no/such/enterprise-catalog.csv")
    a = run_entities(repo, "todo").stdout
    assert a == run_entities(repo, "todo").stdout
    p = repo / DOC
    row = "| Q-001 | 中 | エンティティ「顧客」: 理由 企業カタログ未確認 | A: x | A | 未回答 | — |"
    p.write_text(p.read_text(encoding="utf-8") + "\n\n## 10. 質問票\n\n| ID | 重要度 | 質問 | 選択肢 | 推奨 | 状態 | 回答 |\n|---|---|---|---|---|---|---|\n" + row + "\n", encoding="utf-8")
    b = run_entities(repo, "todo").stdout
    assert not rows(b, "「顧客」") and rows(b, "「注文」") and rows(b, "「在庫」")
    assert "| （採番前） | 中 |" in b


def set_optout(repo: Path) -> None:
    p = repo / "scripts" / "ebak.config.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["enterprise_data_catalog"] = "利用しない"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


# FR-1023 AC-159 AC-232 / FR-1024 AC-234
@pytest.mark.parametrize("explicit", [False, True])
def test_ac159_ac232_ac234_opt_out_no_check_no_todo(tmp_path, explicit):
    repo = make_standard(tmp_path / "r")
    if explicit:
        set_optout(repo)
    for c in ("check", "todo"):
        r = run_entities(repo, c)
        assert r.returncode == 0
        assert "企業データカタログ: 利用しない" in r.stdout
        assert ("（未設定）" in r.stdout) == (not explicit)
        assert "企業カタログ未確認" not in r.stdout and "（採番前）" not in r.stdout
    assert rdcheck(repo).returncode == rdcheck(make_standard(tmp_path / "r2")).returncode


# FR-1023 AC-233 FR-1024 AC-163
def test_ac233_ac163_switch_to_use_and_unusable_reports_all_entities(tmp_path):
    repo = make_standard(tmp_path / "r")
    set_optout(repo)
    set_source(repo, "no/such/enterprise-catalog.csv")
    assert "照合不能" in run_entities(repo, "check").stdout
    out = run_entities(repo, "todo").stdout
    assert rows(out, "「顧客」", "企業カタログ未確認") and rows(out, "「注文」", "企業カタログ未確認")


# NFR-COMPAT-003 AC-168
def test_ac168_other_repo_and_zero_entities(tmp_path):
    repo = make_other(tmp_path / "o")
    for c in ("list", "check", "todo"):
        assert run_entities(repo, c).returncode == 0
    assert "エンティティなし" in run_entities(repo, "list").stdout
