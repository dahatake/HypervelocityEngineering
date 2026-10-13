# HVE 利用停止（EOS）の実証 — StudyReport-Evaluator の前版と new-era の開発資源の比較分析

- 作成日時: 2026-10-07 08:15 JST
- 位置づけ: `202610031135-HVE_EOS_ValidationReport.md`（以下「EOS レポート」）の §9「未検証事項と、HVE 停止後に測るべきこと」の実地確認の 1 つ
- 対象:
  - 前版: `dahatake/StudyReport-Evaluator`（2026-08-31〜10-01、v0.8.6。集計は `202610051515-DevelopmentHistoryReport.md`）
  - new-era: `dahatake/StudyReport-Evaluator-new-era`（2026-10-06〜10-07、commit `8170eb5`。集計は `202610070515-DevelopmentHistoryReport.md`）
- 検証する仮説（利用者の見解）: 「Opus 5.5 と Sonnet 5.5 の性能向上と、GitHub Copilot のコーディングエージェントの機能向上によって、HVE、ATG、汎用の harness や skills は不要になった」
- 表記: 「事実」は資料・実測・公式文書で確かめたこと。「推論」は事実から導いた判断。「未検証」はまだ確かめていないこと

---

## 0. 結論

### 0.1 一言でいうと

**HVE と ATG は不要になった、という判断はこの実証でも支持されます。** 一方、「汎用の harness と skills も不要になった」は、そのままでは言い過ぎです。**harness はなくなったのではなく、置き場所が変わりました。** 独自のフレームワーク（HVE、ATG）から、次の 3 つの層に移っています。

1. GitHub Copilot 本体の harness（Autopilot、サブエージェント、`task_complete`、チェックポイント）
2. 公式ガイドの作法を取り込んだ Prompt（P-RD、P-FR）
3. エージェントがリポジトリの中に作る、決定的な検査（`scripts/verify.ps1`、CI、CodeQL、要求 ID の追跡テスト）

new-era はこの 3 層だけで、**Prompt 7 回・1 日・約 132 USD 相当**で後継版を完成させました。前版は Prompt 254 回・32 日でした。ただし、**この差の大部分は、モデルや harness の差ではなく、前版が 32 日かけて作った「確定した要求定義書」と「コード」を new-era が引き継いだことによるものです（§3）。** 両方とも HVE と ATG を使っていないため、この比較は「HVE あり／なし」を直接比べたものでもありません。

| # | 仮説 | 判定 | 主な根拠 |
|---:|---|---|---|
| H1 | HVE（独自の Workflow フレームワーク）は不要 | **支持（強い）** | new-era は HVE なしで 7 Prompt・1 日で完了した（§2）。EOS レポートの実測（HVE で作ったアプリは未完成）とも一致する。Anthropic は「harness の各部品は、モデルが自力でできないことについての仮定を表したもので、モデルが良くなると古くなる」としている（X8） |
| H2 | ATG（DAG のタスク・オーケストレータ）は不要 | **支持（強い）** | new-era は DAG を使わず、Copilot の組み込みのサブエージェント（4 つ）で並列に実装した（§4.2）。Opus 5.5 の公式ガイドは、並列のサブエージェントを使った数時間の自律作業を Opus 5 より長く続けられるとしている（X2） |
| H3 | 汎用の harness は不要 | **部分的に支持（言い直しが必要）** | 汎用の harness を**フレームワークとして作り、保守すること**は不要。ただし、new-era の成功を支えたのは、42KB の P-FR に書かれた harness の作法と、エージェントの外で合否を決める検証スクリプトだった（§4.1）。Anthropic は「harness の組み合わせの余地は、モデルが良くなっても縮まず、移動する」としている（X8）。harness の違いで、解いた課題あたりのトークンが最大 40 倍変わったという研究もある（X21） |
| H4 | 汎用の skills は不要 | **条件付きで支持** | new-era は Skill を 1 回も使わずに完了した。前版も Skill は `run-tests` を 4 回使っただけだった。一般的なコーディングの作法を Skill にする必要はない。一方、学習データに少ない知識（社内の手順、最新の API、Azure の展開規約など）と、使う時だけ読み込ませたい長い手順には、Skill は今も有効（X5、X10） |

### 0.2 数字の比較（そのまま比べてはいけない理由は §3）

| 指標 | 前版 | new-era | 比 |
|---|---:|---:|---:|
| 暦日（最初の Prompt から完了まで） | 32 日 | 7 時間 19 分 | — |
| Prompt を入力した日数 | 15 日 | 1 日 | 1/15 |
| Prompt 回数 | 254 回 | 7 回 | 1/36 |
| 総待ち時間（ジョブ実行時間の合計） | 143 時間 47 分 | 7 時間 06 分 | 1/20 |
| AI の費用（AIU） | 33,999 以上（下限。記録は 2026-09-24 以降の CLI だけ） | 13,191 | 1/2.6 以下 |
| 金額の目安（1 AIU = 0.01 USD とみなす） | 約 340 USD 以上 | 約 132 USD | — |
| 総トークン | 4.54 億以上（下限） | 2.97 億 | 1/1.5 以下 |
| 使ったモデル | 15 通り以上（主に gpt-5.6-sol-fast） | claude-opus-5.5（high）と gpt-5.6-luna（探索） | — |
| 自動テスト（テスト属性の数） | 1,303 | 1,344 | +41 |
| 外部の検証ゲート | CI（3 workflow） | `verify.ps1`、CI、CodeQL、依存関係の確認、要求 ID の追跡テスト | — |
| 筆者による `verify.ps1` の再実行 | — | exit 1（2,307 件中 1 件が 5 分の時間切れ。単独では合格） | — |
| 公開状況 | v0.8.6 を GitHub Releases で公開 | 版 0.9.0 の候補。手動試験（MT-01〜05）と UAT は未実施 | — |

### 0.3 推奨

1. **HVE と ATG の停止は確定してよいです。** この実証は、EOS レポートの結論を覆す事実を含みません。
2. **「harness 不要」ではなく「harness は薄く、リポジトリの中に置く」と表現を改めます。** 残すのは、P-RD・P-FR、エージェントが作る検証スクリプトと CI、必要なら `agentStop`／`preToolUse` の hook です（EOS レポート §10.2）。
3. **費用は、モデルの設定でまだ下げられます。** Opus 5.5 の既定の effort は `medium` で、公式ガイドは `medium` が Opus 5 の `high` と同等以上としています（X2）。new-era は `high` で実行し、トークンの 77% をサブエージェントが使っていました。実装用のサブエージェントに Sonnet 5.5（入出力の単価は Opus 5.5 の半分）を使う比較を推奨します（§7）。
4. **公平な比較を 1 回だけ追加します。** 前版のコードを使わずに、確定した要求定義書だけから空のリポジトリで作る実験です（§9 の E-1）。これで「コードの引継ぎの効果」と「モデルと Prompt の効果」を分けられます。
5. **new-era を前版と同等と言う前に、手動試験と UAT を行います。** 現時点で言えるのは「自動の検証ゲートをほぼ通った」ところまでです。筆者が再実行すると、2,307 件中 1 件が実行時間の上限（5 分）を超えて失敗しました。単独では合格したので、実装の誤りではなく、ゲートが環境の速さに左右されることが原因です（§2.5.1）。

---

## 1. 調査の範囲と方法

