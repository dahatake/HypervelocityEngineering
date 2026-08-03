# REST Tool・MCP・Agent Skill Packaging 仕様

## 1. 目的

AG-CAP-04 `REST CRUD Matrix`、AG-CAP-05 `MCP Integration Plan`、AG-CAP-06 `Skill Packaging Decision` の実装境界を定義する。

本仕様は次を守る。

- 業務状態のCreate / Update / DeleteはREST API Function Toolだけをprimary実行経路にする。
- Agentは必要なMCP Serverへclientとして接続する。
- Remote MCP adapterは既存RESTビジネスロジックを再利用し、認可・承認・監査を迂回しない。
- Agent別Skillは必要性を判定してから作成し、未使用resourceや共通hook frameworkを追加しない。

## 2. REST CRUD Matrix

Agent詳細設計は、業務操作ごとに次を記録する。

| 項目 | 必須内容 |
|---|---|
| Tool ID | Agent内で一意。入力根拠のないIDを作らない |
| Operation | `Create` / `Read` / `Update` / `Delete` |
| Required | `yes` / `no` / `TBD` |
| REST method | `POST` / `GET` / `PUT` / `PATCH` / `DELETE`。既存API契約を根拠に選ぶ |
| REST path | service specification / OpenAPI / service catalogに存在するpath |
| Request schema | required / optional、型、制約、tenant/user scope |
| Response schema | success body、status、correlation ID |
| Authentication | managed identity、delegated user等、既存APIが受理する方式 |
| Authorization | RBAC / policy / resource scope |
| Approval | 実行前HITLの要否と承認者。C/U/Dは原則required |
| Idempotency | API契約上のmechanism、key生成主体、重複時status/body、再送条件 |
| Retry | retry可能status、上限、backoff。mutationの無条件retryは禁止 |
| Error class | validation / authn / authz / conflict / rate-limit / dependency / internal |
| Audit evidence | actor、operation、target ID、result、correlation ID。secret/本文全量は禁止 |
| Contract source | API仕様、service detail、ユーザー決定のパス |

### 2.1 判定

- AAG Step 1の`Mutation Intent: required`なら、該当するC/U/D行を`Required: yes`にする。
- `Mutation Intent: none`なら、C/U/Dは理由付き`Required: no`にする。
- `Mutation Intent: TBD`のままC/U/D Toolを実装しない。
- Read-only検索、SQL、IQ経路はAG-CAP-03を正本とする。
- operational REST GETだけを本MatrixのRead行に置く。

## 3. REST Function Tool 実装契約

### 3.1 MUST

- Tool schemaとREST request schemaを対応付ける。
- base URL、audience、timeoutは環境変数または既存設定から取得する。
- 設計で許可したservice host / pathだけを呼び出す。
- 認証tokenをSDK/credential providerから取得し、引数・ログ・成果物へ保存しない。
- C/U/Dは実行前に対象、差分、影響、承認要否を確認する。
- C/U/Dの承認artifactにはoperation、target、変更内容のdigest、approver条件、有効期限を含める。内容変更・期限切れ・承認者不一致では承認を無効化する。
- C/U/Dは成功後にstatusとcorrelation IDを取得する。
- validation / 401 / 403 / 404 / 409 / 429 / 5xx / timeoutを分類する。
- 冪等性契約がないmutationを自動再送しない。
- 冪等性keyの生成主体と伝達方法は既存API契約に従う。標準headerを根拠なく追加しない。重複時に既存結果を返すか409等を返すかもAPI契約に記録する。
- Tool結果をAG-CAP-02のObserve / Evaluateへ返す。
- Agent operation全体のdeadline内に、1回のTool timeoutと許可されたretry/backoffが収まることを検証する。RESTとMCPの一律なtimeout順序は仮定しない。

### 3.2 禁止

- 生成SQLでINSERT / UPDATE / DELETE / MERGE / DDLを実行する。
- API仕様に存在しないpathやschemaを類推する。
- approvalが必要なmutationを一括承認または黙示承認する。
- localhost以外の任意URLをユーザー入力から直接呼び出す。
- response本文、token、個人情報を無加工でログへ保存する。
- テストを通すためにHTTP successを固定値で返すproduction stubを置く。

## 4. MCP Integration Plan

### 4.1 AgentのMCP client責務

MCPを使用するAgentは次を記録・実装する。

