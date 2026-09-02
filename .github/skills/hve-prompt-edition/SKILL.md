---
name: hve-prompt-edition
description: >
  HVE natural-language controller for existing workflows. USE FOR: run or plan HVE
  workflows from prose; select ard/aas/aad-web/asdw-web/adfd/adfdv/ada/aag/
  aagd/aar/akm/adi/adoc; resolve input path aliases; resume HVE runs; handle
  no-write credential-placement requests such as "Azure の接続文字列を request
  に入れておいて", including request / リクエスト表記; clarify an ambiguous HVE
  request with a missing Workflow, Step, APP-ID, resource group, input path, or
  deployment boundary, including "Azure にデプロイして", "APP の Web アプリを
  作って", and "バッチを実装して". DO NOT USE FOR: edit
  workflow_registry.py; add or create-and-run workflows or steps;
  GitHub Issue Template or Cloud Agent runs. For these boundaries: terminal
  rejection; no definition or Prompt-field questions; no request/plan/run/write;
  alternate routes are not run by Prompt Edition. Also not for arbitrary shell;
  change output paths or I/O contracts; direct Azure
  deployment explicitly bypassing HVE via azd or an existing azure.yaml. WHEN:
  HVE execution or clarification is requested.
metadata:
  origin: user
  version: 0.1.0
category: planning
---

# hve-prompt-edition

HVE の **第 4 の利用面**（Prompt 版）を扱う Skill。Cloud / GUI / CLI と並ぶ入口だが、
**新しい実行エンジンではない**。自然言語を型付き request へ変換し、既存の
`hve orchestrate` へ委譲するだけの薄い境界である。

対応面: HVE GUI 内の既存 **Copilot CLI** タブ / standalone **GitHub Copilot CLI** /
**VS Code Copilot Chat**。GitHub.com の Cloud Agent Orchestrator は本 Skill の対象外。

## request 作成前ゲート

このゲートは Skill 読込後、以下の第0段階と live D4 判定から順に適用する。どちらにも
該当しない場合だけ、**`hve/workflow_registry.py` の read-only 確認**をその他の tool call と
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
`orchestrate` 既存の副作用として run ディレクトリ `work/run/<run-id>/` の作成と検索索引の更新は発生する。
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
- 利用者の**明示承認**を得た後、Prompt Edition controller は提示済み plan の SHA-256 を渡して **`hve prompt run` を起動する**。HVE が現在の request・設定・HEAD から再計算した SHA-256 との一致を確認した場合だけ、子 `orchestrate` へ委譲する。controller が standalone の `task_scope=multi` / `context_size=large` でも、この起動を plan-only 規則で止めない。
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

自然言語の resume request はこの境界で扱うが、**request v1 は変更しない**。execution ID、
resume action、replay 値などの resume 固有情報を request JSON に追加せず、当該 resume 試行の
一時入力として扱う。

1. Agent は自然言語から対象 execution、action、必要な replay 値を解決する。一意に定まらない
  候補や不足値は利用者へ日本語で確認し、値や秘密情報を推測・捏造しない。
2. 共通 SSOT の `ResumeService.list_candidates()` で候補を取得し、選択後に最初の
  `ResumeService.build_plan()` を呼ぶ。候補、action、risk、missing replay keys、
  `expected_state_version`、`resume_plan_hash` を含む resume plan を日本語で**提示**する。
3. 提示済み resume plan を実行する意思が明確な**明示承認**を得るまで、lease の取得も
  `orchestrate` 子プロセスの起動も行わない。曖昧な同意は承認とみなさず再確認する。
4. 明示承認後、Agent は承認済み hash と当該試行だけの replay 値を既存 `hve resume` へ
  内部転記して委譲する。`hve resume` は `ResumeService.build_plan()` をもう一度呼び、現在の
  durable state と HEAD から plan を**再計算**する。
