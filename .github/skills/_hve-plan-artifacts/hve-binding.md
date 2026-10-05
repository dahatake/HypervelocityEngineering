# HVE 計画成果物バインディング（plan.md / subissues.md）

> 計画の規約（受入条件・完了条件・分割単位・見積）の正本は Skill `task-dag-planning`（[`../task-dag-planning/references/planning.md`](../task-dag-planning/references/planning.md)）。本ファイルは HVE 固有の成果物フォーマットと実行面ごとの扱いだけを定義する。
>
> 本ディレクトリは `SKILL.md` を持たない参照ディレクトリであり、Skill ではない。他リポジトリへは配布しない。

---

## 1. plan.md の必須セクション（CI 検証対象）

`plan.md` の必須セクションは `## 完了条件` だけである（FR-DOD-02）。Cloud では `.github/workflows/plan-validation-and-labeling.yml` が PR で変更された `work/**/plan.md` を `validate-plan` に渡し、`## 完了条件` の存在と非空を検査する。冒頭のメタデータ（旧 `task_scope` など）や分割の判定記録は求めない（FR-PLAN-01）。

### 1.0 plan.md を作る条件

影響範囲や検証方法が作業開始時点で明らかでない場合、または複数の成果物を順に作る場合に、実装開始前に plan.md を作る。テンプレートは [`plan-template.md`](plan-template.md)。

**最初に実行面を区別する**: standalone / Cloud / CLI-GUI / Prompt Edition controller のいずれかを、入力・起動経路・`OrchestratorContext`・明示承認の有無から決める（§4）。実行面によって、分割を選んだ場合の手段が変わる。

### 1.1 分割を選んだ場合（Cloud）

分割するかどうかはモデルが判断する（FR-PLAN-01）。Cloud で 1 セッションに収まらないと判断した場合は、同じディレクトリに `subissues.md` を作り、独立して検証できる単位で Sub-Issue に分ける。作成するファイルは Skill `work-artifacts-layout` のパス規則に従う。

- `plan.md`: DAG + 完了条件 + 検証計画
- `subissues.md`: Sub Issue の本文（§3）
- `work-status.md`: 各ステップの進捗（✅/⏭️/❌）
- `README.md`: 作業ディレクトリの入口

同名の既存ファイルがある場合は、Skill `work-artifacts-layout` の規則に従い削除してから新規作成する（追記・上書きによる混在を避けるため）。

**Sub Issue の扱い**: Copilot cloud agent は PR 作成セッション内で GitHub Issue を直接作成しない。PR に `subissues.md` が含まれると `plan-validation-and-labeling.yml` が `create-subissues` 系のラベルを付け、`create-subissues-from-pr.yml` が Sub-Issue を作成する。

---

## 2. plan.md / subissues.md の最小フォーマット

| 成果物 | 最小フォーマット | テンプレート |
|---|---|---|
| `plan.md` | 概要（目的 / 非対象 / 根拠）・`## 完了条件`（チェックボックス、**FR-DOD-02**）・DAG（ノード一覧と依存）・検証計画 | [`plan-template.md`](plan-template.md) |
| `subissues.md` | Title・背景（1〜3 行）・`## 完了条件`（チェックボックス、**FR-DOD-01**）・根拠（パス / 箇所）・変更候補パス・検証・依存 | [`subissues-template.md`](subissues-template.md) |

- **FR-DOD-01**: 各 `<!-- subissue -->` ブロックに `## 完了条件` を置き、**非空**の記述を 1 行以上書く。空セクション、および `REPLACE_ME` を含む記述だけの状態は拒否される。
- **FR-DOD-02**: `plan.md` に `## 完了条件` を置き、**非空**の記述を 1 行以上書く。
- 分割を選んだ場合だけ [`subissues-template.md`](subissues-template.md) を `read` してコピー元にする。分割しないタスクでは不要なテンプレート読込を増やさない。

---

## 3. subissues.md 作成規約（分割を選んだ場合）

**フォーマット違反は `validate-subissues`（`.github/scripts/{bash,powershell}/validate-subissues.*`）が拒否し、Cloud の Sub-Issue 作成が止まる**。

### 3.1 ファイルレベルメタデータ（最初の `<!-- subissue -->` より前に記載）

```
<!-- parent_issue: NNN -->
```

