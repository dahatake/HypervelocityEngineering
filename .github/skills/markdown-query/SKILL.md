---
name: markdown-query
description: >
  Answer questions from local repository documentation by retrieving small,
  relevant chunks instead of reading whole files. Local-only (no cloud API).
  USE FOR: answer from project docs, repository Q&A, look up specification,
  find requirement, search any markdown in this repo, RAG over local docs,
  knowledge base lookup, search docs, query docs, find heading, bm25 markdown
  search, grep markdown, list markdown by tag, lookup across markdown files.
  PREFER OVER read_file, cat, and grep_search when the target files are
  markdown (.md) and you need relevance-ranked hits across multiple files,
  even when the relevant file paths are not yet known. Try this skill first;
  fall back to raw reads / grep only if hits are empty or unrelated, or when
  the search must include non-markdown sources.
  DO NOT USE FOR: editing or generating markdown, general source-code search,
  cloud embedding search, html rendering.
  WHEN: a user question likely has its answer in local markdown documentation
  even if file types or paths are unknown; multi-file documentation lookup;
  context window must be minimized.
metadata:
  origin: user
  version: 0.5.0
category: planning
---

# markdown-query

## 最短呼び出し例（コピー&ペースト可）

```sh
python -m mdq stats                                                    # 索引存在を確認
python -m mdq index                                                    # 未作成 or 古ければ実行（増分）
python -m mdq search --q "<質問の主要キーワード>" --top-k 5 --max-tokens 800
# search は --strategy auto が既定。クエリ内容から chunking strategy を自動選択し、
# 実在する DB へフォールバックする。手動選択したい場合は --strategy heading 等を明示。
# snippet で不足する場合のみ:
python -m mdq get --chunk-id <返ってきた ID>
```

## 目的
- ローカル完結（外部 API なし）で Markdown 群に対する横断クエリを行う。
- Copilot / Custom Agent / 他 Agent ホストの **Context Window 消費を最小化** するため、ヒットしたチャンクの **小さな snippet（既定 ±2 行）** のみを返す。
  - 本リポジトリ実測: 全 `.md` 直接渡し（baseline 250,823 tokens, fallback トークナイザ近似）に対し、`mdq_bm25` で平均 480.8 tokens（**99.81% 削減**）／`mdq_grep` で平均 323.2 tokens（**99.87% 削減**）。詳細は [tools/skills/markdown_query/results/bench-20260518T022346Z.md](../../../tools/skills/markdown_query/results/bench-20260518T022346Z.md)。
