# 8. スクリプト一覧

すべて Python 3.9 以上の標準ライブラリだけで動きます。リポジトリのどこから実行しても、git のルートを基準にします。`--help` で詳しい使い方を表示します。出力は短く、LLM がそのまま読める形です（1 行 1 指摘、最後に要約の 1 行）。

## verify（L1 決定的検査）

```bash
python scripts/verify.py                  # 管理データの検査（CHK-01〜23）＋ verify.commands
python scripts/verify.py --docs-only      # 管理データの検査だけ（rd-author・test-designer のゲート）
python scripts/verify.py --quick          # "slow": true のコマンドを省く（implementer のゲート）
python scripts/verify.py --run current    # 実行中の run の queue.json との整合（CHK-21）も検査
python scripts/verify.py --strict         # 最終・統合時。重要な警告を error にする
python scripts/verify.py --strict-ledger  # system AC と台帳の対応（CHK-10/11）の不足を error にする（工程 4 以降は自動）
python scripts/verify.py --show-warnings  # 警告も表示
./scripts/verify.sh   /  .\scripts\verify.ps1   # 同じもの（Python を探して verify.py を呼ぶ）
```

exit 0 = 合格。ログの全文は `/work` に保存されます。

## rdcheck.py（要求定義書の解析）

```bash
python scripts/rdcheck.py check [--base REF|none] [--run RUN_ID|current] [--strict] [--json]
python scripts/rdcheck.py show FR-012 AC-031 Q-007     # その要求・AC・質問の節だけを表示（全文を読まない）
python scripts/rdcheck.py list --state 承認済み --priority MUST
python scripts/rdcheck.py list --level system          # System Test の対象の AC
python scripts/rdcheck.py stats                        # 監査のメトリクス（JSON）
python scripts/rdcheck.py digest AC-031                # AC のダイジェスト
```

`--base` の既定は main との分岐点です（差分の検査 CHK-12/13 に使います）。

## next-id.py（ID の採番。G-3）

```bash
python scripts/next-id.py FR                    # FR-013
python scripts/next-id.py NFR-SEC               # NFR-SEC-004
python scripts/next-id.py AC --count 3          # AC-041 AC-042 AC-043
python scripts/next-id.py Q | PARAM | G | SRC | E2E | IT
python scripts/next-id.py --peek FR             # 採番せずに次の ID を表示
python scripts/next-id.py --sync                # ID 台帳の状態を本文に合わせる（使用中・廃止・削除済み）
python scripts/next-id.py --sync --adopt        # 台帳にない既存の ID を取り込む（導入直後）
python scripts/next-id.py --sync --finalize     # 使わなかった採番済みを欠番にする（工程 6）
```

次の番号 = max(要求定義書, ID 台帳, main 上の同じファイル, 台帳, worktree 共通の採番記録) + 1。

## ledger.py（System Test の台帳。G-2）

```bash
python scripts/ledger.py summary [-v]
python scripts/ledger.py --by test-designer add --req FR-012 --ac AC-031 --title "…" --layer e2e --command "…" [--canary]
python scripts/ledger.py --by test-designer update E2E-001 --command "…" --reason "…"   # 理由が必須
python scripts/ledger.py --by test-designer block E2E-001 --reason "…"                 # 削除の代わり
python scripts/ledger.py set E2E-001 blocked --reason "…"
python scripts/ledger.py digests [--update]
python scripts/ledger.py --by conductor run --select changed|failed|all [--canary-first] [--stop-on-canary-fail] [--max-minutes N]
python scripts/ledger.py run --cases E2E-001,IT-002 --no-record   # 作業役の worktree で実行だけ
```

`run` の出力は原本の報告の形（`<id> <requirement_ids> <pass|fail> <秒> <証跡>` と `結果: …`）です。結果の詳細は `work/runs/<run-id>/results.json`。

## select-tests.py（影響範囲のテストの選択。T-7）

```bash
python scripts/select-tests.py [--base REF] [--req FR-012] [--json]
```

変更したファイルに書かれた要求 ID・AC ID と、`--req` から、実行する System Test のケース（`CASE`）と単体・結合テストのファイル（`TEST`）を選びます。canary と not_run・fail のケースは常に含めます。

## summarize.py（ログの要約。R-21）

```bash
python scripts/summarize.py work/runs/<run-id>/logs/verify-…-unit.log [--max-lines 15]
npm test 2>&1 | python scripts/summarize.py -
```

テストランナーの集計行、最初の数件の異なるエラー行、末尾の数行だけを出します。

## run-state.py（conductor の状態。§7.5）

```bash
python scripts/run-state.py start --options "max_hours: 24\ngit_push: しない"   # 実行中なら RESUME
python scripts/run-state.py status
python scripts/run-state.py stage 4 [--done]
python scripts/run-state.py progress "工程 2: 直接矛盾 0。Q-012 を BLOCKED"
python scripts/run-state.py queue add --id I-01 --req FR-012,FR-013 --ac AC-031 --boundary 申請 --shared 下書き保存 --depends I-00
python scripts/run-state.py queue ready --parallel 3
python scripts/run-state.py queue set I-01 --status doing --branch work/<run-id>/I-01 --attempts +1
python scripts/run-state.py time                  # 85% を超えたら exit 3
python scripts/run-state.py complete-check        # 完了条件（§8.3）
python scripts/run-state.py finish --result "全件完了" --credits "…"   # docs/run-history.md に 1 行
```

## clean-work.py（/work の削除。§7.6）

```bash
python scripts/clean-work.py [--days 14] [--dry-run]
```

## hooks/gate.py（hook の本体）

利用者が直接実行することはありません。`.github/hooks/quality-gates.json` から、`session-start`・`pre-tool`・`subagent-start`・`subagent-stop`・`agent-stop` のイベントで呼ばれます。判断の記録は `work/.hve/gate.log` にあります。
