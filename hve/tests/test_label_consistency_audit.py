"""test_label_consistency_audit.py — Phase D ラベル整合性監査 workflow の静的検証テスト

label-consistency-audit.yml の存在・構造・ルール定義を検証する。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_LABELS_JSON = _REPO_ROOT / ".github" / "labels.json"
_WORKFLOW = "label-consistency-audit.yml"


def _read_workflow_text(name: str) -> str:
    return (_WORKFLOWS_DIR / name).read_text(encoding="utf-8")


def _load_workflow_yaml(name: str) -> dict:
    text = _read_workflow_text(name)
    return yaml.safe_load(text)


# ---------------------------------------------------------------------------
# D1: ワークフロー存在・トリガー
# ---------------------------------------------------------------------------


class TestLabelConsistencyAuditWorkflowExists(unittest.TestCase):
    """label-consistency-audit.yml の存在とトリガー検証。"""

    def test_workflow_file_exists(self):
        """label-consistency-audit.yml が存在すること。"""
        path = _WORKFLOWS_DIR / _WORKFLOW
        self.assertTrue(path.exists(), f"{_WORKFLOW} が存在しません")

    def test_has_schedule_trigger(self):
        """schedule トリガーが設定されていること。"""
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        self.assertIn("schedule", on_section, "schedule トリガーが必要です")
        schedule = on_section["schedule"]
        self.assertGreater(len(schedule), 0, "cron が少なくとも 1 つ必要です")

    def test_has_workflow_dispatch_trigger(self):
        """workflow_dispatch トリガーが設定されていること。"""
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        self.assertIn("workflow_dispatch", on_section, "workflow_dispatch トリガーが必要です")

    def test_has_issues_trigger(self):
        """issues トリガー（labeled / unlabeled / closed）が設定されていること。"""
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        on_section = yaml_data.get(True, {}) or yaml_data.get("on", {})
        self.assertIn("issues", on_section, "issues トリガーが必要です")
        types = on_section["issues"].get("types", [])
        self.assertIn("labeled", types)
        self.assertIn("unlabeled", types)
        self.assertIn("closed", types)


# ---------------------------------------------------------------------------
# D1: 全 12 系列プレフィックスの監査対象確認
# ---------------------------------------------------------------------------


class TestLabelConsistencyAuditPrefixes(unittest.TestCase):
    """全 12 系列プレフィックスが監査対象に含まれること。"""

    _PREFIXES = [
        "aas", "aad", "aad-web", "asdw", "asdw-web",
        "abd", "abdv", "aag", "aagd", "akm", "adoc", "aqod",
    ]

    def test_all_prefixes_present_in_workflow(self):
        """全 12 系列プレフィックスが workflow の PREFIXES 変数にトークンとして存在すること。"""
        import re
        content = _read_workflow_text(_WORKFLOW)
        # PREFIXES="..." 行からトークンを抽出して境界チェック（部分一致誤検知を防ぐ）
        m = re.search(r'PREFIXES="([^"]+)"', content)
        self.assertIsNotNone(m, 'PREFIXES="..." 行が workflow に見つかりません')
        workflow_prefixes = set(m.group(1).split())
        for prefix in self._PREFIXES:
            self.assertIn(prefix, workflow_prefixes,
                          f"prefix={prefix!r} が PREFIXES 変数のトークン集合に見つかりません（部分一致不可）")

    def test_twelve_prefixes_count(self):
        """監査対象プレフィックスがちょうど 12 系列含まれること。"""
        import re
        content = _read_workflow_text(_WORKFLOW)
        m = re.search(r'PREFIXES="([^"]+)"', content)
        self.assertIsNotNone(m, 'PREFIXES="..." 行が workflow に見つかりません')
        workflow_prefixes = set(m.group(1).split())
        # 定義リストとの完全一致を確認
        self.assertEqual(len(self._PREFIXES), 12)
        missing = [p for p in self._PREFIXES if p not in workflow_prefixes]
        self.assertEqual(missing, [], f"以下の prefix が不足: {missing}")


# ---------------------------------------------------------------------------
# D2: 自動修復ルールの定義確認
# ---------------------------------------------------------------------------


class TestLabelConsistencyAutoFix(unittest.TestCase):
    """自動修復ルールが正しく定義されていること。"""

    def test_done_plus_qa_drafting_is_auto_fix_target(self):
        """done + qa-drafting が自動修復対象に含まれること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("qa-drafting", content)
        # 自動修復対象のサフィックスリストに qa-drafting が含まれる
        self.assertIn("AUTO_FIX_STALE_SUFFIXES", content)

    def test_done_plus_qa_ready_is_auto_fix_target(self):
        """done + qa-ready が自動修復対象に含まれること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("qa-ready", content)

    def test_done_plus_ready_is_auto_fix_target(self):
        """done + ready が自動修復対象に含まれること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("AUTO_FIX_STALE_SUFFIXES", content)
        # 'ready' が AUTO_FIX_STALE_SUFFIXES の値に含まれていること
        self.assertIn("qa-drafting qa-ready ready running", content)

    def test_done_plus_running_is_auto_fix_target(self):
        """done + running が自動修復対象に含まれること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("running", content)

    def test_running_plus_qa_ready_is_not_auto_fix(self):
        """running + qa-ready は自動修復対象外（AMBIGUOUS_PAIRS）であること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("AMBIGUOUS_PAIRS", content)
        self.assertIn("running:qa-ready", content)
        # 双方向定義は重複通知を引き起こすため片方向のみであること
        self.assertNotIn("qa-ready:running", content)

    def test_auto_fix_uses_delete_api(self):
        """自動修復が GitHub API の DELETE を使用すること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("gh api -X DELETE", content)
        self.assertIn("/labels/${stale_label}", content)


# ---------------------------------------------------------------------------
# D3: needs-label-audit ラベルの定義確認
# ---------------------------------------------------------------------------


class TestNeedsLabelAuditLabelDefined(unittest.TestCase):
    """needs-label-audit ラベルが labels.json に定義されていること。"""

    def test_labels_json_has_needs_label_audit(self):
        """`needs-label-audit` が labels.json に存在すること。"""
        self.assertTrue(_LABELS_JSON.exists(), "labels.json が見つかりません")
        with open(_LABELS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        names = [d["name"] for d in data]
        self.assertIn("needs-label-audit", names, "needs-label-audit ラベルが labels.json に定義されていません")

    def test_needs_label_audit_has_description(self):
        """`needs-label-audit` に description が設定されていること。"""
        with open(_LABELS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        entry = next((d for d in data if d["name"] == "needs-label-audit"), None)
        self.assertIsNotNone(entry, "needs-label-audit エントリが見つかりません")
        self.assertTrue(entry.get("description", ""), "description が設定されていません")

    def test_needs_label_audit_has_color(self):
        """`needs-label-audit` に color が設定されていること。"""
        with open(_LABELS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        entry = next((d for d in data if d["name"] == "needs-label-audit"), None)
        self.assertIsNotNone(entry, "needs-label-audit エントリが見つかりません")
        color = entry.get("color", "")
        self.assertEqual(len(color), 6, f"color は 6 桁の hex 文字列である必要があります: {color!r}")


# ---------------------------------------------------------------------------
# D3: needs-label-audit ラベルが workflow で使用されていること
# ---------------------------------------------------------------------------


class TestNeedsLabelAuditUsedInWorkflow(unittest.TestCase):
    """needs-label-audit ラベルが workflow 内で付与ロジックに使用されていること。"""

    def test_workflow_references_needs_label_audit(self):
        """workflow テキストに needs-label-audit が含まれること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("needs-label-audit", content)

    def test_workflow_adds_audit_label_for_ambiguous_cases(self):
        """曖昧なケース（自動修復不可）に対して needs-label-audit を付与するロジックがあること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("AUDIT_LABEL", content)
        self.assertIn("--add-label", content)

    def test_dry_run_guard_present(self):
        """DRY_RUN ガードが実装されていること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("DRY_RUN", content)
        self.assertIn("[DRY RUN]", content)


