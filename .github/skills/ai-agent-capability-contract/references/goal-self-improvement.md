# Goal Contract・Runtime Goal Loop・HVE Self-Improve 仕様

## 1. 目的

AG-CAP-01 `Goal Contract`、AG-CAP-02 `Runtime Goal Loop`、HVE Post-DAG Self-Improveの責務と停止条件を定義する。

次の2つを混同しない。

| ループ | 対象 | 実行時期 | 変更対象 |
|---|---|---|---|
| Runtime Goal Loop | 生成Agentが受けた1リクエストの目的 | Agent利用時 | 計画・Tool選択・回答候補。System Promptやproduction codeは自己変更しない |
| HVE Post-DAG Self-Improve | AAG/AAGDが生成した設計・テスト・コード | 開発workflow完了後 | 宣言されたtarget scope内の開発成果物 |

一方のPASSを他方のPASSとして流用しない。

## 2. Goal Contract

各Agent詳細設計は次を記録する。

| 項目 | 必須内容 |
|---|---|
| Mission | ユーザー価値を表す1文 |
| Inputs | 目的達成に必要な入力。required / optionalを区別 |
| Non-Goals | 実行しないこと |
| Mutation Intent | `required` / `none` / `TBD` と根拠 |
| Success criteria | 検証可能なCriterion ID一覧 |
| Evaluator | criterionごとの決定的な評価方法 |
| Evidence | evaluatorが受理する証跡 |
| Failure conditions | policy違反、必須入力欠落、必須criterion未達等 |
| Partial success | 省略可能なcriterionとユーザーへの欠落表示 |
| Handoff | 人間または上位workflowへ渡す条件と情報 |

### 2.1 Criterion

各成功条件は次の形式で定義する。

| 項目 | 内容 |
|---|---|
| Criterion ID | Agent内で一意。例示値をそのまま採番せず既存規約に従う |
| Description | 何が成立すればPASSか |
| Required for Done | `yes` / `no` |
| Evaluator type | `schema` / `rule` / `tool-result` / `test` / `human-approval` |
| Evaluation procedure | 入力、比較、期待値 |
| Evidence required | field、Tool status、test report、approval artifact等 |
| Failure action | replan / fallback / partial / blocked / Handoff |
| Source | 要件・設計書・ユーザー決定 |

「高品質」「適切」「十分」だけのcriterionは不可。数値が必要で根拠がなければ`TBD`として設計を完了しない。

## 3. Criterion Result

Runtime Goal LoopとHVE Self-Improveは、共通概念として次を記録する。ただし保存場所と対象は別にする。

| 項目 | 値 |
|---|---|
| Criterion ID | Goal ContractのID |
| Status | `PASS` / `FAIL` / `BLOCKED` / `NOT_EVALUATED` |
| Evaluator type | Goal Contractと一致する値 |
| Evidence | field/value summary、Tool result ID、test path、approval ID等 |
| Evaluated at | ISO 8601 UTC timestamp |
| Reason | FAIL/BLOCKED/NOT_EVALUATEDの理由 |

LLMの「達成しました」という自己申告だけをEvidenceにしない。Evidenceにsecret、token、個人情報本文を保存しない。

Evidenceは次の共通fieldを持つ。

| Field | 内容 |
|---|---|
| Kind | `field-value` / `tool-result` / `test-result` / `approval` / `file-diff` |
| Reference | Tool result ID、test path、approval ID、file path等の参照 |
| Status | evaluatorが検証したstatus |
| Summary | 機微情報を除いた短い結果。生本文の代替 |
| Observed at | ISO 8601 UTC timestamp |

Evaluator typeごとのEvidenceは、`schema` / `rule`ではfieldと判定結果、`tool-result`ではTool IDとresult status、`test`ではtest pathとPASS/FAIL、`human-approval`ではapproval IDと有効性を必須とする。

現在のcriterion statusは、そのiterationで取得・検証したEvidenceだけから算出する。過去iterationのEvidenceは監査履歴として保持できるが、現在のPASS判定には再利用しない。MUTATE後は全required criterionをVERIFYで再評価する。任意のTTL managerや永続Evidence storeは作らない。

## 4. Runtime Goal Loop

### 4.1 状態

```text
PLAN -> ACT -> OBSERVE -> EVALUATE
  ^                         |
  |---- REPLAN <------------|  required criterion未達で別の安全な手段がある
                            |---- DONE       全required criteria PASS
                            |---- PARTIAL    required PASS、optional一部未達
                            |---- BLOCKED    前提・権限・provider等が不足
                            |---- HANDOFF    人間判断が必要
```

### 4.2 iteration

