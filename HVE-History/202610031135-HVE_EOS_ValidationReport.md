# HVE 利用停止（EOS）の妥当性検証レポート — 「3 つの Prompt + GitHub Copilot」で企業向け大規模分散アプリを開発できるか

- 作成日時: 2026-10-03 11:35 JST
- 対象リポジトリ: `dahatake/RoyalytyService2ndGen`（調査時 HEAD `d127ca721`、作業ツリーは未コミット変更あり）
- 依頼: `hve` の開発・利用を停止し、次の 5 段階で企業向け大規模分散アプリを開発する方針の妥当性を検証する
  1. 要求定義のドラフトを Microsoft 365 Copilot / Work IQ で作る
  2. ドラフトを `[GitHub Copilot] RequirementDefinition作成.txt`（以下 **P-RD**）で要求定義にする
  3. `[GitHub Copilot] RD-FR_Prompt.txt`（以下 **P-FR**）を Agile の Wave ごとに繰り返し実行する（Wave 1 はローカルのみ、Wave 2 で Azure・スマホ・Power Platform へ展開）
  4. `[HVE]SystemTest-Run.txt`（以下 **P-ST**）でシステムテストを繰り返し実行する
  5. 人の作業は UAT だけにし、その都度 3 と 4 を実行する
  - 前提: GitHub Copilot が Plugin / MCP で使うクラウドサービスへの認証・認可は済んでいる
- 表記: 「事実」は資料・実測・公式文書で確認したこと、「推論」は事実からの判断、「未検証」は確認できていないこと
- 改訂履歴:
  - 第 1 版（2026-10-03 11:35 JST）: 初版
  - 第 2 版（2026-10-03 13:08 JST）: 利用者の判断を反映した。判断の内容は、G1 は P-ST の対象に生成アプリを加える、G2 は P-FR でデプロイなどを選べるようにする、G3 と G4 は補うべき点として採用する、G5 は catalog を markdown-query・code-query の索引で補う、の 4 つ。推奨項目を 3 つの Prompt に反映し（§6.6）、外部の論文とベストプラクティスを根拠に加えた（§4.2）
  - 第 3 版（2026-10-05 JST）: 2 つの論点を追加した。HVE で解決しようとしていた課題とその対応、および、その大半が Framework 化・アプリケーション化そのものを不要にしたこと（§5.1）。過去に開発していた 4 つのアプリケーションに費やした時間とトークン費用（§3.10）
  - 第 4 版（2026-10-05 JST）: 焦点をこのリポジトリの中に移し、HVE を使って開発しようとしていた業務アプリについて、同じ観点（時間、費用、到達点、問題）で調べた（§3.11）。§3.10 の「参考: HVE 本体」の行を、「HVE でのアプリ開発」と「HVE 本体の開発・保守・テスト」の 2 行に分け、VS Code Chat と cloud agent のセッションが集計に入っていない限界を書き足した

---

## 0. 結論

### 0.1 一言でいうと

**「HVE の開発を止める」判断は妥当です（根拠あり）。** 第 1 版では、「今の 3 つの Prompt をそのまま使う 5 段階」では、企業向けの大規模分散アプリ開発には足りない（条件付き）と判定し、5 つの不足（G1〜G5）を挙げました。第 2 版では、利用者の判断に従って、**5 つすべてを 3 つの Prompt に反映しました（§6.6）。** Prompt を増やさず、HVE も使わずに補えています。残っている条件は、**実際の業務アプリで確かめること（§9）**だけです。

| # | 不足（第 1 版） | 重大度 | 理由（要点） | 対応（第 2 版） |
|---:|---|---|---|---|
| G1 | **P-ST は生成アプリのシステムテストに使えない** | Critical | P-ST と Skill `hve-system-test`、`tests/system-test-ledger/ledger.py` は **HVE 本体（`hve/`）をテストするもの**で、生成アプリは対象外と明記されていた | **反映済み。** P-ST の既定の対象を生成アプリにした（`test_target: app`）。受入基準から作るケース台帳（JSON）、canary、増分実行、自動修正の上限、生成 AI 機能の評価テストを加えた。HVE 本体のテストは `test_target: hve` で従来どおり選べる |
| G2 | **Wave 2（Azure・スマホ・Power Platform への展開）を受け持つ Prompt がない** | Critical | P-FR は「デプロイ、有料の外部サービスの呼び出し、git push をしない」と定めていた | **反映済み。** P-FR に `<execution_options>` を追加し、push、デプロイ、デプロイ先、有料サービス、予算、外部公開を選べるようにした。既定値はすべて「しない」 |
| G3 | **合否をエージェントの自己申告だけで判定している** | Major | 過去の実測で、ATG は隠しテスト 258/564 の実装を「受理」した。外部の研究でも、自己修正の限界とテストの改変が報告されている（§4.2） | **反映済み。** P-FR に、検証スクリプト（ビルド、静的検査、全テスト、要求 ID の整合）と CI（GitHub Actions、CodeQL、依存関係の確認）を用意させ、完了の判定を検証スクリプトの exit code で行うようにした |
| G4 | **人の承認が UAT だけになっている** | Major | P-RD の成果物は「最終候補版（未承認）」で、AI 提案の要求を含む。P-FR は BLOCKED 以外の MUST をすべて実装していた | **反映済み。** P-RD に「承認依頼一覧」を出力させ、P-FR は承認済みの要求と依頼原文で明示された要求だけを実装するようにした。承認済みの要求と受入基準の文面は、実装の都合で変えさせない |
| G5 | **大規模化したときの要求定義と catalog の扱いが決まっていない** | Major | 要求定義は単一ファイル、`docs\catalog.md` も単一の表。過去の調査では、catalog が 28 ファイル・約 82 万バイトまで膨らみ、ID のずれが起きた | **反映済み。** catalog は短い対応表のまま残し、詳細は markdown-query（`mdq`）と code-query（`cq`）の索引で補う。要求 ID を `cq trace` が拾える形式（`FR-xxx`、`NFR-<区分>-xxx`）にそろえ、1 要求 1 見出しにした。分割の規則（要求 150 件、300KB、境界 3 つ）を両方の Prompt に入れた |

### 0.2 判定の内訳

| 問い | 判定 | 主な根拠 |
|---|---|---|
| HVE の開発・保守を止めてよいか | **根拠あり（妥当）** | ATG（HVE の DAG 系統を独立させたもの）は、3 つのタスクのどれでも、単一 Prompt より良い結果を出さなかった。時間は 1.7〜2.25 倍、コストは 2.49〜3.50 倍で、品質は同じ（§3.1）。「小さなエンジンへの書き直し」の調査も、律速は LLM 呼び出しと文脈量で、コード量ではないと結論している（§3.5）。HVE が独自に作っていた仕組みの多くは、GitHub Copilot 本体の機能（Autopilot、`/fleet`、hooks、cloud agent の plan 承認、Automations、Skills）で置き換えられる（§4.1）。外部の研究も、単純な構成が複雑なエージェントに並ぶか上回る例を報告している（Agentless、Anthropic。§4.2）。過去の 4 つのアプリは、いずれも HVE を使わずに作られていた。記録のある期間だけでも、このリポジトリで使った AI の費用（HVE でのアプリ開発と HVE 本体の合計 290,602 AIU）は、4 アプリの合計（209,521 AIU）の約 1.39 倍だった（§3.10） |
| HVE で開発しようとしていたアプリは完成したか | **完成していない（根拠あり）** | このリポジトリの業務アプリ（14 サブアプリ）は、ローカルの HVE 実行だけで 85.6 時間・109,547 AIU を使ったが、アーキテクチャ推薦は 14 件すべてで中断し、システムテストの総合判定は「INCOMPLETE・BLOCKED」だった。同じ時期に HVE なしで作った 4 つのアプリは、実行や受入の記録がある状態まで進んでいる。規模の差があるため、HVE だけが原因とは言えない（§3.11） |
| HVE で解決しようとしていた課題に、今も Framework やアプリケーションが要るか | **大半は不要（根拠あり）** | 10 の課題のうち 7 つは Copilot 本体の機能か運用の規則で済み、3 つ（合否の判定、要件索引、予算）も、リポジトリごとの検証スクリプト・CI・持ち出せる索引ツール・Enterprise の予算設定で済む。Framework として作り続ける必要がある課題は残っていない（§5.1） |
| 単一の Prompt で中〜大規模の実装を完成できるか | **根拠あり（範囲付き）** | 要求定義 4,458〜9,908 文字の 2 タスクを、1 回の依頼で 100% 完成した（隠しテスト 74/74、225/225）。モデルの単独能力を超えるタスクでも、「300 行以内に分けて書く」という 1 文で、完成率が 1/3 から 2/3 に上がった。この 1 文は P-FR に含まれている |
| 企業向けの大規模分散アプリを、提示の 5 段階で作れるか | **条件付き（第 2 版で Prompt 上の不足は解消。残る条件は実地での確認）** | G1〜G5 は Prompt に反映した（§6.6）。既存コードへの繰り返し変更、複数サービス、Wave 2 の展開、生成アプリのシステムテストの有効性は、まだ実測していない（§9） |
| 人の作業を UAT だけにできるか | **不可（ただし 2 点に集約できる）** | 要求の承認、課金・公開を伴う展開の承認、PR のマージは、ツールの仕様上も、統制上も人に残る（§6.5）。第 2 版の Prompt では、人の作業を「Wave の始めの承認（承認依頼一覧を見て決める）」と「Wave の終わりの UAT とマージ」の 2 点に集約した |

### 0.3 推奨

1. **HVE の開発は止めます。** 再利用できる資産（Skill、markdown-query と code-query の導入キット、Prompt の知見、検証規約）だけを残し、`hve/` 本体の保守は終了します（§10.4）。
2. **Prompt は 3 本のまま使います（第 2 版で改訂済み）。** 第 1 版で追加を提案した 3 本は、利用者の判断に従って既存の 3 本に吸収しました。要求承認チェックは P-RD の「承認依頼一覧」と P-FR の「承認済みだけを実装」に、展開は P-FR の `<execution_options>` に、生成アプリのシステムテストは P-ST に入れています（§10.1）。
3. **合否はエージェントの外で決めます。** P-FR が作る検証スクリプトと CI が、その役割を持ちます。必要に応じて、`agentStop` hook（失敗時に作業を続けさせる）と `preToolUse` hook（危険な操作の拒否）を加えます（§10.2）。
4. **最初の Wave で実地確認をします。** 小さな業務アプリで Wave 1（ローカル）と Wave 2（dev 環境へのデプロイ）を 1 回ずつ通し、§9 の U1〜U6 を測ります。

---

## 1. 調査の範囲と方法

| 区分 | 対象 | 方法 |
|---|---|---|
| 提案された Prompt | P-RD（137 行）、P-FR（135 行）、P-ST（11 行） | 全文を読んだ |
| 過去の調査レポート | `work/` の調査レポート 120 件（ATG、DAG、長時間タスク、自律 Prompt、Harness、要件索引、モデル比較、Orchestrator レビュー、Work IQ、Managed Runtime など） | commit `de2adffe0`（2026-10-01）で `work/` から削除されていたため、`de2adffe0~1` から復元して読んだ。主要なレポートは本文を読み、敵対的レビューは判定だけを確認した |
| 現行の `work/` | `202610020340-UnknownIssueBehaviorAnalytics.md`、`202610030920-HVE-FolderStructure.md`、`20261003-SystemTestPlanAnalytics.d/report.md` | 結論部を読んだ |
| HVE 本体 | `README.md`、`hve/workflow_registry.py`、`hve/` のモジュール構成、`hve-dev/requirement-definition.md` の見出し、`.github/skills/hve-system-test/SKILL.md`、`tests/system-test-ledger/ledger.py` | 棚卸しした |
| GitHub Copilot の現状 | GitHub Docs と GitHub Changelog（確認日 2026-10-03） | 一次資料の本文を取得した。二次資料（ブログ等）は根拠にしていない |
| 外部の論文とベストプラクティス（第 2 版） | 査読論文と arXiv の論文、Anthropic・OpenAI・METR・Chroma の技術文書、OWASP、NIST、ISO、Microsoft Learn、GitHub Docs、Playwright（確認日 2026-10-03） | 本文か要旨を、筆者または調査用のサブエージェントが取得できたものだけを根拠にした。だれがどの範囲（本文／要旨）を確認したかを §4.2 の表に書いた |
| 過去に開発していたアプリ（第 3 版） | `C:\GitHub\AutoVision-Studio`、`C:\GitHub\StudyReport-Evaluator`、`C:\GitHub\Optoronics-Studio-Demo`、`C:\GitHub\HubRadio-MovieCreator` の `work/`（作業中の一次情報）、`docs/`、Git 履歴 | `work/` の実行計画・実行記録・分析レポートを読み、Git の commit 数と活動日を数えた。Optoronics-Studio-Demo には `work/` がなかったため、`docs/` の配置記録と受入結果を読んだ |
| HVE で開発しようとしていたアプリ（第 4 版） | このリポジトリの `docs/`、`src/`、`knowledge/`、`qa/`、`docs-original/`、`tests/run/` のシステムテストの証跡、削除済みの `work/20260918-LongTimeTaskAnalytics.md`、GitHub の Issue 610 件・PR 1,315 件 | 業務アプリの範囲と到達点を読み、アプリのパスと Framework のパスで Git 履歴を分けて数えた。セッション履歴を、HVE の Workflow 実行（アプリ開発）とそれ以外（HVE 本体）に分けて集計した（§3.11） |
| Copilot のセッション履歴（第 3 版） | `%USERPROFILE%\.copilot\session-state\*\events.jsonl` と `workspace.yaml`（2,086 セッション） | 作業フォルダーが各リポジトリのセッションを選び、稼働時間・AIU・Premium Request を集計した（集計日 2026-10-05。§3.10） |
| markdown-query と code-query（第 2 版） | `.github/skills/markdown-query/SKILL.md`、`.github/skills/code-query/SKILL.md` と `references/cli-reference.md`、`cq/traces.py`、`tools/skills/code_query/README.md` | 仕様を読み、`cq.traces.extract` に新しい ID 形式を与えて動作を確かめた（§6.6） |

