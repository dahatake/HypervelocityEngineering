"""FR-1035 AC-208/209/210, FR-1036 AC-211/212/213, FR-1037 AC-214/215 の単体・結合テスト（外部連携カタログ）。"""
import re
import sys
from pathlib import Path

from conftest import SOURCE, run

CAT = "docs/integrations.md"

PERSPECTIVES = ["頻度と量", "可用性・SLA", "レート制限", "エラー・再試行・冪等性", "契約・バージョン",
                "変更通知", "監視", "データ保持", "障害時の代替", "法務・ライセンス"]


def entry(n="001", name="受注 API", **over):
    f = {
        "連携先": "取引先 A の受注システム", "方向": "受信", "方式": "REST（HTTPS）", "データ分類": "取引データ（社外秘）",
        "個人情報": "あり", "認証認可": "OAuth 2.0 クライアントクレデンシャル", "秘密の保管場所": "Key Vault（名前は運用手順書）",
        "責任分界": "取引先 A が内容、当社が保管", "状態": "検討中", "関連する要求": "FR-001",
    }
    f.update({k: "なし" for k in PERSPECTIVES})
    f["頻度と量"] = "TBD（Q-001）"
    f.update(over)
    f = {k: v for k, v in f.items() if v is not None}
    return f"#### INT-{n} {name}\n" + "".join(f"- {k}: {v}\n" for k, v in f.items()) + "\n"


INDEX = "| ID | 名前 | 連携先 | 方向 | 状態 | 関連する要求 |\n|---|---|---|---|---|---|\n| INT-001 | 受注 API | 取引先 A | 受信 | 検討中 | FR-001 |\n\n"


def put(sample, body, index=INDEX):
    sample.write(CAT, "# 外部連携カタログ\n\n" + index + body)


def docs(sample):
    return sample.py("verify.py", "--docs-only")


def errors(proc):
    return [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("ERROR") and "CHK-28" in ln]


# FR-1035 AC-208 / FR-1036 AC-212 (違反なしは 0)
def test_valid_catalog_passes_docs_only(sample):
    put(sample, entry())
    proc = docs(sample)
    assert proc.returncode == 0, proc.stdout
    assert not errors(proc)


# FR-1035 AC-210: カタログのない導入先では CHK-28 の報告が一切ない
def test_no_catalog_reports_nothing(sample):
    assert not (sample.path / CAT).exists() or (sample.path / CAT).unlink() is None
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    assert proc.returncode == 0 and "CHK-28" not in proc.stdout


# FR-1035 AC-208 / FR-1036 AC-212: 必須欄・観点の欄の欠落
def test_missing_required_and_perspective_fields_are_reported_with_id_and_line(sample):
    put(sample, entry(連携先=None, 監視=None))
    proc = docs(sample)
    assert proc.returncode != 0
    out = "\n".join(errors(proc))
    assert "INT-001" in out and "必須欄「連携先」" in out and "観点の欄「監視」" in out
    assert re.search(r"docs/integrations\.md:\d+", out)


# FR-1036 AC-212: 値の形式・TBD の Q-ID・方向・状態・関連する要求
def test_value_format_tbd_direction_state_and_requirement_violations(sample):
    put(sample, entry(頻度と量="TBD", 監視="TBD（Q-404）", 方向="どちらも", 状態="稼働", 関連する要求="FR-999", データ保持="未定"))
    out = "\n".join(errors(docs(sample)))
    for needle in ("の形式ではありません", "質問票にありません", "方向「どちらも」", "状態「稼働」", "関連する要求 FR-999", "「データ保持」の値「未定」"):
        assert needle in out, (needle, out)


# FR-1036 AC-212: ID の重複・形式の誤り
def test_duplicate_and_malformed_ids(sample):
    put(sample, entry() + entry(name="重複") + entry(n="1", name="形式誤り"))
    out = "\n".join(errors(docs(sample)))
    assert "INT-001 が重複" in out and "INT-1 は ID の形式" in out


# FR-1035 AC-209: 認証情報の値は違反。方式の名前と保管場所の名前は可
def test_secret_looking_values_and_secret_fields_are_violations(sample):
    for bad in ("パスワード: hunter2hunter2", "Bearer abcdefghijklmnopqrstuvwxyz0123", "Server=db.example.com;Password=abc12345",
                "https://user:pass1234@example.com/x", "sk-abcdefghijklmnopqrstuvwx"):
        put(sample, entry(認証認可=bad))
        proc = docs(sample)
        assert proc.returncode != 0 and "認証情報の値" in "\n".join(errors(proc)), bad
    put(sample, entry().replace("- 状態:", "- 接続文字列: x\n- 状態:"))
    assert "認証情報の値を書く欄" in "\n".join(errors(docs(sample)))
    put(sample, entry(認証認可="OAuth 2.0（秘密の保管場所: Key Vault kv-orders-prod）"))
    assert docs(sample).returncode == 0