| 区分 | 対象 | 方法 |
|---|---|---|
| 開発資源の集計 | `202610051515-DevelopmentHistoryReport.md`（前版）、`202610070515-DevelopmentHistoryReport.md`（new-era） | 全文を読み、指標の定義をそろえて比べた |
| EOS レポート | `202610031135-HVE_EOS_ValidationReport.md`（第 4 版） | §0、§3、§4、§5、§7〜§10 を読み、本件で確かめられる項目（§9 の U1、U8、U9）を特定した |
| リポジトリ | `C:\GitHub\StudyReport-Evaluator`（HEAD `94e5d8c`）、`C:\GitHub\StudyReport-Evaluator-new-era`（`8170eb5`、PR #1 のマージ `e09bdcf`） | 追跡されているファイルをハッシュで突き合わせ、行単位の差分、テスト数、要求定義書の構造、`.github` と `work/` の中身を数えた |
| セッション履歴 | new-era のセッション `46a7048d` の `events.jsonl`。前版の作業フォルダーのセッション 31 件 | ツールの種類と回数、サブエージェントの種類、Skill の使用、検証コマンドの実行回数を数えた |
| new-era の Prompt | Prompt 1（要求定義、46.6KB）と Prompt 7（実装、約 42KB）の添付ファイル | 全文を読み、公式ガイドの記述と対応づけた（§4.1） |
| 独立した再検証 | new-era の `scripts/verify.ps1` | 筆者が新しいプロセスで再実行した（§2.5） |
| 外部資料 | Anthropic の公式文書と技術ブログ、GitHub Docs と Changelog、arXiv、METR など（確認日 2026-10-07） | 主要な 6 件は筆者が本文を読んだ。残りは調査用のサブエージェントが取得し、筆者は題名・URL・主張の対応を確かめた。区別は §5 の「確認」の列に書いた |

**限界:** 比較は 1 組（n=1）です。前版のセッション履歴には欠けた期間があり（2026-09-08〜09-23。09-15 を除く）、VS Code Chat のトークンは一部しか記録されていないため、前版の値はすべて下限です。new-era は、手動試験と UAT をまだ行っていません。

---

## 2. 2 つの開発の比較

### 2.1 基本の指標

| 指標 | 前版 | new-era | 出典 |
|---|---|---|---|
| 開始 | 2026-08-31（リポジトリ作成） | 2026-10-06 21:31（リポジトリ作成） | 両レポート §1 |
| 終了 | 2026-10-01（v0.8.6） | 2026-10-07 05:04（Prompt 7 の完了） | 同上 |
| Prompt 回数 | 254（VS Code Chat 204、Agent Host／CLI 50） | 7（うち実作業は 2、残り 5 は質問票の回答と承認） | 同上 |
| ジョブ実行時間の平均／中央値 | 34.0 分／12.0 分 | 60.8 分／1.9 分 | 同上 |
| 最長のジョブ | 404.8 分 | 385.4 分（Prompt 7） | 同上 |
| commit 数 | 256（リポジトリ全体、10-06 まで） | 24（うちチェックポイントを除く実質の commit は 4） | `git log --all` |

- 事実: new-era の総待ち時間の 90% は、実装を担った Prompt 7 の 1 回（6 時間 25 分）です。前版は、1 回あたりの待ち時間は短い一方で、Prompt の回数が 36 倍でした。
- 推論: **人が介入した回数**が、2 つの開発の最大の違いです。前版は、人が 254 回指示を出して方向を決めた対話型の Vibe Coding でした。new-era は、人が 2 回の大きな依頼と 5 回の短い判断（合計 14 分）を出しただけの、仕様駆動の自律実行でした。

### 2.2 費用

| 項目 | 前版 | new-era |
|---|---:|---:|
| AIU | 33,999 以上（EOS レポート §3.10。2026-09-24 以降の CLI の 27 セッション） | 13,190.77 |
| Premium Request | 149（CLI） | 105 |
| 入力トークン（キャッシュを含む） | 3.92 億（CLI）＋ 0.54 億（VS Code Chat） | 2.96 億 |
| うちキャッシュ読込 | 3.67 億（CLI） | 2.86 億（96.4%） |
| 出力トークン | 162 万（CLI）＋ 577 万（VS Code Chat） | 116 万 |

- 事実（金額の照合）: new-era のトークンを Opus 5.5 の公表単価（入力 4 USD、出力 20 USD、キャッシュ読込 0.20 USD／100 万トークン。X1）で計算すると、キャッシュ読込 57.1 USD、出力 22.3 USD、キャッシュ書込 52.4 USD（単価を入力の 1.25 倍の 5 USD と仮定）で、合計約 131.8 USD です。AIU（13,190.77）を 1 AIU = 0.01 USD で換算した 131.9 USD とほぼ一致します。GitHub Copilot の従量課金は提供元の公表単価に基づくとされており（X13）、換算は妥当と考えられます。
- 事実: 前版の VS Code Chat には「Copilot credits 合計 434,255」という記録がありますが、AIU と同じ単位かを確かめられませんでした。このため表には入れていません。同じ単位だとすると、前版の費用は約 4,300 USD 増えます。
- 推論: 前版の費用は、記録の欠けを考えると 340 USD を大きく上回る可能性が高いです。少なくとも、**new-era の費用は前版の 2.6 分の 1 以下**です。

### 2.3 人の関与

| new-era の Prompt | 内容 | 所要時間 | 人の判断の種類 |
|---:|---|---:|---|
| 1 | 要求定義の Prompt（P-RD 相当、46.6KB）に「草案のアプリを実装してください」を入れて実行 | 28 分 | 依頼 |
| 2 | 「日本語で述べてください。」 | 51 秒 | 表示言語の指定 |
| 3 | 「未回答の質問票は、最良と考える選択肢を採用してください。」 | 7 分 46 秒 | 質問票 Q-001〜Q-009 への一括回答 |
| 4 | 「承認待ちの項目の詳細を説明してください。」 | 39 秒 | 確認 |
| 5 | 「承認待ちは全て承認します。」 | 1 分 06 秒 | AI 提案の 10 件を承認 |
| 6 | 「残る項目は全て: 除外します。やりません。」 | 1 分 57 秒 | 保留の 4 件を廃止 |
| 7 | 実装の Prompt（P-FR 相当、約 42KB）に「要求定義書のアプリケーションを実装してください」を入れて実行 | 6 時間 25 分 | 依頼 |

- 事実: 人が判断した区間（Prompt 2〜6）は、合わせて 14 分でした。EOS レポートが提案した「人の作業を Wave の始めの承認と、Wave の終わりの UAT に集める」という設計（G4）が、そのとおりに動いています。EOS レポートの U8（承認の運用の負担）に対する、最初の実測値です。
- 推論（留保）: 質問票の 9 件はすべて「推奨どおり」、承認待ちの 10 件はすべて承認、保留の 4 件はすべて廃止でした。判断が速いのは利点ですが、内容を吟味せずに AI の提案を受け入れる「自動化バイアス」の危険もあります。NIST AI RMF（EOS レポート E15）は、人による監督が実質的であることを求めています。重要な要求だけは、根拠を読んでから判断する運用を勧めます。

### 2.4 それぞれが作ったもの

| 観点 | 前版（32 日） | new-era（1 日） |
|---|---|---|
| 出発点 | 3.7KB の依頼文（`[ExcelReportEvaluator] 1.要求定義書作成.txt`）。要件はこの時点で未確定 | 前版の最終の要求定義書（266KB。前版と同一のファイル）と、前版のコード一式 |
| 要求定義 | 29 回改訂した（2026-08-31 の 5.3 万文字 → 09-01 に範囲を絞る → v1.0.0 で 2.4 万文字 → v0.8.6 で 13.4 万文字 → 最終 14.1 万文字）。要求 ID の体系はなく、AC は 53 件 | 草案を再構成した（8.6 万文字）。FR 74 件、NFR 21 件、AC 94 件、質問票 10 件。1 要求 1 見出し、決定状態つき |
| 機能 | Excel の評価、参照回答の生成、類似度による減点、Excel 数式、checkpoint と再開、単一 EXE の配布、実データでの調査、性能と同時実行の調整など | 前版の機能を引き継いだうえで、パネルを並べ替えられるワークスペース（`layout.json`）、ペルソナ別の図、OS の表示設定への追従、要求 ID の追跡を追加した。開発用 MSIX と macOS の対応を、利用者の指示で取り除いた |
| 検証の仕組み | CI（`ci.yml`、`release.yml`、`publish-release.yml`）。作業記録（`work/` の 21 ファイル）と敵対的レビュー（rubber-duck 18 回） | `scripts/verify.ps1`（ビルド、全テスト、管理データの整合を 1 コマンドで判定）、CI、CodeQL、依存関係の確認、`RequirementTraceabilityTests`、`docs/manual-tests.md` |

### 2.5 品質の証拠

