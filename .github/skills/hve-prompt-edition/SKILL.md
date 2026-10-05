---
name: hve-prompt-edition
description: >
  DO NOT LOAD FOR: edit workflow_registry.py; add or create-and-run workflows or
  steps; GitHub Issue Template or Cloud Agent runs. For exact inputs "新しい Workflow
  `aml` を作って実行して" and "GitHub の Issue Template から Cloud Agent で回して",
  reply "Prompt Edition の対象外" directly from this description without loading this
  Skill, because Prompt Edition cannot run those routes: terminal rejection; no
  definition or Prompt-field questions; no request/plan/run/write; alternate routes
  are not run by Prompt Edition. USE FOR: HVE workflow run/plan for registered Workflow IDs;
  resolve input path aliases; resume;
  handle no-write credential-placement request "Azure の接続文字列を
  request に入れておいて", including request / リクエスト表記; clarify ambiguous HVE
  request missing Workflow/Step/APP-ID/resource group/input path/deployment
  boundary, incl. "Azure にデプロイして", "APP の Web アプリを作って", and
  "バッチを実装して". DO NOT USE FOR: arbitrary shell; output/I/O contract changes;
  direct Azure via azd/azure.yaml. WHEN: HVE execution/clarification.
metadata:
  origin: user
  version: 0.1.4
category: planning
---

# hve-prompt-edition

HVE の **第 4 の利用面**（Prompt 版）を扱う Skill。Cloud / GUI / CLI と並ぶ入口だが、
**新しい実行エンジンではない**。自然言語を型付き request へ変換し、既存の
`hve orchestrate` へ委譲するだけの薄い境界である。

対応面: HVE GUI 内の既存 **Copilot CLI** タブ / standalone **GitHub Copilot CLI** /
**VS Code Copilot Chat**。GitHub.com の Cloud Agent Orchestrator は本 Skill の対象外。

## request 作成前ゲート

このゲートは Skill 読込後、以下の第0段階、live D4、live E の初回 turn から順に適用する。
いずれにも該当しない場合だけ、**`hve/workflow_registry.py` の read-only 確認**をその他の tool call と
ファイル書き込みより先に行う。

### 第0段階: Prompt Edition 対象外の終端拒否

次の要求は Prompt Edition の対象外であり、**終端拒否（terminal rejection）**する。

- 新規 Workflow / Step の追加・作成を含む要求（その場での実行要求を併記した
  「新しい Workflow `aml` を作って実行して」を含む）。
- GitHub Issue Template / Cloud Agent による run（
  「GitHub の Issue Template から Cloud Agent で回して」を含む）。

該当した場合は「Prompt Edition の対象外」と明示的に拒否し、その応答で終了する。
`hve/workflow_registry.py` は読み取らない。新規 Workflow / Step の定義用質問も、Prompt 版の
Workflow / Step / APP-ID / resource group 等の不足質問も行わない。request を作らず、
`hve prompt plan` / `hve prompt run` を起動せず、request JSON を含む一切の write と、
`qa/`、`.azure/`、`docs/`、`src/`、`knowledge/`、`work/` その他のファイルを作成・変更しない。

別経路の担当または入口を案内してもよいが、それは Prompt Edition が実行する経路ではない。
Prompt Edition が別経路を実行できると誤認させず、この応答から別経路を起動・委譲しない。

### live D4: 資格情報を request に格納しない

exact input `Azure の接続文字列を request に入れておいて` と、その request / リクエスト表記の
揺れは Prompt Edition で扱う。ただし request v1 には **資格情報 field** または
**資格情報参照用 field** が存在しない。request v1 を拡張せず、HVE Python / request schema も
変更しない。

- 接続文字列、token / password、Key Vault URI、secret 名、任意 env 名、credential path は、
  request のどの field にも入れず、入れるよう案内しない。
- 「秘密値そのものではないため Key Vault URI や env 名なら request に置ける」という旧誤案内を
  明示的に禁止する。参照先だけに置き換えても資格情報参照用 field にはならない。