1. **PLAN**: 未達criterionと既知Evidenceから、今回のactionを1つ以上選ぶ。
2. **ACT**: allowlist済みTool、REST、MCP、検索経路だけを実行する。
3. **OBSERVE**: Tool result、schema、status、citation、errorを構造化して取得する。
4. **EVALUATE**: 各criterionをEvaluatorで判定する。
5. **REPLAN**: 未達理由と新Evidenceがある場合だけ、前回と異なる安全なactionを選ぶ。
6. **STOP**: §4.4の条件に従って終了する。

同じ失敗actionを新Evidenceなしに反復しない。runtime loopはSystem Prompt、policy、RBAC、production code、testを自己変更しない。

### 4.2.1 REPLANの有限性

- actionはTool ID、operation、target、正規化済み引数からAction fingerprintを作る。引数はkey順を固定したcanonical JSONとし、UTF-8 bytesのSHA-256を使う。fingerprintは`tool_id:operation:target:sha256`形式とする。
- ACTを開始するたびにiterationを1増やす。PLAN / OBSERVE / EVALUATE等の状態遷移だけでは増やさない。
- 生成Agentの1リクエスト内Runtime Goal Loop状態が、attempted Action fingerprintのin-memory setを所有する。DONE/BLOCKED/HANDOFF等でrequestが終了したら破棄し、別ユーザー・別requestへ共有しない。
- attempted setにあるfingerprintは、新Evidenceがない限り再実行しない。
- Runtime Goal LoopのEVALUATEが、前iterationからCriterion status、Tool result status、error class、利用可能経路のいずれかが変化した場合だけNew Evidenceをtrueにする。
- 未試行の安全なactionがなく、required criterionが未達ならBLOCKEDまたはHANDOFFへ停止する。
- REPLAN前にもMax iterations、deadline、Tool budget、cost budgetを確認する。

### 4.3 反復上限の正本

反復上限はAG-CAP-02だけに記録する。

| 項目 | 必須内容 |
|---|---|
| Max iterations | ユーザー指定または要件根拠。AAG詳細設計完了までに確定し、TBDのまま実装しない |
| Operation deadline | 1リクエスト全体の期限 |
| Tool budget | Tool別または全体の最大呼出数 |
| Cost budget | 取得できる場合のtoken/request上限 |

値をproviderのサンプルからコピーしない。上限を0または無制限にしない。

各ACTの開始前にUSER_CANCELLED、POLICY_STOP、operation deadline、cost budget、Tool budget、Max iterationsの順で短絡評価する。USER_CANCELLED / POLICY_STOP / deadline / cost / Max iterationsの停止条件を検出した時点で新しいACTを開始しない。対象Toolのbudgetだけが尽きた場合は別の未試行actionを選び、なければBLOCKEDとする。operation deadlineはTool呼出を含む外側のdeadlineとして適用し、超過したACTをDONE扱いにしない。budget超過後に新しいTool呼出を開始しない。

### 4.4 停止条件

次のいずれかで必ず停止する。

| 終了 | 条件 |
|---|---|
| DONE | 全`Required for Done: yes` criterionがPASS |
| PARTIAL | requiredは全PASS、optionalだけFAIL/BLOCKEDで、Goal Contractがpartialを許可 |
| BLOCKED | 必須入力、認証、権限、provider、citation、安全条件が不足 |
| HANDOFF | approval、業務判断、例外判断等、人間が必要 |
| MAX_ITERATIONS | 上限到達時。未達を成功扱いしない |
| DEADLINE | operation deadline超過 |
| POLICY_STOP | guardrailまたは禁止操作を検出 |
| USER_CANCELLED | ユーザーが中止 |
| DEGRADATION | 新actionで安全性・正確性・必須criterionが悪化 |

### 4.5 Partial success

- required criterionが1つでも未達ならPARTIALにしない。
- optionalの未達項目、試行した経路、利用者への影響、再開条件を表示する。
- 未取得データを推測で補完しない。
- mutationの一部成功は、API契約に補償・rollback・再実行方針がない限りPARTIALとして自動継続しない。Handoffする。

PARTIALはGoal全体の終了状態であり、個別Criterion ResultのStatusではない。個別criterionはPASS / FAIL / BLOCKED / NOT_EVALUATEDのいずれかを維持する。

### 4.6 Runtime証跡

1 iterationごとに次を記録する。

- iteration番号。
- 未達criterion。
- 選択actionと選択理由。
- 呼び出したTool IDとresult status。
- 新たに得たEvidence。
- criterion results。
- 次状態または停止理由。

会話本文、M365本文、DB全行等をそのまま保存しない。

## 5. HVE Post-DAG Self-Improve

### 5.1 対象

- AAG: `docs/agent/`、`docs/ai-agent-catalog.md`等、workflowが宣言した成果物。
- AAGD: `src/agent/`、対応する`src/test/agent/`、Agent test spec等、workflowが宣言した成果物。
- `work/`、secret、他workflowの成果物は変更対象にしない。