| 証拠 | 前版 | new-era |
|---|---|---|
| 自動テスト | 1,303（135 ファイル） | 1,344（150 ファイル。追加 15 ファイル） |
| 検証スクリプトの独立した再実行 | — | **exit code 1**。2,307 件中 1 件が時間切れで失敗し、単独の再実行では合格（§2.5.1） |
| 静的検査 | — | ビルドを `-warnaserror`（警告をエラーとして扱う）で実行 |
| 手動試験 | clean-host 試験 CH-01〜06 は公開前に未実施（new-era の要求定義書 §2.1 の記述） | MT-01〜MT-05 を手順書にしたが、未実施 |
| 公開 | v0.8.6 を公開済み | 未公開。版 0.9.0 の候補 |
| UAT | 利用者が実データで使った記録がある（`work/` の実行記録） | 未実施 |

#### 2.5.1 検証スクリプトの再実行（筆者が実施、2026-10-07 08:22〜08:42 JST）

筆者が `pwsh -NoLogo -NoProfile -File scripts\verify.ps1` を新しいプロセスで実行しました（作業ツリーは `8170eb5` 以降の変更なし）。

| 段階 | 結果 |
|---|---|
| restore（locked mode） | OK |
| build（アナライザーあり、警告をエラーとして扱う） | OK（0 エラー） |
| Core のテスト | 199 件すべて合格 |
| App のテスト | 2,108 件中、合格 2,097・**失敗 1**・スキップ 10（18 分 47 秒） |
| 管理データの整合 | OK |
| **全体** | **exit code 1（FAILED: tests）**。所要 19 分 49 秒 |

- 事実: 失敗したのは `WindowsPublishPackageTests.Windows_publish_and_unsigned_package_are_safe_launchable_and_reproducible` の 1 件で、原因は判定の失敗ではなく、`scripts/publish-windows.ps1` の実行が 5 分の上限を超えた `TimeoutException` でした。
- 事実: 同じテストを単独で再実行すると、**4 分 35 秒で合格**しました（exit code 0）。上限の 5 分に対して余裕は 25 秒しかなく、全件を流したときの負荷で上限を超えたと考えられます（この環境はほかの利用者とも共有されています）。
- 事実: エージェントは、セッションの中で `verify.ps1` を 21 回実行し、最後に exit code 0 を報告していました。
- 推論: new-era の実装は、合否の面では正しい可能性が高いです。ただし、**検証ゲート自体が、実行環境の速さに左右される（決定的でない）**ことがわかりました。エージェントの環境で通ったゲートが、別の環境では通らないことがあるということです。EOS レポートが求めた「エージェントの外で再実行できる決定的なゲート」（G3）としては、まだ弱点があります。対策は、時間のかかるパッケージのテストを `verify.ps1` の既定から分けて CI の別ジョブにすること、または上限に余裕を持たせることです（§7 の I7）。これは「エージェントの自己申告ではなく、外で再実行して確かめる」ことの価値を示す実例でもあります。
- 事実: テストの件数は、テスト属性で数えると 1,344、Theory の展開を含めて実行した件数で数えると 2,307（199 ＋ 2,108）です。

- 推論: new-era が満たしているのは「エージェントの外で再実行できる自動のゲートを通る」ことです（上の時間に依存する 1 件を除く）。EOS レポート §3.6 が指摘した偽の PASS は、この仕組みで防げます。ただし、利用者の実機での動作、アクセシビリティ、性能、Copilot の実際の応答を使った評価は、手動試験（MT-01〜05）と UAT が終わるまで確認できていません。

---

## 3. 比較の公平性 — この差は何によるものか

この節が本レポートの中心です。0.2 の数字の差を、そのまま「モデルと Copilot の向上の効果」と読むことはできません。

### 3.1 交絡要因

| # | 要因 | 事実 | 結果への影響の向き |
|---:|---|---|---|
| C1 | **要求の成熟度** | new-era の草案 `docs/requirements-definition-draft.md` は、前版の最終の `docs/requirements-definition.md` と**バイト単位で同一**（ハッシュが一致。new-era の要求定義書 §2.1 も「git blob `35e595d` が一致」と記録）。前版は、3.7KB の依頼文から始めて、要求定義書を 29 回改訂し、範囲の変更（2026-09-01「1 つの Excel 入力に範囲を絞る」）も経ていた | new-era を大きく有利にする。**何を作るかを決める費用**は、前版の 32 日の中に入っている |
| C2 | **コードの引継ぎ** | new-era の `src` と `tests` の C#／AXAML は 115,201 行。そのうち新しいファイルが 7,708 行、前版から変えた部分が追加 1,564 行・削除 1,021 行で、**新しく書いた・変えた行は約 9,300 行（約 8%）**。追跡ファイル 462 件のうち、255 件は前版と同一、161 件は変更、46 件は新規。実装の Prompt の中でエージェントが「前版のコードとテストを土台に取り込む」と判断し（Q-010、推奨案で仮実装）、セッションの集計でも変更は +11,162 行／−225 行・77 ファイルだった | new-era を大きく有利にする。new-era の 6 時間 25 分は「15 万行の新規開発」ではなく「約 1 万行の機能追加・削除と、管理データの再構成」に使われた |
| C3 | **モデルの世代とツール** | Opus 5.5 の提供開始は 2026-09-22、Sonnet 5.5 は 09-28（X1、X3、X15）。前版の 254 Prompt のうち、5.5 世代を使ったのは Agent Host／CLI の 44 Prompt（約 17%）で、残りは主に VS Code Chat の gpt-5.6-sol-fast（127 Prompt）、gpt-6-astra（37）、claude-opus-5（22）だった | new-era を有利にする。これは利用者の仮説が主張する効果そのもので、交絡というより「測りたいもの」に近い |
| C4 | **範囲の差** | 前版は、実データでの調査、性能と同時実行の調整、公開までを行った。new-era は、前版にない UI（ワークスペース、ペルソナ別の図）を追加し、MSIX と macOS を取り除いた | どちらにも働く |
| C5 | **測り方の差** | 前版の待ち時間には、人の確認待ちが一部含まれる。前版の記録には欠けた期間がある。new-era は `task_complete` までを測った | 前版の値は過大にも過小にもなり得る。費用は下限 |
| C6 | **利用者の学習** | new-era の Prompt は、前版・HVE・ATG・EOS レポートの経験を反映して作られた（Prompt 自体が、9 か月分の失敗の蓄積） | new-era を有利にする |
| C7 | **HVE と ATG は、どちらも使っていない** | 前版は HVE も ATG も使っていない（EOS レポート §3.10）。前版の CLI セッションで使った Skill は `run-tests` の 4 回だけ。new-era は Skill を使っていない | この比較は「HVE あり／なし」の比較ではない。HVE と ATG についての根拠は、EOS レポートの §3.1、§3.11 が担う |

### 3.2 この比較から言えること・言えないこと

**言えること（事実と推論）**

1. **確定した要求定義書と既存のコードがあれば**、Opus 5.5 と 2 本の Prompt（P-RD、P-FR）で、管理データの再構成、要求の承認、機能の追加と削除、検証ゲートの作成までを、人の介入 7 回・1 日・約 132 USD で行える。
2. このとき、HVE、ATG、Skill、外部のオーケストレータは要らなかった。
3. EOS レポートが Prompt に反映した G2〜G5（実行オプション、外部の判定、承認済みだけの実装、要求 ID と catalog）は、実際に機能した。特に U9（P-FR が検証スクリプトと CI を作り、exit code で完了を判定するか）は**達成**を確認した（§2.4、§2.5）。

**言えないこと**

1. 「同じアプリをゼロから作っても 1 日で終わる」とは言えない（C1、C2）。
2. 「new-era の品質は前版と同等以上」とはまだ言えない（手動試験と UAT が未実施。§2.5）。
3. 「HVE を使うより速い」は、この比較からは直接言えない（C7）。その根拠は EOS レポートにある。
4. 「Opus 5.5 だから成功した」とも断定できない。Sonnet 5.5 や、effort `medium` で同じ結果になるかは測っていない（§7、§9）。

### 3.3 公平に近づけた見方（推論）

前版の 32 日は、大きく 2 つの作業からなっていました。(a) 何を作るかを見つける作業（要求の発見、範囲の変更、実データでの試行）と、(b) 見つけたものを実装し、直し、公開する作業です。new-era が置き換えたのは、ほぼ (b) の一部だけです。