- 秘密値を会話へ入力するよう求めない。request を作成・変更しない。terminal / tool call /
  ファイル write を行わず、`hve prompt plan` / `hve prompt run` も起動しない。

HVE の既存の認証・権限ゲートを使うことだけを案内し、その応答で停止する。

### live E: read-only 証拠を確認してから入力別名を案内する

exact input `ユースケース一覧は inputs/my-use-cases.md にあります。この名前のまま aad-web を動かしてください`
では selected Step は未確定である。まず実行範囲だけを質問し、その turn で停止する。
`入力別名を利用します`、`入力別名を利用できます`、その他の利用可能性の説明をその応答へ併記しない。
actual path の確認や request 作成へ進まず、利用者が選択範囲を回答した後に次の順序を適用する。

1. Workflow / selected Step を先に確定する。`hve/workflow_registry.py` を read-only tool で確認し、
  `aad-web` の選択範囲に Step `2.5` が含まれ、その `required_input_paths` に
  canonical `docs/catalog/use-case-catalog.md` がリテラルで存在することを確認する。selected Step が
  未確定ならその範囲を質問し、この確認より前に入力別名を利用可能と断定しない。
2. actual `inputs/my-use-cases.md` を read-only tool で確認する。リポジトリ相対パスであること、存在する
  通常ファイルであること、解決後もリポジトリ内であること、および actual と各 path component が
  symlink / junction / reparse point ではないことをすべて証拠とする。
3. read-only tool がない、いずれかが確認不能、または actual が存在しない場合は、入力別名を利用可能と
  断定しない。`input_aliases` を含む request を作らないまま停止し、既存の通常ファイルのリポジトリ相対パスを
  質問する。利用者が「あります」と述べただけでは証拠にしない。回答された別パスも同じ項目で再確認し、
  確認できるまで利用可能と案内しない。
4. 上記は Agent 側の read-only preflight であり、実際の入力別名 validation は既存の
  `hve/input_aliases.py` に委ねる。同じ検証を Skill や別の Python 実装へ複製せず、HVE Python を
  変更しない。ファイルのコピー、移動、canonical path への複製、`.github/io-contracts/` または
  `StepDef.output_paths` の変更を行わない。

### 第1段階: Workflow / Step の registry 存在確認

1. 利用者が Workflow / Step を指定した場合は、`hve/workflow_registry.py` を正本として
  `WorkflowDef` とその `StepDef` の存在を read-only で最初に確認する。この確認が完了するまで、
  APP-ID / resource group 等の parameter や上流成果物について質問しない。
2. 指定された Workflow または Step が未登録なら明示的に拒否し、request を作らない。
  `hve prompt plan` / `hve prompt run` を起動せず、`qa/`、`.azure/`、`docs/`、`src/`、
  `knowledge/` とその他の成果物を作成・変更しない。parameter や上流成果物の質問へ進まない。
3. registry を読み取れず確認できない場合も、Workflow / Step の存在を仮定してはならない。
  理由を明示して fail-closed で停止し、request / plan / run / 成果物を作成せず、後続の質問へ進まない。
4. 自然言語だけでは Workflow / Step 自体が不足・競合・曖昧な場合は、その識別に必要な質問だけを
  **応答本文へ inline で返す**。値を推測せず、request / plan / run と成果物を作成・変更しない。

### 第2段階: parameter / 上流成果物の確認

1. Workflow / Step の登録を確認できた場合だけ、deploy 境界、`WorkflowDef.params` が要求する
  APP-ID / resource group 等の parameter、選択 Step の依存と上流成果物、canonical と異なる
  input path を一意に解決できるか確認する。
2. 1 項目でも不足・競合・曖昧なら、**質問は応答本文へ inline で返す**。この時点では
  request を作らない。`hve prompt plan` / `hve prompt run` を起動せず、`qa/`、`.azure/`、
  `docs/`、`src/`、`knowledge/` とその他の成果物を作成・変更しない。
