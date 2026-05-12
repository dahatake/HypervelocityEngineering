# ADR-0002: hve サブタスク Fan-out アーキテクチャ

<!-- task_scope=multi context_size=large phase=0 priority=high date=2026-05-11 -->

| 項目 | 内容 |
|---|---|
| **ステータス** | Accepted |
| **日付** | 2026-05-11 |
| **対象** | `hve/` パッケージ全般（11 ワークフロー: ARD/AAS/AAD-WEB/ASDW-WEB/ABD/ABDV/AAG/AAGD/AKM/AQOD/ADOC） |
| **関連** | `hve/workflow_registry.py`, `hve/dag_planner.py`, `hve/dag_executor.py`, `hve/runner.py`, `hve/console.py`, `hve/run_state.py` |

---

## 1. 背景と課題

`hve` は GitHub Copilot SDK (`copilot.CopilotClient`) をローカル実行するオーケストレーターで、`asyncio.Semaphore` ベースの並列実行基盤（既定 `max_parallel=15`）を持つ ([dag_executor.py](../../hve/dag_executor.py))。

### 既存実装の制約（事実ベース）

- **AKM ワークフロー** は `D01〜D21` の knowledge ドキュメント生成を **単一 StepDef (`id="1"`) ・単一 Copilot セッション** で実施する設計だった ([workflow_registry.py](../../hve/workflow_registry.py))。
- **AAD-WEB / ASDW-WEB / ABD / ABDV / AAG / AAGD** の各 per-screen / per-service / per-job / per-agent ステップも、1 ステップ内で複数成果物を直列生成する設計だった。
- `DAGExecutor` は `depends_on=[]` の N ステップを 1 Wave で `asyncio.create_task` 一斉起動できる ([dag_executor.py](../../hve/dag_executor.py))。基盤は揃っているが、ステップ定義側が単一に閉じているため真の並列度が低かった。

### 解決したい要件

1. **タスク粒度の最小化**: 1 成果物 = 1 サブタスクに分割し、Context Window を最小化。
2. **並列度の最大化**: AKM で D01〜D21 を 21 並列、他 WF も per-element 並列。
3. **サブタスク起動の全レベル可視化**: stderr に必ず可観測な信号を出す。
4. **Copilot SDK 活用の深化**: Streaming / Resume / Custom Agent 切替 / MCP 切替。

---

## 2. 決定サマリ表

| 不明点 | 採用 | 概要 |
|---|---|---|
| A | A-3 | `StepDef.fanout` 指定 → `dag_executor` が展開 |
| B | B-3 | 本体 N 並列 + 横断レビュー 1 join |
| C | C-2 | `WorkflowDef.max_parallel` でワークフロー単位上書き |
| D | D-3 | stderr に JSON 1 行で機械可読出力 |
| E-1 | 採用 | Streaming API でトークン到達を可観測化（基盤のみ実装、SDK 接続は保留） |
| E-2 | 採用 | サブステップでも決定論的 session_id で Resume 保証 |
| E-3 | 採用 | Dxx 毎の追加プロンプト注入で専用エージェント化（I-3 経由） |
| E-4 | 採用 | StepDef レベルで `mcp_servers` 上書き |
| F | F-3 | 静的 keys（F-1）と動的 parser（F-2）の両対応 |
| G | G-1 | `hve/catalog_parsers.py` を新設して 5 パーサ集約 |
| H | H-1 | ADOC は単段（カテゴリ） fan-out まで |
| I | I-3 | 新規 agent ファイルなし、`additional_prompt_template` 注入で代替 |
| J | J-1 | 新規 StepDef を join として追加（横断レビュー） |
| K | K-1 | 動的展開 0 件は自動 skip（`reason="fanout-empty"`） |
| L | L-3 | stderr JSON 詳細スキーマ（fanout_key / session_id 含む） |
| M | M-3 | per-key プロンプトは `hve/prompt/fanout/{wf}/_common.md` 外部化 |
| N | N-1 | サブ 1 件失敗で親 fan-out 元を fail |
| O | O-1 | ARD は対象外 |
| P | P-1 | 横断レビューは AKM / AQOD のみ追加 |
| Q | Q-1 | T3C の SDK イベント仕様はローカルインストール済パッケージから抽出 |
| R | R-1 | T4 系テストは各 WF ごとに分離 |

