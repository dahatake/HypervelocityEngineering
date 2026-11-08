**日本語** | [English](02-daily-workflow.en.md)

# 2. ふだんの進め方

EABK Lite の 1 回の変更は、次の 5 段階で進みます。どれも、いつもの Copilot と git と CI だけで行います。

```text
1. 依頼する            いつもの Copilot（既定のエージェント）にチャットで依頼する（1 章）
2. 同じ変更で更新する   Copilot が要求定義書・カタログ・テスト・コードを同じ変更で直す
3. 手元で検査する       python scripts/verify.py が exit 0
4. push / PR           CI の ebak-verify と ebak-data-layer が同じ検査をする
5. 節目に監査する       リリース前などに rd-auditor で要求の意味を監査する
（いつでも）           状況は EABK Studio で見る
```

> 0.5.x から移行した方へ: run・工程・統合ブランチ・`run-report.md`・自動の main への取り込みはありません。変更はふつうのブランチと PR で取り込みます。0.5.x の run が残した worktree と `work/*` ブランチは自動では消えません。`git worktree list` と `git branch --list "work/*"` で確かめて、手で削除します（[9. 版の管理](09-versioning.md)）。

## 2.1 依頼する

ブランチを作り、チャットで依頼します。書き方は [1. 依頼の書き方](01-writing-requests.md) にあります。

```bash
git switch -c feature/draft-save
```

## 2.2 同じ変更で更新されたかを確かめる

Copilot の報告を読んだら、管理データが同じ変更に入っているかを差分で確かめます。

```bash
git status --short
git diff -- docs/requirements-definition.md   # 要求・AC・決定記録・質問票の変更
git diff -- docs/catalog.md docs/id-registry.md tests/system/ledger.json
```

| 変更の種類 | 同じ変更に入っているべきもの |
|---|---|
| 機能の追加 | 新しい要求と AC（ID は `next-id.py` で採番）、ID 台帳の行、カタログの行、要求 ID・AC ID を書いたテスト、必要なら台帳のケース |
| 機能の変更 | 変えた要求・AC の本文、影響するテスト、台帳のケースの更新（`--reason` つき） |
| 機能の削除 | 要求を「廃止」に、コード・テスト・カタログの行の削除、台帳のケースの停止（`ledger.py block --reason`） |
| 振る舞いを変えない変更（リファクタリング・文言の修正など） | 名前を変えた・消したファイルのカタログの行だけ |