それでも、new-era は 1 回の実装の依頼で、前版のコードを読み込み、新しい要求 21 件程度（FR-065〜FR-074、NFR-UX-003〜010、NFR-SEC-006 のうち承認されたもの）を実装し、2 つの機能を取り除き、94 件の AC を自動テストか手順書に対応させ、検証スクリプトを通しました。前版の 254 Prompt の多くが、こうした (b) の作業を人が細かく指示しながら進めたものだったとすれば、**(b) の部分で人の介入が 1〜2 桁減った**ことは、仮説を支持する実質的な証拠です。

---

## 4. new-era の実行を分解する — 何が効いたか

### 4.1 P-FR は、公式ガイドの作法をほぼそのまま取り込んでいた

new-era の実装の Prompt（P-FR）には、Anthropic の Opus 5／5.5 の公式ガイドの記述と、ほぼ同じ文が複数ありました。**HVE が独自の仕組みで解こうとしていた問題の一部は、今ではモデルの提供元が公式に「この 1 段落を足せばよい」と示しています。**

| P-FR の節 | 対応する公式ガイドの記述 | 解く問題 |
|---|---|---|
| `<turn_endings>`（ターンの終え方。「次の 4 つの形でターンが終わるのを見てきており、どれも望んでいません」） | Prompting Claude Opus 5.5「Unattended agentic runs」の推奨の段落（"The user has seen you end turns in four ways…"）の日本語訳（X2） | 無人の長時間実行が、途中で報告して止まる。HVE が Workflow の連続実行と resume で解こうとしていた問題（EOS レポート §5.1 の課題 1） |
| `<communication>`（「最初のツール呼び出しの前に、これから何をするかを一文で述べてください。作業中は、重要な発見があったときと方針を変えたときにだけ…」） | Prompting Claude Opus 5「User-facing progress updates」の例文と同じ（X3） | 進捗の報告が多すぎる・少なすぎる |
| `<boundaries>` の範囲の規則（「依頼された範囲を、意図された規模で実装してください…黙って狭めたり、広げたり…しません」） | 同「Task scope and over-verification」の例文と同じ（X3） | 範囲の勝手な拡大・縮小 |
| `<boundaries>` のサブエージェントの規則（「大きくて本当に独立し並列化できる作業にだけ…自分の作業の再確認には使いません」） | 同「Controlling subagent spawning」の例文と同じ（X3） | サブエージェントの使いすぎによる費用の増大 |
| `<context>` の `<pasted_content>` の扱い | Prompting Claude Opus 5.5「Mark pasted text in user messages」（X2） | 貼り付けた文章に含まれる指示の混入（プロンプトインジェクション） |
| `<implementation>` の「テストを削除、弱体化、スキップしない」「合否は…エージェントの外でも再実行できるコマンドの結果で決める」 | METR の報酬ハッキングの報告、ImpossibleBench、Anthropic の長時間 harness の記事（X18、X19、X7） | 偽の PASS（EOS レポート §3.6） |
| `<investigation>` の「カタログを最初に読み…詳細は検索で補う」「大きな文書を全文読むと、重要な箇所を見落としやすくなる」 | Anthropic の context engineering、Lost in the Middle、Context Rot（X6、X22、X23） | 文脈の肥大（EOS レポート §5.1 の課題 9） |

- 推論: new-era の成功は「harness なし」の成功ではなく、**「公式ガイドに沿って書いた 1 枚の Prompt と、プラットフォームの harness」の成功**です。HVE が数万行のコードで実現しようとしていたことの多くが、数段落の自然言語と、Copilot 本体の機能に置き換わっています。

### 4.2 Copilot 本体の harness として使われた機能

| 機能 | new-era での使われ方 | EOS レポートで HVE が担っていた役割 |
|---|---|---|
| Autopilot | Prompt 1〜7 をすべて Autopilot で実行。Prompt 7 は 6 時間 25 分、無人で続いた | Workflow の連続実行 |
| `task_complete` と、Autopilot の完了条件（「検証してから完了を宣言する」） | 8 回の `session.task_complete` で区切られた | Step の完了判定 |
| サブエージェント（`task` ツール） | 探索 4 件（gpt-5.6-luna、計 28 万トークン）、実装 4 件（Opus 5.5。`remove-msix-macos`、`workspace-ui`、`persona-charts`、`version-compat-trace`） | DAG による並列実行（ATG） |
| チェックポイント | 各ターンの開始と終了で git に記録（`Agent host session … - turn N`） | 実行台帳、resume |
| To-do（`sql` ツール） | 残作業の管理（8 回） | ATG の状態 DB |
| Web 検索・取得、Work IQ | 公式資料の確認（各 4 回）、社内情報の検索（1 回） | Work IQ のオーケストレーション |

### 4.3 トークンと時間の構造

| 観点 | 事実 | 推論 |
|---|---|---|
| トークンの内訳 | サブエージェントが入力の 77.6%（2.30 億）を使った。最大は `workspace-ui` の 1.15 億トークン（全体の 39%、2 時間 03 分、ツール 303 回） | 費用の最大の要因は、Opus 5.5 で動く実装用のサブエージェント。EOS レポートの AutoVision-Studio の分析（長大セッションとサブエージェントが費用の大半）と同じ傾向 |
| キャッシュ | 入力の 96.4% がキャッシュ読込 | Opus 5.5 のキャッシュ読込は 0.20 USD／100 万トークン（Opus 5 より 60% 安い。X1）。費用を押し下げた |
| 時間 | Prompt 7 の 6 時間 25 分に対し、API の処理時間は合計 3 時間 25 分（並列のサブエージェントを含む）。ツールの実行は 1,021 回 | 経過時間の多くは、ビルドとテストの実行（LLM の外）。EOS レポート §3.4（LLM 以外の時間が 91.8%）と同じ方向 |
| 検証の回数 | セッション全体で、`verify.ps1` の実行が 21 回、`dotnet test` が 101 回、`dotnet build` が 79 回（対象外の Prompt 1 件を含む） | 自己検証は十分以上に行われた。公式ガイドは、Opus 5 系は指示がなくても自分で検証するので、検証を指示する文は過剰な検証の原因になるとしている（X3）。外部の判定ゲート（`verify.ps1`）は残すべきだが、実行の頻度は下げられる可能性がある（§7） |

---

## 5. 外部の根拠（公式ガイド・論文・ベストプラクティス）

確認日はすべて 2026-10-07 です。「確認」の列は、**本文**＝筆者が本文を読んだ、**本文（調査）**＝調査用のサブエージェントが本文を読み、筆者は題名・URL・主張の対応だけを確かめた、**要旨（調査）**＝サブエージェントが要旨だけを読んだ、を表します。EOS レポートの E1〜E24 と重なるものは、その番号を併記しました。

### 5.1 モデルの提供元（Anthropic）の公式情報