---

## 3. 設計の核

### 3.1 StepDef 拡張（後方互換）

```python
@dataclass
class StepDef:
    # ... 既存フィールド ...
    fanout_static_keys: Optional[List[str]] = None
    """静的に既知の fan-out キー（例: AKM の ["D01", ..., "D21"]）"""

    fanout_parser: Optional[str] = None
    """動的解決パーサ名。catalog_parsers の登録済みキー
       ("app_catalog" / "screen_catalog" / "service_catalog"
        / "batch_job_catalog" / "agent_catalog")"""

    additional_prompt_template_path: Optional[str] = None
    """fan-out キー別追加プロンプトのテンプレート絶対/相対パス。
       `hve/prompt/fanout/{wf}/_common.md` 規約推奨（M-3）。
       `{key}` をパス置換、`{{key}}` を本文置換に使用する。"""

    per_key_mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None
    """fan-out キーごとの MCP 上書き定義（E-4）"""
```

### 3.2 動的 fan-out のタイミング (F-3)

- **F-1 (静的展開)**: `dag_planner.compute_waves()` が `fanout_static_keys` または既存ファイル走査で事前展開。
- **F-2 (動的展開)**: `dag_executor` が Wave 起動直前に `fanout_parser` を呼び、上流 step 出力を解析して N ステップを生成。

### 3.3 展開後 step_id 命名 (E-2)

- `{base_id}/{fanout_key}` 形式（例: `1/D01`, `2/APP-01`, `2.2/SVC-billing`）。
- `run_state.make_session_id(run_id, step_id, suffix)` は内部で `/` を `-` に変換するため決定論的 session_id を生成可能。Resume 時に同一キーへ resume できる。

### 3.4 0 件展開のセマンティクス (K-1)

```python
if not expanded_keys:
    self._results[step.id] = StepResult(
        step.id, success=True, skipped=True,
        state="skipped", reason="fanout-empty",
    )
```

### 3.5 横断レビュー join (J-1, P-1)

AKM / AQOD のみ、fan-out 元 StepDef の直下に `depends_on=[<fan-out元のid>]` の review StepDef を新設する。他 WF は既存 `auto_contents_review` (Phase 3 敵対的レビュー) に委譲し追加しない。

例（AKM）:
```python
StepDef(id="1", title="knowledge/ ドキュメント生成", custom_agent="KnowledgeManager",
        fanout_static_keys=[f"D{n:02d}" for n in range(1, 22)],
        additional_prompt_template_path="hve/prompt/fanout/akm/_common.md"),
StepDef(id="2", title="knowledge/ 横断整合性レビュー",
        custom_agent="QA-DocConsistency",
        depends_on=["1"], consumed_artifacts=["knowledge"],
        body_template_path="templates/akm/step-2.md"),
```

### 3.6 stderr JSON スキーマ (D-3 + L-3)

```json
{
  "event": "step_start",
  "step_id": "1/D01",
  "title": "knowledge/D01 生成",
  "agent": "KnowledgeManager",
  "ts": "2026-05-11T12:34:56.789Z",
  "run_id": "hve-20260511-abc",
  "parent_step_id": "1",
  "wave_num": 1,
  "total_waves": 6,
  "fanout_key": "D01",
  "session_id": "hve-20260511-abc-1-D01"
}
```

- 出力先: **stderr 固定**（stdout は人間可読を維持）。
- verbosity / quiet の影響を**受けない**専用パス `Console._emit_structured()` を新設。

### 3.7 Streaming（E-1）

