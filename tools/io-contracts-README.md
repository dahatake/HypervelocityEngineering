# io-contracts 移行スクリプト群

`hve` オーケストレーターの io-contract を per-Agent 形式から per-Step 形式に再設計した際の移行用ワンショットスクリプト。再実行可能（冪等）。

| スクリプト | 用途 | 実行タイミング |
|---|---|---|
| `split_io_contracts.py` | per-Agent YAML を per-Step YAML に分割 | 旧 `<Agent>.yaml` から `<Agent>--<workflow>--<stepId>.yaml` へ移行する初回のみ |
| `normalize_producers.py` | producer 参照を per-Step ファイル名形式に正規化 | split 直後 |
| `enrich_upstream_inputs.py` | StepDef.depends_on の上流 Step 出力を input として補完 | normalize 後 |
| `remove_work_outputs.py` | `{WORK}*` outputs を全 per-Step YAML から除去 | normalize 後 |

## 標準的な実行順序（初回移行時）

```powershell
.venv\Scripts\python.exe tools\split_io_contracts.py
.venv\Scripts\python.exe tools\normalize_producers.py
.venv\Scripts\python.exe tools\enrich_upstream_inputs.py
.venv\Scripts\python.exe tools\remove_work_outputs.py
.venv\Scripts\python.exe .github\scripts\validate-io-contract.py
```

## 注意

- これらのスクリプトは `hve.workflow_registry._REGISTRY` を参照する。`_REGISTRY` の構造変更時はスクリプト側も更新が必要。
- 旧 `<Agent>.yaml` は `split_io_contracts.py` 実行後に手動削除する想定（スクリプト自体は削除しない）。
- 詳細経緯は [CHANGELOG.md](../CHANGELOG.md) の `[Unreleased]` セクション、および [work/pipeline-io-consistency-check-v3.md](../work/pipeline-io-consistency-check-v3.md) を参照。
