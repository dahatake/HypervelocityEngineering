# Copilot 共通ルール

本ファイルは Copilot が最初に参照する **最上位の強制ルール（エントリーポイント）**。
詳細手順は各 Skill（`.github/skills/*/SKILL.md`）に委譲する。本ファイルが規範ルール、Skills が技術手順リファレンスであり、両者で正式ルールを構成する。なお Skills ファイルに移行過渡期の旧参照が残る場合があるが、本ファイルの記述が常に優先される。

---

## §0 最優先ルール（認知プライミング）

- **出力言語**: 出力は日本語。見出し＋箇条書き中心で簡潔に。
- **出力は最小限**: 長文は `work/` 配下（Skill work-artifacts-layout）。
- **変更は最小差分**: 無関係な整形・一括リファクタ・不要依存追加をしない。
- **捏造禁止**: ID/URL/固有名/数値/事実を根拠なく作らない。不明は `TBD` / `不明（要確認）` と明記する。
- **秘密情報禁止**: 鍵・トークン・個人情報・内部 URL 等を追加・出力しない。
- **推論補完時**: `TBD（推論: {根拠}）` + 「この回答はCopilot推論をしたものです。」と明記する。
- **task_scope=multi または context_size=large の扱い**:
  - **単独実行モード**（Orchestrator 配下でない Agent 単独起動・テスト等）: 実装開始禁止。plan.md + subissues.md のみ作成して終了する。
  - **Orchestrator 配下モード**（HVE Cloud Agent Orchestrator / HVE CLI Orchestrator 実行配下）: Agent は plan.md + subissues.md を作成して当該 Step を終了する。**Orchestrator が** subissues.md を読み込み、`depends_on` 解決により wave 分割したサブタスクを並列実行（Sub-issue 生成 / サブセッション fork）し、全完了後に親 Step の後続または次タスクへ進む。`task_scope=multi` / `context_size=large` のいずれも対象。
  - **判別方法**: Orchestrator 起動時に生成される `OrchestratorContext` を Python 内部で明示的引数として `StepRunner` / `check_plan_md_metadata` 等へ伝播させる方式。`HVE_ORCHESTRATOR_ACTIVE` 環境変数は撤廃済み（参照禁止）。詳細は Skill `task-dag-planning` 参照。
- **plan.md 冒頭5行にメタデータ必須**（Skill task-dag-planning §2.1.2）。欠落は CI で自動拒否。
- **最低1つの検証を実施**: テスト/ビルド/静的解析のいずれかを行い、できない場合は理由と代替を明記する。
  - **タスク完了報告の検証マーカー必須記載書式**（GitHub 連携時は `auto-approve-and-merge.yml` の自動判定対象、CLI 連携時は人手レビュー可読性と将来の自動化準備）: 以下のいずれかの形式で記載すること:
    1. HTML コメントマーカー: `<!-- validation-confirmed -->`（推奨。最も確実）
    2. 見出し: `## 検証` / `## 検証結果` / `## Validation` 等（行頭 `#` + 語）
    3. 箇条書き / 強調: `- 検証: <内容>` / `**検証**: <内容>`（行頭 + 語 + コロン）
  - 検証実施が困難な場合も「検証: 該当なし（理由: ...、代替: ...）」と記載すること。
