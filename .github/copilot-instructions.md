# Copilot 共通ルール

本ファイルは Copilot が最初に参照する **最上位の強制ルール（エントリーポイント）**。
詳細手順は各 Skill（`.github/skills/*/SKILL.md`）に委譲する。本ファイルが規範ルール、Skills が技術手順リファレンスであり、両者で正式ルールを構成する。なお Skills ファイルに移行過渡期の旧参照が残る場合があるが、本ファイルの記述が常に優先される。

---

## §0 最優先ルール（認知プライミング）

- **出力言語**: 出力は日本語。見出し＋箇条書き中心で簡潔に。
- **PowerShell は最新 `pwsh` 固定**: Windows の PowerShell 実行は `pwsh.exe`（PowerShell 7+ / PSEdition Core）の最新インストール済み版だけを使う。`powershell` / `powershell.exe` / Windows PowerShell 5.1 の直接実行・フォールバックは禁止。`pwsh` が無ければ PowerShell 7+ 必須として fail-closed で停止する。自動化・テスト・`.ps1` 実行は `pwsh.exe -NoLogo -NoProfile` を基本とする。
- **出力は最小限**: 長文は `work/` 配下（Skill work-artifacts-layout）。
- **変更は最小差分**: 無関係な整形・一括リファクタ・不要依存追加をしない。
- **曖昧なリポジトリ内 HVE 実行意図の優先ルーティング（必須）**:
  - このリポジトリを対象とする「Azure にデプロイして」「APP の Web アプリを作って」「バッチを実装して」のような依頼は、Workflow / Step / APP-ID / resource group / deploy 範囲が不足する **曖昧な HVE 実行意図**として扱う。
  - 外部 Azure Skill の読込み、tool call、ファイル書き込みより先に repository Skill `hve-prompt-edition` を選択し、不足値を応答本文へ inline で質問する。値が一意になるまで request / plan / run を開始せず、`.azure/`、`qa/`、`docs/`、`src/` その他の成果物を作成・変更しない。
  - 利用者が「HVE を介さず、既存 `azure.yaml` を使って `azd` で直接デプロイ」のように HVE を介さないことと操作手段を明示した direct Azure 操作だけはこの優先規則の対象外とし、対応する外部 Azure Skill の承認・安全ゲートへ委ねる。
