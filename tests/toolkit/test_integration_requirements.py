"""FR-1038 AC-216/217、FR-1039 AC-218/219 の結合テスト（外部連携の要求チェックリストと手順書への組込み）。"""
import re
import sys

from conftest import SOURCE, run

SKILLS = SOURCE / ".github" / "skills"
DOC = SKILLS / "requirement-definition" / "integration-requirements.md"

PERSPECTIVES = ["連携先", "方向", "プロトコル／方式", "頻度と量", "データ分類と個人情報", "認証認可", "可用性／SLA",
                "レート制限", "エラー・再試行・冪等性", "契約／バージョン", "変更通知", "監視", "データ保持",
                "障害時の代替", "責任分界", "法務／ライセンス"]
LABELS = ["(a) 確認する問い", "(b) 要求に書く内容", "(c) 受入基準の例", "(d) 書かない設計事項"]


def sections(text):
    parts = re.split(r"^### 観点 (\d+) (.+)$", text, flags=re.M)
    return {int(parts[i]): (parts[i + 1].strip(), parts[i + 2]) for i in range(1, len(parts), 3)}


# FR-1038 AC-216: 16 観点のすべてに (a)〜(d) がある。1 つでも欠ければ不合格
def test_all_16_perspectives_have_four_parts_and_validation_level():
    secs = sections(DOC.read_text(encoding="utf-8"))
    assert sorted(secs) == list(range(1, 17))
    for n, (name, body) in secs.items():
        assert name.replace(" ", "") == PERSPECTIVES[n - 1].replace(" ", "").replace("（AI補足）", "") or name.startswith(PERSPECTIVES[n - 1]), (n, name)
        for label in LABELS:
            m = re.search(r"^- " + re.escape(label) + r"[:：]\s*(\S.*)$", body, flags=re.M)
            assert m, f"観点 {n} {name}: {label} がない"
        assert re.search(r"検証レベル: (system|integration|unit|manual)", body), f"観点 {n}: 検証レベルがない"


# FR-1038 AC-216: 観点が 1 つ欠けた文書は検査で不合格になる（検査の感度）
def test_missing_perspective_is_detected():
    text = DOC.read_text(encoding="utf-8")
    broken = re.sub(r"### 観点 16 .*?(?=\n## )", "", text, flags=re.S)
    assert sorted(sections(broken)) != list(range(1, 17))


# FR-1038 AC-217: 文書の例が、前提の表を足した要求定義書で verify --docs-only を exit 0 で通る。TBD は質問票へ
def test_template_example_passes_docs_only(sample):
    text = DOC.read_text(encoding="utf-8")
    m = re.search(r"````markdown\n(.*?)````", text, flags=re.S)
    assert m, "テンプレートの例がない"
    example = m.group(1)
    assert "検証レベル:" in example and "BLOCKED: Q-901" in example
    rd = sample.read("docs/requirements-definition.md")
    rd = rd.replace("| 申請 | 利用者が提出する書類 | 申込、エントリー |",
                    "| 申請 | 利用者が提出する書類 | 申込、エントリー |\n| 外部連携 | 外部のアプリ・データとのデータの受け渡し | なし |")
    rd = rd.replace("| PARAM-001 | 下書きの保持期間 | 30 | 日 | 依頼原文 | 承認済み |",
                    "| PARAM-001 | 下書きの保持期間 | 30 | 日 | 依頼原文 | 承認済み |\n| PARAM-901 | 受注の反映時間 | 10 | 分 | 依頼原文 | 承認済み |")
    rd = rd.replace("| Q-001 | 高 | 保持期間の起点はいつか | A: 作成時 / B: 最終更新時 | B | 未回答 | |",
                    "| Q-001 | 高 | 保持期間の起点はいつか | A: 作成時 / B: 最終更新時 | B | 未回答 | |\n| Q-901 | 高 | 受注の頻度と量の上限は | 数値 | 未定 | 未回答 | |")
    rd = rd.replace("## 10. 仮定・未解決事項", example + "\n## 10. 仮定・未解決事項")
    sample.write("docs/requirements-definition.md", rd)
    sample.write("docs/integrations.md",
                 "# 外部連携カタログ\n\n| ID | 名前 | 連携先 | 方向 | 状態 | 関連する要求 |\n|---|---|---|---|---|---|\n"
                 "| INT-901 | 受注受信 | 取引先 A | 受信 | 検討中 | FR-901 |\n\n"
                 "#### INT-901 受注受信\n- 連携先: 取引先 A の受注システム\n- 方向: 受信\n- 方式: REST（HTTPS）\n"
                 "- データ分類: 取引データ（社外秘）\n- 個人情報: あり\n- 認証認可: OAuth 2.0 クライアントクレデンシャル\n"
                 "- 秘密の保管場所: Key Vault（名前は運用手順書）\n- 責任分界: 取引先 A が内容、当社が保管\n- 状態: 検討中\n"
                 "- 関連する要求: FR-901\n- 頻度と量: TBD（Q-901）\n"
                 + "".join(f"- {k}: なし\n" for k in ["可用性・SLA", "レート制限", "エラー・再試行・冪等性", "契約・バージョン",
                                                    "変更通知", "監視", "データ保持", "障害時の代替", "法務・ライセンス"]))
    sample.py("next-id.py", "--sync", "--adopt", check=True)
    sample.py("rdfix.py", "--only", "catalog", "--apply", check=True)
    proc = sample.py("verify.py", "--docs-only")
    assert proc.returncode == 0, proc.stdout[-3000:]


def _skill(name):
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


# FR-1039 AC-218: requirement-definition の手順書に 4 点が書かれている
def test_rd_author_skill_requires_integration_steps():
    t = _skill("requirement-definition")
    assert "外部連携カタログ" in t and "next-id.py INT" in t
    assert "16 観点" in t and "TBD（Q-xxx）" in t and "質問票" in t
    assert "包括承認の対象にしません" in t and "個人情報・認証認可・外部公開" in t
    assert "関連する既存資産" in t and "INT-ID" in t
    assert "integration-requirements.md" in t and (SKILLS / "requirement-definition" / "integration-requirements.md").exists()


# FR-1039 AC-219: rd-audit の手順書に観点と、配布物（インストール対象）への反映がある
def test_rd_audit_skill_and_distribution(repo):
    t = _skill("rd-audit")
    assert "16 観点" in t and "外部連携カタログ" in t and "食い違い" in t
    for rel in ("requirement-definition/integration-requirements.md", "requirement-definition/SKILL.md", "rd-audit/SKILL.md"):
        assert (repo.path / ".github" / "skills" / rel).exists(), rel