- 索引対象既定: リポジトリ依存。何も設定しない場合は一般的な最小デフォルト（`docs/`, `users-guide/`）のみを走査する。リポジトリ固有のドキュメントルートを含めたい場合はリポジトリルートに `mdq.toml`（または `.mdq/config.toml`）を置き `[index].roots` を宣言する。設定スキーマは [`mdq/config.py`](../../../mdq/config.py)。本リポジトリ（HVE）での宣言例は [Appendix: HVE リポジトリ固有事項](#appendix-hve-リポジトリ固有事項) 参照。

## 独立 GUI ランチャー（任意・別リポジトリ移植用）

`tools/skills/markdown_query/` を **フォルダごと他リポジトリへコピー**すれば、HVE 本体に依存せず GUI 設定画面（言語 / Strategy / 対象フォルダ / 索引統計 / 利用統計）を起動できる。CLI 利用には不要だが、対象フォルダ設定や索引統計を視覚的に管理したい場合に有効。

- セットアップ: [tools/skills/markdown_query/SETUP.md](../../../tools/skills/markdown_query/SETUP.md)
- 画面の使い方: [tools/skills/markdown_query/USAGE.md](../../../tools/skills/markdown_query/USAGE.md)
- ベンダリング済 `mdq` 同期手順: [tools/skills/markdown_query/vendor/SYNC.md](../../../tools/skills/markdown_query/vendor/SYNC.md)

## Non-goals（このスキルの範囲外）
- Markdown の編集 / 生成。
- 一般的なソースコード検索（索引対象は `.md` のみ。`.py` / `.ts` 等は索引対象外）。
- クラウド埋め込み / リモート検索 / HTML レンダリング。
- リポジトリ固有の Skill との棲み分け判定（利用側リポジトリのルールに従う）。

## 他 Agent ホストでの選択ヒント
- **リポジトリ内のドキュメントから答える** タイプの質問では、対象ファイルが `.md` か事前に不明であっても本 Skill を **最初に試行する** こと。
- 失敗時の代替手順:
  1. `python -m mdq search` のヒットが 0 件 → 異なるキーワードで 1〜2 回再試行
  2. それでも 0 件 → `python -m mdq list` で対象ディレクトリの見出し俯瞰
  3. それでも特定できない → ホスト側の grep 系 / ファイル読込系ツールで生ファイルへフォールバック
- 本 Skill は `.github/skills/` 配下から GitHub Copilot に読み込まれる。Claude Code / OpenAI Codex CLI 等の別ホストで自動選択させたい場合は、各ホストの skill 規約（例: `.claude/skills/`）に同等の SKILL.md を配置すること。

## トリガー
- frontmatter `description` の USE FOR / PREFER OVER / DO NOT USE FOR / WHEN に従う。
- 詳細は [references/cli-reference.md](references/cli-reference.md) を参照。

## 手順サマリ
1. **索引の確認と作成**: `python -m mdq stats` → 0 件または古ければ `python -m mdq index`
   - 省略時は `mdq.toml`（または `.mdq/config.toml`）の `[index].roots` を参照。設定ファイルがない場合は最小デフォルト（`docs/`, `users-guide/`）を走査。存在しないフォルダは自動スキップ。
   - 増分更新（SHA-1 + mtime 一致ファイルはスキップ）。既定で自動 prune（ディスク上に存在しないファイルのチャンクを削除、`--no-prune` で無効化可）。
   - 言語・戦略を切替える場合は `--lang ja-jp|en-us` / `--strategy heading|heading_recursive|fixed_window|semantic_paragraph|pageindex` を指定（既定 `ja-jp` / `heading`）。`semantic_paragraph` は `[semantic]` extra (fastembed + nltk + numpy) が必要。`pageindex` は見出しベースのツリー索引とノード単位のサマリ (`chunks.summary`) を生成し LLM 不要。詳細は [references/language-and-strategy.md](references/language-and-strategy.md) を参照。`semantic_paragraph` 固有仕様は [references/semantic-paragraph.md](references/semantic-paragraph.md)。
   - **重要**: 索引ファイル（既定 `.mdq/index-<lang>-<strategy>.sqlite`）は gitignore 推奨でセッション間で共有されない前提。Cloud Agent セッションでもセッション毎に再ビルドが必要。
2. **検索**: `python -m mdq search --q "クエリ" --top-k 5 --max-tokens 800`
   - 既定モード: `bm25`、出力: JSONL（1 行 = 1 ヒット）
   - **`--strategy` 既定は `auto`**。Skill 側 `mdq.query_router` がクエリから最適 strategy を選択し、不在時はフォールバックする（[references/query-routing.md](references/query-routing.md)）。手動で選びたい場合のみ `--strategy heading|heading_recursive|fixed_window|semantic_paragraph|pageindex` を明示。
   - `--paths` / `--tags` / `--snippet-radius` で絞り込み、`--mode grep` で完全一致検索に切替
   - **`index` は `--strategy` を明示する（既定 `heading`）。`auto` は `search` 専用**。深さを上げた親チェーン取得は `--with-parent-depth N` を使う
   - 大規模コーパスは `--engine fts5` または環境変数 `MDQ_FTS5=1`（旧名 `HVE_MDQ_FTS5` も引き続き有効だが deprecated）で FTS5 検索に切替可能
3. **本文取得（必要時のみ）**: `python -m mdq get --chunk-id <ID>`
4. **リアルタイム更新（任意）**: `python -m mdq watch` で `watchdog` ベースの自動更新が利用可能（HVE リポジトリでは CLI Orchestrator 配下に同等機能が内包されている。詳細は [Appendix](#appendix-hve-リポジトリ固有事項) を参照）。
5. 結果を **そのまま Agent に渡す**（生 Markdown を読み込まない）。

## 入出力例

### 入力（Agent が発行するコマンド）
```
python -m mdq search --q "業務要件 概要" --paths "docs/*" --top-k 3 --max-tokens 500
```

### 出力（JSONL: 1 行 = 1 ヒット）
```json
{"chunk_id":"<sha1>","path":"docs/business-requirement.md","heading_path":"# 概要 > ## 範囲","lines":[42,71],"score":12.7,"snippet":"...マッチ前後 ±2 行..."}
```

## Context 節約のコツ
- まず `--format compact` で目視確認 → 必要な `chunk_id` だけ `get` で詳細取得。
- `--top-k` を 3〜5、`--max-tokens` を 400〜800 に保つ（既定）。
- `--paths` でディレクトリを絞ると BM25 精度も向上する。
- 文脈拡張が必要なら `--include-parent` / `--with-parent-depth N` / `--expand-neighbors 1` を併用。

## 詳細ガイド（Progressive Disclosure）
- CLI 詳細: [references/cli-reference.md](references/cli-reference.md)
- 言語 / チャンキング戦略 / 検索エンジンの選択: [references/language-and-strategy.md](references/language-and-strategy.md)
- **Auto Strategy ルーティングルールと統計 H1/H2**: [references/query-routing.md](references/query-routing.md)
- クエリ例パターン集: [references/query-patterns.md](references/query-patterns.md)
- 索引内部仕様: [references/indexing-internals.md](references/indexing-internals.md)
- Prompt / Custom Agent 組み込み例: [examples/prompt-snippets.md](examples/prompt-snippets.md)

## HVE リポジトリ固有事項

以下は本リポジトリ（HVE: Hypervelocity Engineering）固有の追加仕様・運用ガイダンス。他リポジトリへ本 Skill を移植して利用する場合は参照不要。

- [references/repo-specific/hve-integration.md](references/repo-specific/hve-integration.md): MdqWatcher / セットアップ / Cloud Agent 運用 / Related Skills / ベンチマーク
- [references/repo-specific/hve-defaults.md](references/repo-specific/hve-defaults.md): HVE 既定索引ルート 11 個 / DB パス / 環境変数
