# markdown-query Skill 利用統計レポート

このディレクトリには、Markdown-Query Skill の利用統計レポートが日次で生成・保存される。

## ファイル構成

- `YYYY-MM-DD.json` / `YYYY-MM-DD.md` — 当日生成されたレポート（機械可読 / 人間可読）
- `latest.json` / `latest.md` — 最新生成レポートのコピー（GUI が参照）

## 生成方法

### 自動生成

HVE GUI を起動すると、設定画面の `skills > Markdown-Query` が初期化される際に、
`latest.md` の mtime が 24 時間以上前 / 未生成であれば自動的に再生成される。

### 手動生成

```powershell
python tools/skills/markdown_query/generate_usage_report.py [--window-days 7] [--retention-days 90]
```

GUI からも「利用統計レポートの再生成」ボタンで同等の処理を実行できる。

## 保持ポリシー

- 日付付きレポート (`YYYY-MM-DD.{json,md}`) は既定 90 日保持。`--retention-days <N>` で変更可能。
- `--retention-days 0` を指定すると自動削除を無効化する（手動運用）。
- `latest.json` / `latest.md` は保持期間に関わらず常に保持される。
- 関係しないファイル（`README.md`、手動メモ等）は削除対象外。
- 古いレポートを保持したい場合は他ディレクトリへ退避、または Git にコミットして保存すること（本ディレクトリは .gitignore 対象外）。

## レポートに含まれる指標

15 指標を 5 グループに分類して集計する。各指標の定義・解釈ガイドは
[users-guide/skills-markdown-query.md](../../../../users-guide/skills-markdown-query.md) を参照。

| グループ | 指標 |
|---|---|
| ① 基盤・索引 | E1 索引サイズ / E2 索引鮮度 / E5 孤児チャンク削除累計 / F2 索引差分更新比率 |
| ② 呼び出し量・選択妥当性 | A1 サブコマンド別呼び出し回数 / A2 Step あたり呼び出し回数 / A4 Skill _routing 記載 / D1 DO NOT USE FOR 違反 / **D3 典型クエリ出現率 (全 workflow 横断)** (v1.1, v1.2 で BREAKING) |
| ③ Context 削減 | B1 Context 削減率 / B2 引数平均 / B3 get/search 比率 |
| ④ 結果品質 | C1 ヒット 0 件率 / C2 上位 2 件 score 差平均 / C3 expansion フラグ使用率 |
| ⑤ パフォーマンス / 成果 | F1 search 実行時間 (p50/p95) / G1 mdq 利用 Step 完了率差 / **G4 Step 再実行回数差** (v1.1) |

## データソース

- `.mdq/usage.jsonl` — mdq CLI が呼び出されるたびに自動追記する利用ログ
  （`mdq.usage_log` モジュール）
- `.mdq/index.sqlite` — Markdown 索引 DB（`hve.gui.mdq_index_service.get_index_stats` 経由）

両ファイルとも `.gitignore` 対象でローカル限定。Skill 自体と同様に **クラウド送信なし**。

## レポート JSON スキーマ

`schema_version: 1` 時点では以下フィールドを含む（詳細は実装 [mdq/usage_stats.py](../../../../mdq/usage_stats.py) を参照）:

```
{
  "schema_version": 1,
  "window_days": 7,
  "since_iso": "...",
  "record_count": <int>,
  "generated_at": "...",
  "E1_index_size": {...},
  "E2_index_freshness": {...},
  "E5_pruned_chunks_total": {...},
  "F2_index_delta_update_ratio": {...},
  "A1_command_counts": {...},
  "A2_calls_per_step": {...},
  "A4_skill_routing_listed": {...},
  "D1_donot_use_for_violations": <int>,
  "B1_context_reduction_ratio": {...},
  "B2_arg_averages": {...},
  "B3_get_search_ratio": {...},
  "C1_zero_hit_rate": {...},
  "C2_score_gap_avg": {...},
  "C3_expansion_flag_usage_rate": {...},
  "F1_search_elapsed_ms": {...},
  "G1_step_completion_rate_diff": {...},
  "G4_step_retry_count_diff": {...},
  "D3_typical_query_rate": {
    "value": <float|null>,
    "matched_count": <int>,
    "total_search": <int>,
    "per_workflow": {
      "aad-web":  {"value": ..., "matched_count": ..., "total_search": ..., "per_pattern": [...], "note": ...},
      "asdw-web": {...},
      "adfd":      {...},
      "adfdv":     {...}
    },
    "note": <str|null>
  }
}
```

値が算出不能な指標は `value: null` + `note: "..."` の形で理由を明示する（捏造値を入れない）。

## 古いレポートの取り扱い

日次レポートはディスクに残るため、過去日の推移を `<date>.json` で参照できる。
ストレージ節約が必要な場合は手動で古いファイルを削除してよい（`latest.*` は保持すること）。
