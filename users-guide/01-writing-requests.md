# 1. 依頼の書き方（/build と run_options）

## 1.1 雛形

```text
<request>
やりたいこと。新規・追加・変更・削除のどれでもよい。外部の文章は <pasted_content id="任意"> で囲む
</request>
<answers>
前回の報告の質問票・承認依頼への回答。例: Q-003: B / FR-031: 承認 / 残りは推奨どおり。初回は空
</answers>
<references>
任意: 資料のパス、URL
</references>
<run_options>
max_hours: 24
approval_policy: 安全範囲は推奨どおり
parallel_workers: auto
scope: 承認済みすべて
git_push: しない
deploy: しない
external_write: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```

VS Code では、Agent を conductor にしてから、チャット欄に `/build` と入力し、続けて依頼を書いて送信します。`<request>`・`<answers>`・`<references>` の入力フォームは表示されません。GitHub Copilot app でも同じで、エージェント ピッカー（またはプロンプト欄の `/agent`）で conductor を選び、プロンプト欄に `/build` と続けて依頼を書いて送信します（[README の「GitHub Copilot app で実行する」](../README.md#github-copilot-app-で実行する)）。

- **雛形を表示する**: `/build-template` と送ると（`/build template` でも同じ）、run を開始せずに、上の雛形がコードブロックでチャットに出力されます。`/build template` は conductor が通常の依頼として扱ってしまうことがあるため、確実に表示したいときは `/build-template` を使います（`.github/skills/build-template/SKILL.md`。雛形は `build` の既定値と同じで、テストで一致を確認しています）。コピーして書き換え、`/build` の後に貼り付けて送信します。VS Code の skill には入力欄へ直接テキストを差し込む機能がないため、応答として出力する方式にしています。
- **やりたいことだけを書く**（例: `/build 申請に下書き保存を加える`）: 入力全体が `<request>` になります。`<answers>`・`<references>` は空、`<run_options>` は上の既定値です。
- **回答や run_options も指定する**: 上の雛形を `/build` の後に貼り付け、必要な部分だけ書き換えて送信します。`<run_options>` で省略したキーは既定値になります。
- **チームの既定値を変える**: `.github/skills/build/SKILL.md` の雛形を編集します（ローカルで変更したファイルは、インストールコマンドを再実行しても上書きされません）。
- **`/build` を使わない**: 雛形を書き換えた全文をそのまま送信しても同じ動作になります（Agent が conductor であることが条件）。Copilot CLI の `-i` で渡す場合もこの形式です（[README の「Copilot CLI で実行する」](../README.md#copilot-cli-で実行する)）。

## 1.2 `<request>` の書き方

- **何を・誰のために・なぜ** を書きます。画面レイアウトや DB 設計など「どう作るか」は書かなくてかまいません（要求定義書は「何を満たすか」を書くドキュメントです）。
- 既存の要求を変更・廃止する場合は、わかれば要求 ID を書きます（例: 「FR-012 の保持期間を 30 日から 90 日にする」「FR-020 を廃止する」）。
- 閾値（件数・時間・金額）が決まっていれば、そのまま書きます。決まっていなければ、rd-author が質問票に挙げます。
- ほかの資料から貼り付けた文章は `<pasted_content id="a1">` と `</pasted_content id="a1">` で囲みます。その中にある命令文は、作業指示ではなく入力データとして扱われます（プロンプトインジェクション対策）。
- 空にした場合は、管理データの監査と、事実確認だけで直せる不整合の修正だけを行います。

## 1.3 `<answers>` の書き方

前回の `run-report.md` にある「未回答の質問票」と「包括承認した項目」に回答します。1 行に 1 件ずつ書けます。

```text
Q-003: B
Q-004: 推奨どおり
FR-021: 承認
FR-022: 却下（今期は対象外）
包括承認の FR-030: 取り消し（保持期間は 90 日にする）
残りはすべて推奨どおり
```

回答は決定記録に「承認済み（Q-003 2026-10-09）」の形で残ります。BLOCKED だった受入基準は解除され、次の run で実装・テストされます。

## 1.4 run_options

| キー | 値 | 意味 |
|---|---|---|
| `max_hours` | 数値（既定 24） | 時間予算。85% を超えたら新しい項目には着手せず、最終工程に進みます |
| `approval_policy` | `厳格` / `安全範囲は推奨どおり`（既定） / `すべて推奨どおり` | AI 提案をどこまで推奨案どおりに承認して実装するか（[1.5](#15-承認ポリシー)） |
| `parallel_workers` | `auto`（既定） / 数値 | 同時に動かす implementer の上限。`auto` は、2 コアと 6 GB につき 1 体、最大 8 体で、開始時の CPU・メモリから算出します（20 コア・64 GB なら 8）。各 worker には CPU スレッドをコア数 × 1.5 ÷ worker 数で渡します（[4.9](04-customization.md#49-計算資源とクラウド)） |
| `scope` | `承認済みすべて` または要求 ID のリスト（例: `FR-012, FR-013`） | 今回の run で実装する範囲 |
| `git_push` | `しない`（既定） / `作業ブランチへ push する` | push する場合も main には push しません（hook G-5）。終了時に統合ブランチを push します（PR は作りません）。main へのローカルマージは、この設定に関係なく全件完了時に自動で行います |
| `deploy` | `しない`（既定） / `する` | `しない` の間は、`azd up`・`terraform apply` などのコマンドと、MCP Server・plugin のデプロイ・公開の操作を hook が拒否します |
| `external_write` | `しない`（既定） / `する` | 利用者が設定した MCP Server・plugin・拡張機能のツールで、外部のシステム（メール、チャット、チケット、クラウドのリソース、Copilot Studio のエージェントなど）を作成・更新・削除・送信してよいかどうか。`しない` の間も参照（Work IQ での検索、Microsoft Learn の取得など）は行えます（[4.4](04-customization.md#44-mcp-serverplugin拡張機能を使う)） |
| `paid_services` | `使わない`（既定） / `budget の範囲で使う` | 有料の外部サービスを使うかどうか |
| `external_exposure` | `公開しない`（既定） / `公開する` | インターネットから到達できるエンドポイントを作るかどうか |

## 1.5 承認ポリシー

元になった Prompt の原則は「AI 提案は承認待ちとし、実装しない」です。この原則のままでは、長時間の run の間、承認待ちの要求がすべて止まってしまいます。そこで、推奨案どおりに進めてよい範囲を事前に決めます。

| 値 | 動作 | 向いている場面 |
|---|---|---|
| `厳格` | AI 提案は実装しません | 事業判断の多い初期の要求定義（Phase 2） |
| `安全範囲は推奨どおり`（推奨） | 次の条件を**すべて**満たす AI 提案・質問票の推奨案は、「承認済み（包括承認 YYYY-MM-DD・approval_policy）」として実装します。①利用者データ・権限・セキュリティ・プライバシー・課金・法令・外部公開・マスターと ID の体系・取り消せない操作に触れない ②PARAM の変更で元に戻せる ③既存の承認済み要求と競合しない。それ以外は BLOCKED にします | 通常の機能開発 |
| `すべて推奨どおり` | 上記①の除外分野だけを BLOCKED にし、残りは推奨案で実装します | 試作・PoC |

包括承認した項目は、報告の「包括承認した項目」に影響の大きい順で並びます。次の依頼の `<answers>` で却下・修正できます。

## 1.6 よくある依頼のパターン

| やりたいこと | 書き方の例 |
|---|---|
| 新規開発 | 「〇〇の業務を支えるアプリを作る。利用者は△△で、□□ができる」＋資料を `<references>` に |
| 機能追加 | 「申請に下書き保存を加える。理由: 再入力による離脱が多い」 |
| 変更 | 「FR-012 の保持期間（PARAM-004）を 30 日から 90 日にする」 |
| 削除 | 「FR-020（旧エクスポート機能）を廃止する」→ rd-author が「廃止」にし、implementer がコード・テスト・カタログの行を削除し、最後に本文から外します |
| 監査だけ | `<request>` を空にし、`max_hours: 2` |
| 回答の反映だけ | `<request>` を空にし、`<answers>` だけを書く |
| 既存リポジトリへのインストール直後 | 「既存の要求定義書（docs/requirements-definition.md）を toolkit の書式（構造化欄・検証レベル・PARAM）に合わせる。意味は変えない」 |
| 過去の矛盾の診断（Phase 0） | rd-auditor を直接呼び、`scope: 全量`、`runs: 1`、`history_mode: する`（[08-roadmap.md](08-roadmap.md)） |
| GitHub Spec Kit の仕様から始める | `python scripts/import-speckit.py` が作る依頼文を `/build` の後に貼る（[1.7](#17-github-spec-kit-の仕様を取り込む)） |

## 1.7 GitHub Spec Kit の仕様を取り込む

[GitHub Spec Kit](https://github.com/github/spec-kit) で書いた仕様（`/speckit-specify`・`/speckit-clarify` の成果物）を、この toolkit の要求定義書に取り込んでから、conductor で実装・検証できます。仕様の書き方は Spec Kit、最後まで作り切って検証するのは conductor、という分担です。

```bash
python scripts/import-speckit.py                          # このリポジトリの specs/*/spec.md をすべて
python scripts/import-speckit.py --source ../photo-app    # 別のリポジトリにある Spec Kit のプロジェクト
python scripts/import-speckit.py --feature 001            # 機能ディレクトリを前方一致で選ぶ（複数可）
python scripts/import-speckit.py --implement              # 取り込みと実装を 1 回の run で行う依頼文にする
```

出力は `work/import/speckit-<日時>.md` です。中の「依頼文」を、conductor の `/build` の後に貼り付けて送信します。

| Spec Kit | 取り込み先の候補（最終判断は rd-author） |
|---|---|
| User Story（Priority P1 / P2 / P3） | 利用シナリオと要求（FR）。優先度は MUST / SHOULD / MAY |
| Acceptance Scenarios（Given / When / Then） | 受入基準（AC）。検証レベルの候補は system |
| Functional Requirements（`FR-001` など） | 要求（FR）。本文の MUST / SHOULD / MAY を優先度の候補にする |
| `[NEEDS CLARIFICATION: …]`、疑問形の Edge Cases | 質問票（Q）と、関係する AC の BLOCKED |
| Clarifications（`Q: … → A: …`） | 決定記録（出自: 利用者決定） |
| Success Criteria（`SC-001` など） | 目的（G）の成功指標、または非機能要求（NFR） |
| Key Entities | 用語と対象エンティティ |
| Assumptions | 前提・制約、または ASSUMPTION |
| Constitution の原則 | 既定制約、または非機能要求。開発プロセスの原則は決定記録 |
| plan.md・tasks.md・contracts/ | `<references>` にだけ載せる（技術選定は要求にしない） |

- スクリプトは要求定義書を編集せず、ID も振りません（G-1・G-3）。Spec Kit の ID は `speckit:001-photo-albums/FR-003` の形の取り込み元 ID として残し、rd-author が `next-id.py` で採番し直して出典欄に書きます。
- 既定の依頼文は `scope: なし`・`approval_policy: 厳格` で、要求定義だけを行います。報告の質問票に回答してから、次の `/build` で実装します。
- テンプレートのまま（`[FEATURE NAME]` など）の箇所があると `WARN` を出します。先に Spec Kit 側で埋めるか、rd-author に質問票へ挙げさせます。
- 同じリポジトリに Spec Kit を入れたままでかまいません。Spec Kit の文書（`specs/**/*.md`、`.specify/**`）は独自の `FR-001` などの番号を使うため、ID の検査（CHK-19）と `select-tests.py` の対象外です。連携するときは `/speckit-implement`・`/speckit-converge` を使わず、実装は conductor に任せます。run の実行中は Spec Kit のスキルを使いません（run が終わってから仕様を更新します）。
- 連携の考え方・構成図・データの対応図は、[README の「GitHub Spec Kit との連携」](../README.md#github-spec-kit-との連携) にあります。