| # | 主張 | 出典 | 確認 | 本件への含意 |
|---:|---|---|---|---|
| X1 | Opus 5.5 は Opus 5 より典型的な作業で 40% 安い。入力 4 USD、出力 20 USD、キャッシュ読込 0.20 USD（Opus 5 より 60% 安い）／100 万トークン。出力は 30% 以上速い。「キャッシュ読込が、エージェントやコーディングの費用の大半を占める」。20 万行のコードベースの監査と修正を 3 時間以内に終えた例（Opus 5 は 20 時間超、トークン 2.5 倍） | Anthropic, "Claude Opus 5.5", 2026-09-22, https://www.anthropic.com/claude-opus-5-5 | 本文 | new-era の費用（96.4% がキャッシュ読込）が安く済んだ理由の 1 つ。モデルの効率の向上は実在する |
| X2 | Opus 5.5 の既定の effort は `medium`（Opus 5 は `high`）。Opus 5.5 の `medium` は、コーディングと知的作業の評価で Opus 5 の `high` と同等以上。数時間にわたる大規模な監査や移行を、並列のサブエージェントで、少ない監督のまま最後まで続けることが Opus 5 より得意。無人の実行では、テキストだけで終わったターンを完了とみなさず、残作業をチェックリストで管理し、自動の継続は 2〜3 回で止める。早い停止を防ぐ段落（4 つの止まり方）を例示 | Anthropic, "Prompting Claude Opus 5.5", https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5 | 本文 | P-FR の `<turn_endings>` の出典。new-era は effort `high` で実行しており、`medium` で同等の結果になる可能性がある |
| X3 | Opus 5 は、指示がなくても自分の作業を検証する。「最後に検証の手順を入れる」「サブエージェントで検証する」のような指示は過剰な検証を生むので取り除く。**検証の手順を別に加える古い harness の足場も同じ**。範囲の制御、進捗の報告、サブエージェントの起動の制御について例文を示す | Anthropic, "Prompting Claude Opus 5", https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5 | 本文 | 「古い harness の足場は外す」という公式の推奨。H1〜H3 を支持する。一方で「外部の決定的な判定」まで外せとは言っていない |
| X4 | Claude Code のシステム Prompt の 80% 以上を、Opus 5 と Fable 5 向けに削除しても、コーディングの評価は下がらなかった。「規則を与える」から「判断させる」へ、「例を与える」から「インターフェースを設計する」へ、「すべてを最初に入れる」から「段階的に開示する（progressive disclosure）」へ。検証とコードレビューは Skill に移した | Anthropic（Claude blog）, "The new rules of context engineering for Claude 5-generation models", 2026, https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models | 本文 | H3 を強く支持する。同時に、42KB の P-FR と 47KB の P-RD は「すべてを最初に入れる」形で、まだ削れる余地がある（§7） |
| X5 | Skill は 3 段階の段階的開示で読み込まれ、決定的なスクリプトを同梱できる。信頼できる提供元の Skill だけを入れる | Anthropic, "Equipping agents for the real world with Agent Skills", 2025-12-18 更新, https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | 本文（調査） | Skill の価値は「一般的な作法」ではなく「使う時だけ読み込む専門の手順とスクリプト」にある（H4） |
| X6 | 文脈は有限の資源で、収穫逓減がある。「賢いモデルほど、指示的なエンジニアリングを必要とせず、より自律的に動ける」。圧縮、構造化したメモ、サブエージェント | Anthropic, "Effective context engineering for AI agents", 2025, https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | 本文（調査）。EOS E5 | H1〜H3 を支持する |
| X7 | 長時間のエージェントは、作りすぎて文脈が尽きる失敗と、途中で「完了」を宣言する失敗を起こす。機能の一覧（JSON）、1 機能ずつ、git と進捗ファイル、E2E テスト、テストの削除と編集の禁止が有効だった | Anthropic, "Effective harnesses for long-running agents", 2025, https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents | 本文（EOS レポートで確認）。EOS E4 | P-FR の catalog、検証スクリプト、テストを弱めない規則の根拠 |
| X8 | 「harness の各部品は、モデルが自力でできないことについての仮定を表している。その仮定は誤っていることがあり、モデルが良くなるとすぐ古くなる」。Opus 4.5 で context reset を、Opus 4.6 で sprint の分割を取り除けた。評価役のエージェントは「タスクが現在のモデルが単独で確実にこなせる範囲を超えるときだけ」費用に見合う。部品は 1 つずつ外して効果を確かめる。**「harness の組み合わせの余地は、モデルが良くなっても縮まない。移動する」** | Anthropic, "Harness design for long-running application development", 2026, https://www.anthropic.com/engineering/harness-design-long-running-apps | 本文 | 本レポートの判定の枠組みそのもの。H1・H2 を支持し、H3 には「移動した」と言い直す根拠になる |
| X9 | 単純で組み合わせやすい部品が、複雑なフレームワークに勝ることが多い。複雑さは必要なときだけ足す | Anthropic, "Building effective agents", 2024-12, https://www.anthropic.com/engineering/building-effective-agents | 本文（調査）。EOS E1 | H1・H2 を支持する |
| X10 | 16 の並列の Claude エージェントが、オーケストレータなしで git を同期の手段として、10 万行の C コンパイラ（Linux 6.9 を起動）を作った。費用は約 2 万 USD、入力 20 億トークン。「Opus 4.5 が最初にしきい値を越え、Opus 4.6 が次を越えた」 | Anthropic, "Building a C compiler with a team of parallel Claudes", 2026, https://www.anthropic.com/engineering/building-c-compiler | 本文（調査） | 大規模でも、専用のオーケストレータなしで git を共有状態にする構成が成立する。ATG 不要（H2）を支持する。ただし、大規模なテスト群（決定的な検査）が前提 |
| X11 | Claude Code のベストプラクティス: 自分の作業を検証できる手段（テスト、ビルド、スクリーンショット）を与える。差分を 1 文で説明できる作業なら計画は省く | Anthropic, "Claude Code best practices", https://code.claude.com/docs/en/best-practices | 本文（調査） | 外部の検証手段は今も推奨されている |
| X12 | Sonnet 5.5 は Sonnet 5 より 30% 以上速く、最大 30% 安い。入力 2 USD、出力 10 USD／100 万トークン。effort の水準は Sonnet 5 から再調整されたので、設定を持ち越さずに測り直す | Anthropic, "Claude Sonnet 5.5", 2026-09-28, https://www.anthropic.com/claude-sonnet-5-5 と "Prompting Claude Sonnet 5.5" | 本文（調査） | 実装用のサブエージェントを Sonnet 5.5 にすれば、単価は Opus 5.5 の半分（§7） |

### 5.2 GitHub Copilot の機能（GitHub Docs と Changelog）

| # | 機能 | 日付 | 出典 | 確認 |
|---:|---|---|---|---|
| X13 | 従量課金（2026-06-01 に移行）。Opus 5.5 は入力 4.00 USD・出力 20.00 USD、Sonnet 5.5 は入力 2.00 USD・出力 10.00 USD／100 万トークン（提供元の公表単価） | 2026-06-01〜 | https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing | 本文（調査） |
| X14 | Copilot CLI の一般提供。Autopilot、Agent Skills、hooks、plan モードを含む | 2026-02-25 | https://github.blog/changelog/2026-02-25-github-copilot-cli-is-now-generally-available/ | 本文（調査） |
| X15 | Claude Opus 5.5 が GitHub Copilot で利用可能に／Claude Sonnet 5.5 が利用可能に | 2026-09-22／2026-09-28 | GitHub Changelog | 本文（調査） |
| X16 | VS Code の Autopilot（preview）、入れ子のサブエージェント | 2026-04-08 | https://github.blog/changelog/2026-04-08-github-copilot-in-visual-studio-code-march-releases/ | 本文（調査） |
| X17 | cloud agent の research と plan、自動モデル選択の費用と品質の設定、`gh skill` による Skill の管理、Copilot Memory の既定での有効化 | 2026-04-01、2026-09-14、2026-04-16、2026-03-04 | GitHub Changelog の各記事（§11 に URL） | 本文（調査） |

- 推論: 前版の開発期間（08-31〜10-01）の大部分は、Opus 5.5（09-22）と Sonnet 5.5（09-28）の提供前でした。new-era は、両モデルと Copilot の 2026 年の機能が出そろった後の最初の開発です。

### 5.3 論文と調査報告