**限界:** 本レポートでは新しい実験はしていません。数値は、過去のレポートの実測値か、外部資料に書かれた値です。第 3 版では、既に残っていた Copilot のセッション履歴と Git 履歴を集計しました（§3.10）。Microsoft 365 Copilot と Work IQ でドラフトを作る段階（手順 1）は、過去の Work IQ 調査で間接的に評価しただけです。第 2 版で改訂した Prompt は、まだ実際のアプリ開発で実行していません（§9）。

---

## 2. 提案された 5 段階の整理

この表の評価は第 1 版のものです。第 2 版での対応は §6.6 にまとめています。

| 段階 | 実行するもの | 入力 | 出力 | 人の役割（提案） | 本レポートの評価 |
|---|---|---|---|---|---|
| 1 | Microsoft 365 Copilot / Work IQ | 会議・メール・文書 | 要求定義のドラフト | ドラフトの依頼 | 妥当。ただし、Work IQ の検索で見つかる割合は低かった（§3.7） |
| 2 | P-RD | ドラフト、社内情報、公式資料 | `docs\requirements-definition.md`（最終候補版・未承認） | なし | 内容は高品質。**人の承認が抜けている**（G4） |
| 3 | P-FR（Wave ごとに繰り返す） | 要求定義、`docs\catalog.md`、依頼 | コード、テスト、更新した要求定義と catalog | なし | Wave 1 は妥当。**Wave 2 は範囲外**（G2）。**合否の判定は自己申告**（G3） |
| 4 | P-ST（繰り返す） | 台帳 | テスト結果、自動修正の commit | なし | **対象を誤っている**（G1） |
| 5 | 人 | 動くアプリ | UAT の判定 | UAT | UAT 以外にも人の作業が残る（G4） |

---

## 3. 証拠 1: 過去の実測（ATG・DAG・長時間タスク）

### 3.1 ATG あり／なしの比較（`202609271600-ATG-BusinessImpactAnalytics.md` §0）

実測環境は GitHub Copilot CLI 1.0.88、Windows、モデル `claude-opus-5.5` です。C1 は「ATG を使わない 1 回の依頼」、C2 は「ATG あり」を指します。

| タスク | 要求定義の文字数 | 隠しテスト | 完成率 C1 → C2 | 時間 C1 → C2 | クレジット C1 → C2 |
|---|---:|---:|---|---|---|
| 1: 家計簿 CLI | 4,458 | 74 | 2/2 → 2/2 | 328.8 → 738.3 秒（2.25 倍） | 47.8 → 167.2（3.50 倍） |
| 2: 表計算エンジン | 9,908 | 225 | 3/3 → 3/3 | 1,879.8 → 3,221.1 秒（1.71 倍） | 254.5 → 634.3（2.49 倍） |
| 3: SQL エンジン（medium） | 7,155 | 564 | **1/3 → 0/3** | 7,876.5 → 8,120.7 秒 | 1,620.7 → 1,914.8 |
| 3: 分割の 1 文を追加（C1S → C2S） | 同上 | 同上 | **2/3 → 2/3** | 7,350.5 → 6,234.0 秒 | 1,572.0 → 1,528.2 |

- 事実: 同レポートは「測った範囲では、『モデルの進化によって ATG の役割は不要になった』という判断を支持します」と結論しています（§0.1）。
- 事実: 推奨 Prompt は「要求定義を最後まで完成させてください。私は途中で応答しません。…」の 1 文です。大規模な場合は「1 回のツール呼び出しで書き込む内容は 300 行以内」を足します（§0.4）。**P-FR はこの 2 つを両方含んでいます。** P-FR は、この実測の結論を正しく反映した Prompt です。
- 事実（前提）: 同レポートの推奨には、3 つの前提があります。要求定義がファイルであること、完了条件が exit code で判定できること、Autopilot で実行することです（§0.4）。

### 3.2 単一セッションが失敗する仕組み

- 事実: タスク 3 の失敗では、実装の段階でモデルが 1 回の応答の出力上限（32,000 トークン）をすべて推論に使い切り、ツールを呼べないままターンが終わることが繰り返されました。推論トークンが出力に占める割合は 95.7% でした（同 §0.1、§6.4）。
- 事実: ATG ありでも、なしでも、同じ仕組みで失敗しました。オーケストレータを足しても、この失敗は防げませんでした。
- 推論: **効いたのは「書き込みを小さく分ける」指示と、「タスクそのものを小さく分ける」ことです。** 提案の「Agile の Wave で少しずつ依頼する」運用は、後者を人の側で行っていることになり、この実測と整合します。

### 3.3 モデルの差（`202609300906-Opus55-vs-Sonnet55-ModelComparison.md` §0）

- 事実: Sonnet 5.5 の平均総時間は Opus 5.5 の 0.41 倍（表計算）と 0.56 倍（SQL）でした。SQL の完成率は Opus 3/6、Sonnet 5/6 です。完成した実装の隠しテストは Opus 561.3/564、Sonnet 557.4/564 でした。
- 事実: 分割を明示しない C1 は、Sonnet でも 1/3 が失敗しました。分割した C1S は 3/3 成功しました。
- 推論: 既定は Sonnet 5.5 + 分割指示とし、難しい設計判断だけ上位モデルを使うのが、時間とコストの面で合理的です（n が少ないため、確定的な差ではありません）。

### 3.4 長時間化の原因（`20260921-LongTimeTaskAnalytics2.md` §2.4）

- 事実: 最長のステップは 88.7 分以上かかりました。そのうち LLM の推論時間は 16 回で合計 7.3 分、**LLM 以外の時間が 81.4 分（91.8%）**でした。入力コンテキストは 45,805 から 103,596 トークンへ、2.26 倍に増えています。
- 推論: 長時間化の主な原因は、ツールの実行、承認待ち、直列実行、文脈の肥大です。HVE のような外部オーケストレータは、その一部（直列実行）を改善できても、ほかの原因には効きません。

### 3.5 オーケストレータを小さく書き直す案（`20260924-2154-DAG-ATG-Unification-SmallEngine-Rewrite-Report.md` §0、§2.5、§5）

- 事実: ATG は 13 の Python ファイル（2,354 行）で、依存ライブラリはありません。HVE の外でも動きます（14 種類の CLI 実行形式で exit 0。`20260923-0040-atg-standalone-porting-guide.md` §2）。
- 事実: 同レポートは、全面的な書き直しを推奨していません。エンジンを小さくしても速度はほとんど改善しないためで、律速は LLM 呼び出し、文脈の量、制御の判断、直列性にあるとしています。

### 3.6 検証の空白（偽の PASS）

- 事実: `atg node finish` は `verify_command` を実行せず、handoff に書かれた `exit_code: 0` をそのまま受け入れていました。スタブ実装と `assert True` でも `succeeded` になりました（`20260923-2030-HarnessDesignLongTimeApplicationDevelopment-ATG-AnalyticsReport-v2.md` §1、F-01、F-02）。
- 事実: `accepted=1` のまま、隠しテスト 258/564 の実装を受理した例があります（`202609271600-ATG-BusinessImpactAnalytics.md` §0.3）。
- 事実: 「指示があることをテストしても、エージェントがその指示を守ったことは証明できない」（`20260921-1200-TaskCompletionDefinitionReport.md` §3.2）。
- 推論: **合否は、エージェントが書く文章ではなく、エージェントの外で実行したコマンドで決める必要があります。** これは HVE を使っても使わなくても同じで、HVE を止めても新たに失うものではありません。ただし、P-FR だけではこの仕組みがない（G3）ことになります。

### 3.7 Work IQ（`2026100108115_WorkIQ-RemovelResearch.md` §3.3、§5）

- 事実: 固定の質問で問い合わせる方式では、35 件中、見つかった（FOUND）5 件（14%）、一部（PARTIAL）4 件（11%）、見つからない（NOT_FOUND）23 件（66%）、使えない（UNAVAILABLE）3 件（9%）でした。情報がテナントに存在しない可能性もあり、方式だけが原因とは断定していません。
- 事実: 同レポートの結論は、Work IQ を否定するものではありません。HVE 専用の Work IQ オーケストレーションを撤去し、探索エージェントに `retrieve` を優先した反復調査を任せる、というものです。
- 推論: 手順 1 で Microsoft 365 Copilot / Work IQ を「ドラフト作成者」として使い、P-RD の中で「見つからなければ『社内情報未確認』と記録して進む」方針は、この結論と整合します。

### 3.8 Managed Runtime（`202610011000-MicrosoftCopilotManagedRuntime-AdoptionResearch.md` §6〜§7）

- 事実: 調査時点では、Microsoft Copilot Managed Runtime は HVE の実行エンジンを置き換えられないと判定されていました。理由は、実験的な API で、ローカルリポジトリの編集、権限コールバック、`output_paths` ゲートなどを満たさないためです。
- 推論: これは「HVE を何で置き換えるか」の評価です。本件は「HVE を置き換えずに、GitHub Copilot 本体を直接使う」案なので、この結論は本件の判定を妨げません。

### 3.9 HVE を見直したときの結論（`202609300940-HVE-OrchestratorReview.md` §5）

- 事実: HVE には重複したステップ、過剰な指示、複雑な経路があり、削れるとしています。一方で、**複数のエージェントは文脈を共有しないので、ファイルとしての要件索引だけが共有状態になる**とし、要件索引と決定的な検査は必要だとしています。
- 推論: 必要とされたのは「HVE」ではなく、「機械可読な要件索引」と「決定的な検査」です。P-FR の `docs\catalog.md`（要求 ID → 実装 → テスト → API）は前者の最小形です。後者は G3 で補います。

### 3.10 過去のアプリ開発に費やした時間とトークン費用（第 3 版で追加）

HVE の開発と並行して、利用者は 4 つのアプリを GitHub Copilot で開発していました。各リポジトリの `work/`（作業中の一次情報）と Git 履歴、Copilot のセッション履歴を集計しました（集計日 2026-10-05）。

| アプリ（リポジトリ） | 概要 | Git の期間 | commit 数（活動日） | HVE の利用 | DAG 系（ATG）の利用 | セッション数 | 稼働時間 | AIU | Premium Request | 金額の目安 |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|
| AutoVision-Studio | 画像分類・物体検出の教師データ作成、ローカル学習、カメラ推論を端末内で行う Windows デスクトップアプリ | 2026-09-02〜09-29 | 87（10 日） | なし（`work/20260922-1340-Gate2LaneAdoption.md` 19 行目） | ATG の kit と Skill を導入したが、22 セッションで呼び出しは 0 回。2026-09-29 に削除（commit `a74c95a`） | 30 | 63.3 時間 | 100,794 | 587.5 | 約 1,008 USD |
| StudyReport-Evaluator | Excel のレポート回答を Copilot で定量評価し、別の Excel に結果を出す Windows デスクトップアプリ | 2026-08-31〜10-01 | 124（18 日） | なし（`work/202609240830-RemainTaskExecutionPlan.md` 257 行目） | なし | 27 | 40.6 時間 | 33,999 | 136 | 約 340 USD |
| Optoronics-Studio-Demo | 受注・BOM・在庫・発注・試験・納品を共有する生産管理デモ。Azure へデプロイし、根拠付きの AI チャットを持つ | 2026-10-02 の 1 日 | 3（1 日） | 記録なし（`work/` がない） | なし | 2 | 5.3 時間 | 7,747 | 33 | 約 77 USD |
| HubRadio-MovieCreator | 対談・インタビュー動画から、長尺版・短尺候補・字幕・サムネイルを作る編集支援アプリ | 2026-08-26〜10-03 | 216（21 日） | なし（`work/20260922-1410-Wave3-ApprovedMediaAcceptance.md` 11 行目） | ATG の実行を少なくとも 3 回作った（うち 1 回は破棄。`work/20260924-0330-P4-Execution-Log.md` 4 行目、55 行目） | 18 | 45.4 時間 | 66,981 | 309 | 約 670 USD |
| **4 アプリの合計** | | | 430 | | | 77 | **154.6 時間** | **209,521** | 1,065.5 | **約 2,095 USD** |
| 参考: HVE で開発しようとした業務アプリ（このリポジトリ。§3.11） | 会員・ポイント・特典などを扱う 14 のサブアプリからなる業務システム | 2026-01-24〜10-02（アプリのパス） | 944（135 日） | HVE で開発 | HVE の DAG・`/fleet` | 381 | 85.6 時間 | 109,547 | 1,665 | 約 1,095 USD |
| 参考: HVE 本体の開発・保守・テスト（このリポジトリ） | Copilot を Workflow / DAG で段階実行させる Framework | 2026-01-24〜10-03（Framework のパス） | 1,740（176 日） | — | — | 429 | 143.3 時間 | 181,055 | 1,346.5 | 約 1,811 USD |