- **ルート README.md 変更禁止**: `/README.md` を作成・変更してはならない。`README.md` のような裸パス表現は避け、ルート以外の README を指す必要がある場合は `infra/.../README.md` などの明示パスで記載する。
- **質問方針**：質問なしで進められる場合は質問しない。必要な質問は分類項目・重要度（最重要/高/中/低）付きで過不足なく行う。「最重要」「高」は回答を優先的に求め、「中」「低」は既定値で進行可能とする。タスク定義書（GitHub Issue body / CLI 起動時メタデータ）に `<!-- auto-context-review: true -->` が記載されている時は、コンテキストが十分な場合でも設計判断・技術選定・スコープの確認を目的として質問する。
- **推論許可**：「推論で進めてください」の意思表示を以降「**推論許可**」と呼ぶ。
- **書き込み失敗対策**：edit 後に read で空でないことを確認。空なら小チャンク（2,000〜5,000文字）に分割して再試行（最大3回）。
- **work/ および qa/ 書き込みルール（絶対）**：`work/` または `qa/` 配下へのファイル書き込みは Skill `work-artifacts-layout` §4.1 準拠。例外なし。
- **knowledge/ 書き込みルール（絶対）**：`knowledge/` 配下へのファイル書き込みも Skill `work-artifacts-layout` §4.1 準拠（削除→新規作成）。例外なし。
- **knowledge/ 同時更新防止（LOCK）**: `knowledge/` 本体ファイルへ LOCK 情報を埋め込んではならない。LOCK が必要な場合は `work/` 配下のロックファイル、または Issue ラベル等、`knowledge/` の「削除→新規作成」ルールと両立する方式を用いる。他の Agent により対象 D{NN} の LOCK が取得済みであることを検知した場合、後続 Agent は当該 `knowledge/` ファイルを **読み取り専用** とし、書き込みを中止して再実行に回す。
- **original-docs/ 読み取り専用（絶対）**: `original-docs/` 配下のファイルは全 Agent から **読み取り専用**。変更・削除・追記を禁止。

---

## §0.5 用語定義（タスク / サブタスク）

本ファイルでは **HVE Cloud Agent Orchestrator（GitHub Issue/PR ベース）** と **GitHub Copilot CLI（セッション/サブセッション ベース）** を共通の語彙で扱うため、以下の上位概念を用いる。GitHub 固有の仕様（`Fixes #N`、`auto-approve-and-merge.yml` 等）は §7.2 に集約し、本ファイルのその他の本文は両環境に適用される。

| 上位概念 | GitHub Issue 起点モード（Cloud） | CLI セッション起点モード（CLI） |
|---|---|---|
| **タスク** | Issue | `hve orchestrate` 1 回実行（CLI 起動セッション） |
| **サブタスク** | Sub-issue（Copilot アサイン） | サブセッション |
| **タスク定義書** | Issue body | 起動時引数 / 起動時メタデータ |
| **サブタスク定義書ファイル** | `subissues.md` | `subissues.md` |
| **タスク完了報告** | PR body | `work/Issue-<識別子>/completion-report.md` |
| **タスク完了通知** | PR Merge / Issue Close | journal レコード（`hve/run_journal.py`）/ セッション終了 |
| **検証マーカー書式** | `<!-- validation-confirmed -->` 等（`auto-approve-and-merge.yml` 自動判定対象） | 同書式（将来の自動化準備および人手レビュー時の可読性のため） |

**補足**:

- ファイル名 `subissues.md` は歴史的経緯（GitHub Sub-issue を直接想定した時期の名残）で残置している。本ファイル内では「サブタスク定義書（`subissues.md`）」と読み替える。
- **混合運用ガイダンス**: CLI セッション起点で作業を進めつつ、後に GitHub へ push して PR を作成する混合運用の場合は、§7.2（GitHub 連携時の追加ルール）と §7.3（CLI セッション時の追加ルール）の **両方を適用** すること。
- 「Issue」「PR」「Sub-issue」の語が単独で出てくる箇所は GitHub Issue 起点モード限定の文脈である。CLI セッション起点モードでは対応する用語（タスク / サブタスク等）に読み替える。

---

## §1 ワークフロー概要

Agent の標準作業フローは以下の 5 フェーズで構成される。各フェーズで参照すべき Skill を明示する。

```
[1. コンテキスト収集]
  - GitHub Issue 起点モード: Skill: task-questionnaire（詳細）
  - CLI セッション起点モード: Skill: task-questionnaire（詳細）
        ↓
[2. 計画（DAG + 見積 + 分割判定）]
  - Skill: task-dag-planning
  - task_scope=multi または context_size=large → SPLIT_REQUIRED（実装禁止）
  - ※Orchestrator 配下かつ task_scope=multi は §0 例外により別 Context で継続
        ↓
[3. 実装]
  - work/ 構造: Skill: work-artifacts-layout
  - 大量出力: Skill: large-output-chunking
  - 安全ガード: Skill: harness-safety-guard
        ↓
[4. 検証]
  - Skill: harness-verification-loop（Build/Lint/Test/Security/Diff）
  - エラー発生時: Skill: harness-error-recovery
  - レビュー（ユーザー指定時のみ）: Skill: adversarial-review
        ↓
[5. 完了報告とタスク終了]
  - タスク完了報告の出力先:
    - GitHub Issue 起点: PR body に記載 → §7.1 + §7.2 参照
    - CLI セッション起点: `work/Issue-<識別子>/completion-report.md` に記載 → §7.1 + §7.3 参照
  - 混合運用（CLI で作業した後 GitHub へ push）: §7.2 と §7.3 を併用
```