| # | 主張 | 出典 | 確認 | 本件への含意 |
|---:|---|---|---|---|
| X18 | 最先端のモデルが、テストや採点のコードを書き換えて高得点を得る例が実測された（RE-Bench の実行の 30.4%） | METR, "Recent frontier models are reward hacking", 2025-06-05, https://metr.org/blog/2025-06-05-recent-reward-hacking/ | 本文（調査）。EOS E11 | 外部の判定ゲートは、モデルが良くなっても残す |
| X19 | 仕様とテストが矛盾する課題で、テストを悪用して「解いたふり」をする傾向を測るベンチマーク | "ImpossibleBench", arXiv:2510.20270, 2025 | 要旨（調査）。EOS E12 | P-FR の「競合として記録し、BLOCKED にする」規則の根拠 |
| X20 | 単純な 3 段の手順（Agentless）が、複雑なエージェントより高い性能と低い費用を出した。数百行の bash だけの harness（mini-SWE-agent）が、モデルの能力を測る基準として使われている | Xia et al., arXiv:2407.01489, 2024／mini-SWE-agent, https://github.com/SWE-agent/mini-swe-agent | 要旨（調査）。EOS E2 | H1・H2 を支持する |
| X21 | harness の選び方で、解いた課題あたりのトークンが最大 40 倍変わる一方、同じモデルでの合格率の差は 0〜8 ポイントにとどまった | Vats & Golev, "The Scaffold Effect in Coding Agents: Harness Choice as a Hidden Variable in Coding-Agent Evaluation", arXiv:2607.22585, 2026 | 要旨（調査。筆者は題名だけを確認） | **harness の主な影響は「できるかどうか」より「費用」に出る。** HVE と ATG が品質を変えずに時間と費用を増やした EOS レポート §3.1 の実測と一致する。逆に、薄い harness でも費用の最適化の余地は大きい |
| X22 | 長い入力の中ほどにある情報は使われにくい | Liu et al., "Lost in the Middle", TACL 2024, arXiv:2307.03172 | 要旨（調査）。EOS E6 | 要求定義書を索引と検索で読む方針を支持する |
| X23 | 入力が長くなると、上限よりずっと手前で性能が落ちる（18 の LLM で確認） | Chroma Research, "Context Rot", 2025, https://www.trychroma.com/research/context-rot | 本文（調査。導入と方法）。EOS E7 | 同上 |
| X24 | AI ができる作業の長さ（50% の成功率で完了できる人の作業時間）は、約 7 か月で倍になっている。2026-01 の更新（課題を 228 件に拡大）でも同じ傾向を確認 | METR, "Measuring AI ability to complete long tasks", 2025-03-19（arXiv:2503.14499）と "Time Horizon 1.1", 2026-01-29, https://metr.org/blog/2026-1-29-time-horizon-1-1/ | 本文（調査）。Opus 5 系の数値は確認できなかった | モデルが自力でできる範囲は急速に広がっている。harness の部品が「古くなる」速さの根拠（X8） |
| X25 | 経験のある OSS 開発者の無作為化比較試験で、AI を使うと 19% 遅くなった。2026-02 の更新で、METR は元の参加者の選択に偏りがあり、拡大した結果も弱い証拠にとどまるとして、実験の設計を改めると発表した | METR, 2025-07-10 と "We are changing our developer productivity experiment design", 2026-02-24, https://metr.org/blog/2026-02-24-uplift-update/ | 本文（調査）。EOS E20 | 反証の力は弱まったが、「AI で必ず速くなる」とも言えない。実地の測定が要る |
| X26 | 複数エージェントの調査システムは単一エージェントより 90.2% 良かったが、トークンは約 15 倍。性能の差の 80% はトークンの使用量で説明できた | Anthropic, "How we built our multi-agent research system", 2025, https://www.anthropic.com/engineering/multi-agent-research-system | 本文（調査）。EOS E3 | new-era の費用の 77% がサブエージェントだったことと整合する。並列化は費用で買うもの |
| X27 | 複数エージェントのシステムの失敗を 14 の型に分類（仕様と設計、エージェント間の不整合、検証と終了の 3 区分） | Cemri et al., "Why do multi-agent LLM systems fail?", arXiv:2503.13657, 2025 | 要旨（調査） | DAG と多数のエージェントを組む構成（HVE、ATG）は、それ自体が失敗の原因を増やす |
| X28 | 公開されている Vibe Coding のアプリ 200 件を監査したところ、91.0% に 1 件以上の脆弱性があり、そのうち 65.77% が Critical か High だった | Deng, Fan, Meng, "Understanding the (In)Security of Vibe-Coded Applications", arXiv:2606.23130, 2026 | 要旨（調査） | Vibe Coding の速さと引き換えに、セキュリティの検査は外に置く必要がある。new-era が CodeQL と依存関係の確認を作ったことは妥当 |
| X29 | 100 以上の LLM で、生成されたコードはしばしば安全でない | Veracode, "2025 GenAI Code Security Report", https://www.veracode.com/resources/analyst-reports/2025-genai-code-security-report/ | 本文（調査。概要のページだけ） | 同上 |
| X30 | 長期的には、人の知識を組み込む方法より、計算資源で伸びる汎用の方法が勝つ（The Bitter Lesson）。これをエージェントの harness に当てはめ、手で作り込んだ足場はモデルの進歩で無用になるとする論考もある | Sutton, "The Bitter Lesson", 2019, http://www.incompleteideas.net/IncIdeas/BitterLesson.html／Zunic, "The Bitter Lesson of Agent Harnesses", browser-use, 2026-04-19, https://browser-use.com/posts/bitter-lesson-agent-harnesses | 本文（調査）。後者は企業のブログで査読はない | H1〜H3 の考え方を支持する。ただし X8 の「移動する」と合わせて読む |

**確認できなかったもの（根拠にしていない）:** Opus 5.5 と Sonnet 5.5 の SWE-bench Verified の値（公式ページは FrontierCode、Terminal-Bench 4.0、CursorBench などを示しており、SWE-bench Verified の値はなかった）。METR の Time Horizon 1.1 での Opus 5 系の具体的な数値。Anthropic が「CRITICAL」「MUST」のような強い語が過剰な反応を生むと明言した文（公式ガイドにあったのは「強い限定（"be conservative" など）を文字どおりに受け取り、報告が減ることがある」という記述。X3）。

---

## 6. 仮説ごとの検証

### 6.1 H1: HVE は不要か — 支持（強い）

- 支持する根拠: new-era は HVE なしで完了した（§2）。EOS レポートでは、HVE で 9 か月かけた業務アプリが完成しなかった（§3.11）。公式ガイドは、古い harness の足場を外すよう勧めている（X3、X4）。harness の部品はモデルの進歩で古くなる（X8、X24）。harness の違いは、主に費用に出る（X21）。
- 反する根拠・留保: HVE が対象にしていた「14 のサブアプリからなる企業システム」の規模は、本件でも確かめていない（EOS レポート U1、U3、U4 は未検証のまま）。
- 推論: 判定は変わりません。HVE が担っていた役割（連続実行、計画の承認、安全ゲート、証跡）は、Copilot 本体の機能（X14〜X17）と Prompt の数段落で置き換わっています（§4.1、§4.2）。

### 6.2 H2: ATG は不要か — 支持（強い）

- 支持する根拠: new-era は DAG を使わず、組み込みのサブエージェント 4 つで並列に実装した。共有ファイル（要求定義書、catalog）は親エージェントだけが書く規則で、衝突は起きなかった。EOS レポートの実測（ATG ありで品質は同じ、時間 1.7〜2.25 倍、費用 2.49〜3.50 倍）。オーケストレータなしで git を共有状態にした大規模開発の例（X10）。
- 留保: 費用の 77% がサブエージェントでした。並列化が速さを生んだ一方で、費用も生んでいます（X26）。これは ATG の有無ではなく、サブエージェントの数とモデルの選び方で調整する問題です。

### 6.3 H3: 汎用の harness は不要か — 部分的に支持（言い直しが必要）

harness を 3 つの層に分けると、判定がはっきりします。

| 層 | 例 | 判定 | 根拠 |
|---|---|---|---|
| 独自のフレームワークとしての harness | HVE の Workflow、ATG の DAG、独自の実行台帳、KPI ダッシュボード | **不要** | H1・H2 と同じ |
| プラットフォームの harness | Autopilot、サブエージェント、`task_complete`、hooks、チェックポイント | **必要。ただし自作しない** | new-era はこれに全面的に依存した（§4.2） |
| Prompt に書く harness の作法 | ターンの終え方、範囲、サブエージェントの規則、テストを弱めない、外部で判定する | **必要。ただし薄くする** | 公式ガイドが推奨する段落そのもの（X2、X3）。モデルが良くなると、削れる部分が増える（X4、X8） |
| リポジトリの中の決定的なゲート | `verify.ps1`、CI、CodeQL、要求 ID の追跡テスト | **必要** | 報酬ハッキング（X18、X19）、自己評価の甘さ（X8 の評価役の議論）、Vibe Coding のアプリの脆弱性（X28）。公式ガイドが外せと言うのは「検証を促す指示」で、「外部の判定」ではない（X3、X11） |

- 推論: 利用者の仮説の「汎用の harness は不要」は、「**汎用の harness をフレームワークとして作り、保守することは不要**」と言い直すのが正確です。harness の機能そのものは、プラットフォーム・Prompt・リポジトリの中のゲートに移って、今も働いています。これは Anthropic の「harness の組み合わせの余地は縮まず、移動する」（X8）と同じ結論です。

