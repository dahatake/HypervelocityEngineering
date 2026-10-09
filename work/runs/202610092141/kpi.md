## KPI（run 202610092141）

| 指標 | 値 | 目標 | 判定 | 根拠・内訳 |
|---|---|---|---|---|
| North Star: 人の介入 1 回あたりの検証済み要求 | 0.00 | 前回より増やす | - | 検証済み要求 0 ÷ 人の介入 3 |
| 人の介入 | 3 | 1（回答があれば 2） | 未達 | request 1、resume 2 |
| 検証済み要求 / 実装した要求 | 0/1 | 全件 | 未達 | FR-1001: System Test が pass でない AC: AC-037 |
| 1 回目のゲート通過率 | 100%（1/1） | 70% 以上 | 達成 | attempts が 1 以下で done になった項目 |
| system AC の pass 率 | 0%（0/15） | 100% | 未達 | 承認済み・BLOCKED でない system AC |
| トレーサビリティ網羅率 | 100%（20/20） | 100% | 達成 | 承認済み要求のうち、カタログ行があり system AC がすべて台帳にあるもの |
| 要求 1 件あたりの経過時間 | 1.29h | Phase 1 の計測値より短く | - | 経過 1.29h ÷ 実装 1 件 |
| 項目の完了 / BLOCKED | 1/9（BLOCKED 8） | BLOCKED 0 | 未達 | queue.json |
| 未回答の質問票 | 9 | - | - | 次の Prompt の <answers> で回答する |
| 工程ごとの時間 | 要求定義 51.1 分、独立監査 35.8 分、計画 31.6 分、System Test の設計 30.9 分、実装ループ 17.0 分、最終 24.0 分 | - | - | meta.json の stage_times |
| 実効の並列度（実装ループ） | 3.42 | parallel_workers（2）の 70% 以上 | 達成 | 項目の作業時間の合計 ÷ 実装ループの経過時間 |
| 項目 1 件あたりの作業時間 | 14.6 分 | - | - | queue.json の work_sec（doing の間の時間） |
| 統合の直列時間 | - | ループの 20% 以下 | - | integrate.py merge の所要時間の合計 |
| 実際に使ったモデル | conductor: (既定)×3; implementer: (既定)×4; rd-auditor: (既定)×14; rd-author: (既定)×11; reviewer: (既定)×2; test-designer: (既定)×4 | ebak.config.json の models と一致 | - | models.jsonl（G-7） |