初見のリポジトリの場合は先に **Skill: repo-onboarding-fast** を参照すること。

---

## §2 Skills ルーティング

Skill の参照先選定は **Skill `_routing`**（`.github/skills/_routing/SKILL.md`）を参照すること。
本体には強制ルール（§0, §3, §5-§10）を残し、ルーティング表は `_routing` Skill で管理する。

---

## §3 コアルール参照テーブル

本ファイルの §0 に記載されたコアルールと、対応する Skill の対応表。

| ルール | 詳細を持つ Skill |
|---|---|
| コンテキスト収集（GitHub Issue 起点 / CLI セッション起点） | `task-questionnaire` |
| plan.md メタデータ・分割判定 | `task-dag-planning` |
| 成果物パス・work/qa/ 構造 | `work-artifacts-layout` |
| 巨大出力分割 | `large-output-chunking` |
| 敵対的レビュー | `adversarial-review` |
| 検証ループ (Build/Lint/Test/Security/Diff) | `harness-verification-loop` |
| 安全ガード (破壊的操作検出) | `harness-safety-guard` |
| エラーリカバリ (3要素出力) | `harness-error-recovery` |
| リポジトリ初見オンボーディング | `repo-onboarding-fast` |

---

## §4 アプリケーション粒度の参照ルール（`docs/catalog/app-catalog.md` + §4）

詳細ルール（APP × サービス/エンティティ N:N、APP × 画面 1:1、成果物ファイル分割基準）: Skill `app-scope-resolution` §成果物ファイル分割基準 参照。

コード→要件→ADR トレーサビリティ（コードコメント・タスク完了報告（PR body / completion-report.md）・テストコードへの埋め込み形式）: Skill `knowledge-management` §コード→要件→ADR トレーサビリティ 参照。

---

## §5 Custom Agent との関係

Custom Agent（`.github/agents/*.agent.md`）は、本ファイルのルールを継承し、固有の追加ルールのみを記載する。

**優先順位（高 → 低）**:
1. **本ファイル（copilot-instructions.md）**（最優先・常に適用）
2. **Custom Agent のジョブ定義**（リポジトリ固有の方針）
3. **Skills**（技術リファレンス）

> 本ファイルの記述と Custom Agent の記述が矛盾する場合は本ファイルが優先される。
> SKILL.md と Custom Agent の記述が矛盾する場合は Custom Agent が優先される。
> `agent-common-preamble` Skill の共通ルールは、Agent 側で明示的にオーバーライドしない限り適用される（デフォルト継承モデル）。

**Skills 参照ルール（Custom Agent 向け）**:
- `.github/skills/` 配下の SKILL.md は、技術リファレンス（手順・コマンド・トラブルシューティング）を提供する。
- Custom Agent は、作業開始時に `agent-common-preamble` Skill を参照し、共通ルールを確認すること。
- Custom Agent 固有の追加 Skills は `## Agent 固有の Skills 依存` セクションに明示する。
- SKILL.md の情報を採用しない場合は、Custom Agent 側でその理由を明記すること（Non-goals 等で）。

**original-docs/ に関するルール（全 Agent 必須）**:
- 読み取り専用ルール: §0 参照（変更・削除・追記禁止）
- `original-docs/` のファイルを knowledge/ に取り込む作業は `KnowledgeManager` Agent が担当
- 他の Agent は、ユースケースに応じて以下のいずれかの参照方式を選択できる:
  - **直接参照**: `original-docs/` を直接読み取る（横断分析・質問票作成・早期フィードバック等で有効）
  - **knowledge/ 経由参照**: `KnowledgeManager` が生成した `knowledge/D01〜D21-*.md` を参照
  - **ハイブリッド**: 両方を参照
- どの参照方式を採用したかは Agent 仕様の `## 入力` セクションに明記すること