### 6.4 H4: 汎用の skills は不要か — 条件付きで支持

- 支持する根拠: new-era は Skill を使わずに完了した。前版も、CLI で使った Skill は `run-tests` の 4 回だけだった。Claude 5 世代のモデルは、規則や例を与えなくても判断できる（X4）。
- 残る価値: Anthropic 自身が、検証とコードレビューを Skill に移して、必要なときだけ読み込ませている（X4）。学習データに少ない最新の知識は、Prompt で補う必要があった（X8 の AI 機能の例）。Skill は、決定的なスクリプトを同梱できる（X5）。
- 推論: 「一般的なコーディングの作法を Skill にしたもの」は不要です。一方、次の 3 種類は残す価値があります。(1) 組織に固有の手順（Azure のリージョン方針、デプロイのスクリプト、署名と配布の規約）、(2) 学習データにない、または新しい API の知識、(3) P-FR のうち、毎回は使わない長い節（デプロイ、モバイル、Power Platform）。(3) を Skill に移すと、P-FR を短くでき、X4 の段階的開示にも合います。

---

## 7. 改善の余地 — 同じやり方で、もっと安く・速く

new-era のデータから、次の改善の候補が読み取れます。どれも、効果は測って確かめる必要があります。

| # | 改善の候補 | 根拠 | 期待される効果 | 確かめ方 |
|---:|---|---|---|---|
| I1 | effort を `high` から `medium`（Opus 5.5 の既定）にする | 公式ガイドは、Opus 5.5 の `medium` が Opus 5 の `high` と同等以上で、`xhigh`／`max` は効果を測った作業だけに使うよう勧めている（X2） | 思考トークンと時間の削減 | 同じ Prompt 7 を `medium` で再実行し、`verify.ps1` の結果と AIU を比べる |
| I2 | 実装用のサブエージェントを Sonnet 5.5 にする | サブエージェントがトークンの 77% を使った。Sonnet 5.5 の単価は Opus 5.5 の半分（X12、X13）。EOS レポート §3.3 でも、Sonnet 5.5 は時間 0.41〜0.56 倍、完成率は同等以上だった | 費用の大幅な削減（試算では、サブエージェント分が半額なら全体の約 4 割減） | サブエージェントのモデルを指定して再実行する |
| I3 | `verify.ps1` の全体実行は節目だけにし、作業中は関係するテストだけを回す | `verify.ps1` 21 回、`dotnet test` 101 回。Opus 5 系は指示なしでも自分で検証する（X3） | 経過時間の短縮（経過時間の多くは LLM の外） | ツールの実行回数と経過時間を比べる |
| I4 | P-FR（約 42KB）と P-RD（46.6KB）を短くする。毎回は使わない節を Skill か参照ファイルに移す | Claude Code はシステム Prompt の 80% を削っても評価が下がらなかった（X4）。部品は 1 つずつ外して効果を確かめる（X8） | 文脈の節約、指示の衝突の減少 | 節を 1 つずつ外した版で、同じ依頼を実行して比べる |
| I5 | サブエージェントの数と費用に上限をかける | Opus 5 系はサブエージェントを起動しやすい。公式ガイドは決定的な上限を勧めている（X3） | 費用の上限 | Copilot の設定と Enterprise の予算で上限を設ける（EOS レポート U6） |
| I7 | 時間のかかるパッケージのテストを、`verify.ps1` の既定から分ける（または時間の上限に余裕を持たせる） | 筆者の再実行で、5 分の上限に対して単独でも 4 分 35 秒かかるテストが、全件実行の負荷で時間切れになった（§2.5.1）。全件の実行に約 20 分かかる | ゲートが決定的になり、経過時間も短くなる | 異なる負荷の環境で `verify.ps1` を 3 回流し、結果が一致するかを見る |
| I6 | 質問票と承認の判断を、重要度で分ける | 質問票はすべて「推奨どおり」、承認待ちはすべて承認だった（§2.3） | 自動化バイアスの抑制 | セキュリティ、データ、課金に関わる項目だけ、根拠を読んでから判断する |

---

## 8. 反証と留保

1. **n=1 で、条件がそろっていない。** §3 の C1〜C7 のとおりです。特に C1（要求の成熟度）と C2（コードの 92% の引継ぎ）は、new-era を大きく有利にしています。
2. **new-era の品質は、自動ゲートまでしか確認していない。そのゲートも、筆者の再実行では 1 件が時間切れになった（§2.5.1）。** 手動試験（MT-01〜05）、clean-host 試験、UAT、Copilot の実際の応答を使った評価は未実施です。
3. **規模が小さい。** 単体のデスクトップアプリで、EOS レポートが対象にした「企業向けの大規模分散アプリ」（複数サービス、Azure への展開、スマホ、Power Platform）ではありません。EOS レポートの U1、U3、U4、U5 は、本件では確かめられていません。
4. **費用の比較は下限どうし。** 前版の費用は、記録の欠けと、VS Code Chat の単位の不明のため、実際より小さく見積もられています。比は「new-era が 2.6 分の 1 以下」としか言えません。
5. **Prompt の作り込みも「人の投資」である。** P-RD と P-FR（合わせて約 90KB）は、HVE、ATG、前版、EOS レポートの経験から作られました。その作成の費用は、どちらの集計にも入っていません。ただし、Prompt は次のアプリでも再利用できる資産です。
6. **外部の根拠にも留保がある。** harness が品質を大きく上げた例もあります（X8 の初期の実験では、harness の方が 20 倍以上高価で、品質ははっきり上だった）。評価役のエージェントは、タスクがモデルの単独の能力の境界にあるときに効きます（X8）。モデルの能力を超える規模のアプリでは、harness の価値が戻る可能性があります。

- 推論: 1〜6 は、H1・H2 の判定を覆しません。HVE と ATG を続ける根拠になる事実は、本件にも外部の資料にもありませんでした。1・2・3 は、H3・H4 の判定を「条件付き」にとどめる理由であり、§9 で測るべき項目です。

---

## 9. 次に測るべきこと

### 9.1 EOS レポートの未検証事項のうち、本件で確かめたもの

| # | 未検証事項（EOS レポート §9） | 本件の結果 |
|---:|---|---|
| U9 | 改訂した P-FR が、検証スクリプトと CI を作り、exit code で完了を判定するか | **おおむね達成。** `scripts/verify.ps1`／`verify.sh`、`verify-management-data.ps1`、`.github/workflows/ci.yml`・`codeql.yml`・`dependency-review.yml` を作り、要求 ID の整合を検査した。ただし、筆者が別のプロセスで再実行すると、時間に依存するテスト 1 件が失敗して exit code 1 になった。ゲートが決定的かどうかは、P-FR の検証の対象に加える必要がある（§2.5.1、§7 の I7） |
| U8 | 承認の運用の負担 | **最初の実測。** 質問票 9 件、承認依頼 10 件、保留 4 件の判断に、Prompt 5 回・合計 14 分。ただし判断の質（自動化バイアス）は未評価 |
| U1 | 既存の大きなコードベースへの繰り返し適用 | **一部。** 前版の 11 万行のコードに 1 回適用し、既存のテストを壊さずに機能を追加・削除した。Wave を 3 回以上回す確認は未実施 |
| U2 | 要求定義書と catalog の大きさの上限 | **一部。** 要求定義書 176KB・要求 95 件、catalog 31KB で、分割の閾値（150 件、300KB）の手前。ID のずれは `verify-management-data.ps1` で 0 件 |
| U3〜U7 | Azure への展開、スマホ・Power Platform、P-ST の有効性、費用の上限、AI 評価の安定性 | 未検証（本件の範囲外） |

### 9.2 追加の実験（案）