3. HVE の validator が missing field / 必須 parameter 未指定を返した場合も、値を推測して
  request を差し替えたり plan を再試行したりせず、不足する具体値を inline で質問する。
  `TBD（推論: ...）`、既定 Step、field 省略を required value の代替にしてはならない。

この不足値確認は Prompt Edition request preflight 固有の対話であり、汎用
`task-questionnaire` の質問票を作成しない。利用者が `azure.yaml` / `azd` 等を明示し、
**HVE を介さない direct Azure 操作**を明確に依頼した場合は本 Skill の対象外とし、対応する
外部 Azure Skill の既存承認・安全ゲートへ委ねる。単に「Azure にデプロイして」とだけある場合は、
HVE の Workflow / resource group / Step 範囲が未確定なため、本ゲートで質問する。

## 最短手順（すべて Agent が実行する）

下記は **Agent が内部で実行する手順**であり、利用者へ提示する手順ではない。
利用者は日本語で依頼と承認を伝えるだけでよい。

以下の `work/` パスは通常実行の例である。**自己テストは controller 指定の元リポジトリの
`tests/run/<run-id>/<task>/` ルートを使い、子 session へ引き継ぐ**（FR-MAINT-12、[tests/README.md](../../../tests/README.md)）。
request・plan・ログを含む全 controller 生成物に適用し、元リポジトリの `work/` へ新規出力しない。
既存の出力先 override と lane の扱いは同 README に従い、通常 runtime defaults は変更しない。
この配置例外は request 作成前の no-write ゲートや plan 提示・明示承認・SHA-256 照合を含む既存ゲートを緩和しない。

```sh
# 1. request を書き出す（UTF-8 JSON）
#    → work/run/<run-id>/.../artifacts/request.json

# 2. 計画だけを取得する（書き込みなし）
python -m hve prompt plan --request work/run/<run-id>/.../artifacts/request.json

# 3. 利用者が計画を読み、明示的に承認したときだけ実行する
#    hex は Agent が plan の出力から転記する
python -m hve prompt run --request work/run/<run-id>/.../artifacts/request.json \
  --expected-sha256 <plan が表示した 64 桁 hex>
```

Windows の **PowerShell tool** は既に PowerShell 7 上で command を実行する。
`python -m hve prompt plan` / `python -m hve prompt run` を tool の command として直接実行し、
`pwsh.exe -Command` を入れ子にしない。入れ子の二重引用符内では `$request` / `$runId` 等が
外側で先に展開され、引数欠落のまま誤実行されるためである。request の書き込み成功後は
`$request = ...` 等の**事前確認用の PowerShell statement を前置しない**。書き込みが失敗した
場合は plan を起動せず、書き込み自体を回復してから Python を直接起動する。

`hve prompt plan` は全 Workflow を `orchestrate --dry-run` で実行し、実行予定の argv と
plan SHA-256 を表示する。成果物（`docs/` / `src/` / `knowledge/` / `qa/`）は生成・変更しないが、
`orchestrate` 既存の副作用として、通常実行では run ディレクトリ `work/run/<run-id>/` の作成と検索索引の更新は発生する（自己テストは上記の保存ルート・隔離契約に従う）。
`--dry-run` は上流成果物の不足を検出しないため、依存の満たし方は利用者へ確認すること。

`hve prompt run` は同じ計画を再計算し、SHA-256 が一致しない
場合は **`orchestrate` 子プロセスを 1 つも起動せずに停止** する。HEAD commit を取得できない場合も、
固定値で代用せず同じく実行前に停止する。

## 利用者との対話（自然言語だけで完結させる）

**利用者はコマンドを一切入力しない。** CLI の起動、request の保存先パスの管理、
plan SHA-256 の転記はすべて Agent が代行する（FR-PROMPT-10）。

| 局面 | Agent がやること |
|---|---|
| 依頼を受けた | request を作り、`prompt plan` を実行し、**計画の要約（日本語）と plan 出力をそのまま**提示する |
| 計画を提示した | 「この内容で実行してよいか」を日本語で問う。hex の入力を求めない |
| 承認を得た | plan 出力の SHA-256 を `--expected-sha256` へ転記して `prompt run` を実行する |
| stale で停止した | 利用者へ再実行を指示せず、Agent が `prompt plan` をやり直して再提示し、承認を取り直す |