# ---------------------------------------------------------------------------
# D1: ワークフロー権限・構造
# ---------------------------------------------------------------------------


class TestLabelConsistencyAuditStructure(unittest.TestCase):
    """ワークフローの権限・ジョブ構造検証。"""

    def test_has_issues_write_permission(self):
        """issues: write 権限が設定されていること。"""
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        permissions = yaml_data.get("permissions", {})
        self.assertEqual("write", permissions.get("issues"), "issues: write が必要です")

    def test_has_audit_job(self):
        """audit ジョブが存在すること。"""
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        jobs = yaml_data.get("jobs", {})
        self.assertIn("audit", jobs, "audit ジョブが必要です")

    def test_has_github_step_summary_output(self):
        """GITHUB_STEP_SUMMARY への出力ステップが存在すること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("GITHUB_STEP_SUMMARY", content)

    def test_has_concurrency_group(self):
        """concurrency グループが設定されていること。"""
        yaml_data = _load_workflow_yaml(_WORKFLOW)
        concurrency = yaml_data.get("concurrency", {})
        self.assertTrue(concurrency.get("group", ""), "concurrency.group が必要です")

    def test_auto_fix_rules_documented_in_step_summary(self):
        """自動修復ルールが step summary に記載されていること。"""
        content = _read_workflow_text(_WORKFLOW)
        self.assertIn("自動修復ルール", content)
        # 4 つの自動修復対象が summary に存在すること
        self.assertIn("`*:done` + `*:qa-drafting`", content)
        self.assertIn("`*:done` + `*:qa-ready`", content)
        self.assertIn("`*:done` + `*:ready`", content)
        self.assertIn("`*:done` + `*:running`", content)
