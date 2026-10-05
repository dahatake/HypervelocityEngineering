# Goal Contract・Runtime Goal Loop 仕様

## 1. 目的

AG-CAP-01 `Goal Contract`、AG-CAP-02 `Runtime Goal Loop`の責務と停止条件を定義する。

Runtime Goal Loopは、生成Agentが受けた1リクエストの目的を対象に、Agent利用時に計画・Tool選択・回答候補だけを変更する。System Promptやproduction codeは自己変更しない。

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

Runtime Goal Loopは、次を記録する。

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

## 5. テスト契約

### Runtime Goal Loop

- 1 iterationでDONE。
- FAIL→異なるaction→DONE。
- optional failure→PARTIAL。
- required failure→BLOCKEDまたはHandoff。
- MAX_ITERATIONS / DEADLINE / POLICY_STOP / USER_CANCELLED。
- 同一actionの無根拠反復をしない。
- mutation partial failureで自動継続しない。

## 6. 完了条件

- Goal Contractの全criterionが決定的に評価可能。
- Runtime Goal Loopが有限で、全終了状態を持つ。
- Runtime loopがproduction codeやpolicyを自己変更しない。
- 各iterationの前後Evidenceとdiffが追跡可能。

## 7. 実装所有者

| 対象 | 実装・検証所有者 |
|---|---|
| 生成Agent Runtime Goal Loop | `Dev-Microservice-Azure-AgentCoding`が対象Agent内へ実装し、Agent test spec / test codeで検証 |
| Runtime Action fingerprint / attempted set / Evidence change | 対象Agentの1リクエスト内state。言語別の標準SHA-256とin-memory setを使用 |

この仕様のために`hve/goal_contract.py`、ActionFingerprint class、SnapshotManager、EvidenceLifecycleManager等の新しい抽象層を作らない。