- **運用上必須**。作業対象 Issue の番号（数値のみ、`#` なし）を記載する。
- 取得元: PR の起点となった Issue 番号（`Fixes #N` で指定した Issue と同一）。
- **推論・捏造禁止**: 不明な場合は `TBD` と記載し作業を停止する。
- ワークフロー互換: `<!-- parent-issue: #NNN -->`（ハイフン形式・`#` 付き）も受け付けるが、`<!-- parent_issue: NNN -->` を推奨。
- `validate-subissues.yml` が自動検証するのは title のみであり、`parent_issue` の有無や値整合はこのワークフローでは未検証。
- `create-subissues-from-pr.yml` は **subissues.md のメタデータを最優先**で使用する。PR body の `Fixes #N` はフォールバック。両者は同じ Issue 番号を指すこと。

### 3.2 ブロックレベルメタデータ（必須ルール）

1. 各サブタスクは `<!-- subissue -->` マーカー行で開始する（**必須区切り**。`---` は可読性のためのオプション）。
2. **マーカー直下に `<!-- title: <タイトル> -->` を必ず置く**（空値・`REPLACE_ME` 等のプレースホルダ禁止、大文字小文字不問）。
3. **各ブロックに `## 完了条件` セクションを必ず置く**（FR-DOD-01）。非空の記述を 1 行以上書く。
4. メタデータ（必要時のみ）: `<!-- labels: a,b -->` / `<!-- custom_agent: AgentName -->` / `<!-- depends_on: 1,2 -->`。
   - `custom_agent` を省略すると Copilot がアサインされない。親 Issue の `## Custom Agent` セクションの Agent 名を記載する。親 Issue 番号や Agent 名を推測しない。
   - `depends_on` の番号は **subissues.md 内の `<!-- subissue -->` マーカーの出現順（1 始まり）**。`## [Sub-N]` の N ではない。自身以上のブロック番号への前方参照は禁止。
   - **省略 = 依存なし = ルートノード = Copilot 即時アサイン**。plan.md の DAG に依存がある場合は必ず記載する。
5. Markdown 見出し（`## Sub-N: ...`）と `<!-- title: -->` の内容は一致させる。
6. ファイル保存後、`validate-subissues` を実行し PASS を確認してから完了報告する。Cloud の Sub-Issue 作成が同じ検査で止まるためである。

```bash
bash .github/scripts/bash/validate-subissues.sh --path work/run/<run-id>/<Agent>/<Issue>/subissues.md
```

```powershell
pwsh .github/scripts/powershell/validate-subissues.ps1 -Path work/run/<run-id>/<Agent>/<Issue>/subissues.md
```

### 3.3 最小サンプル

```markdown
<!-- subissue -->
<!-- title: Sub-1 のタイトル -->
<!-- custom_agent: Arch-Microservice-ServiceDetail -->
<!-- depends_on: -->
## Sub-1: Sub-1 のタイトル

- 対象: ...

## 完了条件

- [ ] ...
```

### 3.4 よくある誤り（必ず避ける）

- Markdown 見出しのみ書いて `<!-- title: -->` を省略する → `validate-subissues` が失敗する。
- `## 完了条件` を省略する、または見出しだけ置いて中身を書かない → `validate-subissues` が失敗する。
- `<!-- title: REPLACE_ME -->` や空値のまま放置する → プレースホルダ検出で失敗する。
- `<!-- subissue -->` を箇条書きや見出し配下に埋めて行頭に置かない → ブロック分割が崩れる。

### 3.5 PR description の必須記載

- **元 Issue 番号のリンク記載は、分割の有無を問わず全 PR で必須**。`Fixes #N` / `Closes #N` / `Resolves #N`（推奨）、または `<!-- parent-issue: #N -->`（レガシー互換）。
- `subissues.md` を含む PR では追加で、Sub Issue 一覧と「次にやる最初の Sub」を記載する。PR の Close / Merge は人間が判断する。

---

## 4. 実行面の選択表

**計画より先に実行面を確定する。** 下表は既存規則を選ぶための早見表であり、承認 SHA-256・`output_paths` gate の意味は変更しない。

