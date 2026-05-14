# markdown-query CLI リファレンス

すべてローカル実行。`python -m hve.mdq <subcommand>` 形式。

## 共通オプション
- `--db PATH`: SQLite 索引ファイル。既定 `.hve/mdq.sqlite`。

## index — 索引作成 / 更新

```
python -m hve.mdq index [--root PATH ...] [--rebuild] [--no-prune] [--max-chunk-chars N]
```

- `--root`: 索引対象ルート（繰り返し指定可）。既定 `docs/`, `docs-generated/`, `users-guide/`, `template/`, `knowledge/`, `qa/`, `original-docs/`, `work/`, `sample/`, `session-state/`, `hve-dev/`（存在しないフォルダは自動スキップ）。
- `--rebuild`: SHA-1 が同一でも強制再索引。
- `--no-prune`: 索引ストアに残っているがディスク上に存在しないファイルを削除しない。
- `--max-chunk-chars N`: `N>0` の場合、見出し単位チャンクのうち本文長が `N` 文字を超えるものを段落 / 行境界で 2 次分割する（コードフェンスは不可分）。既定 `0`（無効）。

出力（JSON）: `{"files_indexed": N, "files_skipped": M, "chunks_written": K, "roots": [...]}`

## search — 検索

```
python -m hve.mdq search --q "..." [options]
```

| オプション | 既定 | 説明 |
|---|---|---|
| `--mode` | `bm25` | `bm25` または `grep`（正規表現エスケープした完全一致） |
| `--top-k` | `5` | 返却ヒット件数上限 |
| `--max-tokens` | `800` | 全 snippet 合計の概算トークン上限（超過時打ち切り） |
| `--paths` | なし | `fnmatch` 形式の path glob を複数指定可（例: `docs/*` `users-guide/**`） |
| `--tags` | なし | frontmatter `tags` で AND 絞り込み |
| `--snippet-radius` | `2` | マッチ行の前後何行を snippet に含めるか |
| `--include-parent` | off | ヒットの親見出しチャンクを `expansion.parent` に追加 |
| `--expand-neighbors N` | `0` | 同一ファイル内で `start_line` 前後 N 件を `expansion.neighbors` に追加 |
| `--merge-parts` | off | 2 次分割で生じた同一見出しの他 part を `expansion.parts` に追加 |
| `--format` | `jsonl` | `jsonl` または `compact`（人間可読） |

JSONL 1行スキーマ:
```json
{"chunk_id":"<sha1>","path":"...","heading_path":"...","lines":[start,end],"score":0.0,"snippet":"...","expansion":{"parent":{...},"neighbors":[...],"parts":[...]}}
```
`expansion` キーは関連オプションが指定され、かつ該当データが存在する場合のみ出力される（後方互換）。

## get — 単一チャンク取得

```
python -m hve.mdq get --chunk-id <ID>
```

`search` で返った `chunk_id` を渡すと、本文を含む完全なチャンクを返す。

## list — 見出し一覧

```
python -m hve.mdq list [--paths GLOB ...] [--heading-level N] [--limit 200]
```

ファイル / 見出し階層の俯瞰に使用。

## stats — 索引統計

```
python -m hve.mdq stats
```

`{"files": N, "chunks": M}` を返す。

## 終了コード
- `0`: 正常
- `1`: `get` で `chunk_id` が見つからない等
