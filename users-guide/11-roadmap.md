# 11. 導入ロードマップと KPI

## 11.1 段取り（§12）

| Phase | 目安 | 内容 | 完了条件 | 利用者の作業 |
|---|---|---|---|---|
| 0 診断 | 2〜4 時間（無人） | 過去のリポジトリに rd-auditor を履歴モードで実行し、過去の矛盾がどの commit・どの Prompt から生まれたかを調べます | 矛盾ごとに、生んだ commit と Prompt と仮説がある | Prompt 1 回 |
| 1 基盤 | 1〜2 日（大半は無人） | toolkit を導入し（[02-install.md](02-install.md)）、[03-quickstart.md](03-quickstart.md) §3.5 の 6 項目を確かめます。代表的な作業（要求 3 件分）を、モデルの組み合わせ 2〜3 通り × 2 回で実行し、モデルを決めます | 6 項目の結果が記録され、`models` が決まっている | Prompt 数回、結果の確認 |
| 2 要求定義 v1.0 | 2〜6 時間＋回答 | ドラフトを `<request>` に貼り、`approval_policy: 厳格`、`max_hours` を短めにして、工程 1〜2 を中心に実行します | 承認待ちのない MUST 要求群があり、直接矛盾 0 | Prompt 1 回、回答 1 回 |
| 3 初回の長時間実行 | 24〜48 時間（無人） | `approval_policy: 安全範囲は推奨どおり` で全工程を実行します | run-report の結果が「全件完了」か「blocked あり（理由つき）」。verify exit 0 | Prompt 1 回、報告の確認、取り込み |
| 4 調整 | 継続 | KPI を見て、モデルの振り分け、`parallel_workers`、節目の間隔、skills の文面を調整します | KPI が改善している | 改善案の採否を Prompt で回答 |

### Phase 0 の依頼の例

VS Code で Agent に **rd-auditor** を選び（または Copilot CLI で `--agent rd-auditor`）、次を送ります。

```text
<audit_options>
scope: 全量
runs: 1
history_mode: する
</audit_options>
run-id は diag-<日付> とし、結果は work/runs/diag-<日付>/run-report.md に書いてください。
矛盾ごとに、それを生んだ commit と、その commit を作った Prompt（commit メッセージ・PR から推定）と、原因の仮説（計画書 §4 の H1〜H5）を挙げてください。
```

### Phase 2 の依頼の例

```text
<request>
<pasted_content id="d1">
（要求のドラフトを貼る）
</pasted_content id="d1">
これを要求定義書にする。実装はまだしない。
</request>
<run_options>
max_hours: 4
approval_policy: 厳格
parallel_workers: 1
scope: なし
git_push: しない
deploy: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```

## 11.2 KPI（§13）

| 区分 | KPI | 目標の目安 | 取得元 |
|---|---|---|---|
| 品質 | 承認済み・BLOCKED でない AC の pass 率 | 100% | `docs/run-history.md` の AC pass 率、`ledger.py summary` |
| 品質 | 取り込み後に見つかった直接矛盾・欠陥 | 0 件 | 次回の rd-auditor |
| 品質 | system AC の被覆率と、ダイジェストの不一致 | 100% と 0 | `verify.py --strict-ledger`、`rdcheck.py stats` |
| 時間 | 要求 1 件あたりの経過時間 | Phase 1 の計測値を基準に短縮 | `docs/run-history.md`（経過時間 ÷ 実装した要求の数） |
| 時間 | 1 回目のゲートで通った項目の割合 | 70% 以上 | `docs/run-history.md` の「1 回目のゲート通過率」 |
| Token | 要求 1 件・AC 1 件あたりの AI クレジット | Phase 1 の計測値を基準に削減 | Agent Debug Logs と使用量の表示（`run-state.py finish --credits` で記録） |
| Token | subagent が使った Token の割合 | 記録し、増え続けるなら委譲の範囲を見直す | 同上 |
| 人 | 1 回の依頼で利用者が書く Prompt の回数 | 1 回（回答があれば 2 回） | — |

## 11.3 リスクと対策（§14 の要点）

| リスク | この toolkit での対策 |
|---|---|
| 全権限の長時間実行での破壊的な操作 | New Worktree（または Dev Container）＋サンドボックス。G-5・G-6 の hook。本番の認証情報を置かない。`git_push`・`deploy` は既定で「しない」 |
| PC のスリープ・Agent Host の停止 | スリープさせない。止まったら同じ Prompt で `RESUME` |
| `/work` の削除で情報が失われる | 工程 6 で `/docs` と台帳に転記。実行中・未取り込みの run は削除しない。CHK-23 |
| hook が harness によって効かない | 同じ規則を verify で二重に検査し、統合の前に必ず実行 |
| 包括承認で意図と違う要求が実装される | 除外分野を広めに取る。決定記録に「包括承認」。報告で影響の大きい順に示し、次の Prompt で取り消せる |
| 並行実装の意味の衝突 | 同じ境界・共通部品の項目は並行しない（`queue ready`）。統合は直列でゲートを毎回通す |
| 監査の誤検知・見逃し | 決定的検査を主にし、LLM の監査は別系統のモデルで。最終は 3 回の多数決 |
| プロンプトインジェクション | 外部の文章の命令は材料として扱う（全 skill に明記）。web ツールは rd-author にだけ与える |
