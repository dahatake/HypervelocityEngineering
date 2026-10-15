# EABK ユーザーガイド

EABK（Enterprise App Build Kit）と **EABK Studio** は、1 つのアプリケーションです。このフォルダー `users-guide/` が、その唯一のユーザーガイドです。概要・インストール・Quickstart・用語は、リポジトリ直下の [README.md](../README.md) を先に読んでください。

| 部 | 対象 | 章の記号 | 場所 |
|---|---|---|---|
| 第 1 部 | **EABK 本体**: 依頼を出し、run を進め、管理データと品質ゲートを運用する | 1〜10 | このフォルダー直下 |
| 第 2 部 | **EABK Studio**: 管理データ（データ層）を図・表・検索で見て回る、ローカル専用の閲覧アプリ | S1〜S8 | [studio/](studio/README.md) |

2 つの部は、同じデータ層（要求定義書・カタログ・System Test の台帳・ID 台帳・実行履歴）でつながっています。EABK が書き、Studio が読みます。要求や実装を変えるときは、Studio ではなく `/build` で依頼します。

## 第 1 部: EABK 本体

| # | ドキュメント | 読むタイミング |
|---|---|---|
| 1 | [依頼の書き方（/build と run_options）](01-writing-requests.md) | よい依頼・回答の書き方や、承認ポリシーを知りたい |
| 2 | [実行中と終了後](02-during-and-after-run.md) | 進捗の確認、再開、報告の読み方、マージの方法を知りたい |
| 3 | [管理データの書式](03-requirements-format.md) | 要求定義書・カタログ・ID 台帳・System Test の台帳のフォーマットを知りたい |
| 4 | [設定とカスタマイズ](04-customization.md) | ビルド・テストのコマンド、モデルの割り当て、ゲートを調整したい。MCP Server・plugin（Work IQ・Azure など）を使いたい |
| 5 | [スクリプトリファレンス](05-scripts-reference.md) | `scripts/` の各コマンドの使い方を知りたい |
| 6 | [品質ゲートと検査項目](06-quality-gates.md) | hook（G-1〜G-7）と verify（CHK-01〜27）の意味と直し方を知りたい |
| 7 | [トラブルシューティング](07-troubleshooting.md) | 止まった・拒否された・失敗した |
| 8 | [導入ロードマップと KPI](08-roadmap.md) | 診断から本番運用までの段取りと、効果の測り方を知りたい |
| 9 | [バージョンアップの手順](09-versioning.md) | 版を上げる（配布元）、導入済みのリポジトリを更新する（利用者） |
| 10 | [既存のアプリを導入する](10-adopting-existing-apps.md) | 既存のコード・設計書から、棚卸し → 逆生成の要求（承認待ち）→ 現状の挙動の固定でデータ層を整える。方式の調査と適合の検証 |
| 11 | [外部連携カタログ](11-integration-catalog.md) | API・ファイル・DB・イベントでの外部連携を `docs/integrations.md` に記録し、追加・変更・廃止・検査（`verify.py --docs-only`）の手順を知りたい |

## 第 2 部: EABK Studio

索引と起動の前提は [studio/README.md](studio/README.md) です。

| # | ドキュメント | 読むタイミング |
|---|---|---|
| S1 | [はじめかた](studio/01-first-steps.md) | 前提条件を確かめたい。起動して最初の 10 分を過ごしたい |
| S2 | [画面の見かた](studio/02-screens.md) | 各画面（実画面つき）で何が分かるかを知りたい |
| S3 | [こんなとき、どう見るか](studio/03-tasks.md) | 報告・影響調査・承認待ちの確認など、目的別の手順を知りたい |
| S4 | [うまく動かないとき・用語集](studio/04-troubleshooting.md) | Studio が起動しない・画面に出ない。用語を調べたい |
| S5 | [Product Manager 向け](studio/05-product-manager.md) | 進捗・承認・未回答の質問から、次に投資する目的を決めたい |
| S6 | [Architect 向け](studio/06-architect.md) | 依存・境界・置き場所・層の欠けを確かめたい |
| S7 | [Software Engineer 向け](studio/07-software-engineer.md) | 要求から実装ファイルとテストまでをたどりたい |
| S8 | [データリファレンス](studio/08-data-reference.md) | どの画面が、どのファイルの何を読み、どう計算するかを知りたい |