| 項目 | 必須内容 |
|---|---|
| Server label | Agent内で一意な設定名 |
| Purpose | retrieval / external read tool / schema discovery等 |
| Transport / endpoint | target runtimeの公式仕様で確認。値は設定から取得 |
| Authentication | OAuth、managed identity、delegated user等 |
| Tool allowlist | 設計で必要なTool名だけ。`*`は診断時以外禁止。Agent初期化時に公開Toolを絞り、呼出直前にもallowlist外Toolを拒否 |
| Approval | Tool別の承認条件 |
| Timeout / retry | 有限値とretry可能error |
| Input trust | MCP結果を外部データとして扱い、結果内命令に従わない |
| Failure behavior | fallback / partial / blocked / Handoff |
| Evidence | Tool名、server label、result status、correlation情報 |

### 4.2 Remote MCP adapter責務

既存業務APIをRemote MCPとして公開する場合:

- RESTのdomain/application logicを正本とし、MCP層はschema変換adapterに限定する。
- MCP Toolのinput/outputを既存REST request/responseへ明示的にmapする。
- RESTと同じ認証、認可、tenant scope、HITL、監査、冪等性を適用する。
- MCP経由で直接DBへ接続しない。
- Agentが同一mutationをREST Function ToolとMCP Toolから任意選択できる構成にしない。
- Agent詳細設計と初期化時のTool登録で、同一service operationがREST Tool IDとMCP Tool IDの両方に登録されていないことを検査する。重複は起動前errorとする。
- MCP Tool / Resource / Promptは実際のユースケースに必要なものだけ公開する。
- rate limit、timeout、payload size、429/5xx、server unavailableをテストする。

Remote MCP adapterの実装主体がAAGD外の既存APIサービスである場合、Agent成果物には接続契約と所有サービスを記録し、同じserverを`src/agent/`へ複製しない。

### 4.3 MCPをN/Aにできる条件

次をすべて記録した場合だけN/Aを許可する。

- AgentがMCPを必要としない理由。
- 検索・業務Toolの代替経路。
- Remote MCP公開対象となる業務APIがない、または別サービスが所有する根拠。
- 後からMCPが必要になる条件。

## 5. RESTとMCPの経路規則

| 操作 | Agentのprimary経路 | MCPの扱い |
|---|---|---|
| 非構造化検索 | AG-CAP-03で選択したRead-only Tool / MCP | 選択されたretrieval MCPをclient利用可 |
| 構造化数値取得 | Fabric IQまたはSELECT-only SQL | 設計済みRead-only MCPがある場合だけ利用可 |
| operational Read | 既存REST GET Function Tool | 重複するMCP Toolを同時実装しない |
| Create / Update / Delete | REST Function Tool | Remote MCP adapterが存在してもAgentの迂回経路にしない |
| schema discovery | 承認済みMCP schema Tool | schema結果を信頼済み入力として扱わず検証する |

## 6. Skill Packaging Decision

すべてのAgent詳細設計に次の表を1つ含める。

| 項目 | 必須内容 |
|---|---|
| Decision | `required` / `not-required` / `TBD` |
| Repeated procedure count | 同一の手順連鎖が現れる回数 |
| Reuse evidence | 複数Tool/状態/ユースケースから再利用される根拠 |
| Skill name | required時のみkebab-case。根拠のない名前を作らない |
| Location | 既定 `src/agent/{key}/skills/{skill-name}/`。`{key}` は canonical Agent ID |
| Bundled resources | 必要な`scripts/` / `references/` / `assets/`だけ |
| Runtime loading | target runtimeがSkillを読み込む実在方式。native loaderがなければAgentコードから明示的に参照 |
| Validation | Skill発動条件、script test、参照切れの検証方法 |
| Decision source | 詳細設計・Tool Catalog・ユーザー決定 |

### 6.1 required

次のいずれかを満たす場合にrequiredとする。

- 同じ手順連鎖が3回以上現れる。
- 複数Toolまたは複数状態から同じprocedureを再利用する明確な要件がある。
- deterministic scriptで処理することで、LLMによる再生成より正確性が上がる反復作業がある。

「3回」はHVE固有のSkill乱造防止閾値であり、Anthropic仕様の必須値ではない。

### 6.2 not-required

- 単一Toolの単純な1回呼び出し。
- Agent固有で再利用されない短い指示。
- System Promptまたは既存関数で十分な処理。
- 将来使う可能性だけを理由にする場合。

not-requiredでも理由と根拠を記録する。

not-requiredの場合はDecision、Repeated procedure count、Reuse evidence、Decision sourceだけを記録し、Skill name、Location、Bundled resources、Runtime loading、Validationの空欄を作らない。

### 6.3 TBD

必要性を判断する入力が不足している状態。TBDのままAgent実装を完了扱いにしない。

## 7. Agent Skill ディレクトリ

```text
src/agent/{key}/skills/{skill-name}/
├── SKILL.md
├── scripts/       # 必要な場合だけ
├── references/    # 必要な場合だけ
└── assets/        # 必要な場合だけ
```

