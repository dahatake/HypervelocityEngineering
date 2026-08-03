---
name: agent-common-preamble
description: >
  全 Custom Agent が作業開始時に参照する共通プリアンブル。 USE FOR: agent start, common rules, preamble. DO NOT USE FOR: implementation. WHEN: Custom Agent が作業を開始したとき、共通ルールを確認したいとき。
metadata:
  origin: user
  version: 1.0.0
---

# agent-common-preamble

## 共通ルール

`.github/copilot-instructions.md` §0 を最優先で遵守する。本 Skill は全 Agent 共通の参照先を集約する。

特に Windows 環境で作業する Agent は、§0 の以下 2 項目を必読:

- **ripgrep (rg) 利用ガイドライン（絶対）**: `-g` / `--glob` には `/` 区切りを使い、`\` 区切りや brace-glob のエスケープは禁止（`unopened alternate group; missing '{'` エラー回避）。
- **存在未確定パスの事前チェック**: 上流 Step 部分完了で未生成の可能性があるパスは `Test-Path` / `[ -f ... ]` で事前確認してから rg を起動（`os error 2` / `os error 3` ノイズ抑制）。

## ファイル編集ツールの一意性要件（必須）

`edit` 系ツールは置換対象文字列がファイル内で **一意** であることを要求する。一致が複数あると `Multiple matches found` で失敗し、ターンを 1 往復無駄にする。

- 置換対象には **前後 3〜5 行の変更しない文脈** を必ず含めて一意化する。セル 1 個・単語 1 個だけを対象にしない。
- Markdown の表・箇条書き・繰り返しの定型行は同一文字列が高頻度で再出現する。表を編集する場合は、行頭の見出しセルや直前の見出し行まで含める。
- 同一ファイルへ複数の変更を行う場合は、1 回の編集にまとめるか、変更ごとに異なる文脈を含めて個別に一意化する。
- 失敗した場合は同じ文字列で再試行せず、`view` で範囲を広げて文脈を再取得してから一意な対象を作り直す。

## Azure 公式情報参照（Microsoft Learn MCP 必須）

- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / リージョン対応 / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

### Microsoft Learn Web redirect の単回再試行

- Microsoft Learn MCP を優先する。Web取得へフォールバックし、`WebFetchRedirectError` が最終 `Location` を返した場合だけ、redirect先を再取得してよい。
- `Location` が `/en-us/...` のような相対URLなら、元URLのorigin `https://learn.microsoft.com` と結合して絶対URLにする。再取得前に **HTTPSかつ同一host `learn.microsoft.com`** であることを確認し、別host・HTTP・認証情報を含むURLは拒否する。
- 再取得は、エラーが示した最終絶対URLに対して **一度だけ** 行う。元URLを再試行せず、redirectを連鎖追跡せず、同じ取得を反復しない。
- 単回再試行もredirect / 404 / permission error / その他の失敗になった場合は停止し、別のMicrosoft公式ソースまたはMicrosoft Learn MCPへ切り替える。取得できなければ `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。
- 302例: 元URL `https://learn.microsoft.com/azure/cosmos-db/partitioning`、最終 `Location` `/en-us/azure/cosmos-db/partitioning` の場合、単回再試行先は `https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning`。この再試行先がさらにredirectなら追跡せず停止する。

## Azure External Skill の JIT ルーティング（必須）

Azure または Microsoft Foundry を扱う active HVE Step は、`hve/skill_manifest.json` の `required_skills` / `optional_skills` を正本として扱う。routing 表は候補の説明であり、全 Azure Skill を無条件に公開・読込してはならない。

- **required external Skill**: active Step に明示された Skill の正確な directory だけを session に渡す。未導入・名前不一致・SDK 非対応の場合は、session 作成前に fail-closed とする。
- **optional external Skill**: active workflow / Step に対応する候補のうち、インストール済みの正確な directory だけを JIT で公開する。`~/.agents/skills` 全体またはカテゴリ directory を渡して探索させてはならない。
- optional candidate は「全候補を必ず使う」指示ではない。選定済み Azure サービスと実行操作に一致する candidate だけを読込み・利用し、一致しない candidate は読まない。
- repository Skill と同名の external Skill がある場合は repository Skill を優先する。external Skill が未導入でも、ローカル Skill が存在するものとして扱わない。

