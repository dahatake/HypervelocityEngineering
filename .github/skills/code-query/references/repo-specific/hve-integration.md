# Appendix: HVE リポジトリ固有事項（code-query）

本ファイルは **HVE（Hypervelocity Engineering）リポジトリ固有** の設定・実測値・具体例を収容する。
他リポジトリへ本 Skill を配布する場合、このディレクトリ（`references/repo-specific/`）は同梱されない。

## profile 一覧

`--profile` は対象コードベースの切り替え。本リポジトリの `cq.toml` は次の 2 つを宣言している。

| profile | 対象 | 用途 |
|---|---|---|
| `hve` | `hve/`, `mdq/`, `cq/`, `hve-dev/`, `tools/`, `.github/scripts/` | HVE アプリケーション自体の保守 |
| `app` | `src/` | HVE が生成したアプリケーションの調査 |

`--profile` を毎回書かずに済ませたい場合は環境変数 `CQ_PROFILE`、または配布キットのランチャ
（`cq.ps1` / `cq.sh` / `cq.cmd`）を使う。

## 最短呼び出し例（本リポジトリの値を埋めたもの）

```sh
python -m cq stats  --profile hve                      # 索引の存在と規模を確認
python -m cq index  --profile hve                      # 未作成 or 古ければ実行（増分）
python -m cq search --profile hve --q "<探したい語>"     # 既定 --mode auto / --top-k 5 / --max-tokens 800
python -m cq search --profile hve --q "<探したい語>" --return-unit chunk  # 関数・クラス単位で本文ごと返す
python -m cq def    --profile hve --symbol "StepRunner.set_fork_index"  # 定義へ直行（qualname）
python -m cq get    --profile hve --chunk-id <ID>      # snippet で不足するときだけ本文を取る
python -m cq refs   --profile hve --symbol "resolve_run_id"      # 呼び出し元を列挙
python -m cq trace  --profile app --id TEST-SVC-02-001           # トレース ID → コード位置
python -m cq trace  --profile app --by-path <file>               # コード → 設計文書のパスとアンカー
python -m cq map    --profile hve --paths "hve/gui/*" --max-tokens 1200   # 俯瞰マップ
python -m cq watch  --profile hve                                # 保存を即座に索引へ反映
```

## 検索品質の実測値

ゴールデン 21 問。数値は本リポジトリのコードベースに対するものであり、他リポジトリへは外挿できない。

| profile | 手法 | top-1 | 平均トークン | 平均レイテンシ |
|---|---|---|---|---|
| `hve` | `grep` 対照群 | 9.5% | 1,083 | 2,196 ms |
| `hve` | 全文読み込み対照群 | — | 187,854 | — |
| `hve` | **`cq search`** | **95.2%** | **84.8** | **9.6 ms** |
| `app` | `grep` 対照群 | 71.4% | — | — |
| `app` | **`cq search`** | **95.2%** | **73.5** | **12.3 ms** |

## 索引運用

- 編集が頻繁な場合は `python -m cq watch --profile hve` を並走させる。
- GUI からの索引運用は `hve/gui/settings_window.py` の Code-Query セクション（FR-GUI-04）を使う。
- 配布キットは [tools/skills/code_query/](../../../../tools/skills/code_query/)。
