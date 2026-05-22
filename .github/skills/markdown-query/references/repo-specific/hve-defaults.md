# HVE 既定設定リファレンス

汎用 `markdown-query` Skill の既定値は本来「リポジトリ依存」だが、HVE リポジトリでは下記を既定とする。

---

## 既定の索引対象ルート

`mdq index` を `--root` 引数なしで実行した場合、以下のディレクトリのうち **存在するもの** が索引対象になる（存在しないものは自動スキップ）:

1. `docs/`
2. `docs-generated/`
3. `users-guide/`
4. `template/`
5. `knowledge/`
6. `qa/`
7. `original-docs/`
8. `work/`
9. `sample/`
10. `session-state/`
11. `hve-dev/`

実装位置: 本リポジトリルートの [`mdq.toml`](../../../../../mdq.toml) の `[index].roots`。汎用コード侧の最小フォールバックは `mdq.config.GENERIC_DEFAULT_ROOTS`。`mdq/cli.py` の `DEFAULT_ROOTS` はそのエイリアス。

## 既定の索引 DB / 利用ログパス

- 索引 DB: `.mdq/index.sqlite`（言語×戦略指定時は `.mdq/index-<lang>-<strategy>.sqlite`）
- 利用ログ: `.mdq/usage.jsonl`
- いずれも `.gitignore` 済（リポジトリにコミット不可）

## HVE 固有環境変数

| 変数 | 既定 | 用途 |
|---|---|---|
| `HVE_MDQ_WATCH` | （未設定 = ON） | `0` を設定すると MdqWatcher を無効化 |

詳細は [hve-integration.md](./hve-integration.md) を参照。
