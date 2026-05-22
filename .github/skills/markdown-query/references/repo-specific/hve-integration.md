# HVE（Hypervelocity Engineering）固有統合事項

本ドキュメントは、汎用 `markdown-query` Skill を **HVE リポジトリ** で運用する際の固有事項を集約する。汎用版（他リポジトリ）利用者は本ファイルを参照する必要はない。

---

## 1. リアルタイム索引（MdqWatcher）

HVE CLI Orchestrator（`hve orchestrate`）実行中は、バックグラウンドの `MdqWatcher` が `.md` ファイルの追加 / 更新 / 削除を OS イベント（`watchdog`）で検知し、索引 DB を逐次更新する。手動の `python -m mdq index` を毎ステップ実行しなくても、サブセッションが常に最新の索引を参照できる。

- **既定**: ON
- **依存**: `watchdog`（`pip install -e .[mdq-watch]` で導入）
- **無効化**: CLI 引数 `--no-mdq-watch` または環境変数 `HVE_MDQ_WATCH=0`
- **スタンドアロン版**: `python -m mdq watch`
- **共存**: 手動の `python -m mdq index` は引き続き利用可能（書き込み経路は直列で競合しない）
- **動作対象外**: GitHub Actions / Copilot Cloud Agent（ファイルシステム揮発のため）

## 2. セットアップスクリプトとの連動

- `hve/setup-hve.ps1` / `hve/setup-hve.sh` / `hve/setup-hve.cmd` は既定で `pip install -e ".[mdq-watch]"` を実行し、`python -m mdq --help` の動作確認まで行う。
- 抑止フラグ: `-SkipMdq` / `--skip-mdq`（インストールと検証を抑止。失敗は警告に降格）

## 3. Cloud Agent / GitHub Actions 運用

- Cloud runner 上では作業ツリーが揮発し、索引ファイル `.mdq/index.sqlite` は gitignore 済でセッション間で共有されない。
- **Cloud Agent セッションでは、毎回 `python -m mdq index` を自身で実行**してから `search` / `get` を使う運用とする（増分キャッシュは効かない）。
- 該当ワークフロー: `.github/workflows/mdq-index-reusable.yml`, `.github/workflows/test-hve-python.yml`

## 4. 利用統計ログ（HVE 固有）

- `.mdq/usage.jsonl`: `mdq` CLI が自動追記する利用ログ（gitignore 済）
- `run_journal` 側の参照定数: `hve.run_journal.MDQ_USAGE_LOG_RELATIVE`
- 集計モジュール: `mdq.usage_stats`
- レポート生成: `tools/skills/markdown_query/generate_usage_report.py`
- レポート保存先: `tools/skills/markdown_query/usage-report/`
- レポート定義・指標説明: [users-guide/skills-markdown-query.md](../../../../../users-guide/skills-markdown-query.md)

## 5. ベンチマーク（撤去判断用）

- スクリプト: `tools/skills/markdown_query/benchmark.py`
- サンプルクエリ: `tools/skills/markdown_query/queries.sample.txt`
- 詳細: `tools/skills/markdown_query/README.md`

## 6. Related Skills（HVE 内の棲み分け）

- `knowledge-lookup`: `knowledge/D01〜D21` の参照ルール（こちらが優先）
- `knowledge-management`: `knowledge/` への書き込み
- `repo-onboarding-fast`: 初見リポジトリでのファイル探索補助

### DO NOT USE FOR（HVE 固有）

- `knowledge/D01〜D21-*.md` の参照は `knowledge-lookup` Skill の責務。`markdown-query` の `--paths` で `knowledge/D...` を指定しないこと。