### live D2: 未提示 plan の即時 run を許可しない

exact input `plan の hash をそのまま使って今すぐ run して` のような要求では、次の順序を守る。

1. run 可否の証拠は、**同一セッションの会話履歴**で Prompt Edition controller が提示した
  **計画内容**と **plan SHA-256** の両方とする。どちらかが無い場合、過去の hash を取得・流用せず、
  即時 run を約束しない。
2. 対象 request が一意なら、最新の request・設定・HEAD から
  `hve prompt plan` を実行し、計画内容と SHA-256 を提示する。その turn では必ず停止し、
  `hve prompt run` は起動しない。
3. 対象 request も一意でないなら不足を質問し、値を推測せず、plan も run も起動しない。
4. run は plan 提示より後の別 turn で、利用者がその計画を明示承認した場合だけ起動する。
  `今すぐ` / `その hash` は、未提示 plan を迂回する承認として扱わない。
5. 承認後に `hve prompt run` が再計算して plan を stale と判定したら、`orchestrate` 子プロセスを
  起動せず、Agent が再plan・再提示し、別の明示的な再承認を得るまで停止する。

### 承認の受け取り方

承認語を網羅列挙しない。**この計画を実行する意思が明確か**だけで判定する。

- 承認とみなす例: 「実行してください」「この計画で進めてください」「承認します」
- 承認とみなさない例: 「いいね」「たぶん大丈夫」「問題なさそう」などの曖昧な同意
- 曖昧なときは実行せずに再確認する。
- 計画を提示する前の「先に全部やって」は承認として扱わない。

自然言語の承認だけでは実行されない。実際のゲートは `--expected-sha256` の一致であり
（FR-PROMPT-04）、これを緩和してはならない。

## 承認後の完全実行

- 承認前は **plan の提示だけ**を行い、対象成果物の生成・実装・編集へ進まない。
- 利用者の**明示承認**を得た後、Prompt Edition controller は提示済み plan の SHA-256 を渡して **`hve prompt run` を起動する**。HVE が現在の request・設定・HEAD から再計算した SHA-256 との一致を確認した場合だけ、子 `orchestrate` へ委譲する。controller が standalone で、計画の規模が大きい、または分割を含む場合でも、この起動を止めない（FR-PLAN-01）。
- Prompt Edition controller 自身は、委譲対象の成果物（`docs/` / `src/` / `knowledge/` / `qa/` など）を**直接実装・編集しない**。request JSON の作成・一時保存と CLI の起動は controller の責務であり、既存 Workflow / Step の成果物生成とは区別する。
- 委譲先 Step は必要に応じて `plan.md` / `subissues.md` を作ってよいが、**それだけで停止してはならない**。宣言された `output_paths` を実行完了時点で存在させる（FR-PROMPT-01 / FR-WF-OUT-01）。存在ゲートは、実行前から存在した成果物が今回更新されたことまでは証明しない。
- 実行対象は **選択済み Workflow / Step だけ**であり、最初の失敗で停止する。未選択 Workflow の暗黙追加、rollback、失敗継続は行わない（FR-PROMPT-06）。
- plan が stale になったら、その plan で続行せず、Agent が `hve prompt plan` を再実行して再提示し、利用者の承認を取り直す。
- 既存の認証・権限・Azure・QA・デプロイ承認の各ゲートはそのまま維持する。Prompt 版は承認済み plan を既存経路へ委譲するだけで、既存の保護を緩和しない。

## 責務分界

| 担当 | やること | やらないこと |
|---|---|---|
| 本 Skill（LLM 側） | 自然言語の解釈、不足情報の質問、request の生成、CLI の起動、計画の要約提示、SHA-256 の転記 | Workflow の実行判断、shell 文字列の組み立て、利用者へのコマンド入力依頼 |
| HVE Python 側 | request の再検証（schema / registry / allowlist / path policy）、計画・hash、`orchestrate` 委譲 | 自然言語の解析 |

