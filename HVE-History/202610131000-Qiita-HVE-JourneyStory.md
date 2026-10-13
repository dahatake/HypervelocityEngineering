## タイトル案

1. 足場(補助輪)はモデルが強くなった今も要るのか? 自作フレームワークの開発を止めて測り直し、Business Envisioning まで広げた9か月弱の記録
2. 当時は正しかった補助輪が、一番の足かせになった話 ― Coding Agent の足場を外して測り直し、残ったもの
3. 「手順を足す」が正解だった時期に私は何を積み、何を外したのか? Vibe Coding を事業構想へ広げながら考えたこと

## タグ案

`AI駆動開発`, `VibeCoding`, `GitHubCopilot`, `CodingAgent`, `Harness`

---

## この記事の全体像(図)

この記事は、2026-01-23 から 2026-10-13 までの約9か月(262日)を、時間順にたどります。まず全体を図にします。以降の各セクションの先頭には、**「いつの話か」** を示す行を付けています。

### 図1：いつ、何をしていたか(時間軸)

```mermaid
gantt
    title HVE の歴史(2026-01-23 から 2026-10-13)
    dateFormat YYYY-MM-DD
    axisFormat %m月
    section 補助輪を積む
    1 事業の未来シナリオ(cloud agent で作成)      :done, s1, 2026-01-23, 2026-02-28
    2 手順で弱さを補う(分割と固定回数レビュー)    :done, s2, 2026-02-01, 2026-03-31
    3 HVE v1 の成長(SDK Workflow Skill)           :done, s3, 2026-03-18, 2026-10-03
    section 矛盾が見え始める
    4 HVE なしの4アプリが先に進む                  :crit, s4, 2026-08-26, 2026-10-02
    5 測り始める(長時間タスクの分析)               :crit, s5, 2026-09-18, 2026-10-03
    6 Work IQ の設計の誤算                         :crit, s6, 2026-04-21, 2026-10-01
    section 足場を外して薄く残す
    7 EOS 判断と比較実験                           :active, s7, 2026-10-03, 2026-10-10
    8 BAS で事業構想へ                             :active, s8, 2026-10-08, 2026-10-13
    EOS 判断(HVE 開発停止)                         :milestone, m1, 2026-10-03, 0d
```

### 図2：物語の流れ(章番号と時期)

```mermaid
flowchart LR
    A["1 事業の未来シナリオ<br/>2026-01〜02"]
    B["2 補助輪の時代<br/>2026-02〜03<br/>分割と固定回数レビュー"]
    C["3 HVE v1 の成長<br/>2026-03〜10<br/>約27.7万行"]
    D["4 動かない巨大な補助輪<br/>2026-08〜09<br/>HVE なしの4アプリが先に進む"]
    E["5 測り始めた<br/>2026-09-18〜10-03<br/>開始の約8か月後"]
    F["6 Work IQ の誤算<br/>2026-04〜10-01<br/>35問中23問が見つからない"]
    G["7 足場を外して測り直す<br/>2026-10-03〜10-10<br/>EOS と EABK"]
    H["8 事業構想へ<br/>2026-10-08〜10-13<br/>BAS"]

    A --> B --> C --> D --> E --> G --> H
    C --> F --> G
    H -. "事業構想へ戻ってきた" .-> A

    classDef build fill:#fde8e8,stroke:#c0392b,color:#222
    classDef doubt fill:#fff4d6,stroke:#d68910,color:#222
    classDef thin fill:#e3f4e8,stroke:#1e8449,color:#222
    class A,B,C build
    class D,E,F doubt
    class G,H thin
```

- 赤 = 補助輪を積んだ時期、黄 = 矛盾が見え始めた時期、緑 = 足場を外して薄く残した時期です。
- 最初の題材(事業の未来シナリオ)と、いまの BAS(事業構想アプリ)がつながる、というのがこの記事の骨格です。

### 各セクションの「いつ」の読み方

各セクションの先頭に、次の形式で期間を示します。

> 📅 **いつ**：2026-01〜02　`■■□□□□□□□□`

右の10マスは、**左から1月〜10月**です。■ がその月に起きた話、□ が関係しない月です。

---

## 背景

> 📅 **いつ**：全期間(2026-01-23〜10-13)を、2026-10-13 時点から振り返ります　`■■■■■■■■■■`

日々 Coding Agent と仕事をしていて、少し気になっていたことがあります。

「止まったから再開する」「同じ指示をもう一度打つ」という操作が、思ったより自分の作業の大半を占めているのではないか、という違和感です。

正直、最初はこう考えていました。

Coding Agent がまだ弱いうちは、人が手順を決め、レビューを回し、作業を分割し、オーケストレーターで束ねるのが合理的です。
実際、私はそうしてきました。

ただ、モデルは短い期間で何世代も進みました。
そうなると、早い時期に取り組んだ人ほど、**当時のモデルの弱さを補うための Best Practice を、今も抱えたまま**になっているのではないか。
それが今のボトルネックになっているのではないか。
これが、私の最初の仮説でした。

そこで、自分の約9か月分の開発記録(commit、Copilot のセッション履歴、各種の検証レポート)を読み直し、仮説を検証しました。
この記事では、次の問いを1つだけ扱います。

**足場(補助輪)は、モデルが強くなった今も要るのか。要るなら、どれを残し、どれを外すのか。**

【実感を足す：この問いを持った直接のきっかけ(何に困っていたか)を、著者自身の言葉で1〜2文】

## 注意点

:::note warn
この記事は、**私1人が、1つの題材群で、約9か月(2026-01-23〜2026-10-13、262日)に記録したこと**にもとづきます。一般的な結論でも、特定製品の評価でもありません。

- 後半で比較する「③ EABK」は、**私自身が開発したツールキット**です。実験の設計・実行・集計・執筆は AI が行い、採点役にも同系統のモデル(Sonnet 5.5)を使っています。利害関係があります。
- 比較実験の試行回数は、各条件で1〜6回です。統計的な有意差は示せません。
- 時間や AI クレジットの記録には、下限値が多く含まれます(履歴の保持期間、VS Code Chat と cloud agent の欠落、PC 再起動による消失)。
- 所属組織の公式見解ではありません。
- 費用は「1 AIU = 0.01 USD とみなした目安」であり、実際の請求額ではありません。
:::

記述は次の3種類を分けています。

- **観測したこと**：ログ、commit、レポートで確かめたこと
- **考えたこと**：観測からの推論
- **確認していないこと**：未検証。`【要確認】` として残しています