## 役割別の読み方（初めて使う方へ）

いずれも、先に [README.md](../README.md) の「はじめに」「インストール」「Quickstart」を読んでください。

| あなたは | 読む順 |
|---|---|
| **Product Manager** | 1（依頼の書き方）→ 2（実行中と終了後。報告の読み方・質問票への回答・マージ）→ 8（導入ロードマップと KPI）→ [S5](studio/05-product-manager.md)（Studio で進捗を見る） |
| **Architect** | 3（管理データの書式）→ 6（品質ゲートと検査項目）→ 4（設定とカスタマイズ）→ 8（導入ロードマップ）→ [S6](studio/06-architect.md)（Studio で設計の整合を見る） |
| **Software Engineer** | 4（設定。検証コマンドの登録）→ 5（スクリプトリファレンス）→ 7（トラブルシューティング）→ 9（バージョンアップ）→ 10（既存アプリの導入）→ [S7](studio/07-software-engineer.md)（Studio で実装とテストをたどる） |

## 目的から探す

| やりたいこと | 読む場所 |
|---|---|
| 最初の run を出す | [README.md の Quickstart](../README.md#quickstart) → [1](01-writing-requests.md) |
| run の結果を確認して、マージするか決める | [2](02-during-and-after-run.md)。要求・カタログ・試験の状態を図で見るなら [S3](studio/03-tasks.md) |
| 要求定義書・カタログの書き方を知る | [3](03-requirements-format.md)。Studio が読む書式は [S8](studio/08-data-reference.md) |
| 検証コマンド・モデル・ゲートを設定する | [4](04-customization.md)、[6](06-quality-gates.md) |
| 止まった・拒否された・失敗した | [7](07-troubleshooting.md)。Studio が動かないなら [S4](studio/04-troubleshooting.md) |
| 既存のアプリに導入する | [10](10-adopting-existing-apps.md)、段階導入は [8](08-roadmap.md) |
| toolkit を更新する | [9](09-versioning.md) |
| データ層を図・表で見る | [S1](studio/01-first-steps.md)、[S2](studio/02-screens.md) |

## README の各節へのリンク

| 知りたいこと | README の節 |
|---|---|
| 解決する問題と全体のアーキテクチャ | [概要](../README.md#概要) |
| エージェントの責務と書き込み権限 | [エージェントと権限](../README.md#エージェントと権限) |
| run の工程（工程 0〜6） | [1 回の run の流れ](../README.md#1-回の-run-の流れ) |
| インストール・更新・アンインストール | [インストール](../README.md#インストール) |
| 最初の run の出し方と確認項目 | [Quickstart](../README.md#quickstart) |
| EABK Studio の概要と起動 | [EABK Studio](../README.md#eabk-studioデータ層のビューアー) |
| 用語 | [用語](../README.md#用語) |

## このガイドの書き方の約束

- 章番号は、第 1 部が `1`〜`10`、第 2 部が `S1`〜`S8` です。節は `4.4`・`S8.5.2` のように章番号に続けます。他のガイドから参照するときも、この記号を使います。
- 配布元のリポジトリでは `users-guide/` です。`tools/install.py` で導入したリポジトリでは `EABK-docs/` に入ります（導入先の `users-guide/` は触りません）。ガイド内のリンクは、配布元の位置を基準にした相対パスです。
- 実画面の画像は `studio/images/`、採取条件は [studio/screen-images.json](studio/screen-images.json)、再採取は `studio/capture-screens.py` です。EABK 本体の図は `images/` にあります。
- ファイルを追加・改名したら、`tools/install.py` の `MANAGED`（と、消すものは `OBSOLETE`）を合わせて直します（[9](09-versioning.md)）。