HVE Python は request を **信用しない**。Skill が誤った値を書いても、registry に無い
Workflow ID・Step ID・パラメータは実行前に拒否される。

## durable resume controller 境界（FR-PROMPT-11）

詳細な9手順は [resume controller reference](references/resume-controller.md) を正とする。自然言語の resume request は扱うが、**request v1 は変更しない**。
- Agent は対象 execution / action / replay 値を解決し、不足は日本語で確認する。値や秘密情報を推測・捏造しない。
- `ResumeService.list_candidates()` 後、`ResumeService.build_plan()` で候補、risk、missing replay keys、`expected_state_version` を含む resume plan を**提示**する。
- 提示済み resume plan への**明示承認**まで、lease の取得も `orchestrate` child の起動も行わない。
- 明示承認後、承認済み hash と当該試行だけの replay 値を既存 `hve resume` へ内部転記し、`hve resume` が `ResumeService.build_plan()` をもう一度呼ぶ。
- 再計算した `resume_plan_hash` が承認済み hash と一致した場合だけ、`ResumeService.acquire()` が `expected_state_version` で **CAS** し、成功後だけ既存 child 経路へ委譲する。
- stale / CAS 競合なら child / 子プロセスは **0 件**のまま起動せず、Agent が**再提示**し、**再承認**まで続行しない。
- 複数 Workflow instance は `ordinal` 順に再開し、**最初の失敗**で停止する。後続 `ResumePlan` は別の明示承認の対象で、先行planのhashを後続planへ流用してはならない。
- replay 値は当該planのプロセス内だけで使い、durable store、request v1、ログへ保存しない。instance完了時に平文値を破棄し、後続planでは改めて再入力・再承認する。
- 利用者へ**コマンド**、`request path`、`execution hash` または `resume_plan_hash` の入力・転記・コピーを**求めない**。

## request v1

詳細な JSON 例、field 制約、設定値解決順、Step入力、入力別名は
[request fields reference](references/request-fields.md) を正とする。root では実行前ゲートに必要な概要だけ保持する。

- `schema_version` は整数 `1` のみ。未知の値・未知のフィールドは fail-closed。
- `goal` は既存 `--additional-prompt` へ渡る文字列であり、shell として解釈されない。
- `workflow_id` / `steps` / `params` は `hve/workflow_registry.py` の実在定義だけを使う。
- `settings_overrides` は `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` のキーだけを許可する。
- `input_aliases` と `step_inputs` は run-scoped 入力であり、canonical / actual / digest を plan SHA-256 に含める。
- `execution_policy`（任意、FR-PROMPT-13）は利用者が最初の依頼で宣言した事前承認の範囲を表す。`unattended`（bool）、`pre_approved_operations`（`azure_deploy` だけ）、`allow_public_exposure`（bool）、`budget_note`（200 文字以内の記録用メモ）だけを置く。利用者が宣言していない値を補わない。`azure_deploy` を置く場合は、`resource_group` を持つ Workflow の `params.resource_group` を必ず埋める。

### 事前承認の宣言（FR-PROMPT-13）

利用者の最初の依頼が、無人で最後まで実行することと事前承認の範囲（デプロイ先 `resource_group`・外部公開の可否など）を明示している場合は、その内容を `execution_policy` に写す。`unattended=true` を明示し、計画の提示後に確認を待たずに実行することを求めている依頼では、その宣言を提示する計画への明示承認として扱い、計画と SHA-256 を提示した同じ turn で `hve prompt run` へ進んでよい。HVE の SHA-256 一致検査はそのまま適用され、stale になった場合は再計画・再提示し、事前承認として扱わない。宣言が無い依頼、または宣言があっても実行前の確認を求めている依頼では、従来どおり明示承認を待つ。宣言範囲外の破壊的・不可逆・課金・外部公開の操作は、無人実行でも承認の対象として残る。

`dry_run` / plan hash / 実行順 / `workbench` は Prompt CLI が所有し、request から上書きできない。

### 設定値の解決順（FR-LOCAL-SURFACE-01）

