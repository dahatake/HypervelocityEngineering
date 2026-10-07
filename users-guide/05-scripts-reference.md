# 5. スクリプトリファレンス

すべてのスクリプトは、Python 3.9 以上の標準ライブラリだけで動きます。リポジトリのどこから実行しても、git のルートを基準に動作します。詳しい使い方は `--help` で表示できます。出力は短く、LLM がそのまま読める形式です（1 行に 1 指摘、最後に 1 行の要約）。

## verify（L1 決定的検査）

```bash
python scripts/verify.py                  # 管理データの検査（CHK-01〜23）＋ verify.commands
python scripts/verify.py --docs-only      # 管理データの検査だけ（rd-author・test-designer のゲート）
python scripts/verify.py --quick          # "slow": true のコマンドをスキップする（implementer のゲート）
python scripts/verify.py --run current    # 実行中の run の queue.json との整合性（CHK-21）も検査する
python scripts/verify.py --strict         # 最終工程・統合時用。重要な警告をエラーとして扱う
python scripts/verify.py --strict-ledger  # system AC と台帳の対応（CHK-10/11）の不足をエラーにする（工程 4 以降は自動）
python scripts/verify.py --show-warnings  # 警告も表示する
./scripts/verify.sh   /  .\scripts\verify.ps1   # 同じもの（Python を探して verify.py を呼ぶラッパー）
```

exit 0 なら合格です。ログの全文は `/work` に保存されます。

## rdcheck.py（要求定義書のパーサー）

```bash
python scripts/rdcheck.py check [--base REF|none] [--run RUN_ID|current] [--strict] [--json]
python scripts/rdcheck.py show FR-012 AC-031 Q-007     # 指定した要求・AC・質問の節だけを表示する（全文を読まずに済む）
python scripts/rdcheck.py list --state 承認済み --priority MUST
python scripts/rdcheck.py list --level system          # System Test の対象になる AC
python scripts/rdcheck.py stats                        # 監査のメトリクス（JSON）
python scripts/rdcheck.py digest AC-031                # AC のダイジェスト
```

`--base` の既定値は main との分岐点（merge-base）です。差分の検査（CHK-12/13）に使います。

## next-id.py（ID の採番。G-3）

```bash
python scripts/next-id.py FR                    # FR-013
python scripts/next-id.py NFR-SEC               # NFR-SEC-004
python scripts/next-id.py AC --count 3          # AC-041 AC-042 AC-043
python scripts/next-id.py Q | PARAM | G | SRC | E2E | IT
python scripts/next-id.py --peek FR             # 採番せずに次の ID を表示する
python scripts/next-id.py --sync                # ID 台帳の状態を本文に合わせる（使用中・廃止・削除済み）
python scripts/next-id.py --sync --adopt        # 台帳にない既存の ID を取り込む（インストール直後）
python scripts/next-id.py --sync --finalize     # 使わなかった採番済みの ID を欠番にする（工程 6）
```

次の番号は、max(要求定義書, ID 台帳, main 上の同じファイル, System Test の台帳, worktree 共通の採番記録) + 1 で決まります。

## ledger.py（System Test の台帳。G-2）

```bash
python scripts/ledger.py summary [-v]
python scripts/ledger.py --by test-designer add --req FR-012 --ac AC-031 --title "…" --layer e2e --command "…" [--canary]
python scripts/ledger.py --by test-designer update E2E-001 --command "…" --reason "…"   # 理由は必須
python scripts/ledger.py --by test-designer block E2E-001 --reason "…"                 # 削除の代わりに使う
python scripts/ledger.py set E2E-001 blocked --reason "…"
python scripts/ledger.py digests [--update]
python scripts/ledger.py --by conductor run --select changed|failed|all [--canary-first] [--stop-on-canary-fail] [--max-minutes N]
python scripts/ledger.py run --cases E2E-001,IT-002 --no-record   # 作業役の worktree で、台帳を更新せずに実行だけする
```