- **HVE の版管理と変更履歴（必須）**: HVE の実装または実行契約を変更するジョブは、**ユーザーからの指示・依頼の有無にかかわらず**、完了報告前に同じ変更セットで `CHANGELOG.md` と HVE パッケージ版を更新する。
  - 対象は `hve/**`、`hve-dev/**`、`.github/copilot-instructions.md`、`.github/instructions/**`、`.github/prompts/**`、`.github/skills/**`、`.github/io-contracts/**`、`.github/scripts/**`、`.github/workflows/**`（後述の生成アプリ向けデプロイ workflow を除く）、`.github/ISSUE_TEMPLATE/**`、HVE が使用する `template/**`、および HVE の実行・契約を変える設定・スクリプトとする。`CHANGELOG.md`、`hve/__init__.py`、`pyproject.toml` だけの同期修正は、この規則による追加 bump のトリガーにしない。独立ライフサイクルで版管理する `mdq/**` / `cq/**` / 配布キットは本規則の PATCH 対象ではなく、それぞれの版管理手順に従う。
  - **HVE が生成・支援する別アプリケーションの成果物には適用しない**。`src/**`、`docs/**`、`docs-generated/**`、`knowledge/**`、`qa/**`、`docs-original/**`、`sample/**`、`tests/run/**`、`package.json` / `jest.config.js` / `babel.config.js` / `playwright.config.js`、および `.github/workflows/deploy-*.yml` / `.github/workflows/azure-static-web-apps-*.yml` / `.github/workflows/app<数字>*.yml` は対象外で、これらだけを変更するジョブは HVE の版を上げない。対象判定の単一の機械正本は [.github/scripts/hve_scope.py](.github/scripts/hve_scope.py) であり、本規則の列挙と食い違う場合は同モジュールを正とする。
  - **PATCH（`x.y.z` の `z`）の更新は Copilot が自律的に実施する（必須・確認不要）**。対象変更を 1 件でも含むジョブは、指示・承認を待たずに 1 ジョブにつき 1 回だけ PATCH を増やす。「指示が無い」「差分が小さい」「文書だけの変更に見える」「別ジョブと競合しうる」「`CHANGELOG.md` に既存の `[Unreleased]` がある」のいずれも、省略・後回し・ユーザーへの委譲・提案止まりの理由にしてはならない。判断に迷う場合は更新する側へ倒す。MINOR（`x.y.0` の `y`）への更新だけはユーザーが明示的に判断した場合に行い、Copilot が自律的に増やしてはならない。
  - `pyproject.toml` の `[project].version` と `[tool.bumpversion].current_version`、`hve/__init__.py` の `__version__`、`CHANGELOG.md` の版見出しを同一バージョンへ同期する。`CHANGELOG.md` には変更点・影響・検証結果を記録し、他作業の `[Unreleased]` エントリーを移動または再分類してはならない。既存の `[Unreleased]` 内容がある場合は、その内容の後ろに新しい版見出しを追加し、見出し直後への機械挿入で既存記録を新リリースへ取り込ませない。
  - **完了報告前の版更新セルフチェック（必須）**: 完了報告を出す前に変更パス一覧（`git diff --name-only` 等）を取得し、上記の機械正本で対象変更の有無を判定する。対象変更があるのに (a) `pyproject.toml` / `hve/__init__.py` / `CHANGELOG.md` が同じ変更セットに揃っていない、(b) 前項の 4 箇所の版番号が相互に一致しない、(c) 直前の版から増えていない、のいずれかに該当する場合は、完了報告を出さずに版更新を実施してから再確認する。確認結果は §7.1 の検証結果へ 1 行で記録する。
- **捏造禁止**: ID/URL/固有名/数値/事実を根拠なく作らない。不明は `TBD` / `不明（要確認）` と明記する。
- **秘密情報禁止**: 鍵・トークン・個人情報・内部 URL 等を追加・出力しない。
- **推論補完時**: `TBD（推論: {根拠}）` + 「この回答はCopilot推論をしたものです。」と明記する。
- **task_scope=multi または context_size=large の扱い**:
  - **単独実行モード**（Orchestrator 配下でない Agent 単独起動・テスト等）: 実装開始禁止。plan.md + subissues.md のみ作成して終了する。
  - **Prompt 版承認後の委譲（限定例外）**:
    - Prompt Edition controller（Prompt 版を仲介する Agent）は承認前は plan 提示だけを行い、run してはならない。
    - 提示済み計画への明示承認後、同 controller は提示された SHA-256 を渡して `hve prompt run` を起動する。HVE が FR-PROMPT-04 の SHA-256 一致を確認した場合だけ既存 `orchestrate` へ進む。この委譲を、controller が standalone で `task_scope=multi` / `context_size=large` であることを理由に止めてはならない。
    - この例外は既存 `orchestrate` への委譲に限る。同 controller は対象成果物を直接実装・編集してはならない。
    - `hve prompt run` が plan SHA-256 の不一致を stale として検出した場合は、`orchestrate` へ進まず、再plan・再提示・再承認を実施する。
    - 委譲後も CLI Orchestrator の既存制約、`output_paths` gate、認証・権限・Azure・QA・デプロイ承認を維持する。
  - **Cloud Agent Orchestrator 配下モード**（Issue Template + GitHub Actions + Copilot Cloud Agent）: Agent は plan.md + subissues.md を作成して当該 Step を終了する。PR に `create-subissues` ラベルが付与されると GitHub Actions が subissues.md を読み込み、Sub-Issue を作成して Copilot Cloud Agent にアサインする。
  - **CLI / GUI Orchestrator 配下モード**: GitHub Sub-Issue 作成は行わない。CLI / GUI の標準実行は workflow DAG / fan-out で分割・並列化する。`subissues.md` runtime fork は legacy / 実験用途の明示 opt-in（`OrchestratorContext.split_fork_enabled=True`、Copilot SDK fleet mode）のみ。**このモードでは Agent は `task_scope` / `context_size` による SPLIT_REQUIRED 判定を行わず、宣言された `output_paths` の主成果物を必ず生成してから終了すること**（`plan.md` / `subissues.md` のみの出力で終了すると後続 Step が成果物不在で skip / 失敗するため）。本モードを Agent 側で検知する一次手段は CLI/GUI Orchestrator が prompt 末尾に注入する `## 実行モード制約` セクション、二次的に Python 側ランタイム ([hve/runner.py](hve/runner.py)) が Step 完了時に `output_paths` 全欠落を検出して当該 Step を fail 化する。
  - **判別方法**: Orchestrator 起動時に生成される `OrchestratorContext` を Python 内部で明示的引数として `StepRunner` / `check_plan_md_metadata` 等へ伝播させる方式。詳細は Skill `task-dag-planning` 参照。