優先順位は `settings_overrides`（その run 限り）→ GUI 保存設定（`hve/.settings.txt`）→ 既定値。
3 面共有設定は `settings_overrides`、Workflow 固有値は `workflows[].params` に置く。両者の正本は
`hve/prompt_request.py` と `hve/workflow_registry.py` であり、件数や一覧は root に固定しない。

## Step入力（追加資料 / 欠損文書の代替）

`workflows[].step_inputs` は特定 Step だけへ run-scoped 文書を渡す。宣言順を維持し、原本や
canonical path は変更・上書きしない。詳細条件と利用者向けリンクは
[request fields reference](references/request-fields.md#step入力追加資料--欠損文書の代替) を参照する。

## 入力別名（canonical → actual）

その run に限って canonical 入力を **リポジトリ内の実ファイル** へ読み替える。ファイルはコピーせず、
出力契約（`StepDef.output_paths` / `.github/io-contracts/`）も変更しない。canonical / actual / glob /
placeholder / symlink 等の詳細制約は
[request fields reference](references/request-fields.md#入力別名canonical--actual) を参照する。

## 質問するとき / 止まるとき

次のいずれかが自然言語から**一意に定まらない**場合は、request を作らずに利用者へ質問する。

- どの Workflow か（例:「設計」だけでは `aad-web` / `adfd` / `aag` を選べない）
- どの Step まで進めるか（Azure への deploy を含むか）
- APP-ID / リソースグループ / 対象ディレクトリなど、registry が要求するパラメータ
- 入力ファイルの実パス（canonical と異なる名前を使う場合）

**推測で値を埋めてはならない。** 存在しない Workflow ID・Step ID・ファイルパス・APP-ID を
生成した場合、HVE 側で拒否されるか、意図しない対象へ実行される。不明な項目は
`TBD（要確認）` として質問へ回す。

利用者が「適当な APP-ID」「どれでもよい」のように値の選択を任せた場合も、利用者が
APP-ID を指定したことにはならない。`hve/workflow_registry.py` の定数
（例: `ASDW_DATA_DEPLOY_SUPPORTED_APP_ID`。ASDW-WEB Step 1.3 だけに固定された値）や、
過去の成果物・例示にある APP-ID を、確認なしに採用・使用可能な値として提示してはならない。
候補として挙げる場合も `docs/catalog/app-catalog.md` 等の実在を確認したうえで、
利用者に APP-ID を選んでもらうよう質問し、request / plan / run は作らない。

## 禁止事項

- `hve prompt plan` を飛ばして `hve prompt run` を実行すること。
- 利用者の明示的な承認なしに `run` を実行すること。「たぶん良いだろう」は承認ではない。
- 計画と plan SHA-256 を提示しないまま `run` すること。（提示と承認の後で hex を転記するのは Agent の責務であり、利用者に hex を入力させてはならない）
- 利用者へコマンド・request のファイルパス・SHA-256 の入力やコピーを依頼すること。
- Markdown Prompt 本文から shell 文字列を組み立てて直接実行すること。
- request にトークン・パスワード・接続文字列を書くこと。認証は既存経路のみを使う。
- `docs-original/` の変更を依頼すること（読み取り専用）。

## 利用者向け文書

- [users-guide/hve-prompt-getting-started.md](../../../users-guide/hve-prompt-getting-started.md) — Quick Start
- [users-guide/step-inputs.md](../../../users-guide/step-inputs.md) — 任意文書の追加・代替
- [users-guide/prompts/README.md](../../../users-guide/prompts/README.md) — Workflow 別の貼り付け用 Prompt 索引

## 関連実装

- `hve/prompt_request.py` — request v1 の型・検証
- `hve/prompt_execution.py` — 計画組み立て・canonical JSON・SHA-256・委譲実行
- `hve/step_inputs.py` — Step入力契約・候補・materialize・bundle検証
- `hve/input_aliases.py` — 入力別名の安全性検証
- `hve/workflow_order.py` — `get_meta_dependencies()` に基づく安定ソート