足りないときは、同じチャットで「FR-031 のカタログの行がない。AGENTS.md の規則どおりに直して」のように頼みます。承認待ちと質問票への回答もこのチャットで返します（[1.3](01-writing-requests.md#13-承認はチャットで行う)）。

## 2.3 手元で検査する

```bash
python scripts/verify.py          # 管理データの検査 ＋ verify.commands（ビルド・テスト）
```

exit 0 なら合格です。通常は Copilot が完了の前に実行していますが、push の前に自分でも実行します。不合格のときは次の順で直します。

| 出力 | 対処 |
|---|---|
| `ERROR CHK-07`・`CHK-08`・`CHK-17` などカタログ・台帳・ID 台帳の不整合 | `python scripts/rdfix.py --apply` で自動修正します（要求定義書は変更しません）。残った `MANUAL` の行は、行に書かれた「担当」と「次の行動」に従って直します |
| `ERROR CHK-01`（ID の重複・台帳にない ID） | [2.7](#27-複数の人複数の-pc-で使う) の手順で採番し直します |
| `ERROR CHK-12`（AC の本文が変わったのに台帳のダイジェストが古い） | テストが新しい AC を検証していることを確かめてから、`python scripts/ledger.py digests --update` |
| ビルド・テストのコマンドの失敗 | ログの全文は `/work` にあります。`python scripts/summarize.py <ログ>` で要点だけを読めます |

既定の検査プロファイルは `lite` で、構造と追跡性の検査（`CHK-01, 02, 03, 05, 09, 12, 17, 19, 24`）だけを報告します。曖昧な語・数値の直書き・禁止された同義語などの書式の警告まで見たいときは、次のように `full` を指定します。

```bash
python scripts/verify.py --docs-only --profile full --show-warnings
```

検査項目の一覧は [6. 品質ゲートと検査項目](06-quality-gates.md)、オプションは [5. スクリプトリファレンス](05-scripts-reference.md) にあります。

## 2.4 push と PR（CI）

```bash
git add -A && git commit -m "FR-031 下書き保存"
git push -u origin feature/draft-save
gh pr create --base main
```

push と PR で、2 つのワークフローが動きます。

| ワークフロー | いつ動くか | すること |
|---|---|---|
| `ebak-verify`（`.github/workflows/ebak-verify.yml`） | push・PR | `scripts/verify.sh --show-warnings` を実行します。手元の `verify.py` と同じ検査です |
| `ebak-data-layer`（`.github/workflows/ebak-data-layer.yml`） | PR・push・手動・毎週 | データ層を検査し、不合格なら `rdfix.py --full --apply` で自動修復します。修復が合格したら、その修正を commit します（同じリポジトリの PR はそのブランチへ、push のときは修正用のブランチを作って PR に）。自動で直せないものは Issue にします。要求定義書は変更しません |

マージの前に、少なくとも次を確かめます。

1. `ebak-verify` と `ebak-data-layer` が成功している
2. `git diff main...HEAD -- docs/requirements-definition.md` の要求の変更が、依頼の意図と合っている
3. 「AI提案／承認待ち」のまま実装された要求がない（`python scripts/rdcheck.py list --state 承認待ち` の要求に、対応するコードがない）

`ebak-data-layer` を止めたいときは、ワークフローのファイルを削除するか、GitHub の Actions 画面で Disable にします（[4. カスタマイズ](04-customization.md)）。

## 2.5 節目に監査する（rd-auditor）

毎回の変更で決定的な検査（verify・CI）は行われますが、要求どうしの**意味の**矛盾や、目的（G-ID）とのずれは機械では見つけにくいため、節目に独立した監査役に頼みます。リリースの前、大きな変更をマージする前、要求がまとまって増えたときが目安です。

Agent を **rd-auditor** にして、チャットで頼みます。

| 頼み方 | 範囲 |
|---|---|
| 「差分を監査して」 | `base_branch`（既定 `main`）との差分で変わった要求と、同じエンティティ・状態・PARAM・用語に関わる要求。既定は 1 回 |
| 「全量を 3 回で監査して」 | 要求定義書のすべて。同じ判定を独立に 3 回行い、多数決で確度を付けます |
| 「FR-012 と FR-031 を監査して」 | 指定した要求 |

rd-auditor は git で管理するファイルを変更しません。結果は `work/audit/<YYYYMMDD-HHMM>/` に、各回の出力（`run<n>.md`）と集計（`report.md`）として書かれ、チャットには件数の要約だけが返ります。サブエージェントを使える環境では、各回を並行に行います。

指摘をどう扱うかは利用者が判断し、直すときは別の依頼・別の変更として既定のエージェントに頼みます（例: 「work/audit/20261108-1000/report.md の確度高の指摘 2 件を直して」）。

## 2.6 状況を見る（EABK Studio）

要求・受入基準・カタログ・System Test の台帳の状態は、EABK Studio で図と表として見られます。任意のツールで、なくても作業は進みます。

```bash
python EABK-Studio/studio.py          # ブラウザーで開く（127.0.0.1 だけで待ち受け、読み取り専用）
python EABK-Studio/studio.py --check  # 読み込める件数だけを表示して終了
```

画面ごとの使い方は [EABK Studio のガイド](studio/README.md) にあります。

## 2.7 複数の人・複数の PC で使う

規則はリポジトリ（`AGENTS.md`）に、ID の採番は `next-id.py` に、検査は CI にあります。そのため、誰がどの PC のどの Copilot で依頼しても、個人のプロンプトやメモリに依らず同じ規則と検査が効きます。

| 仕組み | 効果 |
|---|---|
| `next-id.py` | 要求定義書・ID 台帳・`base_branch` 上の同じファイル・台帳のうち最大の番号の次を採番します。同じ PC の別の作業ツリーとも採番の記録を共有します |
| `.gitattributes` の `docs/id-registry.md merge=union` | 別々のブランチで ID 台帳に追記した行が、マージで競合せずに両方残ります |
| CI の `ebak-verify` | 手元で検査を忘れても、PR で同じ検査が動きます |

別の PC・別のブランチで同時に採番すると、同じ ID が 2 つの要求に使われることがあります。マージした後（または main を取り込んだ後）に `verify.py` が `ERROR CHK-01` で検出するので、後からマージする側で次のように直します。

1. `git switch <自分のブランチ>` で main を取り込み、`python scripts/verify.py --docs-only` で重複した ID を確かめる
2. `python scripts/next-id.py FR`（種別は重複したもの）で新しい ID を採番する
3. 自分の側の要求・AC・テストの名前とコメント・カタログの行の ID を新しい ID に置き換える。台帳のケースは `python scripts/ledger.py update <ケース ID> --req <新 ID> --reason "ID の重複を採番し直し"` で直す
4. `python scripts/next-id.py --sync` で ID 台帳を本文に合わせ、`python scripts/verify.py` を exit 0 にする

Copilot に「CHK-01 の重複を、自分のブランチ側の ID を next-id.py で採番し直して直して」と頼んでもかまいません。

## 2.8 /work の扱い

`/work` は git の管理対象外の作業場所です（ログ、検査の結果、監査の結果 `work/audit/`、`adopt.py` の依頼文 `work/import/` など）。自動では削除されません。不要になったものは手で削除してかまいません。