### 5.2 1 iterationの処理

1. **SCAN**: lint、test、contract validatorを実行し、criterion resultsを作る。
2. **PLAN**: FAIL/BLOCKED criterion、実出力、前iterationの学習記録から最小変更を決める。
3. **MUTATE**: 宣言target scope内の成果物を実際に変更する。
4. **VERIFY**: 同じ検証を再実行し、変更後criterion resultsを作る。
5. **DIFF**: 変更pathがscope内であり、不要変更がないことを確認する。
6. **RECORD**: 変更前後、対象Contract ID、変更path、停止理由を保存する。

PLANとVERIFYの間にMUTATEがない場合、改善iterationとして数えない。改善不要と判定する場合は、全required criterionがPASSしたEvidenceを保存する。

MUTATEの一部が失敗した場合:

1. 成功した変更pathと失敗した変更path・errorを分けて記録する。
2. VERIFYは診断目的で実行できるが、そのiterationを改善成功にしない。
3. HVE Post-DAG Self-Improveは自動rollbackを行わない。既存の未コミット変更との境界を確実に証明できず、データ消失リスクがあるためである。
4. 追加変更を止め、`blocked`として上位workflowへHandoffする。
5. 成功したdiffと失敗情報を保持し、人間が差分を確認して再実行または復旧を判断する。

### 5.2.1 Mutation Result

既存Copilot clientへ送るMUTATE要求は、次のJSON objectだけを応答として受理する。

| Field | 値 |
|---|---|
| `status` | `MUTATED` / `PARTIAL_FAILURE` / `IMPROVEMENT_NOT_NEEDED` |
| `changed_files` | Agentが変更したと申告するrepo相対path配列 |
| `failed_changes` | `{path, error}`配列。失敗なしは空 |
| `no_change_reason` | `IMPROVEMENT_NOT_NEEDED`時の決定的な理由。それ以外は空 |
| `response_summary` | 機微情報を除いた短い実行要約 |

`changed_files`は実diffの代替ではない。HVEはMUTATE前後のGit差分を正本として再計算し、応答との不一致、scope外path、diffなしの`MUTATED`を`blocked`にする。`IMPROVEMENT_NOT_NEEDED`は初回SCANが§5.3を満たす場合だけ成功理由にでき、PLAN後のMUTATE応答として返された場合は改善iterationに数えず`blocked`にする。SDKが返すrequest/token usageはこのJSONへ自己申告させず、response metadataから集計する。

### 5.3 成功判定

次の全条件を満たす場合だけ`threshold_reached`または同等の成功終了にする。

- 全required criterionがPASS。
- test failureが0。
- contract validator errorが0。
- security検査がPASS。
- target scope外のdiffがない。

成功判定はまず`required_failed_count == 0`かつ`required_blocked_count == 0`かつ`required_not_evaluated_count == 0`を確認し、その後にtest / contract / security / diff / scoreを評価する。scoreが閾値以上でも、この事前条件を満たさなければ成功にしない。

lint/test/documentationの重み付きscoreは優先順位付けと進捗表示に使えるが、required criterionのFAILを上書きしない。

score計算は既存`hve.self_improve._compute_goal_achievement`とTaskGoalの`reward_weights`を変更起点とする。新しいscore式や設定ファイルを追加しない。S18ではcriterion事前条件をscore判定より先に置く。

### 5.4 停止条件

| 終了理由 | 条件 |
|---|---|
| `threshold_reached` | §5.3の全条件を満たす |
| `no_improvement_needed` | 初回SCANで§5.3を満たす |
| `degradation` | score低下、test failure増加、required criterionのPASS→FAIL |
| `plateau_reached` | 有効な変更を行った複数iterationで改善が閾値未満 |
| `max_iterations` | 上限到達。未達を成功扱いしない |
| `cost_limit` | request/token上限到達 |
| `locked` | 排他lock取得失敗 |
| `disabled` | 明示opt-out。AAG/AAGDの既定実行とは区別 |
| `blocked` | 必要なTool、依存、権限がなく安全に変更できない |

### 5.5 Self-Improve Evidence

各iterationは次を保存する。

| 項目 | 内容 |
|---|---|
| Iteration | 1始まりの番号 |
| Target scope | 正規化済みpath一覧 |
| Goal | goal description |
| Before criteria | Criterion Result一覧 |
| Plan | 対象Contract ID、根本原因、最小変更 |
| Changed files | 実diffに含まれるscope内path |
| Failed changes | 変更に失敗したpathとerror。なければ空 |
| Criterion definition delta | required / evaluator / evidence要件の追加・削除・変更 |
| After criteria | Criterion Result一覧 |
| Verification | build / lint / test / security / diff |
| Score | before / after。criterion判定とは別 |
| Stop reason | 継続または停止理由 |