### 未導入 external Skill の操作別方針

- 設計・read-only 調査・review は、Microsoft Learn MCP を使い、未導入 Skill 名と `要確認（Microsoft Learn MCP 未取得）` の有無を根拠に記録する。
- 選定済みサービスへの実装または Azure write で、対応する official external Skill candidate が未導入なら、Azure write を実行せず block する。generic な `azure-prepare` / `azure-deploy`、または active Step の read-only readiness review 候補として明示されていない `azure-validate` を、Azure resource 操作の代替として使ってはならない。
- `az ... -h` は公式 CLI help の補助確認に限る。未導入 Skill の Azure write 許可や resource 操作の根拠にはしない。

### Microsoft Foundry 固定 Step

- AAGD `2.3` / `3` は external `microsoft-foundry` meta skill を required とし、未導入時は session 作成前に fail-closed とする。
- Foundry meta skill の sub-skill routing を HVE 側で列挙・複製しない。Foundry-required Step は repository-pinned `azure` と `microsoft-learn` MCP の接続確認後に main turn を開始する。

## 出力言語ルール（思考プロセスを含む）

- 最終出力だけでなく **思考プロセス（reasoning / chain-of-thought / 内部独白）も日本語で行う** こと。
- ツール委譲の意図表明（例: "I need to delegate this task to ..."）、計画の自問自答、推論の途中経過もすべて日本語で記述する。
- 英語の固有名詞・コマンド名・ファイルパス・コード識別子・引用文はそのまま英語で構わない。
- 本ルールは hve オーケストレーターのターミナル出力（`○` で始まる Thinking 行）にも適用される。

## 全 Agent 共通 Skills 参照リスト

- `task-questionnaire`：コンテキスト収集・質問票作成の詳細手順
- `task-dag-planning`：DAG計画・見積・分割判定の詳細手順
- `work-artifacts-layout`：work/ 構造設計・README入口
- `large-output-chunking`：巨大出力の分割手順
- `adversarial-review`：敵対的レビューの詳細手順
- `harness-verification-loop`：コード変更の5段階検証パイプライン
- `harness-safety-guard`：破壊的操作の事前検知
- `harness-error-recovery`：エラー発生時の3要素出力
- `docs-output-format`：`docs/` 成果物フォーマットの共通原則
- `knowledge-management`：knowledge/ の分類・状態判定・更新手順
- `knowledge-lookup`：タスク実行中に業務要件が不明瞭な場合の knowledge/ 条件付き参照ルール

## 分割ルール

→ Skill `task-dag-planning` を参照。

## plan.md コミット前バリデーション（全 Agent 必須）

plan.md を作成・更新した場合、コミット前に以下を `execute` で実行すること:

```bash
bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md
```

`✅ PASS` を確認してからコミットする。`❌ FAIL` の場合はエラーメッセージを確認し、plan.md のメタデータ（冒頭4行の HTML コメント）または `## 分割判定` セクションを修正する。

## subissues.md コミット前バリデーション（全 Agent 必須）

subissues.md は Orchestrator がパース ([hve/split_fork.py](../../../hve/split_fork.py)) してサブタスクを fork する。**フォーマット違反は即パース失敗で Step を停止させる** ため、書き手側で以下の手順を厳守すること。

### 作成前（必須・順序固定）

1. **テンプレートを必ず read する**（再発明禁止）:
   `.github/skills/task-dag-planning/references/subissues-template.md`
2. 各サブブロックは template の構造をそのまま踏襲する:
   - `<!-- subissue -->`（マーカー、必須・行頭）
   - `<!-- title: <タイトル> -->`（必須・空値/`REPLACE_ME` 禁止）
   - `<!-- custom_agent: <Agent 名> -->`（必須）
   - `<!-- depends_on: <1-indexed カンマ区切り、なければ空> -->`（任意・前方参照禁止）
   - `## Sub-N: <タイトル>` の Markdown 見出し（`<!-- title: -->` と内容一致）