5. 再計算した `resume_plan_hash` が承認済み hash と一致した場合だけ、`hve resume` が
  `ResumeService.acquire()` を呼ぶ。`acquire()` は plan の `expected_state_version` を用いた
  **CAS** を実施し、成功後だけ既存の `hve resume` / `orchestrate` child 経路へ委譲する。
  Prompt Edition controller 自身は先行または重複して `acquire()` を呼ばない。
6. hash 不一致または CAS 競合で plan が **stale** なら、child / 子プロセスは **0 件**のまま
  起動せず停止する。Agent が最新 plan を再計画して日本語で**再提示**し、利用者から
  **再承認**を得るまで続行しない。
7. 複数 Workflow instance は登録済みの `ordinal` 順に再開し、**最初の失敗**で停止する。
  instance 完了後に構築された後続 `ResumePlan` は別の明示承認の対象とする。Agent は新しいplanを
  再提示し、利用者の再承認を得てから同じhash再計算/CAS手順を繰り返す。先行planのhashを後続planへ流用してはならない。
  後続 instance を暗黙に起動せず、独自の resume 判定や別の実行エンジンを追加しない。
8. output再調停で実行対象が0件になったinstanceは、subcommandなしchildを起動せず、共通
  `ResumeService` が取得済みfenced leaseとoutputを再確認して`succeeded`へ確定する。
9. replay 値は当該planのプロセス内だけで使用し、durable store、request v1、ログへ保存しない。
  instance完了時に平文値を破棄し、後続planへ流用しない。後続planが同じkeyを必要とする場合も
  改めて再入力・再承認する。認証情報などの秘密値が必要な場合も、既存の安全な入力経路を使い、Agent は値を生成しない。

利用者へ**コマンド**、`request path`、`execution hash` または `resume_plan_hash` の入力・転記・
コピーを**求めない**。候補取得、plan の作成、内部引数への転記、既存 CLI の起動は Agent が行う。

## request v1

```json
{
  "schema_version": 1,
  "goal": "実施したい内容を 1〜3 文で",
  "workflows": [
    {
      "workflow_id": "aad-web",
      "steps": ["1", "2.1"],
      "params": { "app_ids": "APP-009" },
      "input_aliases": [
        {
          "canonical": "docs/catalog/app-catalog.md",
          "actual": "inputs/my-app-catalog.md"
        }
      ]
    }
  ],
  "settings_overrides": { "model": "<GUI で選択済みのモデル>" }
}
```

| フィールド | 規則 |
|---|---|
| `schema_version` | 整数 `1` のみ。未知の値・未知のフィールドは fail-closed。 |
| `goal` | 既存 `--additional-prompt` へ渡る文字列。shell として解釈されない。 |
| `workflow_id` | `hve/workflow_registry.py` の canonical ID（`python -m hve orchestrate --help` ではなく registry が正本）。 |
| `steps` | 当該 Workflow に実在する Step ID のみ。省略時は既定の選択。 |
| `params` | 当該 Workflow が宣言したパラメータのみ。値は文字列。 |
| `settings_overrides` | `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` のキーのみ。token / password / 任意 env / 任意コマンドは拒否。 |
| `input_aliases` | 下記「入力別名」の制約に従う。 |

`dry_run` / plan hash / 実行順 / `workbench` は Prompt CLI が所有し、request から上書きできない。

### 設定値の解決順（FR-LOCAL-SURFACE-01）

Prompt 版は GUI が保存した設定を基準値として引き継ぐ。優先順位は次のとおり。

1. request の `settings_overrides`（その run 限り）
2. GUI が保存した設定（`hve/.settings.txt`）
3. 既定値

`settings_overrides` に置けるのは「3 面共有設定」だけで、Workflow 固有の値は `workflows[].params` に置く。両者を取り違えると fail-closed で停止する。

| 種別 | 置き場所 | 例 |
|---|---|---|
| 3 面共有設定 | `settings_overrides` | `model` / `strict` / `enable_tool_search` / Agentic Retrieval 6 項目 / `cloud_session_branch` |
| Workflow 固有 | `workflows[].params` | `app_ids` / `resource_group` / `create_remote_mcp_server` / `tdd_max_retries` |