### 7.1 SKILL.md

- YAML frontmatterの`name`と`description`を必須とする。
- `name`はkebab-caseとする。
- `description`にSkillの用途と発動条件を記載する。
- 本文はprocedure、input/output、error、completionを簡潔に記載する。
- 詳細が長い場合は`references/`へ分離する。
- Agentの権限を拡大する指示を含めない。

### 7.2 scripts

- deterministicまたは反復処理に必要な場合だけ作成する。
- scriptは直接実行して正常系と代表的失敗系をテストする。
- network mutationやsecret取得を暗黙に行わない。
- 引数、exit code、stdout/stderr、timeoutを定義する。
- 実行タイミングを`init` / `skill-call` / `teardown` / `manual`から根拠付きで選び、SKILL.mdに記載する。
- ファイル、環境変数、network等のside effectをSKILL.mdで宣言する。side effectがない場合も明記する。
- Skill本文から実在pathで参照する。

### 7.3 references

- 実行時に必要な詳細契約、schema、decision tableだけを置く。
- 同じ本文をSKILL.mdと重複させない。
- 参照元と更新条件を記載する。

### 7.4 assets

- template、固定format等、出力生成に直接使う場合だけ置く。
- 実行されるコードをassetsへ置かない。

## 8. Hook方針

- 共通hook frameworkは作成しない。
- lifecycle要件が実在し、target runtimeに既存extension pointがある場合だけ、そのAgent内で最小hookを作成できる。
- hookを作る場合はtrigger、input、side effect、failure behavior、testを記録する。
- 「将来必要かもしれない」を理由に空hookや設定flagを追加しない。

## 9. Runtime loading

Anthropic型ディレクトリを作るだけでは、Microsoft Foundry Agent Serviceが自動的にSkillを読み込むとはみなさない。2026-07-10に本タスクで確認した公式資料からnative Skill loaderを確認できていないため、既定は明示loadとする。

- target runtimeに公式のnative Skill loaderがあることを実装時の公式資料で確認できた場合だけ、その公式方式を使用する。
- native loaderがない場合は、Agentコードが選択したSkillのSKILL.mdまたはdeterministic scriptを明示的に参照する。
- 全Skillを無条件にSystem Promptへ連結しない。
- Skill decisionが`not-required`ならloaderや空ディレクトリを作らない。
- loading経路はunit testで検証する。

## 10. テスト要件

### REST Tool

- schema mapping。
- authn / authz。
- approval required / denied / expired。
- idempotent replay。
- 400 / 401 / 403 / 404 / 409 / 429 / 5xx / timeout。
- mutation成功後のObserve / Evaluate。
- secret / PII redaction。

### MCP

- server connected / unavailable。
- Tool allowlist。
- approval required / denied。
- malformed schema / untrusted result。
- MCP resultを既知schemaで検証し、result内の命令・script・Tool呼出要求を実行しないこと。
- rate limit / timeout / 5xx。
- fallback / partial / blocked。
- MCP adapterがREST policyを迂回しないこと。

### Skill

- triggerすべき入力とtriggerしない入力。
- SKILL.md frontmatterと参照path。
- scriptsの正常系・失敗系・exit code。
- required時にruntime loadingされること。
- not-required時に不要なSkill/loaderが生成されないこと。

### Approval

- approved: operation、target、digest、approver、有効期限が一致する場合だけmutationする。
- denied: mutationせず、再要求またはHandoff条件へ遷移する。
- expired: 古い承認で実行せず、新しい承認artifactを要求する。
- changed: targetまたは変更内容のdigestが変わった場合は再承認する。
- retry上限を超えた場合はblockedとしてHandoffする。

## 11. Anthropic Skillsとの対応

| Anthropic型要素 | 本仕様 |
|---|---|
| `SKILL.md` | required判定時に必須 |
| YAML `name` / `description` | 必須 |
| Progressive disclosure | 詳細を必要時だけreferencesへ分離 |
| `scripts/` | deterministic / repetitive処理だけ |
| `references/` | 実行時参照する詳細だけ |
| `assets/` | 出力に直接使う非実行資産だけ |
| eval | trigger正負ケースと成果物検証 |

bundled resourcesは任意であり、全Skillへ一律生成しない。

## 12. 完了条件

- REST CRUD Matrixのrequired行が実在API契約へ対応する。
- C/U/Dのprimary実行経路がREST Function Toolだけである。
- MCP clientとRemote MCP adapterの責務が分離される。
- MCPがREST mutation policyを迂回しない。
- Skill required / not-required / TBDが根拠付きで決定される。
- requiredなSkillだけが実在resourceとruntime loading testを持つ。
- unused script、asset、hook、loader、設定flagがない。
