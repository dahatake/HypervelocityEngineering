# 8. 導入ロードマップと KPI

## 8.1 導入の段取り

チームに導入するときの段取りです。

| Phase | 目安 | 内容 | 完了条件 | 利用者の作業 |
|---|---|---|---|---|
| 0 診断 | 2〜4 時間（無人） | 既存のリポジトリに対して rd-auditor を履歴モードで実行し、過去の矛盾がどの commit・どの Prompt から生まれたかを調べます | 矛盾ごとに、原因の commit・Prompt・仮説が挙がっている | Prompt 1 回 |
| 1 基盤 | 1〜2 日（大半は無人） | toolkit をインストールし（[README の「インストール」](../README.md#インストール)）、[README の「初回に確認すること」](../README.md#初回に確認すること) の各項目を確認します。代表的な作業（要求 3 件分）を、モデルの組み合わせ 2〜3 通り × 2 回で実行し、使うモデルを決めます | 各項目の結果が記録され、`models` が決まっている | Prompt 数回、結果の確認 |
| 2 要求定義 v1.0 | 2〜6 時間＋回答 | ドラフトを `<request>` に貼り付け、`approval_policy: 厳格`、`max_hours` を短めにして、工程 1〜2 を中心に実行します | 承認待ちのない MUST 要求群があり、直接矛盾が 0 件 | Prompt 1 回、回答 1 回 |
| 3 初回の長時間 run | 24〜48 時間（無人） | `approval_policy: 安全範囲は推奨どおり` で全工程を実行します | run-report の結果が「全件完了」か「blocked あり（理由つき）」。verify が exit 0 | Prompt 1 回、報告の確認、マージ |
| 4 チューニング | 継続 | KPI を見ながら、モデルの振り分け、`parallel_workers`、節目の間隔、skills の文面を調整します | KPI が改善している | 改善案の採否を Prompt で回答 |

### Phase 0 の依頼の例

VS Code で Agent に **rd-auditor** を選び（Copilot CLI なら `--agent rd-auditor`、GitHub Copilot app ならエージェント ピッカーか `/agent`）、次の内容を送信します。

```text
<audit_options>
scope: 全量
runs: 1
history_mode: する
</audit_options>
run-id は diag-<日付> とし、結果は work/runs/diag-<日付>/run-report.md に書いてください。
矛盾ごとに、それを生んだ commit と、その commit を作った Prompt（commit メッセージ・PR から推定）と、原因の仮説を挙げてください。
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
external_write: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```

## 8.2 KPI

効果を測るための指標です。`python scripts/kpi.py run`（1 回の run）と `python scripts/kpi.py history`（全 run）で集計できます。工程 6 では conductor が自動で集計し、run-report.md に載せます。

**North Star: 人の介入 1 回あたりの検証済み要求**（＝ 検証済み要求の数 ÷ 利用者の Prompt の数）。人の手を減らすことと、要求どおりに作り切ったと証明できることを、1 つの数で表します。介入を減らしても検証済みの要求が増えなければ上がりません。検証済みの定義は [5 章の kpi.py](05-scripts-reference.md#kpipykpi-の集計) にあります。

| 区分 | KPI | 目標の目安 | 取得元 |
|---|---|---|---|
| North Star | 人の介入 1 回あたりの検証済み要求 | 増加傾向 | `kpi.py`、`docs/run-history.md` の「人の介入」「検証済み要求」 |
| 完走 | 無人完走率（結果が「全件完了」の run の割合） | 80% 以上 | `kpi.py history` |
| 品質 | 承認済みで BLOCKED でない AC の pass 率 | 100% | `docs/run-history.md` の AC pass 率、`ledger.py summary` |
| 品質 | トレーサビリティ網羅率（承認済み要求のうち、カタログ行があり system AC がすべて台帳にあるもの） | 100% | `kpi.py run` |
| 品質 | マージ後に見つかった直接矛盾・欠陥 | 0 件 | 次回の rd-auditor |
| 品質 | system AC のカバレッジと、ダイジェストの不一致 | 100% と 0 件 | `verify.py --strict-ledger`、`rdcheck.py stats` |
| 時間 | 要求 1 件あたりの経過時間 | Phase 1 の計測値を基準に短縮 | `docs/run-history.md`（経過時間 ÷ 実装した要求の数）、`kpi.py history` |
| 時間 | 1 回目のゲートで通過した項目の割合 | 70% 以上 | `docs/run-history.md` の「1 回目のゲート通過率」 |
| Token | 要求 1 件・AC 1 件あたりの AI クレジット | Phase 1 の計測値を基準に削減 | Agent Debug Logs と使用量の表示（`run-state.py finish --credits` で記録） |
| Token | subagent が使った Token の割合 | 記録し、増え続けるなら委譲の範囲を見直す | 同上 |
| 人 | 1 回の依頼で利用者が書く Prompt の回数 | 1 回（回答があれば 2 回） | `run-state.py human` の記録（run-history の「人の介入」） |

GitHub Spec Kit など、ほかの進め方と同じ課題で比べる手順は [bench/README.md](../bench/README.md) にあります。

## 8.3 リスクと対策

主なリスクと対策です。

| リスク | この toolkit での対策 |
|---|---|
| 全権限での長時間実行中の破壊的な操作 | New Worktree（または Dev Container）＋サンドボックス。G-5・G-6 の hook。本番環境の認証情報を置かない。`git_push`・`deploy` は既定で「しない」 |
| PC のスリープ・Agent Host の停止 | スリープさせない。止まったら同じ Prompt で `RESUME` する |
| `/work` の削除による情報の消失 | 工程 6 で `/docs` と台帳に転記する。実行中・未マージの run は削除しない。CHK-23 |
| harness によって hook が効かない | 同じ規則を verify で二重に検査し、統合の前に必ず実行する |
| 包括承認によって意図と違う要求が実装される | 除外分野を広めに取る。決定記録に「包括承認」と残す。報告で影響の大きい順に示し、次の Prompt で取り消せるようにする |
| 並行実装での意味の衝突 | 同じ境界・共通部品に触れる項目は並行しない（`queue ready`）。統合は直列で、毎回ゲートを通す |
| 監査の誤検知・見逃し | 決定的検査を主にし、LLM の監査は別系統のモデルで行う。最終工程は 3 回の多数決 |
| プロンプトインジェクション | 外部の文章に含まれる命令は入力データとして扱う（全 skill に明記）。web ツールは rd-author にだけ与える |