- **plan.md 冒頭5行にメタデータ必須**（Skill task-dag-planning §2.1.2）。欠落は CI で自動拒否。
- **最低1つの検証を実施**: テスト/ビルド/静的解析のいずれかを行い、できない場合は理由と代替を明記する。
  - **タスク完了報告の検証マーカー必須記載書式**（GitHub 連携時は `auto-approve-and-merge.yml` の自動判定対象、CLI 連携時は人手レビュー可読性と将来の自動化準備）: 以下のいずれかの形式で記載すること:
    1. HTML コメントマーカー: `<!-- validation-confirmed -->`（推奨。最も確実）
    2. 見出し: `## 検証` / `## 検証結果` / `## Validation` 等（行頭 `#` + 語）
    3. 箇条書き / 強調: `- 検証: <内容>` / `**検証**: <内容>`（行頭 + 語 + コロン）
  - 検証実施が困難な場合も「検証: 該当なし（理由: ...、代替: ...）」と記載すること。
- **ルート README.md の扱い**: `/README.md` は users-guide への導線インデックスであり、変更してよい（CI の変更制限は [.github/workflows/protect-readonly-paths.yml](.github/workflows/protect-readonly-paths.yml) の `check-readme` ジョブで解除済み）。Workflow ID / Issue Template / `.github/workflows/` の増減を伴う変更では、同じ変更セットで README の該当一覧も更新する。ただし Self-Improve ループの改善適用 Prompt（[hve/prompts.py](hve/prompts.py)）は引き続き `/README.md` を変更しない。`README.md` のような裸パス表現は避け、ルート以外の README を指す必要がある場合は `src/infra/.../README.md` などの明示パスで記載する。
- **質問方針**：質問なしで進められる場合は質問しない。必要な質問は分類項目・重要度（最重要/高/中/低）付きで過不足なく行う。「最重要」「高」は回答を優先的に求め、「中」「低」は既定値で進行可能とする。タスク定義書（GitHub Issue body / CLI 起動時メタデータ）に `<!-- auto-context-review: true -->` が記載されている時は、コンテキストが十分な場合でも設計判断・技術選定・スコープの確認を目的として質問する。
- **推論許可**：「推論で進めてください」の意思表示を以降「**推論許可**」と呼ぶ。
- **書き込み失敗対策**：edit 後に read で空でないことを確認。空なら小チャンク（2,000〜5,000文字）に分割して再試行（最大3回）。
- **一時作業ファイルは `work/` 配下に限定（絶対）**：調査スクリプト・デバッグ出力・ログ・プローブ・実験結果などの一時作業ファイルを **リポジトリルート直下（`/`）に作成してはならない**。必ず `work/run/<run-id>/.../artifacts/` 配下に作成する（Skill `work-artifacts-layout`）。`_tmp_*.py` / `tmp*` / `debug_*` / `*.out.txt` / `MagicMock/` 等をルート直下へ置くことも禁止し、`.gitignore` 済みかどうかは免罪符にならない。ルート直下へ新規追加してよいのは許可リスト（`.github/workflows/protect-readonly-paths.yml` の `ROOT_FILE_ALLOWLIST` / `ROOT_DIR_ALLOWLIST`）に載るリポジトリ標準ファイルのみで、追加が必要な場合は同じ PR で許可リストも更新する。違反は `protect-readonly-paths.yml` の `check-root-temp-files` ジョブが PR で fail させる。
- **work/ および qa/ 書き込みルール（絶対）**：`work/` または `qa/` 配下へのファイル書き込みは Skill `work-artifacts-layout` §4.1 準拠。例外なし。
- **work/run 横断参照の禁止（絶対）**：標準ワークフロー Step は、他 Step の `work/run/<run-id>/...` 配下の作業成果物（`plan.md` / `contracts/` / `artifacts/` / `completion-report.md` 等）を入力として読まないこと。Step 間のデータ受け渡しは `## 入力` に列挙された `docs/` 成果物経由のみとする。SPLIT / Fleet サブタスクが依存完了報告を参照する場合は、コードが明示注入する `dependency_completion_reports` の絶対パスのみを用い、パスを自力推測しないこと。詳細は Skill `work-artifacts-layout` 参照。
- **恒久成果物からの work/ 出典引用の禁止（絶対）**：`docs/` `knowledge/` `qa/` `src/` 等の恒久成果物は使い捨ての `work/` 配下パスをリンク／コードスパンで出典引用してはならない。唯一の例外は `CHANGELOG.md` で、そこでもパス／リンクは禁止し要約文字列のみ許可する。詳細は Skill `work-artifacts-layout` 参照。
- **knowledge/ 書き込みルール（絶対）**：`knowledge/` 配下へのファイル書き込みも Skill `work-artifacts-layout` §4.1 準拠（削除→新規作成）。例外なし。
- **knowledge/ 同時更新防止（LOCK）**: `knowledge/` 本体ファイルへ LOCK 情報を埋め込んではならない。LOCK が必要な場合は `work/` 配下のロックファイル、または Issue ラベル等、`knowledge/` の「削除→新規作成」ルールと両立する方式を用いる。他の Agent により対象 D{NN} の LOCK が取得済みであることを検知した場合、後続 Agent は当該 `knowledge/` ファイルを **読み取り専用** とし、書き込みを中止して再実行に回す。
- **docs-original/ 読み取り専用（絶対）**: `docs-original/` 配下のファイルは全 Agent から **読み取り専用**。変更・削除・追記を禁止。
- **Markdown 横断検索の既定手段**: リポジトリ内 Markdown 群への横断検索・要件参照は `markdown-query` Skill（`python -m mdq search`）を最初に試す。0 ヒット時、対象が `.md` 以外を含む場合、または編集対象ファイルが既知の場合に限り `grep_search` / `read_file` へフォールバックする。**ただし、fail-closed shell allowlist が markdown-query CLI を許可しない Step では、CLI を実行せず read/search tool で宣言済み入力を参照する。** 詳細は Skill `markdown-query`（`.github/skills/markdown-query/SKILL.md`）参照。
- **ソースコード横断検索の既定手段**: リポジトリ内のソースコード（`.py` / `.cs` / `.js` / `.ts` / `.sh` / `.ps1` 等）に対する「どこで定義されているか」「何が呼んでいるか」「実装を探す」系の調査は `code-query` Skill（`python -m cq search`）を最初に試す。0 ヒット時、または編集対象ファイルが既知の場合に限り `grep_search` / `read_file` へフォールバックする。**ただし、fail-closed shell allowlist が code-query CLI を許可しない Step では、CLI を実行せず read/search tool で宣言済み入力を参照する。** 対象が `.md` の場合は `markdown-query` を使う（両者は索引対象が排他）。詳細は Skill `code-query`（`.github/skills/code-query/SKILL.md`）参照。
- **ripgrep (rg) 利用ガイドライン（絶対）**:
  - **glob パス区切り**: `-g` / `--glob` のパターンには **`/` 区切り**を使う。`\` 区切りや `'docs\catalog\{a.md,b.md}'` のような brace-glob のエスケープは禁止（ripgrep が `\{` をエスケープと解釈し `unopened alternate group; missing '{'` エラーになる）。
    - ✗ 悪い例: `rg -g 'docs\catalog\{a.md,b.md}' pattern`
    - ✓ 良い例: `rg -g 'docs/catalog/{a.md,b.md}' pattern`
  - **存在未確定パスの事前チェック**: 宣言済み入力でも、上流 Step が部分完了で未生成の可能性があるパスは `Test-Path`（PowerShell）/ `[ -f ... ]`（bash）で事前確認してから rg を起動し、`os error 2` / `os error 3` のノイズログを抑制する。

---

## §0.5 用語定義（タスク / サブタスク）

本ファイルでは **HVE Cloud Agent Orchestrator（GitHub Issue/PR ベース）** と **GitHub Copilot CLI（セッション/サブセッション ベース）** を共通の語彙で扱うため、以下の上位概念を用いる。GitHub 固有の仕様（`Fixes #N`、`auto-approve-and-merge.yml` 等）は §7.2 に集約し、本ファイルのその他の本文は両環境に適用される。

| 上位概念 | GitHub Issue 起点モード（Cloud） | CLI セッション起点モード（CLI） |
|---|---|---|
| **タスク** | Issue | `hve orchestrate` 1 回実行（CLI 起動セッション） |
| **サブタスク** | Sub-issue（Copilot アサイン） | workflow DAG / fan-out の子 Step |
| **タスク定義書** | Issue body | 起動時引数 / 起動時メタデータ |
| **サブタスク定義書ファイル** | `subissues.md` | 原則なし（workflow 定義 / fan-out メタデータで表現） |
| **タスク完了報告** | PR body | `work/run/<run-id>/Issue-<識別子>/completion-report.md` |
| **タスク完了通知** | PR Merge / Issue Close | journal レコード（`hve/run_journal.py`）/ セッション終了 |
| **検証マーカー書式** | `<!-- validation-confirmed -->` 等（`auto-approve-and-merge.yml` 自動判定対象） | 同書式（将来の自動化準備および人手レビュー時の可読性のため） |

**補足**:

- ファイル名 `subissues.md` は Cloud Agent Orchestrator の Sub-Issue 作成経路で使用する。CLI / GUI 標準経路では workflow DAG / fan-out でサブタスクを表現し、`subissues.md` runtime fork は legacy / 明示 opt-in のみ。
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
  - 敵対的レビュー（marker / label / 明示的な敵対的レビュー依頼 / HVE Phase 3 のみ）: Skill: adversarial-review
        ↓
[5. 完了報告とタスク終了]
  - タスク完了報告の出力先:
    - GitHub Issue 起点: PR body に記載 → §7.1 + §7.2 参照
    - CLI セッション起点: `work/run/<run-id>/Issue-<識別子>/completion-report.md` に記載 → §7.1 + §7.3 参照
  - 混合運用（CLI で作業した後 GitHub へ push）: §7.2 と §7.3 を併用
```

初見のリポジトリの場合は先に **Skill: repo-onboarding-fast** を参照すること。

---

## §2 Skills ルーティング

Skill の参照先選定は **ルーティング表**（`.github/skills/_routing/README.md`）を参照すること。
本体には強制ルール（§0, §3, §5-§10）を残し、ルーティング表は `_routing/README.md` で管理する。

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

## §5 Custom Agent (旧用語) と Prompt の関係

Custom Agent という旧名称は現在「識別子」のみとして残置されている（`step.custom_agent`, `<!-- custom_agent: ... -->`, Issue body `## Custom Agent\n\`<Name>\``）。
Agent の動作仕様本文は `.github/prompts/<Name>.prompt.md` に、入出力契約は `.github/io-contracts/<Name>.yaml` にある。

**優先順位（高 → 低）**:
1. **本ファイル（copilot-instructions.md）**（最優先・常に適用）
2. **Agent のジョブ定義**（リポジトリ固有の方針、`.github/prompts/<Name>.prompt.md`）
3. **Skills**（技術リファレンス）

> 本ファイルの記述と Custom Agent の記述が矛盾する場合は本ファイルが優先される。
> SKILL.md と Custom Agent の記述が矛盾する場合は Custom Agent が優先される。
> `agent-common-preamble` Skill の共通ルールは、Agent 側で明示的にオーバーライドしない限り適用される（デフォルト継承モデル）。

**Skills 参照ルール（Custom Agent 向け）**:
- `.github/skills/` 配下の SKILL.md は、技術リファレンス（手順・コマンド・トラブルシューティング）を提供する。
- Custom Agent は、作業開始時に `agent-common-preamble` Skill を参照し、共通ルールを確認すること。
- Custom Agent 固有の追加 Skills は `## Agent 固有の Skills 依存` セクションに明示する。
- SKILL.md の情報を採用しない場合は、Custom Agent 側でその理由を明記すること（Non-goals 等で）。

**docs-original/ に関するルール（全 Agent 必須）**:
- 読み取り専用ルール: §0 参照（変更・削除・追記禁止）
- `docs-original/` のファイルを knowledge/ に取り込む作業は `KnowledgeManager` Agent が担当
- 他の Agent は、ユースケースに応じて以下のいずれかの参照方式を選択できる:
  - **直接参照**: `docs-original/` を直接読み取る（横断分析・質問票作成・早期フィードバック等で有効）
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

- **出力先**: `work/run/<run-id>/Issue-<識別子>/completion-report.md`。`<run-id>` は `hve.split_fork.resolve_run_id()` が採番し、GUI/CLI 起動時に env `HVE_WORK_ROOT` / `HVE_RUN_ID` として伝播される。ファイル名 `Issue-` prefix は `work-artifacts-layout` Skill の既存規約により残置。`<識別子>` は CLI セッション識別子または作業ディレクトリ名。
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

<!-- TODO(neutralization): §0.5 で導入した「タスク / サブタスク」抽象語彙は、本ファイルおよび `task-questionnaire` / `harness-verification-loop` Skill に適用済み。残課題として `.github/prompts/*.prompt.md` 群および `.github/labels.json` の "Issue" / "PR" 固有表現の中立化（CLI セッション起点モードでの読み替えガイダンス追加）を別タスクで実施すること。 -->


---

## §11 Copilot セッション運用ルール

- **Copilot Coding Agent のセッションを GitHub UI から手動 Stop しない**。手動 Stop を行うと PR タイムラインに `The session was cancelled by the user.` というノイズイベント（タイムライン上に表示）が残る。
- セッションは PR の merge / close によって Copilot プラットフォームが自動終了するため、明示的に停止する必要はない。
- 詳細は [`knowledge/copilot-session-cancelled-event.md`](/knowledge/copilot-session-cancelled-event.md) を参照。

---

## §12 HVE アプリケーション保守ルーティング

- HVE 対象変更・不具合調査では `.github/skills/hve-requirement-traceability/SKILL.md` を使用する。
- HVE コアパスでは `.github/instructions/hve-maintenance.instructions.md` も適用する。
- `hve-dev/requirement-definition.md` 全文を既定の入力にしない。