- 既存 `session.send_and_wait(prompt, timeout=...)` を継続利用しつつ、`session.on(handler)` イベント購読でトークン断片を `console.token_chunk(step_id, ...)` に転送する設計。
- 現時点では `console.token_chunk()` の基盤実装のみ完了。SDK 側との接続（`_handle_session_event` のイベント名特定）は保留。

### 3.8 fan-out 失敗伝搬 (N-1)

`DAGExecutor._run_with_semaphore` で fan-out 後 1 件でも failed → 後続 DAG は起動しない（既存セマンティクス維持）。

---

## 4. 影響範囲（ファイル別）

| ファイル | 変更内容 |
|---|---|
| `hve/workflow_registry.py` | `StepDef` フィールド 4 追加、`WorkflowDef.max_parallel`、AKM/AAS/AAD-WEB/ASDW-WEB/ABD/ABDV/AAG/AAGD/AQOD に fan-out 設定 |
| `hve/catalog_parsers.py` | **新規** — 5 パーサ集約 |
| `hve/fanout_expander.py` | **新規** — WorkflowDef を展開する non-mutating ヘルパー |
| `hve/dag_executor.py` | fan-out 展開呼び出し、N-1 失敗伝搬、K-1 空展開 skip |
| `hve/runner.py` | per-key MCP / prompt 注入 |
| `hve/console.py` | `_emit_structured()`、`token_chunk()`、`set_run_id()` |
| `hve/orchestrator.py` | `DAGExecutor` に `repo_root` 伝搬、`Console.set_run_id()` 呼び出し |
| `hve/prompt/fanout/{wf}/_common.md` | **新規** — per-key プロンプトテンプレ (akm, aas, aad-web, asdw-web, abd, abdv, aag, aagd, aqod) |
| `.github/scripts/templates/akm/step-2.md` | **新規** — AKM 横断レビュー本文テンプレ |
| `.github/scripts/templates/aqod/step-2.md` | **新規** — AQOD 横断レビュー本文テンプレ |

---

## 5. 後方互換性

- `StepDef` の新規フィールドは全て `Optional[...] = None`。既存 StepDef 定義は無変更で動作。
- `WorkflowDef.max_parallel` も `Optional[int] = None`、未指定時は既存 default `15`。
- fan-out 未設定 StepDef は従来通り 1 ステップ・1 セッションで実行（既存テスト互換）。
- Streaming API はオプトイン。Copilot SDK が `session.on()` をサポートしない場合は従来 `send_and_wait` のみで動作。

---

## 6. 検証戦略

1. **単体**: `hve/tests/test_fanout.py`, `hve/tests/test_e2e_akm_fanout_dryrun.py`（実装済）
2. **結合**: AKM 21 並列の DRY-RUN E2E（実装済、2 件 PASS）
3. **整合**: 全 11 WorkflowDef の fan-out 設定が `catalog_parsers` の登録キーと整合（`test_fanout.py::test_all_workflows_fanout_parsers_are_known`）
4. **後方互換**: 既存 `hve/tests/` 全 2249 件 PASS を維持

---

## 7. リスクと緩和

| リスク | 緩和策 |
|---|---|
| Copilot CLI の同時セッション数上限超過 | `WorkflowDef.max_parallel` で WF 単位制御。AKM/AQOD は 21 を明示。 |
| Streaming API の SDK 非互換 | 検出時は従来 `send_and_wait` にフォールバック |
| per-key プロンプトの分散による保守性低下 | `hve/prompt/fanout/{wf}/_common.md` ディレクトリ規約で集約 |
| 動的展開時の上流出力 schema 変更 | パーサ単体テストで検証、版数 mismatch 時は明示エラー |

---

## 8. 範囲外

- ARD ワークフロー（O-1）
- ADOC の二段 fan-out（H-1）
- per-key MCP の secrets を Key Vault / .env 経由で動的解決すること
- 既存 `auto_contents_review=True` (Phase 3 敵対的レビュー) のロジック変更
- T3C: Streaming API の SDK 接続実装（基盤のみ完了）
- T3D: fan-out resume の E2E 検証（既存 `make_session_id` で動作可能だが未検証）
