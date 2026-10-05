# Agent Playbook（常駐情報）

## 目的
- 指示ファイル（copilot-instructions / AGENTS / instructions）を短く保つための参照資料。
- 本ファイルは通常の Markdown 参照資料であり、`.instructions.md` のような自動適用対象ではない。旧 frontmatter の `applyTo` はポリシー機能として扱わない。

## 定義
- 「10分」：エージェントの作業時間見積り（壁時計ベースのラフな X–Y 分レンジ）。
- 「Shard」：パススコープの指示（`.github/instructions/*.instructions.md` の applyTo と、ネスト AGENTS.md）。

## リポジトリ構成の扱い
- この playbook は固定のディレクトリ構成を断定しない。
- リポジトリ固有の構成は、対象 root の現物（workspace tree / README / 対象ファイル）を確認する。

## 日本向け運用（圧縮版）
- UI文言/ドキュメントは日本語優先。
- 個人情報・ログ・規制領域は日本の法規制/コンプラ影響があり得るため、前提と確認事項を明示（断定しない）。

## Windows 固有手順（Windows のみ）

Windows 環境で作業する Agent は、以下 2 項目を確認する:

- **ripgrep (rg) 利用ガイドライン**: `-g` / `--glob` には `/` 区切りを使い、`\` 区切りや brace-glob のエスケープは使わない。`\` や brace のエスケープを含む glob は `unopened alternate group; missing '{'` エラーで検索全体が失敗するため。
- **存在未確定パスの事前チェック**: 上流 Step 部分完了で未生成の可能性があるパスは `Test-Path` / `[ -f ... ]` で事前確認してから rg を起動（`os error 2` / `os error 3` ノイズ抑制）。

## ファイル編集ツールの一意性要件（必須）

`edit` 系ツールは置換対象文字列がファイル内で **一意** であることを要求する。一致が複数あると `Multiple matches found` で失敗し、ターンを 1 往復無駄にする。

- 置換対象には **前後 3〜5 行の変更しない文脈** を必ず含めて一意化する。セル 1 個・単語 1 個だけを対象にしない。
- Markdown の表・箇条書き・繰り返しの定型行は同一文字列が高頻度で再出現する。表を編集する場合は、行頭の見出しセルや直前の見出し行まで含める。
- 同一ファイルへ複数の変更を行う場合は、1 回の編集にまとめるか、変更ごとに異なる文脈を含めて個別に一意化する。
- 失敗した場合は同じ文字列で再試行せず、`view` で範囲を広げて文脈を再取得してから一意な対象を作り直す。

## Azure 公式情報参照（Microsoft Learn MCP 必須）

適用条件: Azure サービス選定 / Azure CLI / SDK / REST API / SKU / リージョン対応 / 状態プロパティ / サンプルコードを扱う場合のみ。

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

適用条件: Azure または Microsoft Foundry を扱う active HVE Step のみ。

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

## 生成アプリケーション要求トレーサビリティ

適用条件: AAS / ADA / AAD-WEB / ASDW-WEB / ADFD / ADFDV / AAG / AAGD / AAR の 9 Workflow のみ。

AAS / ADA / AAD-WEB / ASDW-WEB / ADFD / ADFDV / AAG / AAGD / AAR の 9 Workflow は、生成アプリケーション（APP）のスコープ確定と要求定義書参照を独自実装せず、Skill `application-requirement-traceability` へルーティングする。

- 対象 APP-ID の解決は `app-scope-resolution` を、要求定義書内の該当箇所検索は `markdown-query` を再利用する。同じパス解決・ID 検証を Workflow ごとに再実装してはならない。
- canonical path（`docs/architectural-requirements-app-NNN.md`）と対象 APP-ID・Requirement ID だけを Prompt へ注入し、**要求定義書全文を既定の入力にしない**。詳細本文が必要な箇所だけを `markdown-query` で選択取得する。
- 対象文書の欠落・構造不正・対象外 APP-ID・未解決 `TBD`（`Blocker=yes`）が 1 件でもあれば、警告降格やデフォルト値の代入を行わず fail-closed で当該 APP を停止する。
- 完了報告には `application-requirement-traceability` Skill が定義する trace block（`<!-- app-requirements:start/end -->` と 4 キー）を 1 つだけ記録する。
- 詳細手順は Skill `application-requirement-traceability` を参照。

## 分割（Split Mode）用 Prompt テンプレ
## Parent Issue
- <link or placeholder>

## Goal
- ...

## Plan
- [ ] ... (X–Y min)

## Dependencies
- Inputs:
- Outputs（paths）:

## Parallelism
- ...

## Risks & Checks
- ...

## Questions
- ...（最大3、無ければNone）

## plan.md コミット前バリデーション

適用条件: plan.md を作成・更新した場合のみ。

plan.md を作成・更新した場合、コミット前に以下を `execute` で実行すること:

```bash
bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md
```

`✅ PASS` を確認してからコミットする。`❌ FAIL` の場合はエラーメッセージを確認し、`## 完了条件` セクション（非空の記述を 1 行以上）を修正する。

## subissues.md コミット前バリデーション

適用条件: subissues.md を作成・更新した場合のみ。

subissues.md は Cloud の `create-subissues-from-pr.yml` が Sub-Issue の作成に使う。フォーマット違反があると `validate-subissues` が拒否して Sub-Issue を作れないため、書き手側で以下の手順に従う。

### 作成前（必須・順序固定）

1. **テンプレートを必ず read する**（再発明禁止）:
   `.github/skills/_hve-plan-artifacts/subissues-template.md`
2. 各サブブロックは template の構造をそのまま踏襲する:
   - `<!-- subissue -->`（マーカー、必須・行頭）
   - `<!-- title: <タイトル> -->`（必須・空値/`REPLACE_ME` 禁止）
   - `<!-- custom_agent: <Agent 名> -->`（必須）
   - `<!-- depends_on: <1-indexed カンマ区切り、なければ空> -->`（任意・前方参照禁止）
   - `## Sub-N: <タイトル>` の Markdown 見出し（`<!-- title: -->` と内容一致）
   - `## 完了条件`（必須）と、その配下の非空の記述 1 行以上。空白のみ・水平線 `---` のみ・`REPLACE_ME` を含む記述だけの状態は欠落として拒否される

Markdown 見出し（`## Sub-N: ...`）だけで `<!-- title: -->` を省略すると `validate-subissues` が失敗する。両方が必要である。`## 完了条件` を省略する、または見出しだけ置いて中身を書かない場合も同じく失敗する。

### 作成後（必須）

完了報告前に必ず以下を `execute` で実行すること:

```bash
bash .github/scripts/bash/validate-subissues.sh --path {WORK}subissues.md
```

PowerShell 環境（Windows）では:

```powershell
pwsh -NoProfile -File .github/scripts/powershell/validate-subissues.ps1 -Path {WORK}subissues.md
```

`✅ PASS` を確認してから完了報告する。`❌ FAIL` の場合は、欠落している `<!-- title: -->` や `## 完了条件` 等を補い、`.github/skills/_hve-plan-artifacts/hve-binding.md` §3 subissues.md 作成規約に従って修正・再検証する。**PASS まで完了報告禁止**。