`run` の出力は、元の Prompt が定める報告形式（`<id> <requirement_ids> <pass|fail> <秒> <証跡>` と `結果: …`）です。結果の詳細は `work/runs/<run-id>/results.json` にあります。

## select-tests.py（影響範囲のテスト選択）

```bash
python scripts/select-tests.py [--base REF] [--req FR-012] [--json]
```

変更したファイルに書かれている要求 ID・AC ID と、`--req` で指定した ID から、実行すべき System Test のケース（`CASE`）と、単体・結合テストのファイル（`TEST`）を選びます。canary と、not_run・fail のケースは常に含めます。

## summarize.py（ログの要約）

```bash
python scripts/summarize.py work/runs/<run-id>/logs/verify-…-unit.log [--max-lines 15]
npm test 2>&1 | python scripts/summarize.py -
```

テストランナーの集計行、最初の数件の（重複しない）エラー行、末尾の数行だけを出力します。

## run-state.py（conductor の状態管理）

```bash
python scripts/run-state.py start --options "max_hours: 24\ngit_push: しない"   # 実行中の run があれば RESUME
python scripts/run-state.py status
python scripts/run-state.py stage 4 [--done]
python scripts/run-state.py progress "工程 2: 直接矛盾 0。Q-012 を BLOCKED"
python scripts/run-state.py queue add --id I-01 --req FR-012,FR-013 --ac AC-031 --boundary 申請 --shared 下書き保存 --depends I-00
python scripts/run-state.py queue ready --parallel 3
python scripts/run-state.py queue set I-01 --status doing --branch work/<run-id>/I-01 --attempts +1
python scripts/run-state.py time                  # 時間予算の 85% を超えたら exit 3
python scripts/run-state.py complete-check        # 完了条件の判定
python scripts/run-state.py human answers --note "Q-003: B"   # 利用者の Prompt を 1 回として記録（answers / resume / instruction）
python scripts/run-state.py finish --result "全件完了" --credits "…"   # docs/run-history.md に 1 行追記
```

新しい run の最初の依頼は `start` が `request` として記録します。`human` は、利用者の Prompt で run を再開したときに conductor が 1 回だけ実行します。記録した回数は KPI の「人の介入」になります。

## kpi.py（KPI の集計）

```bash
python scripts/kpi.py run                          # 実行中（なければ最新）の run の KPI を Markdown で表示
python scripts/kpi.py run --run 202610080900 --format json
python scripts/kpi.py run --format html --out work/runs/<run-id>/kpi.html
python scripts/kpi.py history                      # docs/run-history.md 全体の集計
```

North Star は「人の介入 1 回あたりの検証済み要求」です。**検証済み要求**は、実装した要求のうち、承認済みで、カタログの行があり、BLOCKED の AC がなく、system の AC がすべて台帳で `pass` のものです。検証済みにならなかった要求は、理由（「カタログの行がない」など）を表示します。指標と目標は [08-roadmap.md の 8.2](08-roadmap.md#82-kpi) にあります。

## import-speckit.py（GitHub Spec Kit からの取り込み）

```bash
python scripts/import-speckit.py [--source DIR] [--feature 001] [--implement] [--no-constitution] [--out F | --stdout | --json]
```

`specs/*/spec.md` と `.specify/memory/constitution.md` を読み、対応表と `/build` の依頼文を `work/import/speckit-<日時>.md` に書きます。要求定義書は編集せず、ID も振りません。使い方は [1.7](01-writing-requests.md#17-github-spec-kit-の仕様を取り込む) にあります。

## clean-work.py（/work のクリーンアップ）

```bash
python scripts/clean-work.py [--days 14] [--dry-run]
```

## hooks/gate.py（hook の本体）

利用者が直接実行することはありません。`.github/hooks/quality-gates.json` から、`session-start`・`pre-tool`・`subagent-start`・`subagent-stop`・`agent-stop` の各イベントで呼び出されます。判定の記録は `work/.hve/gate.log` にあります。