# FR-1036 AC-213: 未定義参照・trace・運用中で未承認は警告
def test_undefined_reference_trace_and_active_warning(sample):
    put(sample, entry())
    rd = sample.read("docs/requirements-definition.md").replace(
        "- 受入基準 AC-002: 保持期間を過ぎた下書きは表示されない。",
        "- 受入基準 AC-002: 保持期間を過ぎた下書きは表示されない。INT-777 とは連携しない。")
    sample.write("docs/requirements-definition.md", rd)
    proc = docs(sample)
    assert proc.returncode != 0 and "INT-777" in proc.stdout and "未定義参照" in proc.stdout
    sample.write("docs/requirements-definition.md", rd.replace("INT-777", "INT-001"))
    t = sample.py("rdcheck.py", "trace", "INT-001", check=True).stdout
    assert "FR-001" in t and "AC-002" in t
    sample.write("docs/requirements-definition.md", sample.read("docs/requirements-definition.md").replace("承認済み（依頼 2026-10-08）", "承認待ち"))
    put(sample, entry(状態="運用中"))
    out = sample.py("rdcheck.py", "check", "--base", "none").stdout
    assert re.search(r"WARN CHK-28 .*INT-001 は運用中", out)
    assert sample.py("rdcheck.py", "trace", "INT-404").returncode == 1


# FR-1036 AC-211: next-id.py INT
def test_next_id_int_allocates_records_and_peek_does_not(sample):
    assert sample.py("next-id.py", "INT", check=True).stdout.strip() == "INT-001"
    assert "| INT-001 | INT | 採番済み |" in sample.read("docs/id-registry.md")
    assert sample.py("next-id.py", "--peek", "INT", check=True).stdout.strip() == "INT-002"
    assert sample.py("next-id.py", "--peek", "INT", check=True).stdout.strip() == "INT-002"
    put(sample, entry() + entry(n="005", name="別連携"))
    assert sample.py("next-id.py", "INT", check=True).stdout.strip() == "INT-006"
    assert sample.py("next-id.py", "XYZ").returncode != 0


def test_next_id_int_is_shared_across_worktrees_and_sync_keeps_used_rows(sample):
    from conftest import Repo, git
    wt = sample.path / "work" / "worktrees" / "r-9"
    git(sample.path, "worktree", "add", "-q", str(wt), "-b", "work/r/9")
    a = sample.py("next-id.py", "INT", check=True).stdout.strip()
    b = Repo(wt).py("next-id.py", "INT", check=True).stdout.strip()
    assert (a, b) == ("INT-001", "INT-002")
    put(sample, entry())
    sample.py("next-id.py", "--sync", check=True)
    assert re.search(r"\| INT-001 \| INT \| 使用中 \|", sample.read("docs/id-registry.md"))


# FR-1037 AC-214 / AC-215: 配布物と版
def test_install_distributes_template_and_checklist_and_version_is_bumped(repo):
    text = repo.read(CAT)
    assert "| ID | 名前 | 連携先 | 方向 | 状態 | 関連する要求 |" in text
    assert (repo.path / ".github/skills/requirement-definition/integration-checklist.md").is_file()
    assert repo.py("rdcheck.py", "check", "--base", "none").returncode == 0
    ver = re.search(r'TOOLKIT_VERSION = "([\d.]+)"', (SOURCE / "scripts" / "ebaklib.py").read_text(encoding="utf-8")).group(1)
    assert ver != "0.3.0"
    out = run([sys.executable, str(SOURCE / "tools" / "install.py"), "--version"], SOURCE).stdout.strip()
    assert out == ver
    # AC-215: users-guide の手順と実際の挙動の対応
    guide = (SOURCE / "users-guide" / "03-requirements-format.md").read_text(encoding="utf-8")
    assert "next-id.py INT" in guide and "docs/integrations.md" in guide and "--docs-only" in guide
    assert "docs/integrations.md" in (SOURCE / "README.md").read_text(encoding="utf-8")
    assert "外部連携カタログ" in (SOURCE / "CHANGELOG.md").read_text(encoding="utf-8")