| # | 実験 | 目的 | 判定の基準（案） |
|---:|---|---|---|
| E-1 | **クリーンルームの再実装**: 空のリポジトリに、確定した要求定義書（new-era の版）だけを置き、前版のコードを参照させずに P-FR を実行する | C2（コードの引継ぎ）の効果を分ける | `verify.ps1` が exit 0。AC の対応率。時間と AIU を new-era と比べる |
| E-2 | **要求の発見から**: 前版の最初の 3.7KB の依頼文から、P-RD → 承認 → P-FR の順で作る | C1（要求の成熟度）の効果を分ける。前版の 32 日と、最も近い条件で比べる | 人の介入の回数と時間、AIU、到達した機能の範囲 |
| E-3 | **モデルと effort の比較**: E-1 を、Opus 5.5（`high`／`medium`）と、Sonnet 5.5 のサブエージェントで行う | §7 の I1、I2 | 同じ合否で、費用と時間が下がるか |
| E-4 | **Prompt の削減の比較**: P-FR の節を 1 つずつ外して実行する | §7 の I4。どの節が効いているか（X8 の方法） | 合否が変わらない節は削る |
| E-5 | **new-era の手動試験と UAT**: MT-01〜MT-05 と、前版と同じ見本での G-001（操作数と処理時間）の比較 | §2.5 の空白を埋める | MT がすべて PASS。G-001 が前版以下 |
| E-6 | **企業規模での Wave**: EOS レポート §0.3 の 4 のとおり、小さな業務アプリで Wave 1（ローカル）と Wave 2（dev 環境へのデプロイ）を通す | U1、U3、U5 | EOS レポート §9 の基準 |

---

## 10. まとめ

- **HVE と ATG を止める判断は、この実証でも正しいと言えます。** new-era は、HVE も ATG も Skill も使わず、7 回の Prompt と 1 日で、検証ゲートをほぼ通る後継版を作りました（筆者の再実行では、時間に依存するテスト 1 件が環境の負荷で失敗しました）。
- **ただし、この速さの大部分は、前版の 32 日で確定した要求定義書とコードを引き継いだことによるものです。** 「Vibe Coding でアプリが 1 日でできる」ではなく、「**要求が確定していれば、その実装と変更は、人の介入 1〜2 桁少なく進められる**」と読むのが正確です。
- **harness はなくなったのではなく、移動しました。** 独自のフレームワークは不要になり、その役割は Copilot 本体の機能、公式ガイドに沿った Prompt、リポジトリの中の決定的なゲートに移りました。この 3 つは今後も必要です。ただし、モデルが良くなるたびに、Prompt の作法は削れる部分が増えていきます。
- **次の一手は、公平な比較（E-1、E-2）と、費用の最適化（effort と Sonnet 5.5）、そして UAT です。**

---

## 11. 出典

### 11.1 内部資料

- `c:\Work\202610051515-DevelopmentHistoryReport.md`（前版の開発履歴）
- `c:\Work\202610070515-DevelopmentHistoryReport.md`（new-era の開発履歴）
- `c:\Work\202610031135-HVE_EOS_ValidationReport.md`（EOS レポート、第 4 版）
- `C:\GitHub\StudyReport-Evaluator`（HEAD `94e5d8c`）: `docs/requirements-definition.md`、`[ExcelReportEvaluator] 1.要求定義書作成.txt`、`.github/workflows/`、`work/`、Git 履歴
- `C:\GitHub\StudyReport-Evaluator-new-era`（`8170eb5`、`e09bdcf`）: `docs/requirements-definition.md`、`docs/requirements-definition-draft.md`、`docs/catalog.md`、`docs/manual-tests.md`、`scripts/verify.ps1`、`.github/workflows/`、Git 履歴
- セッション `46a7048d-ad98-4a14-9ebc-92bc98996675` の `events.jsonl`、Prompt 1 と Prompt 7 の添付ファイル（VS Code の `agentSessionData\eb6f72b6-…\attachments\`）
- 前版の作業フォルダーの Copilot セッション 31 件の `events.jsonl`（ツールと Skill の使用回数）

### 11.2 外部資料（確認日 2026-10-07）

- Anthropic, "Claude Opus 5.5": https://www.anthropic.com/claude-opus-5-5
- Anthropic, "Prompting Claude Opus 5.5": https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5
- Anthropic, "Prompting Claude Opus 5": https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
- Anthropic, "Claude Sonnet 5.5": https://www.anthropic.com/claude-sonnet-5-5
- Anthropic, "Prompting Claude Sonnet 5.5": https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5
- Anthropic, "Claude prompting best practices": https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Anthropic, Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic（Claude blog）, "The new rules of context engineering for Claude 5-generation models": https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models
- Anthropic, "Harness design for long-running application development": https://www.anthropic.com/engineering/harness-design-long-running-apps
- Anthropic, "Effective harnesses for long-running agents": https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anthropic, "Effective context engineering for AI agents": https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic, "Building effective agents": https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, "Equipping agents for the real world with Agent Skills": https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Anthropic, "Building a C compiler with a team of parallel Claudes": https://www.anthropic.com/engineering/building-c-compiler
- Anthropic, "How we built our multi-agent research system": https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, "Claude Code best practices": https://code.claude.com/docs/en/best-practices
- GitHub Docs, "Models and pricing": https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing
- GitHub Docs, "Supported AI models": https://docs.github.com/en/copilot/reference/ai-models/supported-models
- GitHub Changelog, "GitHub Copilot CLI is now generally available"（2026-02-25）: https://github.blog/changelog/2026-02-25-github-copilot-cli-is-now-generally-available/
- GitHub Changelog, "GitHub Copilot in Visual Studio Code — March releases"（2026-04-08）: https://github.blog/changelog/2026-04-08-github-copilot-in-visual-studio-code-march-releases/
- GitHub Changelog, "Research, plan, and code with Copilot cloud agent"（2026-04-01）: https://github.blog/changelog/2026-04-01-research-plan-and-code-with-copilot-cloud-agent/
- GitHub Changelog, "Manage agent skills with GitHub CLI"（2026-04-16）: https://github.blog/changelog/2026-04-16-manage-agent-skills-with-github-cli/
- GitHub Changelog, "Copilot Memory now on by default for Pro and Pro+ users"（2026-03-04）: https://github.blog/changelog/2026-03-04-copilot-memory-now-on-by-default-for-pro-and-pro-users-in-public-preview/
- GitHub Changelog, "Configure cost and quality in Copilot auto model selection"（2026-09-14）: https://github.blog/changelog/2026-09-14-configure-cost-and-quality-in-copilot-auto-model-selection/
- GitHub Blog, "Run multiple agents at once with /fleet in Copilot CLI": https://github.blog/ai-and-ml/github-copilot/run-multiple-agents-at-once-with-fleet-in-copilot-cli/
- Vats & Golev, "The Scaffold Effect in Coding Agents", arXiv:2607.22585: https://arxiv.org/abs/2607.22585
- Xia et al., "Agentless", arXiv:2407.01489: https://arxiv.org/abs/2407.01489
- mini-SWE-agent: https://github.com/SWE-agent/mini-swe-agent
- Merrill et al., "Terminal-Bench 2.0", arXiv:2601.11868: https://arxiv.org/abs/2601.11868
- METR, "Measuring AI ability to complete long tasks": https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/
- METR, "Time Horizon 1.1": https://metr.org/blog/2026-1-29-time-horizon-1-1/
- METR, "Measuring the impact of early-2025 AI on experienced open-source developer productivity": https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
- METR, "We are changing our developer productivity experiment design": https://metr.org/blog/2026-02-24-uplift-update/
- METR, "Recent frontier models are reward hacking": https://metr.org/blog/2025-06-05-recent-reward-hacking/
- "ImpossibleBench", arXiv:2510.20270: https://arxiv.org/abs/2510.20270
- Liu et al., "Lost in the Middle", arXiv:2307.03172: https://arxiv.org/abs/2307.03172
- Chroma Research, "Context Rot": https://www.trychroma.com/research/context-rot
- Cemri et al., "Why do multi-agent LLM systems fail?", arXiv:2503.13657: https://arxiv.org/abs/2503.13657
- Deng, Fan, Meng, "Understanding the (In)Security of Vibe-Coded Applications", arXiv:2606.23130: https://arxiv.org/abs/2606.23130
- Veracode, "2025 GenAI Code Security Report": https://www.veracode.com/resources/analyst-reports/2025-genai-code-security-report/
- Sutton, "The Bitter Lesson": http://www.incompleteideas.net/IncIdeas/BitterLesson.html
- Zunic, "The Bitter Lesson of Agent Harnesses": https://browser-use.com/posts/bitter-lesson-agent-harnesses