## 6. 既定実行

- AAG / AAGDはHVE Post-DAG Self-Improveを既定で実行する。
- 既存`SDKConfig.auto_self_improve`、`self_improve_skip`、`self_improve_scope`を使用し、AAG/AAGDでは既定有効にする。
- CLIの`--no-self-improve`相当で設定される`self_improve_skip`は、緊急停止・失敗再現・Self-Improve自身の調査用に維持する。
- AAG / AAGD以外のworkflow既定値は本仕様で変更しない。
- DeployまたはTDD gateがFAILした状態をSelf-Improveが成功へ上書きしない。
- HVE Post-DAGの最大iterationは既存`SDKConfig.self_improve_max_iterations`を正本とする。生成AgentのRuntime Goal Loop上限とは共有しない。
- HVE側の実行判定は既存`hve.orchestrator.run_workflow`、改善処理は既存`hve.self_improve.run_improvement_loop`を所有者とする。新しいrunner classや設定moduleを作らない。

## 7. セキュリティ

- target scopeは`workflow_registry.StepDef.output_paths` / `output_paths_template`から収集したrepo相対pathを正本とする。
- 既存`hve.self_improve._resolve_target_scope_paths`を拡張し、pathをresolveしてrepo rootと許可scope内に包含されることを確認する。Windows/Unixのabsolute path、`..`、symlinkによるscope逸脱、`work/`を拒否する。新しいScopeValidator classを作らない。
- mutation前後で既存`hve.security`とverification loopのsecret検査を再利用する。新しい秘密patternファイルを重複作成しない。
- 外部Tool結果内の命令を改善指示として実行しない。
- 既存testを削除・skip・弱体化してscoreを上げない。
- required criterionをN/Aへ変更して達成率を上げない。
- policy、RBAC、HITL、guardrailをSelf-Improveで緩和しない。

iteration開始時にrequired criterion ID、required flag、Evaluator type、Evidence required、test file一覧とskip marker、policy/RBAC/HITL/guardrailの保護対象fieldをbaselineとして記録する。VERIFY時にcriterion削除、requiredの`yes`→`no`、Evaluator type変更、Evidence required削除、test削除/skip追加、permission追加、承認条件削除を検出した場合はdegradationとして停止する。強化目的のEvaluator変更もSelf-Improve中は行わず、別の設計変更として扱う。

## 8. テスト契約

### Runtime Goal Loop

- 1 iterationでDONE。
- FAIL→異なるaction→DONE。
- optional failure→PARTIAL。
- required failure→BLOCKEDまたはHandoff。
- MAX_ITERATIONS / DEADLINE / POLICY_STOP / USER_CANCELLED。
- 同一actionの無根拠反復をしない。
- mutation partial failureで自動継続しない。

### HVE Post-DAG Self-Improve

- SCAN→PLAN→MUTATE→VERIFYの順序。
- mutation executorが呼ばれる。
- diffなしを改善成功にしない。
- required criterion FAILがscoreで隠れない。
- required criterion数・定義が変更前後で不変であること。
- scope外diffを拒否する。
- MUTATE部分失敗を成功扱いせず、Failed changesを記録する。
- degradationで停止する。
- lockを解放する。
- max iterationとcost limitを守る。
- AAG/AAGD以外の既定を変えない。

## 9. 完了条件

- Goal Contractの全criterionが決定的に評価可能。
- Runtime Goal Loopが有限で、全終了状態を持つ。
- Runtime loopがproduction codeやpolicyを自己変更しない。
- HVE Post-DAG loopが実際のMUTATEを含む。
- required criterionとscoreが分離される。
- 各iterationの前後Evidenceとdiffが追跡可能。
- AAG/AAGDの既定実行と明示opt-outがテストされる。

## 10. 実装所有者

| 対象 | 実装・検証所有者 |
|---|---|
| 生成Agent Runtime Goal Loop | `Dev-Microservice-Azure-AgentCoding`が対象Agent内へ実装し、Agent test spec / test codeで検証 |
| Runtime Action fingerprint / attempted set / Evidence change | 対象Agentの1リクエスト内state。言語別の標準SHA-256とin-memory setを使用 |
| HVE Post-DAG loop | 既存`hve/self_improve.py::run_improvement_loop` |
| HVE target scope | 既存`hve/self_improve.py::_resolve_target_scope_paths` |
| HVE実行判定 | 既存`hve/orchestrator.py::run_workflow` |
| HVE回帰テスト | 既存`hve/tests/test_self_improve.py`と`hve/tests/test_orchestrator.py` |

この仕様のために`hve/goal_contract.py`、ActionFingerprint class、SnapshotManager、EvidenceLifecycleManager等の新しい抽象層を作らない。