> ⚠️ Markdown 見出し（`## Sub-N: ...`）だけで `<!-- title: -->` を省略するとパーサが即失敗する。**両方が必須**。

### 作成後（必須）

完了報告前に必ず以下を `execute` で実行すること:

```bash
bash .github/scripts/bash/validate-subissues.sh --path {WORK}subissues.md
```

PowerShell 環境（Windows）では:

```powershell
pwsh -NoProfile -File .github/scripts/powershell/validate-subissues.ps1 -Path {WORK}subissues.md
```

`✅ PASS` を確認してから完了報告する。`❌ FAIL` の場合は、欠落している `<!-- title: -->` 等を補い、Skill `task-dag-planning` §subissues.md 作成規約に従って修正・再検証する。**PASS まで完了報告禁止**。

## 書き込み失敗/巨大出力への対策

→ Skill `large-output-chunking` を参照。

## 最終品質レビュー

- 通常時は、Prompt 固有の観点を1回のインライン・セルフチェックとしてまとめて確認する。
- 通常時は Review Sub-agent を起動しない。
- HVE CLI / GUI では `auto_contents_review=true` の場合だけ Phase 3 が実施する。
- 敵対的レビューの発動条件と実施手順は Skill `adversarial-review` に従う。Prompt に観点が記載されているだけでは発動しない。

## knowledge/ STALENESS CHECK（セッション開始時）

1. `knowledge/` 配下の対象ファイル冒頭にある STALENESS メタブロック（sources / blob_sha / generated_at / generator）を確認する
2. 記録された source path の現在 blob SHA とメタブロックの SHA を比較する
3. 不一致がある場合は「stale」と判定し、knowledge ファイルの再生成を優先する
4. 再生成時は work-artifacts-layout §4.1（削除→新規作成）に従い、メタブロックも最新 SHA で再作成する

## knowledge/ 条件付き参照（タスク実行中）

タスク実行中に業務要件・仕様・用語が不明瞭な場合は、Skill `knowledge-lookup` を参照すること。
Agent 固有の `### knowledge/ 参照` セクションで指定された D 番号はそちらを優先する。

## 入力ファイル確認

→ Skill `input-file-validation` を参照。Agent 固有の必読ファイルリストは Agent 側で定義する。

## APP-ID スコープ解決

→ Skill `app-scope-resolution` を参照。

**重要（AAD-WEB / ASDW-WEB / ADFD / ADFDV 向け）**:
APP-ID 未指定時に「全 APP 対象」とはしない。
`docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` を参照し、
workflow に対応する推薦アーキテクチャの APP-ID のみを対象とする。
詳細は Skill `app-scope-resolution` を参照。

## 参照資料

- `.github/skills/agent-common-preamble/references/agent-playbook.md`

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-questionnaire` | 参照 | コンテキスト収集・質問票作成の詳細手順 |
| `task-dag-planning` | 参照 | DAG計画・見積・分割判定の詳細手順 |
| `work-artifacts-layout` | 参照 | work/ 構造設計・README入口 |
| `large-output-chunking` | 参照 | 巨大出力の分割手順 |
| `adversarial-review` | 参照 | 敵対的レビューの詳細手順 |
| `harness-verification-loop` | 参照 | コード変更の5段階検証パイプライン |
| `harness-safety-guard` | 参照 | 破壊的操作の事前検知 |
| `harness-error-recovery` | 参照 | エラー発生時の3要素出力 |
| `docs-output-format` | 参照 | `docs/` 成果物フォーマットの共通原則 |
| `knowledge-management` | 参照 | knowledge/ 分類・状態判定・ステータス管理 |
| `knowledge-lookup` | 参照 | タスク実行中の knowledge/ 条件付き参照ルール |
| `input-file-validation` | 参照 | 入力ファイル確認・欠損時処理 |
| `app-scope-resolution` | 参照 | APP-ID スコープ解決 |
