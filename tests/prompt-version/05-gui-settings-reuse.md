# 05. 保存済み GUI 設定の再利用と override allowlist（FR-PROMPT-07）

## GitHub Copilot に貼り付ける Prompt

以下のコードブロック全体をコピーして貼り付けてください。

````markdown
このリポジトリで、HVE Prompt 版統合テスト「05. 保存済み GUI 設定の再利用と override allowlist
（FR-PROMPT-07）」を実施してください。必要なコマンドとファイル操作はすべてあなたが実行し、
利用者にコマンド、request の保存先、plan SHA-256 の入力を求めないでください。実測していない結果を
作らず、以下の目的、前提、実施項目、記録すること、重要をすべて満たしてください。
開始前に `tests/prompt-version/README.md` の全 Prompt 共通の前提・禁止事項・既知の未修正事項を確認してください。

## 目的

- Prompt 版が **GUI で保存した設定** を基準値として `OrchestrateArgs` を構築し、
  その解釈が現行 GUI と一致することを検証する。
- 構築が **Qt ウィジェットを起動しない純粋関数** であり、PySide6 未導入環境でも動作することを確認する。
- `settings_overrides` の allowlist が効いていることを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-settings/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- 設定の保存先は `hve/.settings.txt`（`python -c "from hve.gui import settings_store; print(settings_store.settings_path())"` で確認）。
- **テスト前に `hve/.settings.txt` をバックアップし、テスト後に復元すること。**
- 対象実装は `hve/gui/orchestrate_args.py` の `args_from_settings()`。

## 実施項目

### A. 設定値の反映

GUI で次を変更して保存し、`hve prompt plan` の argv に反映されることを 1 項目ずつ確認する。
**GUI を操作できない場合は `settings_store.load()` の結果を直接編集して `save()` してもよい**が、
その場合は「GUI 経由ではない」ことを報告に明記する。

| # | 設定 | 期待する argv |
|---|---|---|
| A1 | モデル | `--model <値>` |
| A2 | reasoning effort | `--reasoning-effort <値>` |
| A3 | context tier | `--context-tier <値>` |
| A4 | 並列数 | `--max-parallel <値>` |
| A5 | タイムアウト | `--timeout <値>` |
| A6 | verbosity | `--verbosity <値>` |
| A7 | branch | `--branch <値>` |

**期待するオプション名は推測せず、`hve/gui/orchestrate_args.py` の `to_argv()` から確認すること。**

### B. 型の解釈（GUI と同一であること）

1. **3 状態（`""` / `"on"` / `"off"`）**: `""` は該当オプションを出さない、`"on"` は肯定フラグ、
   `"off"` は否定フラグ（`--no-*`）になることを確認する。対象例: `force_refresh` / `mdq_watch` / `cq_watch`。
2. **リスト値**: `;` 区切りの設定値が argv で複数トークンに展開されることを確認する。対象例: `target_files` / `ignore_paths`。
3. **0 を「未指定」として扱うフィールド**: `context_max_chars` / `max_file_lines` 等が `0` のとき
   オプションが出ないことを確認する。
4. **`akm` の sources**: GUI のチェックボックス（`sources_qa` / `sources_original_docs` / `sources_workiq`）が
   `--sources` のカンマ区切り値になることを確認する。

### C. Qt 非依存

1. PySide6 を import できない状態でも `args_from_settings()` が動作することを確認する。
   実測例:

```sh
python -c "
import sys
class B:
    def find_module(self, n, p=None): return self if n.split('.')[0]=='PySide6' else None
    def load_module(self, n): raise ImportError('simulated')
sys.meta_path.insert(0, B())
from hve.gui.orchestrate_args import args_from_settings
from hve.gui import settings_store
print(args_from_settings(settings_store.defaults(), workflow='aas').to_argv()[:3])
"
```

2. `hve prompt plan` 実行中に GUI ウィンドウが開かないことを確認する。

### D. Prompt 版が所有する値（設定で上書きできないこと）

1. `hve/.settings.txt` の `workbench` を `full` にしても、argv が `--workbench off` になることを確認する。
2. `plan` の argv に `--dry-run` が含まれず、`run` 実行時にも付与されないことを確認する
   （`--dry-run` は `plan` の子プロセス起動時にだけ付く）。

### E. `settings_overrides` の allowlist

1. `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` を実測で取得する。

```sh
python -c "from hve.prompt_request import ALLOWED_SETTINGS_OVERRIDES; print(sorted(ALLOWED_SETTINGS_OVERRIDES))"
```

2. allowlist 内のキーで request の `settings_overrides` を指定し、**保存済み設定より優先される**ことを確認する。
3. allowlist 外のキー（`cli_path` / `mcp_config` / `repo_root` / 任意の env 名）が拒否されることを確認する。
4. 資格情報らしき名前（`token` / `password` / `secret`）が拒否されることを確認する。

## 記録すること

- A / B の各項目について、**設定値 → 実際の argv** の対応表
- C の実出力（Qt 非依存で成功したこと）
- E の allowlist の実測値と、拒否されたキーのエラー本文
- 復元した `hve/.settings.txt` が元の内容と一致することの確認

## 重要

- **捏造は絶対に禁止**です。オプション名を推測で書かず、`to_argv()` の実装または実出力から取る。
- **`hve/.settings.txt` は必ず復元すること。** 復元漏れは他の作業へ影響する。
- テストを通すために `hve/gui/orchestrate_args.py` を書き換えないこと。
- A1〜A7 / B1〜B4 は互いに独立なので並列実行してよい。各ケース完了後に敵対的レビューを行い、
  レビュー結果を反映してから次へ進むこと。
````
