# TDD リトライメトリクス ダッシュボード

> 生成日時: 2026-05-14 02:59:59 UTC  
> 集計期間: 過去 30 日  
> リポジトリ: dahatake/HypervelocityEngineering

## ワークフロー別サマリー

| ワークフロー | :blocked (open) | :blocked (総計) | :human-required (open) | :human-required (総計) | :human-resolved (総計) | エスカレーション率 |
|---|---:|---:|---:|---:|---:|---:|
| `aas` | 0 | 0 | 0 | 0 | 0 | — |
| `aad` | 0 | 0 | 0 | 0 | 0 | — |
| `aad-web` | 0 | 0 | 0 | 0 | 0 | — |
| `asdw` | 0 | 0 | 0 | 0 | 0 | — |
| `asdw-web` | 0 | 0 | 0 | 0 | 0 | — |
| `abd` | 0 | 0 | 0 | 0 | 0 | — |
| `abdv` | 0 | 0 | 0 | 0 | 0 | — |
| `aag` | 0 | 0 | 0 | 0 | 0 | — |
| `aagd` | 0 | 0 | 0 | 0 | 0 | — |
| `akm` | 0 | 0 | 0 | 0 | 0 | — |
| `aqod` | 0 | 0 | 0 | 0 | 0 | — |
| `adoc` | 0 | 0 | 0 | 0 | 0 | — |
| **合計** | **0** | **0** | **0** | **0** | **0** | **—** |

## 凡例

| ラベル | 説明 |
|---|---|
| `:blocked` | TDD リトライ上限（`tdd_max_retries`、既定 5）または Deploy TDD（最大 3 回）超過 |
| `:human-required` | `:blocked` 付与から SLA（既定 24h）経過後に自動昇格 |
| `:human-resolved` | 人間が解決済みと判断。付与すると `:ready` へ自動復帰 |

## 参考リンク

- SLA・介入基準: [`docs/hitl/escalation-sla.md`](../../docs/hitl/escalation-sla.md)
- エスカレーションワークフロー: [`.github/workflows/auto-blocked-to-human-required.yml`](../../.github/workflows/auto-blocked-to-human-required.yml)
- 復帰ワークフロー: [`.github/workflows/auto-human-resolved-to-ready.yml`](../../.github/workflows/auto-human-resolved-to-ready.yml)

---

*このファイルは `tdd-retry-metrics.yml` ワークフローにより自動生成されます。手動編集しないでください。*