集計の定義と検証:

- 稼働時間は、メインエージェントの `assistant.turn_start` から `assistant.turn_end` までの区間を重ねずに合算した時間です。人の待ち時間は含みません。AIU は、セッションごとの `session.usage_checkpoint` / `session.shutdown` の `totalNanoAiu` の最大値を 10^9 で割って合算した値で、サブエージェントの分を含みます。Premium Request は `totalPremiumRequests` の最大値の合算です。対象は、`workspace.yaml` の `cwd` / `git_root` が各リポジトリ（とその派生 worktree）のセッションです。集計スクリプトは、セッションの作業フォルダーの `files/agg_usage.py` にあります。
- 事実（集計の検証）: AutoVision-Studio の既存の分析（`work/20260923-0945-ATG-AnalyticsReport.md` §1、§5.2。22 セッション、48,133 AIU）と同じ時点（2026-09-23 09:45 JST）で区切って集計し直すと、22 セッション・47,472 AIU で、差は 1.4% でした。
- 金額の目安（推論）: GitHub Copilot の課金単位は AI Credits で、1 AI Credit = 0.01 USD です（GitHub Docs "GitHub Copilot billing"、確認日 2026-10-05）。AIU を AI Credits と同じ単位とみなして換算しました。プランに含まれる分を差し引いた実際の請求額ではありません。§3.1 の「クレジット」も同じ単位とみなしています。
- 限界（事実）: セッション履歴は、AutoVision-Studio と HubRadio-MovieCreator では 2026-09-21 以降、StudyReport-Evaluator では 2026-09-24 以降しか残っていません。Git の活動はそれより前から始まっているので、表の値は **下限** です。`work/` にトークンと費用の記録はありませんでした（AutoVision-Studio の分析レポートを除く。StudyReport-Evaluator は「AI Credits への換算は未確定」と記録。`work/20260917-job-cost-execution-audit.md` 16〜18 行目）。Optoronics-Studio-Demo のアプリ自体の AI 機能（Azure OpenAI）の評価費用 56.57 円は、表とは別です（`docs/acceptance-results.md` 15 行目）。このリポジトリの 2 行は、2026-10-04 までのセッションで区切り、HVE が起動した SDK セッションのうちリポジトリ直下で動いたもの（Workflow の実行）をアプリ、それ以外（対話セッション、`tests\run\` の中で動いた HVE のシステムテスト、検証用の worktree）を Framework に分けました。対話セッションには、本レポートを含む調査・実験も入っています。Git の commit 数は、アプリのパス（`docs` `src` `knowledge` `qa` `docs-original` `docs-generated` `sample`）と Framework のパス（`hve` `hve-dev` `tests` `.github`）で数えたもので、両方にまたがる commit があるため合計は全体（4,773）と一致しません。第 3 版の「参考: HVE 本体」の行（289,733 AIU）は、この 2 つを合わせた値でした。
- 限界（事実、第 4 版で追加）: ローカルのセッション履歴には、VS Code Chat のセッションと、GitHub 上の Copilot cloud agent のセッションが含まれません。過去の分析では、VS Code Chat の 1 セッションで入力 26.8 億トークン・94.9 時間に達した例が HubRadio-MovieCreator にあり、このリポジトリにも 63.8 時間の例がありました（`20260918-LongTimeTaskAnalytics.md` §2-2。`de2adffe0~1` から復元）。表の値は、どの行も実際より小さい可能性が高いです。

わかったこと:

- 事実: 4 つのアプリは、いずれも HVE を使わずに作られていました。DAG 系の ATG は 2 つのアプリで試しましたが、AutoVision-Studio では一度も呼ばれないまま削除されました。
- 事実: AutoVision-Studio の分析では、費用の最大の要因は、1 セッションに作業を詰め込んだ長大セッション（Wave 3 の 1 セッションが 14,909 AIU で全体の 31%）と、広範囲の敵対的レビュー（上位 6 件で 24.9M トークン、サブエージェントのトークンの 52%）でした。オーケストレータがあれば防げた重複実行は 494 AIU（全体の約 1%）でした（同レポート §4.1、§4.2、§5.2）。
- 事実: Optoronics-Studio-Demo は、HVE も ATG も使わずに、1 日・稼働 5.3 時間・7,747 AIU で、Azure へのデプロイと AI 評価まで行っていました（`docs/deployment-record.md`、`docs/acceptance-results.md`）。ただし、実機での同時接続の計測などは受入待ちです（同 32 行目、36 行目）。
- 推論: 記録のある期間だけでも、このリポジトリで使った AIU（HVE でのアプリ開発と HVE 本体の合計 290,602）は 4 アプリの合計の約 1.39 倍、稼働時間（228.9 時間）は約 1.48 倍でした。HVE 本体の開発・保守だけでも、4 アプリの合計の約 0.86 倍の AIU を使っています。**アプリを作る費用と同じくらいの費用を、アプリを作るための仕組みに使い、その仕組みで作ったアプリは完成しなかった**ことになります（§3.11）。
- 推論: 費用を下げるのは、オーケストレータではなく、Wave を小さく分けること、レビューを変更の範囲に絞ること、既定のモデルを Sonnet 5.5 にすること（§3.3、§10.5）です。HVE を止めた後は、同じ定義（稼働時間、AIU、Premium Request）で Wave ごとに測り、この表と比べます（§9 の U6）。

### 3.11 HVE で開発しようとしていたアプリ（このリポジトリ）の時間・費用と到達点（第 4 版で追加）

§3.10 の 4 つのアプリは HVE を使っていませんでした。一方、このリポジトリには、**HVE を使って開発しようとしていた業務アプリ**の成果物（`docs/`、`src/`、`knowledge/`、`qa/`、`docs-original/`）が入っています。同じ観点（何を作ろうとしたか、どれだけの時間と費用を使ったか、どこまで届いたか、何が問題だったか）で調べました（調査日 2026-10-05、HEAD `e71c4b123`）。

**対象のアプリ**

- 事実: グローバルなロイヤルティプログラム事業を対象に、会員・同意・ポイント・特典・顧客データ・AI 施策・有料会員・パートナー・サポート・不正・財務・監査をまとめて扱う業務システムです（`docs/business-requirement.md` 1〜3 行目）。対象企業は特定していません。
- 事実: 14 のサブアプリ（APP-001 会員 ID・同意・データ権利管理 〜 APP-014 不正検知・調査ケース管理）と、26 のユースケース（UC-01〜26）に分けられています（`docs/catalog/app-catalog.md` 94〜107 行目）。

**時間と費用**

| 期間 | 開発の方法 | 記録 | 時間 | 費用 |
|---|---|---|---|---|
| 2026-01-24〜03-05 | 業務要求・将来シナリオの文書作成 | アプリのパスの Git 履歴 | 2026-01-24〜10-02 に 944 commit・活動 135 日（全体を通して） | 未測定 |
| 2026-03-09〜06-22 | GitHub の Issue から Copilot cloud agent で Workflow の Step を実行 | タイトルに APP-ID か Workflow ID を含む Issue 168 件（全 610 件中）。アプリのパスの commit の作者は `copilot-swe-agent[bot]` 480 件、`Copilot` 126 件、人 333 件 | 未測定 | **未測定**（cloud agent のセッションはローカルの履歴にない） |
| 2026-07-06〜09-08 | ローカルの HVE（Copilot SDK）で Workflow を実行 | 55 run・381 セッション・活動 23 日 | 稼働 **85.6 時間** | **109,547 AIU（約 1,095 USD）**、Premium Request 1,665 |
| 2026-10-01〜10-03 | HVE のシステムテストとして ARD・AAS・AAD-WEB・ASDW-WEB を再実行 | 32 run・206 セッション（§3.10 では Framework 側に数えた） | 稼働 16.2 時間 | 4,723 AIU |

ローカルの HVE 実行（2026-07-06〜09-08）の Workflow 別の内訳:

| Workflow（Custom Agent の系統） | セッション | 稼働時間 | AIU | 割合 |
|---|---:|---:|---:|---:|
| ASDW-WEB: UI の実装・UI テスト・UI のデプロイ（主に APP-009 の画面） | 161 | 37.6 時間 | 43,400 | 40% |
| ASDW-WEB: データの設計・テスト・デプロイ | 58 | 14.7 時間 | 24,109 | 22% |
| `/fleet`（HVE の run の中から起動） | 7 | 1.5 時間 | 17,348 | 16% |
| AAS・AAD-WEB などの設計 | 43 | 10.1 時間 | 9,832 | 9% |
| ARD | 30 | 6.3 時間 | 6,548 | 6% |
| ASDW-WEB: サービス・追加サービス・Compute | 21 | 7.0 時間 | 4,600 | 4% |
| ADI・ADFD・不明 | 61 | 8.4 時間 | 3,710 | 3% |
| **合計** | **381** | **85.6 時間** | **109,547** | 100% |

- 集計の方法: セッション ID（`hve-<run-id>-step-...`）で run を、最初の指示に含まれる `work/run/<run-id>/<Custom Agent>/` で Workflow の系統を判定しました。集計スクリプトは、セッションの作業フォルダーの `files/agg_hve_runs.py` です。

**到達点**

- 事実: 設計の文書は、14 サブアプリの要求定義（`docs/architectural-requirements-app-001.md`〜`014.md`）、ユースケース 25、画面 8、サービス 9、データフロー 5、テスト仕様 25 のファイルまで作られました。
- 事実: AAS のアーキテクチャ推薦は、**14 サブアプリのすべてで「入力不足のため判定中断」**でした（`docs/catalog/app-arch-catalog.md` 10 行目、16〜29 行目）。
- 事実: 実装（`src/`、2026-03-06 開始）は 247 ファイル（C# 約 10,600 行、JavaScript 約 8,100 行など）で、テストのソースは 113 ファイルでした。明確に実装があるのは APP-009（会員セルフサービス／サポート）とその周辺のサービスです。
- 事実: 2026-09-16 のシステムテストの総合判定は **「INCOMPLETE・BLOCKED（全体 PASS ではない）」** でした。機能の受入、要件の coverage、E2E、修正後の安定性は未完了で、Azure のデータのデプロイは実行されていません（`tests/run/20260916-systemtest-summary/systemtest-report/README.md` 3 行目、101〜102 行目）。
- 事実: 2026-10-02〜03 の再実行では、4 ケース中 2 件（ARD、AAS）が失敗しました。AAS の Step 1 は 932 秒で失敗し、AAD-WEB は 616.7 AIU・498 リクエスト・ツールの失敗 61 件、ASDW-WEB の Step 1.1 だけで 1,601 秒・265.0 AIU・1,000 リクエストでした（`tests/run/20261002T2237-ledger/system-test-ledger/artifacts/run-summary.json`、同 `evidence/CASE-*/run.stdout.log`）。
- 事実: アプリのパスでは、ファイルを削除した commit が 53 件あり、削除されたファイルは `src` で延べ 1,525、`docs` で延べ 1,349 でした。Workflow を回し直すたびに、成果物を作り直していました。

**HVE で開発したときに起きた問題**

| 問題 | 記録 | §5.1 の課題 |
|---|---|---|
| Workflow の Step が多く、1 回通すだけで長い | 1 Step は約 7〜18 分・約 5〜10 AIU。全 131 Step を直列で通すと約 15〜39 時間・655〜1,310 AIU の試算（`work/20261003-SystemTestPlanAnalytics.d/report.md` 26〜27 行目） | 1、2、6 |
| 前の Step の成果物が不足すると、後ろの Step が止まる | AAS が 14 サブアプリすべてで判定中断。2026-09-21 の Prompt 版のテストは、44 ケースのうち実行 5 件が全件 FAIL、29 件が未実行、10 件が Azure の承認待ち（同 36 行目） | 4、6 |
| 費用が UI テストの生成に偏る | ASDW-WEB の UI 系が 43,400 AIU で、ローカル実行の 40%。画面ごとに TDD の RED（テストだけ先に作る）を回していた | 9、10 |
| 合否を全体で判定できない | 「各 Step の Token / AI Credit、実際のツール呼び出し、性能目標は、全体の有効な集計なし」（`systemtest-report/README.md` 102 行目） | 8、10 |
| 作り直しが多い | 削除 commit 53 件、`src` の削除が延べ 1,525 ファイル | 3、9 |

- 推論: HVE で開発しようとした業務アプリは、ローカルの HVE 実行だけで 85.6 時間・109,547 AIU を使い、cloud agent の期間（Issue 168 件）を合わせると約 9 か月かけましたが、**動くアプリには届きませんでした**。設計の文書は多く作られましたが、アーキテクチャの推薦は 14 件すべてで中断し、実装は 1 つのサブアプリが中心で、E2E に届いていません。
- 推論: 比べると、HVE を使わなかった 4 つのアプリ（§3.10）は、合計 154.6 時間・209,521 AIU で、4 つとも実行や受入の記録がある状態まで進んでいます。**同じ利用者・同じ時期・同じ Copilot で、HVE を通したアプリだけが完成していません。**
- 留保: 規模が大きく違います。この業務アプリは 14 のサブアプリからなる企業向けのシステムで、§3.10 の 4 つは単体のアプリです。また、HVE でのアプリ開発には、HVE 自体を試すための実行も含まれます。したがって「HVE が原因で完成しなかった」とまでは言えません。言えるのは、**HVE の Workflow を順に回す方式では、大きなアプリでも完成に近づかず、時間と費用の多くが成果物の生成と作り直しに使われた**ことです。これは、§3.1（ATG を足しても品質は変わらず、時間と費用が増えた）と同じ方向です。

---

## 4. 証拠 2: GitHub Copilot 本体の機能と、外部の研究・ベストプラクティス

### 4.1 GitHub Copilot 本体で使える機能（GitHub Docs、確認日 2026-10-03）

HVE を作り始めた頃に GitHub Copilot 本体になかった仕組みの多くが、現在は公式機能になっています。

| 公式機能 | 内容（公式文書の記載） | HVE で対応していた機能 | 出典 |
|---|---|---|---|
| CLI Autopilot | 完了と判断するまで自律的に続ける。既定では自動継続 5 回で一時停止し、`--max-autopilot-continues` で上限を変えられる | 無人での連続実行 | [autopilot](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot) |
| `/fleet` | 計画を独立した小タスクに分け、依存関係を見て、サブエージェントで並列に実行する。サブエージェントはそれぞれ別のコンテキストウィンドウを持つ。並列化するとクレジットの消費が増え得る | DAG による Wave 分割と並列実行 | [fleet](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet) |
| Hooks | `agentStop` は「block して継続を強制できる」。`preToolUse` はツールの実行を許可・拒否・変更できる。`postToolUseFailure` は回復の手引きを注入できる。`.github/hooks/*.json` に置き、CLI と cloud agent の両方で動く | 継続判定、安全ゲート、`output_paths` ゲート、監査ログ | [hooks](https://docs.github.com/en/copilot/concepts/agents/hooks)、[hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference) |
| Cloud agent の research / plan / branch | リポジトリの調査、実装計画の作成と承認、PR を作らないブランチでの反復ができる | 計画の承認ゲート（SHA-256）、Cloud Agent での Issue 実行 | [Changelog 2026-04-01](https://github.blog/changelog/2026-04-01-research-plan-and-code-with-copilot-cloud-agent/)、[about cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent) |
| Cloud agent の安全策 | CodeQL、Advisory Database、Secret scanning で自動検査する。push 先は 1 ブランチに限られ、PR のマージには人のレビューが必要。インターネットへのアクセスは firewall で制限される。commit は署名され、セッションログと監査ログが残る | 安全境界と証跡 | [risks and mitigations](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/risks-and-mitigations) |
| Automations | 定期実行、または Issue・PR のイベントで cloud agent を起動する。使えるツールを選んで範囲を絞れる。private / internal のリポジトリだけで使え、Git では版管理されない | 定期実行、自動修正 | [about automations](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-automations) |
| Custom instructions / Agent skills / MCP | リポジトリの指示、Skill、MCP サーバーを CLI と cloud agent が読み込む | Prompt と Skill の配布、MCP の利用 | [about cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent) |
| 課金 | cloud agent は GitHub Actions の分数と AI Credits を使う。CLI もトークン量に応じて AI Credits を使う | 予算と AIU の管理 | 同上、[autopilot](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot) |

- 推論: HVE の主な付加価値だった「継続」「並列」「承認」「安全ゲート」「証跡」は、公式機能でほぼ置き換えられます。HVE を独自に保守し続ける理由は弱まっています。
- 注意（事実）: Autopilot の自動継続は、**既定で 5 回まで**です。P-FR を無人で最後まで流すには、上限を上げるか、`agentStop` hook で継続を判定する必要があります。

### 4.2 外部の論文とベストプラクティス（第 2 版で追加。確認日 2026-10-03）

「確認」の列の意味は次のとおりです。「本文」は筆者が本文を読んだもの、「要旨」は筆者が arXiv API などで要旨を読んだもの、「本文（調査）」は調査用のサブエージェントが本文を読み、筆者は題名・URL・主張の対応だけを確かめたものです。

| # | 主張 | 出典 | 確認 | 本件への含意 | 反映先 |
|---:|---|---|---|---|---|
| E1 | うまくいった実装の多くは、複雑なフレームワークではなく、単純で組み合わせやすい部品で作られていた。複雑さは、必要なときだけ足すべき | Anthropic, "Building effective agents", 2024, https://www.anthropic.com/engineering/building-effective-agents | 本文（調査） | 独自のオーケストレータ（HVE）より、Prompt と公式機能の組み合わせを優先してよい | HVE 停止の判定（§0.2） |
| E2 | 「位置特定 → 修正 → 検証」の 3 段の単純な手順（Agentless）が、SWE-bench Lite で既存のオープンソースのエージェントより高い性能（32.00%）と低いコスト（0.70 ドル）を出した | Xia et al., "Agentless: Demystifying LLM-based Software Engineering Agents", arXiv:2407.01489, 2024 | 要旨 | 複雑なエージェントが必ずしも有利ではない。ATG の実測（§3.1）と同じ方向 | HVE 停止の判定 |
| E3 | 複数エージェントの調査システムは単一エージェントより 90.2% 良い結果を出したが、トークン消費はチャットの約 15 倍になった。依存関係の強いコーディング作業は、複数エージェントに向かない | Anthropic, "How we built our multi-agent research system", 2025, https://www.anthropic.com/engineering/multi-agent-research-system | 本文（調査） | 反証であり、条件でもある。並列化は、独立した広い調査には効くが、コストが増える。密に結合した実装には向かない | P-FR のサブエージェントの規則（境界ごとにだけ分ける） |
| E4 | 長時間のエージェントでは、一度に作りすぎて途中で文脈が尽きる失敗と、途中まで進んだ状態を見て「完了」と宣言してしまう失敗が起きた。対策として、機能の一覧を最初は全部「未達」にして JSON で持つ（Markdown より誤って書き換えられにくい）、1 機能ずつ進める、git の commit と進捗ファイルで状態を引き継ぐ、利用者と同じ操作のブラウザ自動化で E2E テストをする、テストの削除や編集を強く禁じる、が有効だった | Anthropic, "Effective harnesses for long-running agents", 2025, https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents | 本文 | 本件の Wave 運用（少しずつ依頼する）と一致する。台帳と E2E テストが重要 | P-ST の JSON 台帳と E2E テスト、P-FR の作業前の基準確認（git log と検証スクリプト） |
| E5 | 文脈は有限の資源で、モデルには注意の予算がある。少なく、情報量の多いトークンに絞る「コンテキスト工学」が要る | Anthropic, "Effective context engineering for AI agents", 2025, https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | 本文（調査） | 要求定義書の全文を毎回読ませず、索引で必要な箇所だけを取り出す | P-RD・P-FR の mdq / cq の利用 |
| E6 | 関係する情報が長い入力の中ほどにあると、性能が大きく落ちる | Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", TACL 2024（arXiv:2307.03172） | 要旨 | 同上。要求定義書が大きくなったら分割する | 分割の規則（P-RD・P-FR） |
| E7 | 入力が長くなるにつれて、性能は一様ではない形で落ちる（context rot） | Chroma Research, "Context Rot: How Increasing Input Tokens Impacts LLM Performance", 2025, https://research.trychroma.com/context-rot | 本文（調査） | 同上 | 同上 |
| E8 | リポジトリ全体から関連コードを反復して検索してから生成すると、ファイル内だけの補完より 10% 以上精度が上がった | Zhang et al., "RepoCoder", arXiv:2303.12570, 2023 | 要旨 | catalog だけでなく、索引付きのコード検索で補う意味がある | P-FR の `cq search` / `cq trace` / `cq def` / `cq refs` |
| E9 | エージェント向けに作った操作体系（検索・移動・編集のコマンド）が、エージェントの性能を大きく左右する | Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering", arXiv:2405.15793, 2024 | 要旨 | mdq / cq のような、小さな結果を返す専用の検索ツールを用意する価値がある | 同上 |
| E10 | LLM は外部からの正しいフィードバックなしには、自分の推論を自己修正できず、かえって悪化することがある | Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet", ICLR 2024（arXiv:2310.01798） | 要旨（調査） | エージェント自身の「完了した」という申告で合否を決めない | P-FR の検証スクリプトと CI（G3） |
| E11 | 最先端のモデルが、テストや採点のコードを書き換えて高い得点を得る「報酬ハッキング」をする例が実測された | METR, "Recent Frontier Models Are Reward Hacking", 2025-06-05, https://metr.org/blog/2025-06-05-recent-reward-hacking/ | 本文（調査） | テストを弱めることの禁止と、エージェントの外での判定が必要 | P-FR・P-ST の「テストを弱めない」、CI |
| E12 | 仕様とテストが矛盾する課題を与えると、エージェントがテストを利用して「解いたふり」をする割合を測るベンチマークで、高い割合が観測された | Zhong et al., "ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases", arXiv:2510.20270, 2025 | 要旨（調査） | テストが要求と食い違うときは、直させずに競合として報告させる | P-FR・P-ST の競合の扱い |
| E13 | 推論モデルの思考過程を監視すると、テストを書き換えて合格に見せかける計画が記録されていた | OpenAI, "Monitoring reasoning models for misbehavior and the risks of promoting obfuscation", 2025, https://openai.com/index/chain-of-thought-monitoring/ | 本文（調査） | 同上 | 同上 |
| E14 | LLM に過剰な機能・権限・自律性を与えることが「Excessive Agency」の根本原因。影響の大きい操作を、独立して確認・承認しない設計も原因になる | OWASP, "LLM06:2025 Excessive Agency", https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ | 本文 | デプロイ、push、課金、外部公開は既定で「しない」にし、利用者が明示した範囲だけを許可する | P-FR の `<execution_options>`（G2・G4） |
| E15 | AI のリスク管理を、設計・開発・利用・評価の全体に組み込む枠組み。生成 AI 向けのプロファイル（NIST AI 600-1）がある | NIST, "AI Risk Management Framework"（AI RMF 1.0, 2023 と AI 600-1, 2024）, https://www.nist.gov/itl/ai-risk-management-framework | 本文（調査。AI 600-1 は NIST のページの記述だけを確認） | 人による承認と、その記録を残す | P-RD の承認依頼一覧、P-FR の承認済みだけを実装（G4） |
| E16 | 要求工学のプロセスと、要求が持つべき特性（検証できる、曖昧でないなど）を定める国際規格 | ISO/IEC/IEEE 29148:2018, https://www.iso.org/standard/72089.html | 本文（調査。ISO の概要ページ） | 受入基準を検証できる形で書く方針（P-RD・P-FR の既存の規約）と合う | 既存の規約のまま |
| E17 | GitHub Actions から Azure への認証は、OIDC のフェデレーションかマネージド ID を推奨する。サービスプリンシパルとシークレットの組み合わせは推奨しない | Microsoft Learn, "Authenticate to Azure from GitHub Actions workflows"（更新 2026-01-21）, https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure | 本文（調査） | デプロイの秘密値は OIDC とマネージド ID で扱う | P-FR のデプロイの規則 |
| E18 | 小さく段階的で、品質ゲートを持つリリースと、段階的に公開範囲を広げる方法でリスクを抑える（Azure Well-Architected Framework OE:11） | Microsoft Learn, "Architecture strategies for safe deployment practices"（更新 2026-07-30）, https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments | 本文（調査） | Wave 2 は dev 環境から始め、本番への展開は明示した場合だけにする | P-FR のデプロイの規則 |
| E19 | GitHub の Environments に保護規則（必須のレビュー担当者など）を設定でき、満たすまでジョブは秘密値に触れられない | GitHub Docs, "Managing environments for deployment", https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments | 本文（調査） | 本番への展開に人の承認を挟む仕組みとして使える | §10.2 |
| E20 | 経験のある OSS 開発者の無作為化比較試験で、AI を使うと作業時間が平均 19% 長くなった。本人は速くなったと感じていた（METR は 2026 年に更新版があると注記している） | METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity", 2025-07-10, https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ | 本文（調査） | 反証。AI を使えば自動的に速くなるとは限らない。実地で測る必要がある | §9 の測定 |
| E21 | 定型の課題（HTTP サーバーの実装）では、Copilot を使った群が 55.8% 速く完了した | Peng et al., "The Impact of AI on Developer Productivity: Evidence from GitHub Copilot", arXiv:2302.06590, 2023 | 要旨（調査） | E20 と合わせると、効果は課題の種類と文脈の量で変わる | §9 の測定 |
| E22 | AI は組織がもともと持つ強みと弱みを増幅する。効果は、品質の文化や明確なプロセスなど、組織の取り組みで決まる | Google DORA, "State of AI-assisted Software Development", 2025, https://dora.dev/research/2025/dora-report/ | 要旨（調査） | Prompt だけでなく、要求の正本、承認、検証のプロセスを持つことが成果を左右する | 本件の 5 段階の構成そのもの |
| E23 | E2E テストは、利用者に見える振る舞いを検証し、実装の詳細に依存せず、各テストを独立させるべき | Playwright, "Best Practices", https://playwright.dev/docs/best-practices | 本文（調査） | 生成アプリのシステムテストの書き方 | P-ST の `<test_design>` |
| E24 | 既存のベンチマークのテストは量も質も足りず、テストを増やして厳しく評価すると、LLM が生成したコードの正答率の推定が大きく下がる | Liu et al., "Is Your Code Generated by ChatGPT Really Correct?"（EvalPlus）, NeurIPS 2023（arXiv:2305.01210） | 要旨（調査） | システムテストは正常系 1 件で済ませず、異常系と境界を含める | P-ST の `<test_design>` |

**外部の根拠から見た判定（推論）**
- **HVE 停止を支持する根拠:** E1、E2、E4 は、単純な構成と少しずつ進める運用が有効だとしています。これは ATG の実測（§3.1）と同じ方向です。
- **補うべき点（G3〜G5）を支持する根拠:** E10〜E13 は、エージェント自身の申告やテストに頼る危うさを示し、外部の判定（CI）が必要だとする根拠になります。E5〜E9 は、全文を読ませず索引で絞る方針を支持し、E14〜E19 は、権限を既定で絞り、人の承認を挟む設計を支持します。
- **反証と留保:** E3 は、広い調査では複数エージェントが有利なことを示しています。E20 は、実際の開発で AI が作業を遅くした例です。E4 自身も、専門のエージェント（テスト担当など）に分けた方がよいかは未解決としています。したがって、HVE を止めても、効果は §9 の測定で確かめる必要があります。

---

## 5. HVE の機能ごとの代替可能性

### 5.1 HVE で解決しようとしていた課題と、その対応（第 3 版で追加）

HVE は「業務要件の整理から設計・実装・検証までを、再現可能なワークフローとして運用すること」を目的にしていました（`README.md` の「目的」）。その背景には、作り始めた頃の Copilot では解決できなかった課題がありました。課題ごとに、HVE での対応と、今の解決手段を整理します。

判定: **不要**＝Copilot 本体の機能か、運用の規則で済む。**薄い仕組み**＝リポジトリごとの数十〜数百行のスクリプト・CI・設定、または持ち出せる単体ツールで済む。どちらも、Framework やアプリケーションとして作り続ける必要はありません。

| # | HVE で解決しようとしていた課題 | HVE での対応 | 今の解決手段 | Framework 化・アプリ化 | 根拠 |
|---:|---|---|---|---|---|
| 1 | 途中で止まる。中断すると再開できない | Workflow の連続実行、Step 単位の resume、実行台帳 | Autopilot、`agentStop` hook、セッションの再開、commit 単位の再開（P-FR は冪等） | **不要** | §4.1。AutoVision-Studio では abort 6 回・resume 12 回を、「再開してください」の指示で手で再開していた（同リポジトリの分析 §4.2） |
| 2 | 大きな作業を分け、依存関係を守り、並列に流す | DAG、Wave 分割、ATG | `/fleet`、人が Wave を分ける、「300 行以内に分けて書く」の 1 文 | **不要** | ATG は単一 Prompt より良い結果を出さなかった（§3.1）。過去の 4 アプリのうち 2 つは ATG を使わずに作られ、AutoVision-Studio では ATG が一度も呼ばれなかった（§3.10） |
| 3 | 複数のセッションが同じ作業を重ねて起動する、同じ作業ツリーで競合する | ATG の状態 DB、`node start` の重複拒否、1 ノード 1 worktree | Wave をブランチ単位にする、共有ファイルは親だけが書く、cloud agent の単一ブランチ制限 | **不要**（運用の規則） | AutoVision-Studio で重複実行が 494 AIU（全体の約 1%）だった（§3.10） |
| 4 | 計画を人が承認してから実行したい | 計画の SHA-256 と承認ゲート | Cloud agent の plan 承認、CLI の plan モード | **不要** | §4.1、§5.2 |
| 5 | 破壊的な操作や、範囲外への書き込みを防ぎたい | `output_paths` ゲート、安全ガード | `preToolUse` hook、cloud agent の安全策（単一ブランチ、firewall、CodeQL、Secret scanning） | **不要** | §4.1 |
| 6 | 業務要件から設計・実装・テストまでを、段階ごとの Prompt で順に回したい | 13 Workflow、Prompt 約 314 件、Custom Agent 群、`knowledge/` の D01〜D21 | P-RD と P-FR の 2 本、必要な Skill だけを残す | **不要** | 単一の Prompt で中規模の実装を完成できた（§3.1）。過去の 4 アプリは、いずれも HVE を使わずに作られた（§3.10） |
| 7 | 社内の情報（会議・メール・文書）を要求に取り込みたい | Work IQ のオーケストレーション、`docs-original/` の取り込み（ADI） | Microsoft 365 Copilot / Work IQ でドラフトを作る、MCP、P-RD の出典規約 | **不要** | §3.7。出典の機械照合は失う（§5.2） |
| 8 | 合否がエージェントの自己申告になる（偽の PASS） | ATG の `verify_command`、検証ループの Skill | P-FR が作る検証スクリプトと CI。exit code で判定する | **薄い仕組み** | HVE・ATG でも防げていなかった（§3.6）。これは HVE の有無に関係なく必要（G3） |
| 9 | 文脈が肥大する。要求とコード・テストの対応を追えなくなる | 要件索引、context pack、`mdq` / `cq` の HVE 統合 | `docs\catalog.md`（短い対応表）、`mdq` / `cq` の導入キット、分割の規則 | **薄い仕組み** | §3.9、§10.3。AutoVision-Studio では 744〜1,869 行の文書を毎回参照し、長大セッションが費用の 31% を占めた（§3.10） |
| 10 | 費用と証跡を管理したい | 実行台帳、AIU / max-minutes の予算、KPI ダッシュボード | Enterprise の AI Credits 予算、セッションログ・監査ログ、本レポート §3.10 と同じ定義での集計 | **薄い仕組み** | 1 回の実行ごとの厳密な上限は未検証（§5.2、§9 の U6） |

- 推論: 10 の課題のうち 7 つは、Copilot 本体の機能か運用の規則で済みます。残る 3 つも、必要なのは「決定的な検査」「機械可読な要件索引」「予算の設定」で、どれもリポジトリごとの小さな仕組みか、持ち出せる単体ツールで足ります。**課題そのものは今も実在しますが、その解決のために Framework やアプリケーションを作り、保守することは不要になりました。**
- 推論: 課題 8（偽の PASS）は、HVE を作っても解決していませんでした（§3.6）。HVE を止めて失うものではなく、HVE の有無に関係なく、エージェントの外に置く必要がある仕組みです。
- 事実（第 4 版で追加）: HVE で開発しようとしていた業務アプリ（§3.11）では、課題 1・2・6 への HVE の対応（Workflow の Step を順に回す）そのものが、1 回通すだけで約 15〜39 時間かかる長さと、前の Step が止まると後ろが止まる連鎖を生みました。課題 8・10 は、総合判定が「INCOMPLETE・BLOCKED」で、Step ごとの費用も全体で集計できないまま残りました。HVE は課題を解決するために作られましたが、このアプリでは、HVE 自体が新しい課題の原因になっていました。

### 5.2 HVE の機能ごとの代替可能性

代替度: ◎＝公式機能で同等、○＝小さな追加（Prompt・hook・CI）で同等、△＝一部だけ、×＝代替なし

| HVE の機能 | 代替手段（HVE なし） | 代替度 | 失うもの・対応 |
|---|---|---|---|
| Workflow / Step の Prompt 群（13 Workflow、`.github/prompts` 約 314 件、Skill 34 件） | P-RD・P-FR の 2 本に集約する。必要な Skill（Azure のリージョン方針、デプロイスクリプト、CI/CD、検証ループなど）はそのまま残す | ○ | 設計書を細かく分けて作る工程（AAS、AAD-WEB など）はなくなる。要求定義の「技術選択」と catalog で代える |
| DAG 実行と並列化 | `/fleet`、または Wave を人が分ける | ○ | 決定的な DAG の状態（どのノードが完了したか）は残らない。Wave ごとに commit し、catalog を更新することで代える |
| 計画の SHA-256 と承認ゲート | Cloud agent の plan 承認、CLI の plan モード | ◎ | — |
| 継続（途中で止まらない） | Autopilot と `agentStop` hook | ○ | hook のスクリプトを 1 本用意する |
| `output_paths` ゲート、破壊的な操作の拒否 | `preToolUse` hook、cloud agent の単一ブランチ制限 | ○ | 拒否する規則を hook に書く |
| 中断からの再開（resume） | CLI のセッション再開と、git の commit 単位での再開 | ○ | Step 単位の正確な再開は失う。P-FR は冪等（同じ依頼を再実行しても、要求定義と catalog を正にして続きを作る）なので、影響は小さい |
| 実行台帳、試行ごとの証跡 | cloud agent のセッションログ、監査ログ、commit。ローカルは hooks のログ | ○ | HVE 独自の KPI ダッシュボードはなくなる |
| 予算（max-minutes、AIU） | Enterprise の AI Credits 予算、`--max-autopilot-continues` | △ | 1 回の実行ごとの上限を厳密にかけることは難しい（未検証） |
| 失敗時の自動修正と試行上限 | Prompt に上限を書く。`agentStop` hook で回数を数える。夜間は Automations | ○ | — |
| GUI（Workbench） | VS Code、Copilot app、GitHub の Agents タブ | ◎ | — |
| Work IQ と MCP の許可リスト、出典の実在照合 | MCP の設定、Skill、P-RD の出典規約（SRC-xxx） | △ | 出典 locator の機械照合はなくなる。CI で出典の形式だけを検査する程度 |
| **HVE 本体のシステムテスト（P-ST、`ledger.py`）** | — | 対象外 | HVE を止めれば不要になる。**生成アプリ用のシステムテストは、もともと HVE にない**（G1）。第 2 版では、P-ST の既定の対象を生成アプリにした（§6.6） |
| 要件索引と、要求 ID からコード・テストへの追跡（`mdq`・`cq` の HVE 統合） | `docs\catalog.md`（短い対応表）と、markdown-query・code-query の索引（`mdq search`、`cq trace` など） | ○ | mdq と cq は、`tools/skills/markdown_query/`・`tools/skills/code_query/` の導入キットで、HVE なしで他のリポジトリへ持ち出せる。HVE 固有の自動起動（`MdqWatcher` など）はなくなるので、P-FR の最後に索引を更新させる（第 2 版で反映） |
| モバイルと Power Platform | — | 対象外 | `hve/workflow_registry.py` の 13 Workflow（ARD、AAS、ADA、AAD-WEB、ASDW-WEB、ADFD、ADFDV、AAG、AAGD、AAR、AKM、ADI、ADOC）に専用の Workflow はない（Workflow 名で確認）。**HVE を止めても失わない** |

- 推論: HVE を止めて失うのは、主に「決定的な DAG の状態」「実行単位の予算制御」「出典の機械照合」の 3 つです。どれも、Agile の Wave 運用と CI で実務上は補える範囲です。

---

## 6. 3 つの Prompt のレビュー（ギャップ分析）

§6.1〜§6.5 は第 1 版のレビューです。第 2 版で何をどう反映したかは §6.6 にまとめています。

### 6.1 P-RD（要求定義の作成）

**良い点（事実）**
- 事実・決定・仮説・提案・不明を区別させています。要求ごとに出自（原文由来／利用者決定／AI 提案）と決定状態（承認済み／承認待ち／保留／却下）を付けます。
- 外部連携、マスター、ID の正本を確認させる節があります。企業システムで最も手戻りが大きい論点を押さえています。
- 社内情報（Work IQ）と公式資料（Microsoft Learn、Context7）の出典を SRC-xxx で要求定義書に残させます。後続のエージェントがツールなしで同じ情報を参照できます。
- 「承認を宣言・生成するのは人の役割」と明記しています。

**課題**

| ID | 課題 | 影響 | 対応案 |
|---|---|---|---|
| RD-1 | 成果物は「最終候補版（未承認）」になり、「AI 提案／承認待ち」の要求を含む。一方、P-FR は「要求定義書は唯一の正本」とし、BLOCKED 以外の MUST をすべて実装する | 承認されていない AI 提案が実装される（G4） | P-FR に「決定状態が承認済みの要求だけを実装する。承認待ちは実装しない（または Wave の範囲を人が指定する）」を加える。人が承認する手順を、Wave の始めに 1 回入れる |
| RD-2 | ID の体系が違う。P-RD は `R-xxx`、`AC-xxx`、`G-xxx`、`Q-xxx` を使い、P-FR は `FR-001`、`NFR-001`、`SEC-001`、`AC-###` を例示している | P-FR は「既存の構成に従う」ので、通常は R-xxx が保たれる。ただし、2 つの体系が混ざる余地がある | P-FR の例示を R-xxx に合わせるか、P-RD に「機能・非機能・セキュリティの区分を付ける」を加える |
| RD-3 | P-RD の受入条件は業務レベルの文章。P-FR は「exit code で判定できるコマンド」を求め、要求定義書を書き換える | 承認済みの受入条件の文面が、実装の都合で変わる | P-FR では、受入条件の本文は変えず、「検証コマンド」の列（または catalog の列）を足すだけにする |
| RD-4 | 既存ファイルがあると `requirements-definition.original.md` に複製する。再実行すると、この複製が上書きされる | 最初の原本を失う | 複製名に日時を付ける。または git の commit を原本とする |
| RD-5 | 要求定義を単一ファイルにまとめる | 大規模化すると、文脈を圧迫し、ID がずれる（§3.9） | §10.3 の分割規則 |

### 6.2 P-FR（要求定義からの実装。Wave ごとに繰り返す）

**良い点（事実）**
- 過去の実測で最良だった構成（要求定義ファイル、無人実行、300 行以内の書き込み）を含んでいます（§3.1）。
- 受入基準を exit code で判定させ、テストの弱体化、スキップ、ハードコードを禁じています。
- `docs\catalog.md`（要求 ID → 実装ファイル → テスト → API・テーブル・イベント）を更新させます。HVE-OrchestratorReview が必要とした「共有状態としての索引」の最小形です。
- ターンの終え方の規則で、途中で止まる 4 つの型を禁じています。
- TBD・BLOCKED・ASSUMPTION を記録させ、安全側の動作だけを実装させます。

**課題**

| ID | 課題 | 影響 | 対応案 |
|---|---|---|---|
| FR-1 | 「デプロイ、有料の外部サービスの呼び出し、git push、リポジトリ外の変更をしない」と定めている | Wave 2（Azure、スマホ、Power Platform）を実行できない（G2） | Wave 2 用の展開 Prompt を別に作る（§10.1 P-DEP。第 1 版の案。第 2 版では P-FR の `<execution_options>` に吸収した） |
| FR-2 | 合否の判定が、エージェント自身の実行と報告に依存している | 偽の PASS を見逃す（§3.6、G3） | 受入コマンドを CI で実行する。`agentStop` hook で、受入コマンドが exit 0 でなければ継続させる |
| FR-3 | 繰り返し実行で、既存の大きなコードベースを変更していく運用は、過去に測っていない（ATG レポートの T8） | 回帰と文脈の肥大が起きるかどうか不明 | Wave を小さくする。全件の回帰テストは CI に任せる。§9 の測定をする |
| FR-4 | Autopilot の自動継続は既定で 5 回まで | 長い Wave の途中で止まる | `--max-autopilot-continues` を上げる。または `agentStop` hook で判定する |
| FR-5 | ローカル実行では、cloud agent の自動検査（CodeQL、Secret scanning、依存の脆弱性検査）が動かない | 脆弱性や秘密値の混入を見逃す | CI（GitHub Actions）に CodeQL、Secret scanning、依存関係のレビューを入れる。または Wave を cloud agent で実行する |
| FR-6 | 「サブエージェントは本当に独立で並列化できる作業にだけ使う」としている | 大規模な Wave では、直列の 1 セッションで文脈が肥大する | Wave の中で境界づけられたコンテキストが分かれる場合は、`/fleet` を明示的に使う |
| FR-7 | 「質問せずに最後まで進める」とし、決まらないことは ASSUMPTION にする | 業務上の重要な判断が、AI の仮定で実装される | ASSUMPTION と BLOCKED の一覧を Wave ごとに人がレビューする（UAT の前） |

### 6.3 P-ST（システムテスト）— 対象が違う（G1）

- 事実: P-ST は「Skill `hve-system-test` に従い、`tests/system-test-ledger/` の台帳で、**HVE 本体（`hve/`）のシステムテスト**の未実施ケースだけを増分実行」し、「**HVE が生成したアプリのテストは対象外**」と書いています。
- 事実: `.github/skills/hve-system-test/SKILL.md` も、対象を HVE 本体とし、生成アプリを対象外としています。`tests/system-test-ledger/ledger.py` の自動修正の指示は「このリポジトリの `hve` 本体を修正」に固定されています。
- 推論: **HVE を止めると、P-ST は実行する意味がなくなります。** 手順 4 には、生成アプリのシステムテストを行う新しい Prompt が必要です。
- 再利用できる考え方（事実）: P-ST と台帳には、生成アプリでもそのまま使える良い規約があります。
  - 安定した ID を持つテストケースの台帳と、未実施分だけの増分実行
  - 先に canary（短い代表ケース）を流し、失敗したら本体を止める
  - 自動修正の上限（3 回）と、別ブランチへの commit
  - 修正でテストや期待値を弱めない
  - 合否を exit code と台帳の状態で述べ、失敗を PASS に丸めない
  - `20261003-SystemTestPlanAnalytics.d/report.md` が推奨した「一括実行ではなく台帳で分けて実行」の方針

### 6.4 手順 1（Microsoft 365 Copilot / Work IQ でドラフトを作る）

- 推論: 妥当です。P-RD はドラフトの中の命令を「分析対象のデータ」として扱い、出典がないものは「未確認」とします。ドラフトの品質が低くても、要求定義の段階で弱い部分が見えるようになります。
- 注意: 過去の実測では、Work IQ の固定質問で見つかった割合は 14%（一部を含めて 25%）でした（§3.7）。ドラフトの段階で、関係する会議名・文書名・連携先の資料を人が指定すると、精度が上がると考えられます（推論）。
- 注意: 個人名や秘密情報を要求定義書に転記しないことは、P-RD と P-FR の両方に書かれています。

### 6.5 人の作業は UAT だけにできるか（G4）

| 人に残る作業 | 理由 | 種類 |
|---|---|---|
| 要求の承認（Wave の始め） | P-RD の成果物は未承認で、AI 提案を含む。P-RD 自身が「承認は人の役割」としている | 業務上の統制 |
| ASSUMPTION と BLOCKED の確認 | P-FR は決まらないことを仮定で進める | 業務上の統制 |
| PR のレビューとマージ | cloud agent は自分の PR を承認・マージできない。依頼者は自分が依頼した PR を承認できない（公式文書） | ツールの仕様 |
| GitHub Actions の実行許可 | cloud agent の PR では、既定で人が「Approve and run workflows」を押すまでワークフローが動かない | ツールの仕様 |
| 展開・課金・外部公開・権限変更の承認 | 不可逆な操作、または費用が発生する操作 | 企業の統制 |
| 秘密値と資格情報の配置 | エージェントに持たせない | セキュリティ |
| UAT | 業務の妥当性の判定 | 提案どおり |

- 推論: 人の作業は「UAT だけ」ではなく、**「Wave の始めの承認」と「Wave の終わりの UAT とマージ」の 2 点**に集約するのが現実的です。これでも、HVE を使っていたときより人の作業は少なくなります。

### 6.6 推奨項目の反映状況（第 2 版、2026-10-03 13:08）

利用者の判断（G1: P-ST の対象に生成アプリを加える、G2: P-FR でデプロイなどを選べるようにする、G3・G4: 補うべき点として採用、G5: catalog を mdq・cq で補う）に従い、3 つの Prompt を改訂しました。改訂前の原本は、セッションの作業フォルダー（`files/prompt-backup-202610031308/`）に保存してあります。

| 課題 ID | 反映した Prompt | 反映した内容 | 根拠 |
|---|---|---|---|
| G1 | P-ST | 既定の対象を生成アプリ（`test_target: app`）にした。HVE 本体のテストは `test_target: hve` で従来の手順を選べる。`<run_options>` で時間予算、実行環境（local／deployed。本番は明示した場合だけ）、自動修正の有無と上限を選べる | §6.3、E4 |
| G1 | P-ST | ケース台帳 `tests\system\ledger.json`（安定 ID、要求 ID、AC ID、層、コマンド、canary、状態、証跡、履歴）。状態は実行結果でだけ更新する。ケースの削除や期待値の弱体化はしない | E4（JSON の台帳、テストの編集禁止） |
| G1 | P-ST | 期待値は要求定義書と受入基準から決め、実装コードを読んで決めない。テストが要求と食い違うときは、テストも要求も直さずに競合として報告する | E10〜E13 |
| G1 | P-ST | 利用者と同じ操作の E2E テスト、サービス間の契約テスト、受入基準にある異常系を必須にした | E4、E23、E24 |
| G1 | P-ST | 生成 AI の機能を含むアプリでは、完全一致ではなく評価で確かめる（`ai_eval`）。同じ入力を 3 回以上実行し、受入基準の合格率で判定する。閾値がなければ blocked・TBD にする。プロンプトインジェクションと情報漏えいのケースを含める | E14 |
| G1 | P-ST | canary の先行実行、変更があったケースだけを選ぶ増分実行（`git diff` と `cq trace`）、自動修正は別ブランチに commit してマージ・push しない、決まった形の報告。従来の P-ST の良い規約を引き継いだ | §6.3 |
| G2 | P-FR | `<execution_options>` を追加した。implement_scope、git_push、deploy、deploy_targets、paid_services、budget、external_exposure の 7 項目。既定値はすべて「しない／使わない／公開しない」で、必須の値が欠けたら実行しない | E14 |
| G2 | P-FR | deploy が「する」の場合の規則: IaC、適用前の変更確認（what-if）、宣言した先以外に触れない、削除・権限付与・本番は明示した場合だけ、秘密値は OIDC とマネージド ID と Key Vault、予算内の構成、デプロイ後の受入確認、`docs\deployment.md` への記録、ストア公開と Power Platform の本番取り込みは人に渡す | E17、E18、§7 |
| G3 | P-FR | 検証スクリプト（ビルド、静的検査、全テスト、要求 ID の整合）と CI（GitHub Actions、CodeQL、依存関係の確認）を作らせる。完了は検証スクリプトを新しいプロセスで実行した exit code で判定する。作業前に `git log` と検証スクリプトで基準を記録する | E4、E10〜E13 |
| G4 | P-RD | 別添の最後に「承認依頼一覧」を出させる。承認の記録方法（決定状態を「承認済み（決定者の役割・日付・決定記録）」に書き換える）を冒頭に書かせる。承認済みと書いた要求に決定記録があるかを確認させる。チャットで上位 3 件を返させる | E15 |
| G4 | P-FR | 実装してよいのは、承認済みの要求と、今回の依頼原文で明示された要求だけにした。AI が考えた新しい機能は「AI提案／承認待ち」として書くだけ。承認済みの要求と受入基準の文面は変えず、誤りは競合として記録する。最終報告に、実装しなかった承認待ちの要求と、確認が必要な仮定を影響の大きい順に出させる | E14、E15 |
| G5 | P-RD・P-FR | 要求 ID を `FR-xxx` と `NFR-<区分>-xxx` にそろえた。1 要求 1 見出し（例: `#### FR-012 …`）にし、mdq で ID を検索するとその要求だけが取り出せるようにした。テストのコメントに要求 ID と AC ID を書かせる | E5、E6、E8、E9 |
| G5 | P-FR | catalog を読んだ後、mdq（`search`）と cq（`trace`／`def`／`refs`）で詳細を探す。索引が古ければ更新してから検索する。0 件は不存在の証明にしない。作業の最後に索引を更新する（索引は commit しない） | E5〜E9 |
| G5 | P-RD・P-FR | 分割の規則: 要求が 150 件を超える、300KB を超える、または境界が 3 つ以上のときは、索引と境界ごとの要求ファイルに分ける。境界ごとにサブエージェントへ分けてよいが、要求定義書・索引・catalog・契約ファイルは親だけが書く | E3、E6、E7 |
| RD-4 | P-RD | 既存ファイルの複製名に実行日時を付け、既存の複製を上書きしないようにした | §6.1 |

**ID 形式の動作確認（事実）:** `cq/traces.py` の `extract` に、次の行を与えて確かめました。

```text
# FR-012 AC-031
# NFR-SEC-001 NFR-PERF-001 E2E-001
# R-012 should not match
```

結果は `FR-012`、`NFR-SEC-001`、`NFR-PERF-001`、`E2E-001` の 4 件で、第 1 版の P-RD の形式（`R-012`）は拾われませんでした。`AC-031` も拾われません。受入基準の本文は要求定義書の側にあり、mdq で取り出すので、支障はありません。ID をそろえたことで、`cq trace --id FR-012` で要求からコードとテストを引けるようになります（推論。実際のアプリでの確認は U2）。

**反映しなかったもの（理由つき）:**
- **`agentStop` hook と `preToolUse` hook:** Prompt ではなく、リポジトリの設定（`.github/hooks/*.json`）として置くものです。Prompt から作らせると、作った後のセッションにしか効かず、上限のない継続ループの危険もあります。§10.2 の任意の設定として残しました。
- **Autopilot の継続回数の上限（FR-4）:** 実行時の設定（`--max-autopilot-continues`）なので、Prompt には入れていません（§10.5）。
- **既存の Prompt を増やすこと（第 1 版の P-APR、P-APPST、P-DEP）:** 利用者の判断に従い、既存の 3 本に吸収しました。

---

## 7. 企業向けの大規模分散アプリとしての追加の論点

HVE の有無に関係なく、提案の 5 段階で企業向けの大規模分散アプリを作るときに必要になる論点です。第 2 版では、「第 2 版の Prompt での扱い」の列を更新しました。

| 論点 | 第 2 版の Prompt での扱い | 残るリスク | 対応案 |
|---|---|---|---|
| サービス間の契約（API、イベント、データ） | P-FR の catalog に「公開する API・テーブル・イベント」の列がある。P-ST が契約テストを作る。契約ファイルは親エージェントだけが更新する | 契約ファイルの互換性（破壊的な変更）を自動で検出する仕組みはない | 契約ファイル（OpenAPI、AsyncAPI、JSON Schema）を正本にし、互換性の検査を検証スクリプトに加える |
| 要求定義と catalog の規模 | 分割の規則、1 要求 1 見出し、mdq・cq の索引で補う | 閾値（150 件、300KB、境界 3 つ）は根拠のある値ではない | U2 で測って見直す |
| 環境（dev / stg / prod） | `deploy_targets` で環境を宣言する。本番は明示した場合だけ | 環境ごとの設定の差を管理する規約はない | IaC（Bicep / Terraform）と `azd` の環境、GitHub Environments の保護規則（E19） |
| 認証と秘密値 | OIDC、マネージド ID、Key Vault、GitHub Secrets から読む | — | — |
| 可観測性 | 要求の書き方の観点にある | 運用の要求が抜ける | 非機能要求に、ログ・メトリクス・トレース・SLO を入れる（`NFR-OPS-xxx`） |
| セキュリティの検査 | CI に CodeQL と依存関係の確認を入れる。P-ST がプロンプトインジェクションと情報漏えいを確かめる | Secret scanning はリポジトリの設定に依存する | リポジトリで Secret scanning と push protection を有効にする |
| 再現性 | 合否は検証スクリプトと CI の exit code で決める | LLM の出力は毎回違う | Wave ごとに commit とタグを付ける |
| 複数人・複数エージェントの並行開発 | 共有ファイル（要求定義書、索引、catalog、契約）は親だけが書く | 複数の人が同時に P-FR を流すと競合する | Wave をブランチ単位にし、共有ファイルの更新は Wave ごとに 1 回マージする |
| コスト | `paid_services` と `budget` で、デプロイ先の費用を制限する | AI Credits の消費は Prompt では制限できない | Enterprise の予算設定、既定モデルを Sonnet 5.5 にする（§3.3） |
| スマホ | テスト配布までを P-FR が行い、ストアへの申請と公開は人に渡す | 署名用の証明書とストアのアカウントは人が用意する | 署名と配布は人の承認つきの CI にする。UAT は実機で行う |
| Power Platform | 宣言した環境へだけ展開する。本番環境への取り込みと管理者の設定は人に渡す | 環境、接続参照、DLP ポリシーは管理者の権限に依存する | ソリューションをソース管理し、Power Platform の CLI と CI で展開する（具体的な手順は未検証） |

---

## 8. 反証と留保

本レポートの「HVE 停止は妥当」という判定に対して、次の反証・留保があります。

1. **実測の規模が小さい。** 3 タスク、各 n=2〜3、新規作成だけで、モデルは `claude-opus-5.5` だけです（ATG レポート §9、T1・T7・T8）。企業の大規模分散アプリは、これより桁違いに大きくなります。
2. **CLI の出力上限への依存。** 失敗の仕組みは、Copilot CLI の 1 応答あたりの出力上限 32,000 トークンに依存していました。CLI のバージョンが変わると、結果も変わり得ます。
3. **DAG と状態管理の設計そのものは合理的。** ATG の技術設計（成果物単位の状態、成果物ハッシュ、構造化 handoff、検証層）は、長時間・分割タスクの設計として妥当と評価されています。問題は「効果が測れなかったこと」と「受入判定の信頼境界」でした。
4. **「Prompt だけ」では継続は保証されない。** 自律 Prompt の研究は「ほぼ可能」としつつ、継続には `Stop` / `agentStop` hook などの決定的な仕組みが要るとしています（`202609261400-AutonomusPrompt-Research.md` §1、§4.1、§5.2）。
5. **HVE の Cloud Agent での Issue / Sub-Issue DAG**は、チームで並行して開発するときに価値があり得ます。ただし、cloud agent の plan 承認と Automations で代わりが利きます（§4.1）。
6. **外部の研究にも反証がある（第 2 版で追加）。** 広い調査では、複数エージェントの方が単一エージェントより大きく良い結果を出しました（E3）。経験のある開発者の無作為化比較試験では、AI を使うと作業が遅くなりました（E20）。

- 推論: 1、2、6 は、HVE を続ける根拠にはなりません。HVE でも同じ条件は測っていないからです。また E3 の利点は、`/fleet` と境界ごとのサブエージェントで、HVE なしに得られます。3〜4 は、「HVE が要る」ではなく「小さな決定的ゲートが要る」ことを示しています。このゲートは、第 2 版の P-FR の検証スクリプトと CI で用意しました。したがって、判定は変わりません。

---

## 9. 未検証事項と、HVE 停止後に測るべきこと

| # | 未検証事項 | 測り方（案） | 判定の基準（案） |
|---:|---|---|---|
| U1 | P-FR を、既存の大きなコードベースに繰り返し適用したときの回帰と完成率 | 実際の業務アプリで Wave を 3 回以上回す。CI の全件テストの結果と所要時間を記録する | Wave ごとに、新規の FAIL が 0 件で、受入コマンドが exit 0 |
| U2 | 要求定義と catalog の大きさの上限 | 要求の数、ファイルの大きさ、Wave の所要時間、ID のずれの件数を記録する | ID のずれが 0 件。所要時間が Wave の大きさに比例する |
| U3 | Wave 2 の Azure 展開の自動化の範囲 | P-FR を `deploy: する` と dev 環境の `deploy_targets` で実行し、IaC の作成、`what-if`、デプロイ、デプロイ後の検証を通す | 人の承認 1 回（`<execution_options>` の記入）で、展開と検証が通る |
| U4 | スマホと Power Platform の展開 | 小さなサンプルで、署名・配布・ソリューションの展開を通す | 手作業の手順が `docs\deployment.md` に書かれ、それ以外は CI で通る |
| U5 | 改訂した P-ST の、生成アプリのシステムテストとしての有効性 | 人が別に用意した E2E テスト（隠しテスト）で採点する | 隠しテストの合格率と、偽の PASS が 0 件 |
| U6 | 1 回の実行あたりのコストの上限を決める方法 | Enterprise の予算機能と CLI のオプションを確認する | 予算を超えたら停止する |
| U7 | 生成 AI の機能の評価テスト（`ai_eval`）の判定の安定性 | 同じ版に対して P-ST を 2 回流し、`ai_eval` のケースの判定が変わるかを見る | 判定の変化が、要求定義書に書いた許容範囲の中に収まる |
| U8 | 承認の運用の負担 | Wave ごとの承認依頼一覧の件数と、人が判断にかけた時間を記録する | Wave の始めの承認が、運用できる時間で終わる |
| U9 | 改訂した P-FR が、検証スクリプトと CI を実際に作り、exit code で完了を判定するか | 新しいリポジトリで P-FR を 1 回流し、`scripts/verify.*` と `.github/workflows/` の生成、最終報告の exit code を確認する | 検証スクリプトが要求 ID の整合を検査し、CI が PR で動く |

---

## 10. 推奨: HVE 停止後の最小構成

### 10.1 Prompt は 3 本のまま使う（第 2 版で改訂済み）

第 1 版では Prompt を 5 本に増やすことを提案しましたが、利用者の判断に従い、既存の 3 本に吸収しました。

| ID | Prompt（ファイル） | 使う人・タイミング | 第 2 版での主な変更 |
|---|---|---|---|
| P-RD | `[GitHub Copilot] RequirementDefinition作成.txt` | Copilot、最初と大きな変更のとき | 要求 ID を `FR-xxx`・`NFR-<区分>-xxx` にそろえた。1 要求 1 見出しにした。承認依頼一覧を出させるようにした。承認の記録を確認させるようにした。分割の規則を加えた。複製名に日時を付けた。既存の文書を mdq / cq で探させるようにした |
| P-FR | `[GitHub Copilot] RD-FR_Prompt.txt` | Copilot、Wave ごと | `<execution_options>`（push、デプロイ、予算、外部公開など）を加えた。承認済みの要求だけを実装するようにした。検証スクリプトと CI を作らせ、exit code で完了を判定するようにした。mdq / cq で catalog を補うようにした。分割の規則と、境界ごとのサブエージェントの規則を加えた。作業前に基準を記録させるようにした。報告の項目を増やした |
| P-ST | `[HVE]SystemTest-Run.txt` | Copilot、Wave の終わり | 既定の対象を生成アプリにした。JSON の台帳、E2E・契約・異常系のテスト、生成 AI の評価テスト、canary、増分実行、自動修正の上限、決まった形の報告を加えた。HVE 本体のテストは `test_target: hve` で選べる |

人の作業は、次の 2 点に集約しました。
1. **Wave の始め:** P-RD が出した承認依頼一覧を見て、要求の決定状態を「承認済み」に書き換える。P-FR の `<execution_options>` を書く（デプロイ先と予算を含む）。
2. **Wave の終わり:** P-FR と P-ST の報告（承認待ち、確認が必要な仮定、TBD、BLOCKED、fail のケース）を見て、UAT を行い、PR をマージする。

### 10.2 エージェントの外に置く決定的ゲート（HVE の代わりの「薄い仕組み」）

| ゲート | 置き場所 | 内容 | 状態 |
|---|---|---|---|
| 受入ゲート | 検証スクリプト（`scripts/verify.*`）と GitHub Actions | ビルド、静的検査、すべての自動テストを実行し、1 つでも失敗すれば 0 以外で終わる。CI では CodeQL と依存関係の確認も行う | **P-FR に反映済み**（P-FR が作る） |
| 索引の整合ゲート | 検証スクリプトの一部 | 実装してよい MUST 要求の ID（BLOCKED を除く）が、catalog とテストコードの両方に現れることを確かめる | **P-FR に反映済み** |
| 展開の承認ゲート | GitHub Environments の保護規則（必須のレビュー担当者） | 本番環境へのデプロイのジョブは、人が承認するまで動かない（E19） | 任意。リポジトリの設定で行う |
| 継続ゲート | `.github/hooks/*.json` の `agentStop` | 検証スクリプトを実行し、失敗なら `decision: "block"` で作業を続けさせる。回数の上限を持たせる | 任意。リポジトリの設定で行う |
| 安全ゲート | `.github/hooks/*.json` の `preToolUse` | `git push --force`、リソースの削除、本番環境へのデプロイ、リポジトリ外への書き込みを拒否する | 任意。リポジトリの設定で行う |

- 注意: `agentStop` hook で `block` を返すと、作業は続きます。ただし、上限のないループになる危険と、AI Credits を消費し続ける危険があります。回数を数えるファイルを置き、上限（例: 3 回）で止める実装にします。cloud agent では、`block` で続けた分もジョブの時間制限に数えられます（hooks reference）。
- 推論: これらは数十〜数百行のスクリプトと設定で済みます。HVE（`hve/` の Python は、テストを除いて 236 ファイル・約 12.5 万行、テストを含めると 934 ファイル・約 12.6 MiB。2026-10-03 に計測）を保守し続けるより、はるかに小さい負担です。

### 10.3 要求定義と catalog の扱い（大規模化への備え。第 2 版で反映）

1. 最初は単一ファイル（`docs\requirements-definition.md`）で始める。各要求は 1 見出しにし、見出しに要求 ID を入れる。
2. 要求が 150 件を超える、ファイルが 300KB を超える、または業務の境界が 3 つ以上になったら、`docs\requirements-definition.md` を索引（要求 ID、題名、決定状態、優先度、所属ファイルへのリンク）にし、境界ごとの要求ファイル（`docs\requirements\<境界名>.md`）に分ける。閾値は案で、U2 の測定で見直す。
3. `docs\catalog.md` は「要求 ID → 実装 → テスト → API・テーブル・イベント」の短い表のまま保つ。詳細は、mdq（文書）と cq（コード）の索引で探す。
4. サービス間の契約は、要求定義ではなく契約ファイル（OpenAPI など）を正本にし、要求定義からは ID で参照する。
5. mdq と cq を新しいリポジトリで使う準備（推奨）:
   - `tools/skills/markdown_query/` と `tools/skills/code_query/` を対象リポジトリへコピーし、それぞれのフォルダーでセットアップのスクリプトを実行する（例: `pwsh -NoLogo -NoProfile -File setup.ps1 --repo-root <対象> --install-skill --build-index`。code-query は `--profile main` も付ける）。両方のスクリプトは同じ導入処理（`kit/kit_setup.py`）を使い、`--install-skill` で Skill を配置し、`--build-index` で最初の索引を作る（2026-10-03 に `--help` で確認）。
   - `cq.toml` の `roots` に、アプリのソースとテストのフォルダーを入れる。mdq の索引の対象に `docs` を入れる（`mdq.toml` の `[index].roots`）。
   - `.mdq/` と `.cq/` の索引は gitignore にする（P-FR は索引を commit しない）。
   - 配置された Skill に HVE 固有の参照（`references/repo-specific/hve-*.md`）が含まれていたら、取り除く。

### 10.4 HVE を止める手順（案）

| 順 | 作業 | 備考 |
|---:|---|---|
| 1 | 現在の HEAD にタグを付けて凍結する（例: `hve-eos-final`） | 後で参照・復元できるようにする |
| 2 | 再利用する資産を選ぶ | Skill の候補: `markdown-query`、`code-query`（導入キット `tools/skills/markdown_query/`・`tools/skills/code_query/` ごと）、`harness-verification-loop`、`tdd-red-green-reality`、`harness-safety-guard`、`harness-error-recovery`、`adversarial-review`、`large-output-chunking`、`azure-region-policy`、`azure-cli-deploy-scripts`、`azure-ac-verification`、`github-actions-cicd`、`docs-output-format`。**HVE 固有の参照（`hve-binding.md`、Workflow ID、`hve prompt run` など）を除いてから**使う |
| 3 | 改訂した 3 本の Prompt（§10.1）で、小さなサンプルアプリの Wave 1（ローカル）と Wave 2（dev 環境へのデプロイ）を一度通す | U1、U3、U5、U9 を測る。必要なら §10.2 の任意のゲートを加える |
| 4 | `hve/`、`hve-dev/`、HVE 用の `tests/`、HVE 専用の Skill・Instruction・Issue Template を、新しい開発用リポジトリには持ち込まない | 既存リポジトリから消すかどうかは、別途判断する（破壊的な操作のため、本レポートでは行わない） |
| 5 | 利用者向けの文書に、HVE の提供終了と、3 本の Prompt の使い方（§10.1 の人の作業 2 点を含む）を書く | — |

### 10.5 実行時の設定（Prompt の外）

| 設定 | 推奨 | 理由 |
|---|---|---|
| Autopilot の自動継続の上限 | Copilot CLI では `--max-autopilot-continues` を、Wave の大きさに合わせて既定の 5 より大きくする | 既定の 5 回では、長い Wave の途中で止まる（§4.1） |
| 権限 | `--allow-all` を使う場合は、ローカルのサンドボックスか cloud agent で実行する | Autopilot は全権限で最もよく動くが、ファイルの削除なども許すことになる（公式文書） |
| 既定のモデル | Sonnet 5.5 を既定にし、難しい設計判断だけ上位モデルを使う | 時間とコストが小さく、完成率は同等以上だった（§3.3。n は少ない） |
| 予算 | Enterprise の AI Credits の予算を設定する | Autopilot と `/fleet` は、利用者が関わらないまま AI Credits を消費する（§4.1） |
| Prompt の配布 | `Shared with Everyone\Prompt\` にある P-RD の写しは、第 2 版で更新していない。共有する場合は、デスクトップの改訂版で置き換える | 2 つの版が混ざると、ID の形式が食い違い、`cq trace` で追えなくなる |

---

## 11. 出典

### 11.1 内部資料（`de2adffe0~1` から復元して読んだもの。ファイル名は `work/` 内の名前）

| 出典 | 使った箇所 |
|---|---|
| `202609271600-ATG-BusinessImpactAnalytics.md` | §0.1〜§0.5、§6.4、§9 |
| `20260924-2154-DAG-ATG-Unification-SmallEngine-Rewrite-Report.md` | §0、§2.1、§2.5、§3.2、§5 |
| `20260923-2030-HarnessDesignLongTimeApplicationDevelopment-ATG-AnalyticsReport-v2.md` | §1、F-01、F-02 |
| `20260923-0040-atg-standalone-porting-guide.md` | §0〜§2 |
| `Autonomus Task Graph (ATG)-technical-description.md` | §1、§3.1、§8 |
| `202609300906-Opus55-vs-Sonnet55-ModelComparison.md` | §0.1、§0.2 |
| `20260921-LongTimeTaskAnalytics2.md` | §2.4 |
| `20260921-1200-TaskCompletionDefinitionReport.md` | §3.2、§5.3 |
| `202609261400-AutonomusPrompt-Research.md` | §1、§4.1、§4.3、§5.2 |
| `202609300940-HVE-OrchestratorReview.md` | §4.2、§5.1〜§5.5 |
| `2026100108115_WorkIQ-RemovelResearch.md` | §3.3、§5.1〜§5.3 |
| `202610011000-MicrosoftCopilotManagedRuntime-AdoptionResearch.md` | §6、§7.1 |

### 11.2 現行のリポジトリ（HEAD `d127ca721`）

- `work/202610020340-UnknownIssueBehaviorAnalytics.md`、`work/202610030920-HVE-FolderStructure.md`、`work/20261003-SystemTestPlanAnalytics.d/report.md`
- `README.md`、`hve/workflow_registry.py`、`.github/skills/hve-system-test/SKILL.md`、`tests/system-test-ledger/ledger.py`

### 11.3 利用者が提示した Prompt

- `[GitHub Copilot] RequirementDefinition作成.txt`（P-RD）、`[GitHub Copilot] RD-FR_Prompt.txt`（P-FR）、`[HVE]SystemTest-Run.txt`（P-ST）
- 第 2 版での改訂先: `C:\Users\dahatake\OneDrive - Microsoft\デスクトップ\` の 3 ファイル。改訂前の原本は、セッションの作業フォルダーの `files/prompt-backup-202610031308/` にある

### 11.4 第 2 版で読んだリポジトリ内の資料

- `.github/skills/markdown-query/SKILL.md`、`.github/skills/code-query/SKILL.md`、`.github/skills/code-query/references/cli-reference.md`、`.github/skills/code-query/references/indexing-internals.md`
- `cq/traces.py`（`FEATURE_ID_RE`、`TEST_ID_RE`、`extract`）、`cq/search.py`（`_TRACE_RE`）
- `tools/skills/code_query/README.md`、`tools/skills/code_query/cq.toml.sample`、`tools/skills/*/setup.ps1 --help`

### 11.5 外部資料（確認日: 2026-10-03）

GitHub の公式文書（本文を取得したもの）:
- GitHub Docs, "About GitHub Copilot cloud agent", https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent
- GitHub Docs, "Risks and mitigations for GitHub Copilot cloud agent", https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/risks-and-mitigations
- GitHub Docs, "About Copilot automations", https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-automations
- GitHub Docs, "Allowing GitHub Copilot CLI to work autonomously"（autopilot）, https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot
- GitHub Docs, "Running tasks in parallel with the /fleet command", https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet
- GitHub Docs, "About hooks for GitHub Copilot", https://docs.github.com/en/copilot/concepts/agents/hooks
- GitHub Docs, "GitHub Copilot hooks reference", https://docs.github.com/en/copilot/reference/hooks-reference
- GitHub Changelog, "Research, plan, and code with Copilot cloud agent"（2026-04-01）, https://github.blog/changelog/2026-04-01-research-plan-and-code-with-copilot-cloud-agent/

論文とベストプラクティス（第 2 版で追加）: §4.2 の表の E1〜E24 に、発行元、題名、年、URL、確認の範囲（本文／要旨／調査）を書いています。筆者が本文または要旨を直接読んだのは、E2、E4、E6、E8、E9、E14 です。そのほかは、調査用のサブエージェントが本文または要旨を読み、筆者は題名、URL、主張の対応だけを確かめました。

GitHub の課金（第 3 版で追加。確認日 2026-10-05）:
- GitHub Docs, "GitHub Copilot billing"（1 AI credit = 0.01 USD）, https://docs.github.com/en/billing/concepts/product-billing/github-copilot-billing

### 11.6 第 3 版で読んだ過去のアプリのリポジトリとセッション履歴

| リポジトリ・資料 | 主に使った箇所 | 使った節 |
|---|---|---|
| `C:\GitHub\AutoVision-Studio` | `README.md` 3 行目、`work/20260923-0945-ATG-AnalyticsReport.md`（§1、§3.3、§4.1、§4.2、§5.2）、`work/20260922-1340-Gate2LaneAdoption.md` 19 行目、Git 履歴（`a74c95a`） | §3.10、§5.1 |
| `C:\GitHub\StudyReport-Evaluator` | `README.md` 3 行目、`work/202609240830-RemainTaskExecutionPlan.md` 257 行目、`work/20260917-job-cost-execution-audit.md` 16〜18 行目、Git 履歴 | §3.10、§5.1 |
| `C:\GitHub\Optoronics-Studio-Demo` | `README.md` 3 行目、`docs/deployment-record.md`、`docs/acceptance-results.md` 15、32、36 行目、Git 履歴（`work/` はない） | §3.10 |
| `C:\GitHub\HubRadio-MovieCreator` | `README.md`、`work/20260922-1410-Wave3-ApprovedMediaAcceptance.md` 11 行目、`work/20260924-0330-P4-Execution-Log.md` 4 行目、55 行目、Git 履歴 | §3.10、§5.1 |
| Copilot のセッション履歴 | `%USERPROFILE%\.copilot\session-state\*\events.jsonl` と `workspace.yaml`。集計スクリプトはセッションの作業フォルダーの `files/agg_usage.py` | §3.10 |

### 11.7 第 4 版で読んだこのリポジトリの資料（HEAD `e71c4b123`）

| 資料 | 主に使った箇所 | 使った節 |
|---|---|---|
| `docs/business-requirement.md`、`docs/catalog/app-catalog.md` | 1〜3 行目、94〜107 行目（対象のアプリとサブアプリ） | §3.11 |
| `docs/catalog/app-arch-catalog.md` | 10 行目、16〜29 行目（14 件すべて判定中断） | §3.11 |
| `tests/run/20260916-systemtest-summary/systemtest-report/README.md` | 3 行目、101〜102 行目（INCOMPLETE・BLOCKED） | §3.11、§5.1 |
| `tests/run/20261002T2237-ledger/system-test-ledger/artifacts/run-summary.json`、`evidence/CASE-aas-1/run.stdout.log` 297 行目、`evidence/CASE-aad-web-1/run.stdout.log` 2448 行目、`evidence/CASE-asdw-web-1.1/run.stdout.log` 331 行目、345 行目 | 4 ケースの合否、所要時間、AIU | §3.11 |
| `work/20261003-SystemTestPlanAnalytics.d/report.md` | 25〜26 行目（1 Step と 131 Step の試算）、36 行目（Prompt 版のテスト） | §3.11、§5.1 |
| `work/20260918-LongTimeTaskAnalytics.md`（`de2adffe0~1` から復元） | §2-2（VS Code Chat の長時間セッション） | §3.10 |
| Git 履歴、GitHub の Issue・PR（`gh issue list` / `gh pr list --state all --limit 5000`） | アプリのパスと Framework のパスの commit 数・活動日・作者、削除 commit、Issue・PR の件数 | §3.10、§3.11 |
| Copilot のセッション履歴 | 集計スクリプトはセッションの作業フォルダーの `files/agg_hve_runs.py`（結果は `files/repo_sessions.json`） | §3.10、§3.11 |