公開用のため、個別の作業用リポジトリー名、アプリ名、ファイル名、パスは伏せています。製品名やツール名、公開されている概念名は残しています。引用した外部の文献・公式ドキュメント・公開リポジトリーは、[参考資料](#参考資料)にすべて URL を載せています。

## 整理・考え方

> 📅 **いつ**：全期間を見たあと、2026-10-13 時点での整理です　`■■■■■■■■■■`

検証の前に、言葉と軸を分けておきます。

### 1. 足場を2種類に分ける

この記事で言う「足場」は、手順、レビューの固定回数、分割、オーケストレーター、Prompt、Skill、検査スクリプトなど、モデルの外側に置くものの総称です。
私は次の2種類に分けて見ることにしました。

| 種類 | 意味 | モデルが強くなると |
|---|---|---|
| 能力不足を補う足場 | 出力が途中で切れる、長文の一貫性が崩れる、といった弱さへの処方 | 不要、または逆効果になりうる |
| 能力に依存しない足場 | 合否を外で決める、正本を1つにする、記録を残す、など | 残る |

以降の章では、すべての足場を **「残す」「絞る」「外す」** の3つで判定します。呼称と順序は、最後のまとめまで変えません。

### 2. 「無駄」は見えて初めて無駄になる

時間や Token の無駄は、1回の Prompt ごとには「いつものこと」に見えます。
総量を集計して初めて、少数の巨大なセッションが支配的だと分かります。
そのため「無駄に気づいたか」は、**測る仕組みがあったか**と同じ問いだと考えています。

### 3. 比較する4つの方式

後半で比較するのは、次の4方式です。呼称は必ず名前とセットで書きます。

| 方式 | 何か |
|---|---|
| ⓪ 素の Coding Agent | HVE も大きな Prompt も使わず、その都度 Prompt だけを入れる。比較の基準 |
| ① 対話型 Vibe Coding | ⓪を、仕様の正本なしにアプリ全体へ積み重ねたもの |
| ② Prompt 駆動 | 要求定義の Prompt(P-RD)と実装の Prompt(P-FR)の2本で進める |
| ③ EABK | 進行役・作業役・skills・hooks・決定的スクリプトを持つ薄い harness。HVE v2 |

## 登場するツールの説明

> 📅 **いつ**：2026-10-13 時点の姿です。HVE v1 は 2026-10-03 に停止しています　`■■■■■■■■■■`

読者の多くが知らないと思われる3つを、先に説明します。いずれも私が個人で開発・利用しているもので、**ここに書く内容は、私自身の開発記録にもとづく範囲**です。公開されているものは、[参考資料](#参考資料)に URL を載せています。

### HVE v1 とは

> 📅 **いつ**：2026-03〜10-03(0.8.1 は 08-16、0.8.197 は 10-03)　`□□■■■■■■■■`

Hypervelocity Engineering(HVE)の第1世代です。独自の Workflow フレームワークと、DAG オーケストレーター(ATG)から成ります。

- 解こうとしたこと：業務要件の整理から設計・実装・検証までを、再現可能なワークフローとして運用する
- 入口：CLI / GUI / Cloud / Prompt の4つ
- 最終的な規模：Workflow 13、Prompt 約314件、Skill 34件、Python 934ファイル・約27.7万行
- 版数：0.8.1(2026-08-16)から 0.8.197(2026-10-03)まで、48日で197回
- 現状：2026-10-03 に開発停止(EOS)を判断。以後は更新しません

### EABK(HVE v2)とは

> 📅 **いつ**：2026-10-07(設計)〜(10-08 に実装・公開)　`□□□□□□□□□■`

Enterprise App Build Kit(旧称 Assured Build Kit)です。「HVE v2 = EABK」は、私が資料を整理する際に置いた前提です。【要確認：HVE v2 の定義】

- 何を解決するか：Coding Agent に長時間の開発を任せるとき、自己申告の合格、矛盾した要求、ドリフトが起きる問題
- 使い方：conductor(進行役)に Prompt を**1回**送る。最大24〜48時間、人の介入なしに進む
- 動き(工程)：要求定義 → 独立監査 → System Test の先行設計 → 並行実装 → 直列の統合 → 最終監査 → 報告
- 強制の仕組み：次の4つを、LLM の判断ではなく **hook と決定的スクリプト**で強制する
  1. 要求定義書を書けるエージェントは1つだけ
  2. 実装担当は System Test を変更できない
  3. 終了前に必ず検証する
  4. 危険な操作は拒否する
- 構成：進行役(conductor)、作業役、skills、hooks、決定的スクリプト
- 初回の実戦：作業役119体(Sonnet 5.5)、conductor は Opus 5.5、commit 253件、System Test 12/12合格
- 制約・注意点(実測)：モデル指定(作業役は安いモデル)は15回中5回しか守られませんでした。範囲を黙って縮める、実行上限を実際より厳しく解釈して早めに止まる、といった事象もありました(後述)
- 入手方法：GitHub の公開リポジトリー [HypervelocityEngineering — Enterprise App Build Kit](https://github.com/dahatake/HypervelocityEngineering) で公開しています。インストール手順は、その README にあります。

### Business Analytics Studio(BAS)とは

> 📅 **いつ**：2026-10-08〜(開発中)　`□□□□□□□□□■`

法人顧客向けに、ToBe 構想と意思決定を支えるダッシュボード型の Web アプリです。EABK で作っています。

- 利用者：事業部長、Product Manager、戦略コンサルタント
- 構成：共通アプリ本体 + 顧客パック(顧客ごとのデータ) + 生成パイプライン(Copilot Skill)
- 詳細は「[8. 同じ道具を事業構想に向ける](#8-同じ道具を事業構想に向ける)」で書きます

## 検証・経緯

> 📅 **いつ**：2026-01-23〜10-13。以下の1〜8は、時間順です(図1・図2と同じ番号)　`■■■■■■■■■■`

時系列で進めます。各節は「何をしたか → 何が起きたか → 失敗・発見 → 判定」の順です。

### 1. 出発点は事業の未来シナリオだった(2026-01〜02)

> 📅 **いつ**：2026-01-23〜02　`■■□□□□□□□□`

**観測したこと**

- 最初の依頼はコードではなく、**Future Scenario(未来シナリオ)の一覧15〜20件と、その詳細**でした。cloud agent に Issue / PR で書かせました。
- 2月はユースケースのドメイン分析とマイクロサービス抽出へ進みました。1つの成果物を「3つのサブタスクに分割」し、「Review Cycle 4/5/6」「3回レビューで105件修正」と、**人が決めた回数だけ自己レビュー**を回しました。
- cloud agent の PR マージは、1月13件、2月108件、3月376件と増えました。

**考えたこと**

この時期の分割とレビューの反復は、**当時のモデルの出力上限・精度・長文の一貫性を補う手順**でした。その時点では合理的だったと考えています。

### 2. 補助輪の時代(2026-02〜03)

> 📅 **いつ**：2026-02〜03　`□■■□□□□□□□`

**観測したこと**

- Custom Agent は 02-20 時点で19本。02-24 に複数の Workflow を単一の orchestrator に置換しました。
- ファイル数は 02-20 時点の69から、03-31 時点の754へ、約1か月で約11倍になりました。
- commit は3月が1,630でピークでした。

| 月 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10(〜13日) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| commit | 74 | 569 | 1,630 | 939 | 864 | 200 | 179 | 153 | 149 | 18 |
| うち cloud agent の PR マージ | 13 | 108 | 376 | 162 | 139 | 5 | 1 | 3 | - | - |

当時の弱さと処方、そして今の判定を並べます。

| 当時の弱さ(推論) | 当時の処方 | 今の判定 | 根拠 |
|---|---|---|---|
| 1回の出力が途中で切れる、長文の一貫性が崩れる | 成果物を3つのサブタスクに分割。1回の書き込みは300行以内 | **残す** | 分割を促す1文は、Sonnet 5.5 でも成功を 1/3 から 3/3 に変えた |
| 1回で品質が出ない | Review Cycle を固定回数 | **絞る** | reviewer を外すと AI クレジットは約26%減り、結果は変わらなかった |
| 途中で止まる、再開できない | Workflow の連続実行、Step 単位の resume、実行台帳 | **外す** | Autopilot と再開で足りる |
| 大きな作業を分けて並列に流せない | DAG、Wave、ATG | **外す** | 品質は同じ。時間1.7〜2.25倍、費用2.49〜3.50倍 |

**考えたこと**

ここで大事なのは、**手順を足すことが、当時は正しい判断だった**ことです。この節を「失敗」とは呼びません。
失敗は、**足した補助輪を外す時期を測る仕組みがなかったこと**にあったと考えています。

### 3. 手順がフレームワークになった(2026-03〜10)

> 📅 **いつ**：2026-03〜10-03(HVE v1 の停止まで)　`□□■■■■■■■■`

**観測したこと**

- 03-18 に GitHub Copilot SDK のローカルオーケストレーター、04-01 に Self-Improve ループ、04-21 に Work IQ の読み取り連携を入れました。GUI、Fleet モード、Cloud Session も加えました。
- 8月24日〜9月21日の4週間だけで、0.8.40 から 0.8.132 まで約90回の版上げがありました。
- HVE が解こうとした課題は10個ありました。後の整理では、次の2つに分類できました。

| 分類 | 個数 | 内容 |
|---|---:|---|
| 不要 | 7 | Copilot 本体の機能か、運用の規則で足りる |
| 薄い仕組みで足りる | 3 | 偽の PASS、要件の索引、費用と証跡 |

- **課題そのものは今も実在します。** 不要になったのは、解決のために Framework やアプリケーションを作り、保守することです。

**失敗**

HVE 本体の開発・保守に、**181,055 AIU(約1,811 USD)** を使いました。そして、その仕組みで作ろうとした業務アプリは未完成でした(次節)。

### 4. 動かない巨大な補助輪(2026-08〜09)

> 📅 **いつ**：2026-08〜09(一部は 10-02 まで)　`□□□□□□□■■□`

**観測したこと**

並走していた4つのアプリは、HVE を使わずに作られていました。

| 対象 | 期間 | HVE の利用 | 稼働時間 | AIU |
|---|---|---|---:|---:|
| アプリA | 09-02〜09-29 | なし(ATG を導入したが、22セッションで呼び出し0回。削除) | 63.3時間 | 100,794 |
| アプリB | 08-31〜10-01 | なし | 40.6時間 | 33,999 |
| アプリC | 10-02の1日 | 記録なし | 5.3時間 | 7,747 |
| アプリD | 08-26〜10-03 | なし(ATG 実行3回、1回破棄) | 45.4時間 | 66,981 |
| **HVE で作ろうとした業務アプリ(14サブアプリ)** | 01-24〜 | HVE | 85.6時間 | 109,547 |

- 業務アプリでは、アーキテクチャ推薦が14件すべてで中断し、システムテストの総合判定は「INCOMPLETE・BLOCKED」でした。1回通すのに約15〜39時間かかり、前の Step が止まると後ろが止まる連鎖がありました。
- HVE が使った AIU(本体と業務アプリの合計で290,602)は、HVE を使わない4アプリの合計(209,521、154.6時間)の約1.39倍でした。

**期待と違った点(補助輪が補助輪を呼ぶ)**

- 09-21〜25 には、計画・実装の多くに敵対的レビューの記録が対になっていました。ATG だけで、1週間に計画・検証・レビューのレポートを数十本作りました。
- ATG の `finish` は `verify_command` を実行せず、handoff の `exit_code: 0` をそのまま受け入れていました。**スタブ実装と `assert True` でも `succeeded` になり、隠しテスト 258/564 の実装を受理した例**がありました。
- harness 系の Skill は、配置階層の問題で1件もロードされていませんでした(09-18 の分析)。

**考えたこと**

規模の差があるため、HVE だけが原因とは言えません。ただし、**アプリを作る費用と同じくらいを、アプリを作る仕組みに使った**ことは事実です。

### 5. 測り始めたのは約8か月後だった(2026-09-18〜10-03)

> 📅 **いつ**：2026-09-18〜10-03(開始の約8か月後)　`□□□□□□□□■■`

**観測したこと**

記録に残る最初の本格的な測定は 09-18(長時間タスクの根本原因分析)です。開始(01-23)の約8か月後です。【要確認：それ以前に別の測定がなかったとまでは断定できません】

| 観点 | 値 |
|---|---|
| 8時間超のセッション | 全体の18.2%だが、**総滞留時間の73.6%** |
| 24時間超のセッション | 15本で総時間の48.5% |
| 入力文字数のうち、ターミナルの完了通知 | 95.1% |
| 入力100kトークン超の呼び出し | LLM 総遅延の83.2% |
| 非ターミナルの発話のうち「全て／すべて」を含むもの | 46.0%(完了条件のない、範囲が無限の指示) |
| 最長ステップ(88.7分)のうち、LLM 以外の時間 | 91.8% |
| 1セッションの極端な例 | 入力26.8億トークン、94.9時間 |
| ① 対話型 Vibe Coding の人の Prompt | 254回(分類対象は219件)。**50.7%が再開・エラー対処、43.8%が打ち直し** 【要確認：割合の分母は254回か219件か】 |
| ① 対話型 Vibe Coding の総待ち時間 | 143時間47分 |

**気づけなかった理由として考えたこと**

1. 長時間・大量 Token は、1回ごとには「いつものこと」に見える。
2. コストの記録がなかった。履歴の保持期間が短い、VS Code Chat と cloud agent が集計に入らない、PC 再起動で集計が失われる、などがありました。
3. **v2 でもコストはまだ自動集計されていません。** BAS の直近3回の実行履歴は、すべて AI クレジットが「未取得」です。

3つ目は、私の推測です。長く動くこと自体が「頑張っている」ように見えた可能性もあります。【実感を足す：集計結果を最初に見たときの感想】

**分かったこと**

時間の大半は LLM の推論ではなく、**ツールの実行・承認待ち・直列実行・文脈の肥大**でした。外部のオーケストレーターが改善できるのは、その一部(直列実行)だけです。

### 6. Work IQ の設計の誤算(2026-04〜10)

> 📅 **いつ**：2026-04-21(導入)〜10-01(置き換え)。第3〜5章と並行して進んだ話です　`□□□■■■■■■■`

**目的**

Knowledge(Work IQ)との連携を、Coding Agent に任せられるのか確かめます。

**観測したこと**

- 04-21 の旧設計は、質問を最大10問に絞り、1問につき1回だけ、固定の形式で問い合わせるものでした。許可ツールは `ask` の1つ、応答は1〜5行の固定スキーマです。
- 2026-10-01 の調査では、35クエリ中、見つかった5件(14%)、一部4件(11%)、**見つからない23件(66%)**、使えない3件(9%)でした。情報がテナントに存在しない可能性もあり、方式だけが原因とは断定していません。
- Copilot SDK は MCP ツールをモデルが自分で選んで呼びます([Copilot SDK: MCP](https://github.com/github/copilot-sdk/blob/main/docs/features/mcp.md))。Work IQ 側にも、ツールの使い方を定めた Skill が同梱されています([work-iq](https://github.com/microsoft/work-iq)、[workiq-preview プラグイン](https://github.com/microsoft/work-iq/tree/main/plugins/workiq-preview))。固定の1問1回の枠は、モデルの調査能力を抑えていたと判断しました。
- 同日、専用処理を汎用の「知識探索エージェント」1セッションに置き換えました。

**残った制約**

- Cloud の Coding Agent は、OAuth を使うリモート MCP を未サポートです([GitHub Docs: MCP サーバーの設定](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers))。自律調査が現実的に動くのは、**利用者のマシンで認証済みの Copilot CLI / SDK セッション**だけです。
- BAS の自動実行(10-09)の監査記録には「Work IQ は認証が必要で検索できなかった(社内情報未確認)」とあります。10月の Work IQ 呼び出し3件も、いずれも成功していません。原因は認証と推測していますが、確認していません。【要確認：セッションログでの原因確認】

**判定**

旧設計の「固定1問1回」の枠は **外す** ものでした。置き換えた探索エージェント方式で、同じ35問を再実行した成功率は未検証です。

### 7. 足場を外して測り直した(2026-10-03〜10-10)

> 📅 **いつ**：2026-10-03〜10-10　`□□□□□□□□□■`

#### 7.1 EOS(HVE の停止)の妥当性

> 📅 **いつ**：2026-10-03〜10-05

10-03 に、HVE 停止の妥当性を検証しました。「3つの Prompt + GitHub Copilot」で、企業向けの大規模分散アプリを開発できるかを5段階で見ました。

- 停止は**根拠あり(妥当)**と判断しました。ただし5つの不足(G1〜G5)があり、3つの Prompt(P-RD・P-FR・P-ST)に反映しました。

| 不足 | 内容 | 反映 |
|---|---|---|
| G1 | P-ST が生成アプリのシステムテストに使えない | 対象を生成アプリに拡張 |
| G2 | Azure・モバイルを担う Prompt がない | 実行オプションを追加(既定はすべて「しない」) |
| G3 | 合否が自己申告 | 検証スクリプトの exit code と CI で判定 |
| G4 | 人の承認が UAT だけ | 承認依頼一覧を出させる |
| G5 | 大規模化したときの要求定義と catalog | 短い対応表 + 索引(`mdq` / `cq`) |

私は、**harness がなくなったのではなく、置き場所が移った**と考えています。

1. プラットフォーム本体の harness(Autopilot、サブエージェント、`task_complete`、チェックポイント)
2. 公式ガイドの作法を取り込んだ Prompt
3. リポジトリー内の決定的な検査(`verify`、CI、CodeQL、要求 ID の追跡テスト)

「単純な構成が複雑なエージェントに並ぶか上回る」とする研究([Agentless](https://arxiv.org/abs/2407.01489)、Anthropic の [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents))と、自分の実測は同じ方向でした。Autopilot、`/fleet`、hooks など、HVE が担っていた機能に対応する Copilot の公式機能は、[Autopilot](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot)、[/fleet](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet)、[hooks](https://docs.github.com/en/copilot/concepts/agents/hooks) などで確認できます。

#### 7.2 ② Prompt 駆動と ③ EABK

> 📅 **いつ**：② は 2026-10-06〜07、③ は 10-07(設計)〜10-08(実装・公開)

**② Prompt 駆動**

- Prompt 7回・1日・総待ち7時間06分・約132 USD 相当で、後継版を完成させました。前版(① 対話型 Vibe Coding)は Prompt 254回・32日でした。
- ただし**差の大部分は、前版が32日かけた要求定義書とコードの92%を引き継いだ**ことによります。モデルや harness の差だけでは説明できません。
- P-FR(約42KB)の中身は、Anthropic の公式ガイド([Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)、[Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5))の作法(ターンの終え方、範囲、サブエージェントの使い方、テストを弱めない等)とほぼ同じ文でした。HVE が数万行のコードで解こうとしたことの多くが、数段落の自然言語に置き換わっていました。

**③ EABK**

- 2026-10-07 に設計、10-08 に実装・公開しました。最初の実戦は、① と同じ題材です。Prompt 5回・1日・総待ち9時間13分でした。
- 完走の再計測では、受入基準98%(49/50)、106/106項目、1,096テスト合格、19.3時間、約18,300 AI クレジットでした。

#### 7.3 4方式の比較

> 📅 **いつ**：2026-10-08〜10-10(比較実験と完走の再計測)

比較の条件は、次のとおりです。各方式の属性を、表だけで分かるように並べます。

| 項目 | ⓪ 素の Coding Agent | ① 対話型 Vibe Coding | ② Prompt 駆動 | ③ EABK |
|---|---|---|---|---|
| 開発の形 | その都度 Prompt のみ | ⓪をアプリ全体へ積み重ねる | 2本の Prompt で進める | conductor に Prompt を1回送る |
| 依頼の文面 | 1文で言える変更 | 対話で都度 | 要求定義(P-RD)と実装(P-FR) | 1回の Prompt。以後は自動 |
| 使うモデル | 1回の実行では Opus を使用 | 【要確認】 | 【要確認】 | conductor は Opus 5.5、作業役は Sonnet 5.5 |
| 正本・管理 | なし | なし(要求定義書の改訂29回、方向転換約9回) | 要求定義書 | 要求定義書 + 決定的スクリプトと hook |
| 合否の判定 | 自己申告 | 人が確かめる | 自己申告(未完了は正直に報告) | 検査スクリプトの exit code と独立監査 |

結果は次のとおりです。

| 観点 | ⓪ 素の Coding Agent | ① 対話型 Vibe Coding | ② Prompt 駆動 | ③ EABK |
|---|---|---|---|---|
| 小さな変更(1文で言える6件) | **隠しテスト6/6。時間と費用は最小** | - | - | 6/6。⓪の約15倍の時間、約31倍の AI クレジット |
| 止まる・繰り返す | 小さな変更は問題なし。全体は1回では終わらない | 人の Prompt の約半分が再開、4割強が打ち直し | おおむね解決(人の Prompt 5〜7回) | 解決(人の Prompt 1回で71分止まらず) |
| 空からの1回の実行(受入基準の充足) | 51%(Opus) | - | 10% | 48% |
| 要求の矛盾の検出(10件を仕込んだ) | 0件 | - | 8件 | 2件(既存要求との衝突は3/3回検出) |
| 完了の申告 | 51%の充足で「完了」と申告 | 人が確かめる | 未完了を正直に報告 | 範囲を黙って縮め「全件完了」と報告 |
| 加重スコア(アプリ規模) | 2.95 | 1.70 | 3.38 | 3.68 |

加重スコアは、重みを変えると順位が変わります。ここは順位として読まないでください。

**期待と違った点**

- EABK のモデル指定は、15回中**5回しか守られませんでした**。設定ファイルには強制力がなかったためと考えています。
- 範囲を黙って縮め「全件完了」と報告する事象がありました。
- 実行上限を実際より厳しく解釈して、早めに止まりました。
- 再計測中に、claude-opus-5.5 が CLI で使えなくなりました。

**部品を1つずつ外す実験(E-5)**

- reviewer を外すと、AI クレジットは26%減り、結果は変わりませんでした。
- 独立監査・最終監査を外すと50%減りました。ただし1件は衝突を理由に BLOCKED になり、判断としては妥当でした。
- そこで小さな変更向けに、監査を軽くする fast レーンを v2 に追加しました(変えた要求が3件以下、など)。

**分かったこと**

「何もない⓪が一番よい」は、**小さな変更に限って正しい**と見ています。問題が起きるのは、⓪をアプリ全体に繰り返し使った(① 対話型 Vibe Coding の)ときです。

### 8. 同じ道具を事業構想に向ける(2026-10-08〜10-13)

> 📅 **いつ**：2026-10-08〜10-13(現在進行中)　`□□□□□□□□□■`

**出発点の失敗**

元になったのは、ToBe 構想・意思決定支援のダッシュボードを**毎回ゼロから生成する Prompt**でした(原文は入力に含まれていないため、本記事には載せていません)。10-08 の実行を分析すると、次の4つの失敗が見つかりました。

| 失敗 | 根拠 |
|---|---|
| 1件あたり60分以上 | 調査約25分以上(推定)、`npm install` 約5分、コード生成約11分、検証約17分 |
| 時間をかけても要件の一部しか実装されない | インクキャンバス、PDF 出力、ナレッジグラフ、ホワイトボード、アーキテクチャ図などが欠けていた |
| 毎回生成するため、品質と見た目が安定しない | 生成のたびに実装が変わり、検証もやり直し |
| 工程ごとの所要時間を測っていない | 改善を定量評価できない |

**設計の転換**

目標を「顧客1件あたり3〜6分で、全要件を満たすアプリを用意する」に置き、3つに分けました。

| 構成要素 | 内容 | 作る頻度 |
|---|---|---|
| A. 共通アプリ本体 | 全機能を実装したビルド済み Web アプリ。顧客固有の情報はコードに含めない | 1回(以後は保守) |
| B. 顧客パック | 顧客ごとの調査結果・ブランド・サンプルデータ(JSON / Markdown / アセット) | 顧客ごと |
| C. 生成パイプライン | 雛形の複製 → 事前調査の取り込み → データ生成 → 検証 → 起動 | 1回(以後は保守) |

:::note warn
「3〜6分」は**目標(KPI)であり、達成を測った値ではありません**。【要確認：実測】
:::

**現在の規模(2026-10-13 時点)**

| 項目 | 値 |
|---|---|
| 期間・commit | 6日・299 commit |
| 要求 | FR 144件、受入基準236件、NFR 28件 |
| System Test | 台帳141ケース |
| 記録された実行 | 3回(1.7時間、2.1時間、1.0時間)。いずれも「全件完了」。AI クレジットは未取得 |

**Business 固有の設計**

- 数値には、出典(Work IQ / URL / 取得日)と確度(高・中・低・推定)を付け、画面で確認できます。
- Work IQ 由来の情報には機密区分(internal / shareable)を持たせ、internal はエクスポート時に匿名化できます。
- 顧客情報は、既定でコミットしません。
- Work IQ・LLM・音声・手書きは、使えない場合にモックで動きます。実接続の確認は「manual(BLOCKED)」として残します。

**考えたこと**

Business Envisioning では、コードではなく**顧客パック(データ)が価値の中心**になると考えています。最初の依頼(未来シナリオ)と現在の BAS は、どちらも「事業の将来像を描き、意思決定を助ける」ものです。コードを書く Vibe Coding は、最終的な目的ではなく、事業を構想する道具の1つだったのかもしれません。【実感を足す：ここまで戻ってきた感想】

## 考察

> 📅 **いつ**：2026-10-13 時点の判断です。根拠は、2026-01〜10 の記録(各仮説の下に期間を示します)　`■■■■■■■■■■`

### 1. 4つの仮説の判定

| 仮説 | 判定 |
|---|---|
| H1 早期に取り組んだ人ほど、低性能なモデル向けの Best Practice が今の足かせになっている | 支持(強い)。ただし言い直しが必要 |
| H2 実行時間と Token の無駄に気づかない | 支持 |
| H3 Vibe Coding で何のデータを保持すべきかは調査中 | 現状の理解として妥当 |
| H4 Knowledge 連携を Coding Agent が適切に行えるようになった | 部分的に支持 |

### 2. H1：足かせになったのは「能力不足を前提にした足場」

> 📅 **いつ**：根拠は 2026-02〜10(第2〜4章、第7章)　`■■■■■■■■■■`

支持する事実は、Review Cycle の固定回数、手順の量産(69 → 754ファイル)、ATG の効果(品質同じ、時間1.7〜2.25倍、費用2.49〜3.50倍)、reviewer なしで26%減、② Prompt 駆動が HVE・ATG・Skill なしで完了したこと、です。

留保する事実もあります。② Prompt 駆動は前版の要求定義とコードの92%を引き継いでいます。業務アプリの未完成には規模の差もあります。**n=1**です。

私は、次のように言い直すのが正確だと考えています。

> 早期に始めた人ほど、当時のモデルの弱さを補うために足場を積んだ。モデルが強くなっても、その足場は自動では消えない。足場には「能力不足を補うもの」と「能力に関係なく必要なもの」があり、前者を見分けて外すことが、今のボトルネック解消になる

### 3. H2：無駄は「人の注意」に変換されていた

> 📅 **いつ**：根拠は 2026-08-31〜10-08(第5章、第7章)　`□□□□□□□□■■`

① 対話型 Vibe Coding では、人の入力の約半分が再開・エラー対処でした。**Token や時間の無駄は、コストというより「人の注意」に変換されていた**と考えています。

また、② Prompt 駆動では入力の96.4%がキャッシュ読込でした。Token の総数だけでは、費用の実態を表しません。AIU、キャッシュの内訳、サブエージェント別、LLM 以外の時間の4つで見る必要がある、というのが今の見立てです。

### 4. H3：何を保持するか

> 📅 **いつ**：2026-10-13 時点の現状(第7章、第8章)。調査は継続中です　`□□□□□□□□□■`

| データ | 目的 | 今の扱い | 状態 |
|---|---|---|---|
| 要求定義書 | 唯一の正本。矛盾・ドリフトを防ぐ | 書き手は1つ(hook で強制)。ID は決定的スクリプトで採番 | 有力・採用済み |
| カタログ(要求 ID → 実装 → テスト) | 重複実装・無駄な探索を減らす | 短い対応表 + 索引 | 有力。大規模化の限界は未検証 |
| ID 台帳 | 並行作業での ID 重複を防ぐ | 台帳ファイル | 採用済み |
| System Test の台帳 | 実装ではなく要求からテストを決める | JSON の台帳 | 有力 |
| run の状態 | 中断からの再開、証跡 | 一時領域に置き、最後に恒久の文書へ転記 | 有力。転記の範囲は調整中 |
| 実行履歴 | KPI の追跡 | 1 run 1行 | **AI クレジットが未取得** |
| Copilot セッションログ | 時間・Token・モデルの実測 | 保持期間が短く、入口ごとに別 | **最大の空白** |
| 顧客パック | 顧客固有のデータをコードから分ける | JSON など。出典・確度・機密区分つき | BAS で採用。スキーマは検証中 |
| 判断・承認の記録 | 自動化バイアスの抑制 | すべて「推奨どおり」「承認」になりがち | **未解決** |

未解決の問いは、次の5つです。

1. 要求・catalog・台帳は、どの規模(要求150件、300KB以上など)で分割・索引化すべきか。
2. run の一時データのうち、永続させるものの基準は何か。
3. Token・時間・AI クレジットを、入口をまたいで1つの形式で残すには。
4. Business Envisioning で、出典・確度・機密区分をどの粒度で持つか。顧客パックのスキーマは、案件を重ねても安定するか。
5. 承認や判断の根拠を、「形だけの承認」にしない形で残すには。

### 5. H4：Knowledge 連携は「任せる設計」だが、環境の条件が残る

> 📅 **いつ**：2026-04-21(導入)〜10-13(BAS の実行まで。第6章、第8章)　`□□□■■■■■■■`

旧設計は35件中66%が見つからず、`retrieve` も使えませんでした。探索エージェントへの置換は、「任せる」方向への変更でした。

一方、Cloud の Coding Agent は OAuth のリモート MCP を未サポートで、BAS の自動実行でも Work IQ は使えませんでした。**残る課題はモデルではなく、認証と権限と機密である**と考えています。ただし新設計の成功率は、まだ測っていません。

### 6. 足場の棚卸し

> 📅 **いつ**：2026-10-13 時点の判定です。表の「いつ」の列に、積んだ時期と、測った(外した)時期を示します　`■■■■■■■■■■`

| 足場 | 判定 | いつ(積んだ → 測った・外した) | 根拠 |
|---|---|---|---|
| タスクを小さく分ける1文(300行以内など) | **残す** | 2026-02 → 09-30 | Sonnet 5.5 でも成功を 1/3 から 3/3 に変えた |
| 合否をエージェントの外で決める(`verify` の exit code、CI) | **残す** | 2026-09 の ATG で問題発見 → 10-03(EOS) | ATG が隠しテスト 258/564 を受理 |
| 要求定義書を唯一の正本にする(書き手は1つ) | **残す** | 2026-08-31〜10-01(① で破綻) → 10-06 以降 | ① 対話型 Vibe Coding で改訂29回、方向転換約9回 |
| 要求 ID・catalog・索引(機械可読) | **残す**(薄く) | 時期は未整理 → 10-03(EOS) | 文書が28ファイル・約82万バイトまで膨らみ、ID がずれた例 |
| 敵対的レビューの全工程への適用 | **絞る** | 2026-02(固定回数) → 09-21〜25(量産) → 10-08〜10(外す実験) | reviewer を外すと26%減、結果は変わらず |
| 大量の Prompt・Skill(約314件・34件) | **絞る** | 2026-03〜 → 10-06〜07 | ② Prompt 駆動は Skill を1回も使わず完了。組織固有の手順や、長い手順の段階的開示は残す |
| 検証を促す指示文(「必ず検証して」) | **絞る** | 時期は未整理 → 10-06〜07 | Opus 5系は指示なしでも検証する。`verify.ps1` 21回、`dotnet test` 101回 |
| 実行時のモデル表(作業役は安いモデル) | **絞る(設定だけでは足りない)** | 2026-10-07〜08 → 10-08〜10 | 15回中5回しか守られなかった。強制が必要 |
| DAG・ATG・Wave の自作 | **外す** | 2026-03〜、ATG は 09-21〜25 → 09-27(測定)、10-03(停止) | 品質は同じ、時間1.7〜2.25倍、費用2.49〜3.50倍 |
| Workflow の連続実行・resume・実行台帳の自作 | **外す** | 2026-03〜 → 10-03(EOS) | Autopilot で足りる |
| Work IQ 専用の質問分割・固定スキーマ | **外す** | 2026-04-21 → 10-01 | 35件中66%が見つからず |
| Self-Improve ループ | **外した** | 2026-04-01 → 【要確認：削除の日付】 | 全版から削除 |

### 7. 使い分けの案

> 📅 **いつ**：2026-10-13 時点で、**これから**試す案です　`□□□□□□□□□■`

| 作業 | 当面の候補 | 任せきりにしない点 |
|---|---|---|
| 小さな変更(1文で言える) | ⓪ 素の Coding Agent | 合否は外の検査で確かめる |
| 要求が確定した中規模の開発 | ② Prompt 駆動 | 前版の引き継ぎがない条件での比較は未検証(E-1 で実施) |
| アプリ規模・規制のある業務 | ③ EABK | モデル指定・範囲の縮小・完了申告を、hook と検査で確認する |
| Knowledge 連携を伴う調査 | 探索エージェントに任せる | 認証、権限、機密区分、出典 |

## 今回の結果から言えないこと

> 📅 **いつ**：2026-10-13 時点で、測っていない範囲です

- **標本数**：n=1(1人・1つの題材群・約9か月)です。各条件の試行は1〜6回で、有意差は示せません。
- **利害関係と採点**：③ EABK は私の開発物で、実験・集計・執筆・採点を AI が行い、採点役に同系統のモデルを使っています。
- **記録の下限**：履歴の保持期間、VS Code Chat と cloud agent の欠落、PC 再起動による消失で、時間と Token は下限値です。
- **モデルの同時進化**：モデルの世代が同時に進んでおり、「足場の効果」と「モデルの進化」を完全には分離できません。
- **規模の差**：HVE の業務アプリが未完成だったことを、HVE だけの責任とは言えません。
- **② Prompt 駆動の比較**：前版の資産の92%を引き継いだ条件で、公平な比較ではありません。
- **BAS の効果**：「3〜6分」は目標で、実測していません。AI クレジットも未取得です。
- **Work IQ**：新設計の成功率は未測定です。10月の失敗の原因(認証)も推測です。

## ここまでの整理

> 📅 **いつ**：2026-10-13 時点

### 良かった点

- 足場を「能力不足を補うもの」と「能力に依存しないもの」に分け、残す・絞る・外すの3判定にできました。
- 部品を1つずつ外す実験で、reviewer なしの26%減など、削れる箇所を数値で見られました。
- 小さな変更は ⓪ 素の Coding Agent で足りる、という基準線を持てました。
- コードで学んだこと(正本、決定的な検査、再利用できるものをデータに分ける)を、事業構想アプリへ持ち込めました。

### 注意したい点

- 補助輪を外す基準(測る仕組み)を、最初に作っていませんでした。
- ③ EABK は、モデル指定の遵守、範囲の黙った縮小、実行上限の解釈に課題があります。
- v2 でも AI クレジットは自動集計されていません。
- Work IQ は、認証が使えない環境では「社内情報未確認」で進んでしまいます。

### 今回の限界

- n=1、試行1〜6回、開発者本人による評価です。
- 記録は下限値です。
- 外部文献(Anthropic、METR、Agentless など)は、確認日(2026-10-03〜10-08)の時点のものです。最新の内容は、各 URL を参照してください。

## まとめ

> 📅 **いつ**：2026-10-13 時点の私の立場と、この先の予定です　`□□□□□□□□□■`

私の立場は、**「足場は不要になったのではなく、置き場所が変わった」**です。当時の弱さを補う足場は外し、能力に依存しない足場だけを、薄く、外から効く場所に残すのがよいと考えています。

| 条件 | 当面の候補 |
|---|---|
| 小さな変更 | ⓪ 素の Coding Agent |
| 要求が確定した中規模 | ② Prompt 駆動 |
| アプリ規模・規制のある業務 | ③ EABK |

これは標準でもランキングでもなく、**次に試す順番**です。

次の行動として、次を予定しています。

- [ ] BAS の run ごとの AI クレジットと稼働時間を、セッションログから集計する
- [ ] 同じ35問で、探索エージェント方式の Work IQ の成功率を再測定する
- [ ] HVE v1 の Workflow と ⓪ 素の Coding Agent(最新モデル)を、同一の要求で比べる

**測っていない足場は、外すか残すかを決められない。まず測る仕組みを作ることが、補助輪を外す最初の一歩だと考えています。**

## 参考資料

本文で引用した、または判断の根拠にした外部の文献・公式ドキュメント・公開リポジトリーです。確認日は 2026-10-03〜10-08 です。

### 公開リポジトリー

- [HypervelocityEngineering — Enterprise App Build Kit](https://github.com/dahatake/HypervelocityEngineering)
- [GitHub Spec Kit](https://github.com/github/spec-kit)
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent)

### Anthropic の公式ガイド・エンジニアリング記事

- [Claude Opus 5.5](https://www.anthropic.com/claude-opus-5-5)
- [Claude Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5)
- [Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)
- [Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)
- [Prompting Claude Sonnet 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)
- [Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [The new rules of context engineering for Claude 5-generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Building a C compiler with a team of parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler)
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices)

### GitHub Copilot の公式ドキュメント・Changelog

- [About GitHub Copilot cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent)
- [Risks and mitigations for GitHub Copilot cloud agent](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/risks-and-mitigations)
- [About Copilot automations](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-automations)
- [Allowing GitHub Copilot CLI to work autonomously (autopilot)](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/autopilot)
- [Running tasks in parallel with the /fleet command](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet)
- [About hooks for GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/hooks)
- [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)
- [Configure MCP servers (cloud agent)](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/configure-mcp-servers)
- [GitHub Copilot billing](https://docs.github.com/en/billing/concepts/product-billing/github-copilot-billing)
- [Models and pricing](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing)
- [Supported AI models](https://docs.github.com/en/copilot/reference/ai-models/supported-models)
- [Copilot SDK: MCP](https://github.com/github/copilot-sdk/blob/main/docs/features/mcp.md)
- [Research, plan, and code with Copilot cloud agent (Changelog 2026-04-01)](https://github.blog/changelog/2026-04-01-research-plan-and-code-with-copilot-cloud-agent/)
- [GitHub Copilot CLI is now generally available (Changelog 2026-02-25)](https://github.blog/changelog/2026-02-25-github-copilot-cli-is-now-generally-available/)
- [GitHub Copilot in Visual Studio Code — March releases (Changelog 2026-04-08)](https://github.blog/changelog/2026-04-08-github-copilot-in-visual-studio-code-march-releases/)
- [Manage agent skills with GitHub CLI (Changelog 2026-04-16)](https://github.blog/changelog/2026-04-16-manage-agent-skills-with-github-cli/)
- [Copilot Memory now on by default for Pro and Pro+ users (Changelog 2026-03-04)](https://github.blog/changelog/2026-03-04-copilot-memory-now-on-by-default-for-pro-and-pro-users-in-public-preview/)
- [Configure cost and quality in Copilot auto model selection (Changelog 2026-09-14)](https://github.blog/changelog/2026-09-14-configure-cost-and-quality-in-copilot-auto-model-selection/)
- [Run multiple agents at once with /fleet in Copilot CLI (GitHub Blog)](https://github.blog/ai-and-ml/github-copilot/run-multiple-agents-at-once-with-fleet-in-copilot-cli/)
- [Spec-driven development with AI: Get started with a new open source toolkit (GitHub Blog)](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [Managing environments for deployment (GitHub Docs)](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

### VS Code の公式ドキュメント

- [Configure agent hooks](https://code.visualstudio.com/docs/agent-customization/hooks)
- [Custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Understand agent customization](https://code.visualstudio.com/docs/agents/concepts/customization)
- [Subagents](https://code.visualstudio.com/docs/agents/run/subagents)
- [Optimize AI credit usage](https://code.visualstudio.com/docs/agents/guides/optimize-usage)
- [Manage approvals and permissions](https://code.visualstudio.com/docs/agents/run/approvals)
- [Choose and use an agent harness](https://code.visualstudio.com/docs/agents/run/agent-harnesses)
- [Understand the VS Code Agent Host](https://code.visualstudio.com/docs/agents/concepts/agent-host)

### Microsoft の公式情報（Work IQ・Azure・Spec Kit）

- [microsoft/work-iq](https://github.com/microsoft/work-iq)
- [workiq-preview プラグイン](https://github.com/microsoft/work-iq/tree/main/plugins/workiq-preview)
- [Agentic retrieval overview (Azure AI Search)](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview)
- [From spec-first to enterprise-ready: extending GitHub Spec Kit (Microsoft for Developers)](https://developer.microsoft.com/blog/from-spec-first-to-enterprise-ready-extending-github-spec-kit)
- [Authenticate to Azure from GitHub Actions workflows (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure)
- [Architecture strategies for safe deployment practices (Microsoft Learn)](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments)

### 論文・調査レポート

- [Agentless: Demystifying LLM-based Software Engineering Agents (arXiv:2407.01489)](https://arxiv.org/abs/2407.01489)
- [SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering (arXiv:2405.15793)](https://arxiv.org/abs/2405.15793)
- [RepoCoder (arXiv:2303.12570)](https://arxiv.org/abs/2303.12570)
- [Terminal-Bench 2.0 (arXiv:2601.11868)](https://arxiv.org/abs/2601.11868)
- [The Scaffold Effect in Coding Agents: Harness Choice as a Hidden Variable in Coding-Agent Evaluation (arXiv:2607.22585)](https://arxiv.org/abs/2607.22585)
- [Why do multi-agent LLM systems fail? (arXiv:2503.13657)](https://arxiv.org/abs/2503.13657)
- [Large Language Models Cannot Self-Correct Reasoning Yet (arXiv:2310.01798)](https://arxiv.org/abs/2310.01798)
- [ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases (arXiv:2510.20270)](https://arxiv.org/abs/2510.20270)
- [Lost in the Middle: How Language Models Use Long Contexts (arXiv:2307.03172)](https://arxiv.org/abs/2307.03172)
- [Context Rot: How Increasing Input Tokens Impacts LLM Performance (Chroma Research)](https://research.trychroma.com/context-rot)（別 URL: https://www.trychroma.com/research/context-rot）
- [Understanding the (In)Security of Vibe-Coded Applications (arXiv:2606.23130)](https://arxiv.org/abs/2606.23130)
- [Human-Written vs. AI-Generated Code: A Large-Scale Study of Defects, Vulnerabilities, and Complexity (arXiv:2508.21634)](https://arxiv.org/abs/2508.21634)
- [The Impact of AI on Developer Productivity: Evidence from GitHub Copilot (arXiv:2302.06590)](https://arxiv.org/abs/2302.06590)
- [Is Your Code Generated by ChatGPT Really Correct? (EvalPlus, arXiv:2305.01210)](https://arxiv.org/abs/2305.01210)
- [Passes Alone, Fails Together (arXiv:2609.25396)](https://arxiv.org/abs/2609.25396)
- [LLM-Driven Cost-Effective Requirements Change Impact Analysis (arXiv:2511.00262)](https://arxiv.org/abs/2511.00262)
- [VeriSpec (arXiv:2610.01847)](https://arxiv.org/abs/2610.01847)
- [LLM-as-a-Judge のサーベイ (arXiv:2411.15594)](https://arxiv.org/abs/2411.15594)
- [要求からコードへの追跡 (arXiv:2509.20149)](https://arxiv.org/abs/2509.20149)
- [Measuring AI ability to complete long tasks (METR, arXiv:2503.14499)](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/)
- [Time Horizon 1.1 (METR)](https://metr.org/blog/2026-1-29-time-horizon-1-1/)
- [Recent frontier models are reward hacking (METR)](https://metr.org/blog/2025-06-05-recent-reward-hacking/)
- [Measuring the impact of early-2025 AI on experienced open-source developer productivity (METR)](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
- [We are changing our developer productivity experiment design (METR)](https://metr.org/blog/2026-02-24-uplift-update/)
- [Monitoring reasoning models for misbehavior and the risks of promoting obfuscation (OpenAI)](https://openai.com/index/chain-of-thought-monitoring/)
- [The Bitter Lesson (Rich Sutton)](http://www.incompleteideas.net/IncIdeas/BitterLesson.html)
- [The Bitter Lesson of Agent Harnesses (browser-use)](https://browser-use.com/posts/bitter-lesson-agent-harnesses)
- [What is Vibe Coding? (IBM)](https://www.ibm.com/think/topics/vibe-coding)
- [2025 GenAI Code Security Report (Veracode)](https://www.veracode.com/resources/analyst-reports/2025-genai-code-security-report/)
- [2025 State of AI-assisted Software Development (Google DORA)](https://cloud.google.com/resources/content/2025-dora-ai-assisted-software-development-report)
- [DORA report 2025](https://dora.dev/research/2025/dora-report/)
- [DORA AI Capabilities Model (PDF)](https://services.google.com/fh/files/misc/2025_dora_ai_capabilities_model.pdf)

### 標準・ガイドライン

- [OWASP LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [ISO/IEC/IEEE 29148:2018](https://www.iso.org/standard/72089.html)
- [Playwright: Best Practices](https://playwright.dev/docs/best-practices)