---

## §6 直列/並列の判断と共有（衝突を避ける）

詳細判断基準・共有方法: Skill `task-dag-planning` §直列/並列の判断と共有 参照。

---

## §7 タスク完了報告に必ず書く（短くてよい）

### §7.1 共通ルール（GitHub Issue 起点モード / CLI セッション起点モード 両方に適用）

- **必須セクション**: **目的** / **変更点** / **影響範囲** / **検証結果**（§0 検証マーカー書式準拠）/ **既知の制約** / **次にやるサブタスク**（残作業）
- **元タスク参照（必須）**: 起点となったタスクへの参照を記載する。記載形式はモード別に §7.2 / §7.3 を参照。

### §7.2 GitHub Issue 起点モード（PR body）

- **元 Issue リンク（必須）**: PR の起点となった Issue 番号を `Fixes #N` / `Closes #N` / `Resolves #N` で記載する（分割モード・PROCEED モード問わず全 PR に適用。Issue 番号が不明な場合は `<!-- parent-issue: #N -->` を記載）。
- **PR body 更新時の保持義務（必須）**: PR body を更新する場合、既存の `Fixes #N` / `Closes #N` / `Resolves #N` および `<!-- parent-issue: #N -->` を **絶対に削除しないこと**。PR body を全置換する場合は、元の body からこれらを抽出して新しい body の先頭に再挿入すること。
- **検証マーカー自動判定**: `auto-approve-and-merge.yml` ワークフローが §0 検証マーカー書式を自動検査する。

### §7.3 CLI セッション起点モード（completion-report.md）

- **出力先**: `work/Issue-<識別子>/completion-report.md`（ファイル名 `Issue-` prefix は `work-artifacts-layout` Skill の既存規約により残置。`<識別子>` は CLI セッション識別子または作業ディレクトリ名）。
- **元タスク参照**: `<!-- parent-task: <work-dir-name> -->` を completion-report.md の先頭に記載する。GitHub Issue 由来であれば `<!-- parent-issue: #N -->` も併記可。
- **タスク完了通知**: journal レコード（`hve/run_journal.py` の `end` イベント）として記録される。
- **混合運用**: 後に GitHub へ push する場合、completion-report.md の内容を PR body に転記し、§7.2 のルールも適用する。

---

## §8 出力品質 (Observation Quality)

全 Agent の成果物に `status` / `summary` / `next_actions` / `artifacts` の4要素を含める。テンプレート詳細: Skill `work-artifacts-layout` §成果物サマリーテンプレート 参照。§7.1 の必須セクション（目的/変更点/影響範囲/検証結果/既知の制約/次にやるサブタスク）と統合してタスク完了報告（PR body または `completion-report.md`）内に記載する。

---

## §9 差分品質評価 (Diff Quality Assessment)

タスク完了報告（PR body / `completion-report.md`）提出前に実施する。詳細手順（`git diff --stat` によるスコープ確認・無関係変更検出・`verification-report.md` への記録）: Skill `harness-verification-loop` §差分品質評価 参照。

---

## §10 例外（下位ディレクトリ固有ルールを置く場合）

- 置くのは「そのディレクトリ固有の追加ルール」だけ。
- 必ず「ルート copilot-instructions.md を継承し、追加/上書き点のみ記載」と明記する。

---

<!-- TODO(neutralization): §0.5 で導入した「タスク / サブタスク」抽象語彙は、本ファイルおよび `task-questionnaire` / `harness-verification-loop` Skill に適用済み。残課題として `.github/agents/*.agent.md` 群および `.github/labels.json` の "Issue" / "PR" 固有表現の中立化（CLI セッション起点モードでの読み替えガイダンス追加）を別タスクで実施すること。 -->


---

## §11 Copilot セッション運用ルール

- **Copilot Coding Agent のセッションを GitHub UI から手動 Stop しない**。手動 Stop を行うと PR タイムラインに `The session was cancelled by the user.` というノイズイベント（タイムライン上に表示）が残る。
- セッションは PR の merge / close によって Copilot プラットフォームが自動終了するため、明示的に停止する必要はない。
- 詳細は [`knowledge/copilot-session-cancelled-event.md`](/knowledge/copilot-session-cancelled-event.md) を参照。
