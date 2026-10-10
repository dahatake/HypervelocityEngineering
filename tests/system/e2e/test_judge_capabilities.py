"""Pre-implementation System Tests for the six mandatory judge capabilities.

Expected results come only from AC-044..AC-053 in requirements-definition.md.
The application source is used only for its startup command and public routes.
"""

import hashlib
import json
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect


ROOT = Path(__file__).resolve().parents[3]
STUDIO = ROOT / "EABK-Studio" / "studio.py"
ROUTES = {
    "dashboard": ("ダッシュボード", ("目的", "進捗", "要求")),
    "map2d": ("2D マップ", ("ノード", "関係", "詳細")),
    "map3d": ("3D マップ", ("ノード", "関係", "視点")),
    "diagrams": ("図式", ("図", "関係", "根拠")),
    "placement": ("配置", ("ファイル", "配置", "詳細")),
    "source": ("ソース対応", ("管理データ", "実装", "詳細")),
    "tables": ("表", ("種別", "絞り込み", "行")),
}


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _write_repo(base, name, requirements, catalog="# カタログ\n", ledger=None):
    repo = base / name
    (repo / "docs").mkdir(parents=True)
    (repo / "tests" / "system").mkdir(parents=True)
    (repo / "docs" / "requirements-definition.md").write_text(requirements, encoding="utf-8")
    (repo / "docs" / "catalog.md").write_text(catalog, encoding="utf-8")
    (repo / "docs" / "id-registry.md").write_text(
        "# ID 台帳\n\n| ID | 種別 | 使用状態 |\n|---|---|---|\n"
        "| FR-VALID | FR | 使用中 |\n| AC-VALID | AC | 使用中 |\n",
        encoding="utf-8",
    )
    (repo / "docs" / "run-history.md").write_text(
        "# 実行履歴\n\n| run-id | 工程状態 | commit | 要求 | AC | ケース |\n"
        "|---|---|---|---|---|---|\n"
        "| 202610100001 | 完了 | abcdef1 | FR-VALID | AC-VALID | E2E-900 |\n",
        encoding="utf-8",
    )
    (repo / "tests" / "system" / "ledger.json").write_text(
        json.dumps(
            ledger
            or {
                "version": 1,
                "ac_digests": {"AC-VALID": "sha256:deliberately-wrong"},
                "cases": [
                    {
                        "id": "E2E-900",
                        "requirement_ids": ["FR-VALID"],
                        "ac_ids": ["AC-VALID"],
                        "title": "Synthetic not-run case",
                        "layer": "e2e",
                        "command": "python -c \"raise SystemExit(0)\"",
                        "canary": False,
                        "status": "not_run",
                        "last_commit": None,
                        "last_run_at": None,
                        "evidence": None,
                        "history": [],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return repo


@pytest.fixture()
def studio_page(browser):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(STUDIO), "--repo", str(ROOT), "--port", str(port), "--no-open"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/model", timeout=0.3).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("EABK Studio did not start")
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.goto(f"http://127.0.0.1:{port}")
    page.wait_for_load_state("networkidle")
    yield page
    context.close()
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def _switch_repo(page, repo):
    page.locator("#repoBtn").click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("textbox").fill(str(repo))
    dialog.get_by_role("button", name="OK").click()
    expect(page.locator("#repoBtn")).to_contain_text(repo.name)


def _whole_repo_fingerprint(repo):
    return {
        path.relative_to(repo): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


# FR-1002 AC-044
def test_every_page_has_page_specific_analysis_for_all_three_personas(studio_page):
    page = studio_page
    personas = ("Product Manager", "Architect", "Software Engineer")
    page_texts = {}
    for route, (screen_name, screen_terms) in ROUTES.items():
        page.goto(page.url.split("#")[0] + f"#/{route}")
        analysis = page.get_by_role("region", name=re.compile("分析|analysis", re.I))
        expect(analysis).to_be_visible()
        expect(analysis).to_contain_text(screen_name)
        for persona in personas:
            section = analysis.get_by_role("heading", name=persona).locator("..")
            expect(section).to_contain_text(re.compile("表示情報|information", re.I))
            expect(section).to_contain_text(re.compile("分析観点|perspective", re.I))
            expect(section).to_contain_text(re.compile("判断|decision", re.I))
            assert any(term in section.inner_text() for term in screen_terms)
        page_texts[route] = analysis.inner_text()
    assert len(set(page_texts.values())) == len(ROUTES), "generic text reused instead of page-specific analysis"


# FR-1003 AC-045
def test_current_and_ideal_structure_explain_every_layer_and_difference_type(studio_page, tmp_path):
    requirements = """# Synthetic structure repository
- 目的 G-VALID: Goal
#### FR-VALID Valid requirement
- 要求: Valid
- 決定状態: 承認済み
- 上位: G-VALID
- 受入基準 AC-VALID: Valid criterion
  - 検証レベル: system
#### FR-ORPHAN Parentless requirement
- 要求: Orphan
- 決定状態: 承認済み
- 受入基準 AC-MISSING-REF: references Q-NOT-DEFINED
  - 検証レベル: system
#### FR-DUP Duplicate one
- 要求: first duplicate
#### FR-DUP Duplicate two
- 要求: second duplicate
#### FR-EXTRA Extra
- 要求: unregistered extra
"""
    catalog = """# Catalog
## 機能
| 要求ID | 題名 | 決定状態 | 実装ファイル |
|---|---|---|---|
| FR-VALID | Wrong title | 承認待ち | missing.py |
| FR-VALID | Duplicate row | 承認済み | missing-too.py |
## API・イベント
| 要求ID | 名前 |
|---|---|
## テーブル
| 要求ID | 名前 |
|---|---|
"""
    repo = _write_repo(tmp_path, "all-structure-differences", requirements, catalog)
    # Create invalid/extra records in the remaining canonical layers.
    (repo / "docs" / "id-registry.md").write_text(
        "# ID 台帳\n| ID | 種別 | 使用状態 |\n|---|---|---|\n"
        "| FR-VALID | AC | 使用中 |\n| FR-DUP | FR | 使用中 |\n| FR-DUP | FR | 使用中 |\n"
        "| FR-NOT-DEFINED | FR | 使用中 |\n",
        encoding="utf-8",
    )
    (repo / "docs" / "run-history.md").write_text(
        "# 実行履歴\n| run-id | 工程状態 | commit | 要求 | AC | ケース |\n|---|---|---|---|---|---|\n"
        "| duplicate-run | 完了 | absent | FR-NOT-DEFINED | AC-NOT-DEFINED | E2E-NONE |\n"
        "| duplicate-run | 完了 | absent | FR-NOT-DEFINED | AC-NOT-DEFINED | E2E-NONE |\n",
        encoding="utf-8",
    )
    _switch_repo(studio_page, repo)
    studio_page.goto(studio_page.url.split("#")[0] + "#/structure")
    view = studio_page.locator("#view")
    for layer in ("要求定義書", "境界別要求", "カタログ", "System Test", "ID 台帳", "実行履歴", "境界間"):
        expect(view).to_contain_text(layer)
    expect(view).to_contain_text(re.compile("現状.*理想|current.*ideal", re.I))
    for difference in ("妥当", "不足", "余剰", "孤立", "重複", "参照不整合"):
        row = view.get_by_text(difference, exact=True).first.locator("..")
        expect(row).to_contain_text(re.compile("ID|位置|location", re.I))
        expect(row).to_contain_text(re.compile("必須要素|親子制約|参照制約|required|parent|reference", re.I))
        expect(row).to_contain_text(re.compile("理由|reason", re.I))


def _maintenance_repo(tmp_path):
    requirements = """# Maintenance target
- 目的 G-VALID: Goal
#### FR-VALID Canonical title
- 要求: Canonical title
- 決定状態: 承認済み
- 上位: G-VALID
- 受入基準 AC-VALID: valid
  - 検証レベル: system
"""
    catalog = """# Catalog
## 機能
| 要求ID | 題名 | 決定状態 | 実装ファイル | テスト | 共通部品 |
|---|---|---|---|---|---|
| FR-VALID | Stale title | 承認待ち | app.py | test_app.py | UI |
## API・イベント
| 要求ID | 名前 |
|---|---|
## テーブル
| 要求ID | 名前 |
|---|---|
## 共通部品
| 要求ID | 名前 |
|---|---|
"""
    return _write_repo(tmp_path, "maintenance-target", requirements, catalog)


# FR-1004 AC-046
def test_explicit_maintenance_previews_and_applies_only_two_catalog_columns(studio_page, tmp_path):
    repo = _maintenance_repo(tmp_path)
    _switch_repo(studio_page, repo)
    before = _whole_repo_fingerprint(repo)
    studio_page.get_by_role("link", name=re.compile("整合性保守|maintenance", re.I)).click()
    studio_page.get_by_text("FR-VALID", exact=True).click()
    preview = studio_page.get_by_role("dialog", name=re.compile("preview|プレビュー", re.I))
    expect(preview).to_contain_text("docs/catalog.md")
    expect(preview).to_contain_text("FR-VALID")
    expect(preview).to_contain_text("Stale title")
    expect(preview).to_contain_text("Canonical title")
    expect(preview).to_contain_text("承認待ち")
    expect(preview).to_contain_text("承認済み")
    expect(preview).to_contain_text("python scripts/verify.py --docs-only")
    assert _whole_repo_fingerprint(repo) == before, "preview must not write"
    preview.get_by_role("button", name=re.compile("確認して実行|confirm.*apply", re.I)).click()
    result = studio_page.get_by_role("status")
    expect(result).to_contain_text(re.compile("exit 0", re.I))
    expect(result).to_contain_text(re.compile("preview.*一致|matches.*preview", re.I))
    after = _whole_repo_fingerprint(repo)
    changed = [path for path in after if before.get(path) != after[path]]
    assert changed == [Path("docs/catalog.md")]
    updated = (repo / "docs" / "catalog.md").read_text(encoding="utf-8")
    assert "Canonical title" in updated and "承認済み" in updated
    assert "| app.py | test_app.py | UI |" in updated


# FR-1004 AC-047
@pytest.mark.parametrize(
    "failure",
    ("unsupported", "invalid-input", "preview-conflict", "write-error", "outside-preview", "verify-failure"),
)
def test_maintenance_failures_roll_back_every_byte_and_offer_retry_or_cancel(
    studio_page, tmp_path, failure
):
    repo = _maintenance_repo(tmp_path / failure)
    catalog = repo / "docs" / "catalog.md"
    target_id = "FR-VALID"
    if failure == "unsupported":
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                "| FR-VALID | Stale title | 承認待ち | app.py | test_app.py | UI |",
                "| FR-NOT-DEFINED | Unsupported orphan | 承認済み | app.py | test_app.py | UI |",
            ),
            encoding="utf-8",
        )
        target_id = "FR-NOT-DEFINED"
    elif failure == "invalid-input":
        row = "| FR-VALID | Stale title | 承認待ち | app.py | test_app.py | UI |"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(row, row + "\n" + row),
            encoding="utf-8",
        )
    elif failure == "verify-failure":
        (repo / "scripts").mkdir()
        (repo / "scripts" / "verify.py").write_text(
            "raise SystemExit(1)\n", encoding="utf-8"
        )
    _switch_repo(studio_page, repo)
    before = _whole_repo_fingerprint(repo)
    studio_page.goto(studio_page.url.split("#")[0] + "#/maintenance")
    studio_page.get_by_text(target_id, exact=True).first.click()
    preview = studio_page.get_by_role("dialog", name=re.compile("preview|プレビュー", re.I))
    if preview.count():
        if failure == "preview-conflict":
            catalog.write_text(
                catalog.read_text(encoding="utf-8") + "\n<!-- concurrent edit -->\n",
                encoding="utf-8",
            )
            # The rollback target for a conflict is the bytes at apply start.
            before = _whole_repo_fingerprint(repo)
        elif failure == "write-error":
            catalog.chmod(stat.S_IREAD)
            before = _whole_repo_fingerprint(repo)
        elif failure == "outside-preview":
            readme = repo / "README.md"
            if readme.exists():
                readme.unlink()
            readme.hardlink_to(catalog)
            before = _whole_repo_fingerprint(repo)
        preview.get_by_role(
            "button", name=re.compile("確認して実行|confirm.*apply", re.I)
        ).click()
    error = studio_page.get_by_role("alert")
    expect(error).to_contain_text(
        {
            "unsupported": re.compile("未対応|unsupported", re.I),
            "invalid-input": re.compile("入力条件|input condition", re.I),
            "preview-conflict": re.compile("競合|conflict", re.I),
            "write-error": re.compile("書込み|write", re.I),
            "outside-preview": re.compile("preview.*外|outside.*preview", re.I),
            "verify-failure": re.compile("検査|verify", re.I),
        }[failure]
    )
    expect(error).to_contain_text(re.compile("バイト単位.*戻|byte.*restor", re.I))
    expect(error.get_by_role("button", name=re.compile("再試行|retry", re.I))).to_be_visible()
    expect(error.get_by_role("button", name=re.compile("中止|cancel", re.I))).to_be_visible()
    assert _whole_repo_fingerprint(repo) == before


# FR-1005 AC-048
def test_runtime_and_data_placement_show_local_none_and_defined_cloud_boundaries(studio_page, tmp_path):
    local = _write_repo(
        tmp_path,
        "local-only",
        "# Local\n- 目的 G-VALID: Goal\n#### FR-VALID Local\n"
        "- 要求: Local\n- 決定状態: 承認済み\n- 上位: G-VALID\n"
        "- 受入基準 AC-VALID: Local only\n  - 検証レベル: system\n",
    )
    cloud = _write_repo(
        tmp_path,
        "cloud-linked",
        "# Cloud\n- 目的 G-VALID: Goal\n"
        "- 外部連携 EXT-CLOUD: Azure API（外部送信）\n"
        "#### FR-VALID Cloud\n- 要求: Cloud linked\n- 決定状態: 承認済み\n"
        "- 上位: G-VALID\n- 関連する既存資産: `src/cloud_client.py`\n"
        "- 受入基準 AC-VALID: sends data to EXT-CLOUD\n  - 検証レベル: system\n",
    )
    for repo, boundary in ((local, "なし"), (cloud, "EXT-CLOUD")):
        _switch_repo(studio_page, repo)
        studio_page.goto(studio_page.url.split("#")[0] + "#/placement?kind=runtime")
        view = studio_page.locator("#view")
        for item in ("PC", "ブラウザー", "Studio", repo.name, "管理データ", "実装ファイル"):
            expect(view).to_contain_text(item)
        expect(view).to_contain_text(boundary)
        for direction in ("読取", "書込", "外部送信"):
            expect(view).to_contain_text(direction)
        expect(view).to_contain_text(re.compile("実行場所|runs on", re.I))
        expect(view).to_contain_text(re.compile("データの所在|data location", re.I))


# FR-1006 AC-049
def test_layer_consistency_traces_normal_missing_layer_and_dangling_reference_by_id(studio_page, tmp_path):
    repo = _write_repo(
        tmp_path,
        "layer-consistency",
        "# Consistency\n- 目的 G-VALID: Goal\n"
        "#### FR-VALID Complete\n- 要求: Complete chain\n- 決定状態: 承認済み\n- 上位: G-VALID\n"
        "- 受入基準 AC-VALID: complete\n  - 検証レベル: system\n"
        "#### FR-MISSING Missing test layer\n- 要求: Missing test\n- 決定状態: 承認済み\n- 上位: G-VALID\n"
        "- 受入基準 AC-MISSING: no case\n  - 検証レベル: system\n",
        "# Catalog\n## 機能\n| 要求ID | 題名 | 決定状態 | 実装ファイル |\n|---|---|---|---|\n"
        "| FR-VALID | Complete | 承認済み | valid.py |\n"
        "| FR-MISSING | Missing test | 承認済み | missing.py |\n"
        "| FR-DANGLING | No requirement | 承認済み | nowhere.py |\n",
    )
    _switch_repo(studio_page, repo)
    studio_page.goto(studio_page.url.split("#")[0] + "#/consistency")
    view = studio_page.locator("#view")
    for identifier, outcome in (
        ("FR-VALID", "正常"),
        ("FR-MISSING", "一層欠落"),
        ("FR-DANGLING", "参照先なし"),
    ):
        row = view.get_by_text(identifier, exact=True).first.locator("..")
        expect(row).to_contain_text(outcome)
        for layer in ("要求", "AC", "試験", "カタログ", "実装ファイル"):
            expect(row).to_contain_text(layer)


# FR-1006 AC-050
def test_entity_er_uses_requirement_evidence_and_never_invents_missing_relations(studio_page, tmp_path):
    repo = _write_repo(
        tmp_path,
        "entity-relations",
        "# ER\n- 目的 G-VALID: Goal\n"
        "#### FR-VALID Order contains Items\n- 要求: Order contains Items\n- 決定状態: 承認済み\n"
        "- 上位: G-VALID\n- 対象エンティティ: Order、Item\n"
        "- 関係: Order 1 -- * Item\n"
        "- 受入基準 AC-VALID: relation visible\n  - 検証レベル: system\n"
        "#### FR-NORELATION Customer\n- 要求: Customer exists\n- 決定状態: 承認済み\n"
        "- 上位: G-VALID\n- 対象エンティティ: Customer\n"
        "- 関係: なし\n- 受入基準 AC-NORELATION: no invented relation\n  - 検証レベル: system\n",
    )
    _switch_repo(studio_page, repo)
    studio_page.goto(studio_page.url.split("#")[0] + "#/diagrams?kind=er")
    view = studio_page.locator("#view")
    for text in ("Order", "Item", "FR-VALID", "1", "*"):
        expect(view).to_contain_text(text)
    expect(view).to_contain_text("Customer")
    expect(view).to_contain_text(re.compile("関係情報.*不足|missing relation", re.I))
    assert "FR-NORELATION →" not in view.inner_text()


# FR-1006 AC-051
def test_history_progress_and_infographics_drill_to_evidence_without_counting_not_run_as_pass(
    studio_page,
):
    page = studio_page
    page.goto(page.url.split("#")[0] + "#/dashboard")
    view = page.locator("#view")
    for dimension in ("決定記録", "実行履歴", "要求状態", "実装登録", "System Test", "目的", "データ種別"):
        expect(view).to_contain_text(dimension)
    expect(view).to_contain_text(re.compile("時系列|timeline|状態別|by status", re.I))
    expect(view).to_contain_text(re.compile("測定時点|measured at", re.I))
    not_run = json.loads((ROOT / "tests/system/ledger.json").read_text(encoding="utf-8"))["cases"]
    expected_pass = sum(case["status"] == "pass" for case in not_run)
    expect(view.get_by_test_id("system-test-pass-count")).to_have_text(str(expected_pass))
    for chart in ("目的", "データ種別"):
        view.get_by_role("figure", name=re.compile(chart)).locator("[role=button]").first.click()
        expect(page.locator("#drawer")).to_contain_text(re.compile("根拠|evidence", re.I))


# FR-1007 AC-052
def test_screen_manifest_has_reproducible_same_commit_real_screenshots_for_all_views(
    studio_page, tmp_path
):
    manifest_path = ROOT / "EABK-Studio" / "users-guide" / "screen-images.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest["screens"]
    assert {row["screen_id"] for row in rows} == set(ROUTES)
    assert len(rows) == len({row["screen_id"] for row in rows})
    commits = {row["commit"] for row in rows}
    assert len(commits) == 1
    commit = commits.pop()
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == commit
    for row in rows:
        image = (manifest_path.parent / row["image"]).resolve()
        assert image.is_file()
        assert hashlib.sha256(image.read_bytes()).hexdigest() == row["sha256"]
        assert row["capture_command"] and commit in row["capture_command"]
        route = row["screen_id"]
        page = studio_page
        page.goto(page.url.split("#")[0] + f"#/{route}?select=FR-001")
        for required in row["required_elements"]:
            expect(page.locator("#view")).to_contain_text(required)
        captured = tmp_path / f"{route}.png"
        page.screenshot(path=str(captured), full_page=True)
        assert captured.read_bytes() == image.read_bytes(), (
            f"{route}: manifest image is not the reproducible real screen for {commit}"
        )


def _model_for_start(script, cwd, repo_arg=None):
    port = _free_port()
    command = [sys.executable, str(script), "--port", str(port), "--no-open"]
    if repo_arg is not None:
        command += ["--repo", str(repo_arg)]
    proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/model", timeout=0.4) as response:
                    return json.load(response)
            except OSError:
                time.sleep(0.1)
        raise AssertionError("Studio did not start")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


# FR-010 AC-053
def test_repository_precedence_is_explicit_then_cwd_then_studio_placement(tmp_path):
    explicit = _write_repo(
        tmp_path, "explicit-repo", "# Explicit\n- 目的 G-EXPLICIT: explicit marker\n"
    )
    current = _write_repo(tmp_path, "current-repo", "# Current\n- 目的 G-CURRENT: current marker\n")
    placement = _write_repo(
        tmp_path, "placement-repo", "# Placement\n- 目的 G-PLACEMENT: placement marker\n"
    )
    shutil.copytree(ROOT / "EABK-Studio", placement / "EABK-Studio")
    script = placement / "EABK-Studio" / "studio.py"
    scenarios = (
        (_model_for_start(script, current, explicit), explicit, "G-EXPLICIT"),
        (_model_for_start(script, current), current, "G-CURRENT"),
        (_model_for_start(script, tmp_path), placement, "G-PLACEMENT"),
    )
    for model, expected_repo, marker in scenarios:
        assert Path(model["meta"]["repo"]).resolve() == expected_repo.resolve()
        assert model["meta"]["name"] == expected_repo.name
        assert marker in json.dumps(model, ensure_ascii=False)
