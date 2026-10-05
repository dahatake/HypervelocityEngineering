---
name: hve-system-test
description: >
  HVE 本体（このリポジトリの hve/ アプリケーション）のシステムテストを台帳で増分実行する。 USE FOR: HVE system test, run remaining system test, incremental test ledger. DO NOT USE FOR: HVE が生成したアプリケーションのシステムテスト、単体テスト、hve の実装変更。 WHEN: 「HVE の残りのシステムテストを実行して」など、HVE 本体のシステムテストの続き・再実行を依頼されたとき。
metadata:
  origin: user
  version: 1.0.0
---
# hve-system-test

HVE **本体**のシステムテストを、台帳 `tests/system-test-ledger/ledger.json` で未実施ケースだけ増分実行する。
対象は `hve` コマンド（Workflow の Step 実行）。HVE が生成したアプリのテストは対象外で、このスキルを使わない。

## 手順（トークン節約のため出力は要約のみ読む）

1. 対象確認: 依頼が HVE 本体か、HVE で作ったアプリかを依頼文で判定する。後者、または判別できない場合はこの Skill を使わず利用者へ確認する。
2. 状況: `python tests/system-test-ledger/ledger.py status --brief`（1 行）。
3. 計画: `python tests/system-test-ledger/ledger.py run [絞り込み]`（既定は計画表示のみ。先頭 12 件だけ出る）。
4. 実行: 利用者の依頼が実行を求めているので、同じ引数に `--execute` を付ける。1 回の予算は `--max-minutes`（既定の目安 120〜180）で区切る。
5. 結果: 出力の 1 行要約と `結果:` 行だけを利用者へ報告する。失敗は台帳 `evidence` 配下の `run.stderr.log` 末尾だけを読む。全文を読まない。

絞り込み: `--workflow` `--wave` `--ids` `--range A:B` `--limit` `--status`。「次の 3 件だけ」なら `--limit 3`、「aas だけ」なら `--workflow aas`。

## 必ず守ること

- 実行は実モデル呼び出し・課金を伴う。依頼で実行が明示された範囲だけ `--execute` を付ける。曖昧なら計画表示で止めて確認する。
- `approval` が `azure-write` のケース（Wave 9）は、subscription / resource group / 費用 / cleanup の具体値と個別承認が揃うまで `--include-approval` を付けない。
- canary（先頭の最小ケース）が現 HEAD で未達なら `run` が先に canary を実行し、失敗すれば本体を止める。`--skip-canary-check` は利用者が明示したときだけ。
- 失敗後に修正した場合は `ledger.py invalidate --failed --reason "<修正内容>"` で戻してから再実行する。過去の attempt は消さない。
- 証跡は `tests/run/<run-id>/system-test-ledger/` に保存される。元リポジトリの `work/` へは書かない。
- 結果の合否は exit code と台帳の status で述べる。失敗を PASS に丸めない。台帳の設計・規則は `tests/system-test-ledger/README.md`。

## Non-goals（このスキルの範囲外）

- HVE が生成したアプリケーションのシステムテスト。
- 新しいテストケース設計・要件の判定・hve 本体の修正（失敗の報告までを扱う）。
- 全ケースの一括実行。常に未実施分を予算内で増分実行する。

## 入出力例

入力: 「HVE の残りのシステムテストを実行してください」
出力: `status --brief` → `run --max-minutes 120` で計画確認 → `run --max-minutes 120 --execute` → 「pass=5, fail=1（CASE-aas-2.1: exit 1）。証跡 tests/run/…」の要約。