| 実行面 | 選ぶ条件 | 分割を選んだ場合の扱い |
|--------|----------|----------------------------|
| standalone | `OrchestratorContext` が無い単独実行 | 分割した単位を順に実装する。`subissues.md` を作っても自動では実行されない。 |
| Cloud | GitHub Issue Template + GitHub Actions + Copilot Cloud Agent | `subissues.md` を作ると、Sub-issue 作成 / assign は既存 GitHub Actions が担当する。親 Issue を推測しない。 |
| CLI / GUI | `hve orchestrate` / GUI の通常実行 | workflow DAG / fan-out で分割・並列化する。`subissues.md` を実行時に fork する経路は無い。 |
| Prompt Edition controller 例外 | 同一セッションで提示済み plan をユーザーが明示承認済み | controller は SHA-256 付きで `hve prompt run` へ委譲するだけ。HVE の一致確認後、既存 orchestrate が `output_paths` gate まで実行する。 |

---

## 5. Cloud Agent Orchestrator の分割経路

HVE Cloud Agent Orchestrator（Issue Template + GitHub Actions + Copilot Cloud Agent）で Agent が分割を選んだ場合、Agent は `plan.md + subissues.md` を作って PR を終え、実装の継続は GitHub Actions が担う（`create-subissues-from-pr.yml` が Sub-issue を作成し、既存 `assign-copilot.sh` 経由で Copilot をアサインする）。

- **CLI / GUI**: GitHub Sub-Issue 作成は行わない。workflow DAG / fan-out で分割・並列化する。`subissues.md` を実行時に fork する経路は無い。

**判別方法**: CLI / GUI の実行コンテキスト伝播は `OrchestratorContext`（[`hve/orchestrator_context.py`](../../../hve/orchestrator_context.py)）を Python 内部で明示的引数として伝播させる方式。`HVE_ORCHESTRATOR_ACTIVE` 環境変数は撤廃済み（参照しない）。

---

## 6. Prompt Edition controller 例外（SHA-256 委譲）

「承認済みの実行計画を既存 orchestrate へ橋渡しする」ための狭い例外だけを認める。

### 6.1 許可されること

1. Prompt Edition controller が、提示済み実行計画への**明示承認**を取得済みである。
2. controller が提示された plan SHA-256 を `--expected-sha256` へ渡して既存 `hve prompt run` を起動する。

この 2 条件を満たす場合、controller 自身が standalone で、計画の規模が大きい、または分割を含む場合でも、**`hve prompt run` の起動**を止めない（FR-PLAN-01）。HVE が FR-PROMPT-04 の SHA-256 一致を確認した場合だけ、子 `orchestrate` へ進む。

### 6.2 禁止境界

- controller 自身が対象成果物を直接実装・編集すること。
- 既存 orchestrate を迂回する別実行経路を追加すること。
- 新フラグ・新抽象化・Python 実装変更を前提にこの例外を成立させること。
- 承認前に `hve prompt run` を起動すること、または HVE が stale を検出した後も `orchestrate` へ進むこと。stale 時は controller が再plan・再提示・再承認へ戻る。
- この例外を根拠に、通常 standalone / Cloud / CLI-GUI の既存規則、plan.md の `## 完了条件`、subissues.md 規則を緩和すること。

### 6.3 委譲先の扱い

例外が許可するのは controller の委譲開始までであり、委譲先 Step は既存 Orchestrator 規則に従う。委譲先 Step は plan/subissues だけで止まらず、宣言された `output_paths` を実行完了時点で存在させなければならない。

---

## 7. `task-dag-planning` との境界

| 区分 | 本ファイル（HVE バインディング） | Skill `task-dag-planning` |
|---|---|---|
| 扱うもの | HVE 固有の成果物フォーマット（plan.md / subissues.md / 実行面 / CI 連携） | 受入条件・完了条件・分割単位・見積の規約 |
| 正本 | 本ファイル | [`../task-dag-planning/references/planning.md`](../task-dag-planning/references/planning.md) |

### 7.1 関連 Skill

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-questionnaire` | 前提 | コンテキスト収集が完了してから計画フェーズへ遷移する |
| `task-dag-planning` | 正本 | 受入条件・完了条件・分割単位・見積の規約 |
| `work-artifacts-layout` | 出力先 | `plan.md` / `subissues.md` / `work-status.md` / `README.md` の配置パス規則 |
| `harness-verification-loop` | 後続 | 実装後の検証パイプライン |
| `adversarial-review` | 後続 | レビュー（marker / label / ユーザー依頼 / HVE Phase 3 の明示時のみ） |

実装の実行・テストの実行・コンテキスト収集・Sub Issue の GitHub 直接作成は、いずれも本ファイルの責務ではなく上表の Skill または GitHub Actions が担う。
