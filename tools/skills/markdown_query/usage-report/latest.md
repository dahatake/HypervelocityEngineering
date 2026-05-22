# markdown-query Skill 利用統計レポート

対象指標: v1 採用 15 指標 + v1.1 追加 D3 / G4 = 計 17 指標。
各指標の定義・解釈は [users-guide/skills-markdown-query.md](../../../../users-guide/skills-markdown-query.md) を参照。

| 項目 | データ |
|:---|---:|
| 生成時刻 | 2026-05-22T12:32:22 |
| 集計ウィンドウ | 直近 7 日 |
| 集計開始時刻 (UTC) | 2026-05-15T03:32:21+00:00 |
| レコード数 | 48 |
| Tokenize 言語 (表示中の DB) | ja-jp |
| Chunking Strategy (表示中の DB) | heading_recursive |
| 集計スコープ | 全 (lang, strategy) 横断 |

> 各指標の定義・解釈は [users-guide/skills-markdown-query.md](../../../users-guide/skills-markdown-query.md) を参照。

**① 基盤・索引**

| 項目 | データ |
|:---|---:|
| E1 索引サイズ - ファイル数 | 496 |
| E1 索引サイズ - チャンク数 | 6676 |
| E2 索引鮮度 - 経過秒 | 0 |
| E2 索引鮮度 - DB mtime | 2026-05-22T12:32:21 |
| E5 孤児チャンク削除累計 (件) | 279 |
| E5 集計対象 index 実行回数 | 4 |
| F2 索引差分更新比率 | 0.5588 |
| F2 サンプルサイズ | 4 |

**② 呼び出し量・選択妥当性**

| 項目 | データ |
|:---|---:|
| A1 サブコマンド別呼び出し回数 | index=4, search=41, stats=3 |
| A2 Step あたり呼び出し回数 (全 Workflow) | 4.56 |
| A2 総呼び出し回数 | 41 |
| A2 distinct Step 数 | 9 |
| A4 Skill _routing 記載 | はい |
| D1 DO NOT USE FOR 違反 (件) | 0 |
| D3 典型クエリ出現率 (合算) | 0 |
| D3 合算マッチ件数 | 0 |
| D3 合算 search 総件数 (patterns 定義済み workflow のみ) | 20 |
| D3 aad-web 出現率 | 0 |
| D3 aad-web マッチ件数 | 0 |
| D3 aad-web search 総件数 | 20 |
| D3 aad-web パターン別マッチ数 | 画面定義=0, サービス定義=0, TDD テスト仕様=0, APP-ID=0, サービスカタログ=0, データモデル=0 |
| D3 asdw-web 出現率 | （データ不足） |
| D3 adfd 出現率 | （データ不足） |
| D3 adfdv 出現率 | （データ不足） |

- D3 asdw-web 注記: template/typical-queries.json に asdw-web エントリ未定義
- D3 adfd 注記: template/typical-queries.json に adfd エントリ未定義
- D3 adfdv 注記: template/typical-queries.json に adfdv エントリ未定義
- D3 パターン別カウントの読み方: 各パターンの count は独立集計のため、合計が matched_count と一致するとは限らない（1 search が 複数パターンにマッチする場合あり）。
**③ Context 削減**

| 項目 | データ |
|:---|---:|
| B1 Context 削減率 | 0.9881 |
| B1 snippet 文字数合計 | 52082 |
| B1 参照元ファイル文字数合計 | 4361291 |
| B2 top_k 平均 | 5.51 |
| B2 max_tokens 平均 | 968.29 |
| B2 snippet_radius 平均 | 2 |
| B2 サンプルサイズ | 41 |
| B3 get/search 比率 | 0 |
| B3 get 回数 | 0 |
| B3 search 回数 | 41 |

**④ 結果品質**

| 項目 | データ |
|:---|---:|
| C1 ヒット 0 件率 | 0 |
| C1 zero-hit 回数 | 0 |
| C1 search 回数 | 41 |
| C2 上位 2 件 score 差 (平均) | 1.6021 |
| C2 サンプルサイズ | 41 |
| C3 expansion フラグ使用率 | 0 |
| C3 expansion 回数 | 0 |
| C3 search 回数 | 41 |

**⑤ パフォーマンス / 成果**

| 項目 | データ |
|:---|---:|
| F1 search 実行時間 p50 (ms) | 219 |
| F1 search 実行時間 p95 (ms) | 875 |
| F1 サンプルサイズ | 41 |
| G1 mdq 利用 Step 完了率差 | -0.2499 |
| G1 利用 run 平均 | 0.3845 |
| G1 未利用 run 平均 | 0.6344 |
| G1 利用 run 数 | 7 |
| G1 未利用 run 数 | 40 |
| G1 mdq 利用 run_id 数 | 16 |
| G4 Step 再実行回数差 (平均/Step) | 0 |
| G4 利用 run 平均 | 0 |
| G4 未利用 run 平均 | 0 |
| G4 利用 run 数 | 7 |
| G4 未利用 run 数 | 78 |