正本は `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` と `hve/workflow_registry.py` の `WorkflowDef.params`。ここへ件数や一覧を固定記述せず、必ず正本を確認する。

## 入力別名（canonical → actual）

その run に限って canonical 入力を **リポジトリ内の実ファイル** へ読み替える。
ファイルはコピーせず、出力契約（`StepDef.output_paths` / `.github/io-contracts/`）も変更しない。

- `canonical` は選択した Step の `required_input_paths` に**リテラルで一致**するものだけ。
- v1 は glob（`*` `?` `[`）、placeholder（`{` `}`）、ディレクトリ入力を受理しない。
- `actual` はリポジトリ内の相対パスの通常ファイル。絶対パス・`..`・symlink・不存在は拒否。
- 同じ canonical への重複指定、選択済み上流 Step が生成する出力の差し替えは拒否。

### live E: read-only 証拠を確認してから入力別名を案内する

exact input `ユースケース一覧は inputs/my-use-cases.md にあります。この名前のまま aad-web を動かしてください`
では、利用者の記述だけから入力別名を利用可能と断定してはならない。`input_aliases` を含む
request を作る前に、次の順序を固定する。

1. Workflow / selected Step を先に確定する。`hve/workflow_registry.py` を read-only tool で確認し、
  `aad-web` の選択範囲に Step `2.5` が含まれ、その `required_input_paths` に
  canonical `docs/catalog/use-case-catalog.md` がリテラルで存在することを確認する。selected Step が
  未確定ならその範囲を質問し、この確認より前に入力別名を利用可能と断定しない。
2. actual `inputs/my-use-cases.md` を read-only tool で確認する。リポジトリ相対パスであること、存在する
  通常ファイルであること、解決後もリポジトリ内であること、および actual と各 path component が
  symlink / junction / reparse point ではないことをすべて証拠とする。
3. read-only tool がない、いずれかが確認不能、または actual が存在しない場合は、入力別名を利用可能と
  断定しない。`input_aliases` を含む request を作らないまま、既存の通常ファイルのリポジトリ相対パスを
  質問する。利用者が「あります」と述べただけでは証拠にしない。回答された別パスも同じ項目で再確認し、
  確認できるまで利用可能と案内しない。
4. 上記は Agent 側の read-only preflight であり、実際の入力別名 validation は既存の
  `hve/input_aliases.py` に委ねる。同じ検証を Skill や別の Python 実装へ複製せず、HVE Python を
  変更しない。ファイルのコピー、移動、canonical path への複製、`.github/io-contracts/` または
  `StepDef.output_paths` の変更を行わない。

## 質問するとき / 止まるとき

次のいずれかが自然言語から**一意に定まらない**場合は、request を作らずに利用者へ質問する。

- どの Workflow か（例:「設計」だけでは `aad-web` / `adfd` / `aag` を選べない）
- どの Step まで進めるか（Azure への deploy を含むか）
- APP-ID / リソースグループ / 対象ディレクトリなど、registry が要求するパラメータ
- 入力ファイルの実パス（canonical と異なる名前を使う場合）

**推測で値を埋めてはならない。** 存在しない Workflow ID・Step ID・ファイルパス・APP-ID を
生成した場合、HVE 側で拒否されるか、意図しない対象へ実行される。不明な項目は
`TBD（要確認）` として質問へ回す。

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
- [users-guide/prompts/README.md](../../../users-guide/prompts/README.md) — Workflow 別の貼り付け用 Prompt 索引

## 関連実装

- `hve/prompt_request.py` — request v1 の型・検証
- `hve/prompt_execution.py` — 計画組み立て・canonical JSON・SHA-256・委譲実行
- `hve/input_aliases.py` — 入力別名の安全性検証
- `hve/workflow_order.py` — `get_meta_dependencies()` に基づく安定ソート
