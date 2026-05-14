# 索引内部仕様

## ストア
- SQLite (`.hve/mdq.sqlite`, stdlib `sqlite3`)
- テーブル:
  - `files`(path PK, sha1, mtime, size_bytes, frontmatter JSON)
  - `chunks`(chunk_id PK, path, heading_path, level, start_line, end_line, token_est, text, tags JSON, `part_index`, `part_total`)
- `PRAGMA user_version` でスキーマ世代を管理（現行 = 1）。
- 旧スキーマ DB は `open_store()` 時に `PRAGMA table_info(chunks)` を確認し、不足カラムを `ALTER TABLE ... ADD COLUMN` で追加してから利用する（破壊的再構築なし）。

## チャンク化
- Markdown を **見出し単位** で分割（H1〜H6）。
- 各チャンクは「見出し行 → 次の同等以上レベルの見出し直前」までの本文。
- 先頭の見出し前の本文は `(preface)` チャンクとして登録。
- フェンスドコードブロック（``` または ~~~）内の `#` は見出しとして扱わない。

### 2 次分割（`--max-chunk-chars N`）
- 既定 (`N=0`) では無効。`N>0` の場合、見出し単位チャンクの本文長が `N` を超えるとさらに分割する。
- アルゴリズム:
  1. `_segment_by_fence` で本文を「フェンス領域」と「テキスト領域」に分解。フェンスは不可分。
  2. テキスト領域は空行で段落へ分割し、`N` 以内に収まるよう段落をまとめてサブチャンク化。
  3. 1 段落が `N` を超える場合は改行単位に分割。1 行が `N` を超える場合は文字数でハードカット（最後の手段）。
- 同一見出しから派生したサブチャンクは `heading_path` / `level` を共有し、`part_index`（0 始まり）/ `part_total` のみ異なる。
- `start_line` / `end_line` はサブチャンクごとに実際の行範囲に再計算される。

## frontmatter
- ファイル先頭の `---` ブロックを PyYAML で解析（PyYAML はプロジェクト依存）。
- `tags`（list または str）をチャンクの `tags` にも複製し検索フィルタに利用。

## ID / 増分更新
- `chunk_id` = SHA1(`path \0 heading_path \0 start_line`)
  - `start_line` がサブチャンクごとに異なるため、2 次分割でも衝突しない。
- ファイル単位で SHA-1 を保持し、再索引時に一致するファイルはスキップ。

## BM25
- 既定で `rank_bm25` を利用（任意導入）。未導入時は同等の `_MiniBM25` フォールバック（stdlib 実装）に切替。
- トークナイザ: 英数 + 日本語 1 文字単位（CJK Unified / Hiragana / Katakana を 1 トークン）。
- スコア > 0 のチャンクのみ返却。
- 注意: 小コーパスでは `df ≈ N/2` の語の IDF が 0 になりヒットしないことがある（BM25-Okapi の特性）。

## snippet と expansion
- snippet: マッチした query token を最も多く含む 1 行を中心に `--snippet-radius` 行を抽出。`max_chars=400` で末尾切り詰め。
- `Hit.expansion`（任意フィールド）: `--include-parent` / `--expand-neighbors N` / `--merge-parts` 指定時のみ付与される dict。
  - `parent`: 親見出し（`heading_path` から最後の `> ...` を除いた pat に一致するチャンク）。
  - `neighbors`: 同一ファイル内で `start_line` が直前/直後の N 件。
  - `parts`: 同一 `(path, heading_path)` の他 part（`part_total > 1` の場合のみ）。
- いずれも JSON 出力では `{"chunk_id", "path", "heading_path", "lines", "text"}` の最小ブリーフ表現で返す。

## 既知の制約（捏造禁止）
- BM25 はチャンク全件をクエリ時にメモリへロードする（小〜中規模向け）。大規模化したら SQLite FTS5 への移行を検討。
- 日本語形態素解析は行っていない（1 文字単位）。固有表現の精度は限定的。
- `expansion` の snippet 長は `max_tokens` の予算とは独立にカウントされない（本体ヒットのみ予算対象）。
