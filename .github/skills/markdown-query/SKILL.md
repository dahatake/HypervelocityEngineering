---
name: markdown-query
description: >
  ローカルのみで動作する Markdown 横断クエリを実行し、該当チャンクのみを返して Context Window を最小化する。
  USE FOR: search markdown, query docs, find heading, lookup across markdown files, bm25 markdown search, grep markdown, list markdown by tag.
  DO NOT USE FOR: editing markdown (use knowledge-management), knowledge/ D01-D21 lookup (use knowledge-lookup), cloud embedding search, html rendering.
  WHEN: 複数 Markdown を横断検索したい、見出し単位で本文を取得したい、Context を節約しつつドキュメント参照したい。
metadata:
  origin: user
  version: 0.1.1
category: planning
---

# markdown-query

## 目的
- ローカル完結（外部 API なし）で Markdown 群に対する横断クエリを行う。
- Copilot / Custom Agent の **Context Window 消費を最小化** するため、ヒットしたチャンクの **小さな snippet（既定 ±2 行）** のみを返す。
- 索引対象既定: `docs/`, `docs-generated/`, `users-guide/`, `template/`, `knowledge/`, `qa/`, `original-docs/`, `work/`, `sample/`, `session-state/`, `hve-dev/`（存在するもののみ。`hve` オーケストレーターが生成するフォルダを含む）。

## Non-goals（このスキルの範囲外）
- Markdown の編集 / 生成（`knowledge-management` Skill）。
- `knowledge/D01〜D21` の参照ルール判定（`knowledge-lookup` Skill）。
- クラウド埋め込み / リモート検索 / HTML レンダリング。

## トリガー
- frontmatter `description` の USE FOR / DO NOT USE FOR / WHEN に従う。
- 詳細は [references/cli-reference.md](references/cli-reference.md) を参照。

## 手順サマリ
1. **索引（初回 or 変更後）**: `python -m hve.mdq index`
   - 既定で `docs/`, `docs-generated/`, `users-guide/`, `template/`, `knowledge/`, `qa/`, `original-docs/`, `work/`, `sample/`, `session-state/`, `hve-dev/` を走査（存在しないフォルダはスキップ）
   - 増分更新（SHA-1 + mtime 一致ファイルはスキップ）
   - 既定で自動 prune（ディスク上に存在しないファイルのチャンクを削除、`--no-prune` で無効化可）
   - **重要**: 索引ファイル `.hve/mdq.sqlite` は gitignore 済でセッション間で共有されない。**この Skill を使う前に必ず 1 回実行すること**。Copilot Cloud Agent セッションでも同様にセッション毎に再ビルドが必要。
   - **リアルタイム索引（HVE CLI Orchestrator のみ）**: `hve orchestrate` 実行中は `MdqWatcher` がバックグラウンドで `.md` の追加/更新/削除を OS イベントで検知し `.hve/mdq.sqlite` を逐次更新する（既定 ON、`watchdog` 必須: `pip install -e .[mdq-watch]`）。セットアップスクリプト（`hve/setup-hve.ps1` / `hve/setup-hve.sh`）を実行している場合は `watchdog` は導入済み（`-SkipMdqWatch` / `--skip-mdq-watch` 未指定時）。無効化は `--no-mdq-watch` または `HVE_MDQ_WATCH=0`。スタンドアロン版は `python -m hve.mdq watch`。手動の `python -m hve.mdq index` も引き続き利用可能（共存）。Cloud Agent / GitHub Actions では本機能は動作しない。
2. **検索**: `python -m hve.mdq search --q "クエリ" --top-k 5 --max-tokens 800`
   - 既定モード: `bm25`、出力: JSONL（1行=1ヒット）
   - `--paths`, `--tags`, `--mode grep`, `--snippet-radius` で絞り込み
3. **本文取得（必要時のみ）**: `python -m hve.mdq get --chunk-id <ID>`
4. 結果を **そのまま Agent に渡す**（生 Markdown を読み込まない）。

## 入出力例

### 入力（Agent が発行するコマンド）
```
python -m hve.mdq search --q "業務要件 概要" --paths "docs/*" --top-k 3 --max-tokens 500
```

### 出力（JSONL: 1行=1ヒット）
```json
{"chunk_id":"<sha1>","path":"docs/business-requirement.md","heading_path":"# 概要 > ## 範囲","lines":[42,71],"score":12.7,"snippet":"...マッチ前後 ±2 行..."}
```

## Context 節約のコツ
- まず `--format compact` で目視確認 → 必要な `chunk_id` だけ `get` で詳細取得。
- `--top-k` を 3〜5、`--max-tokens` を 400〜800 に保つ（既定）。
- `--paths` でディレクトリを絞ると BM25 精度も向上する。

## 詳細ガイド（Progressive Disclosure）
- CLI 詳細: [references/cli-reference.md](references/cli-reference.md)
- クエリ例パターン集: [references/query-patterns.md](references/query-patterns.md)
- 索引内部仕様: [references/indexing-internals.md](references/indexing-internals.md)
- Prompt / Custom Agent 組み込み例: [examples/prompt-snippets.md](examples/prompt-snippets.md)

## Related Skills
- `knowledge-lookup`: D01〜D21 の参照ルール（こちらが優先）
- `knowledge-management`: knowledge/ への書き込み
- `repo-onboarding-fast`: 初見リポジトリでのファイル探索補助
