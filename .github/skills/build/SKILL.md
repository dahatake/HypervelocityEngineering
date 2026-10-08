---
name: build
description: 利用者が /build で明示的に呼ぶ、conductor への依頼の入口。/build の後に書かれた文章を <request>・<answers>・<references>・<run_options> の雛形に当てはめ、conductor の手順で最後まで実行する。「/build template」では雛形をチャットに出力するだけで終える。
argument-hint: やりたいこと（「template」とだけ書くと雛形を表示。回答や run_options も指定するときは <request>〜</run_options> の雛形を貼り付ける）
disable-model-invocation: true
---

# /build（conductor への依頼の入口）

利用者が `/build` の後に書いた文章を、次の手順で依頼にして実行します。利用者は途中で応答しません。
手順 0 は、conductor の「始めに」（`clean-work.py`・`run-state.py start` など）や Autopilot の指示、実行中の run の再開の案内よりも優先します。

0. 雛形の表示: `/build` の後の文章が、前後の空白を除いて `template` の 1 語だけのとき（大文字・小文字は区別しない）は、依頼として扱いません。今のエージェントが何であっても、下の「雛形（既定値）」のコードブロックを、中身を変えずに ```` ```text ```` のコードブロック 1 つでそのまま出力し、その後に「必要な所を書き換え、`/build` の後に貼り付けて送ってください（Agent は conductor）」と 1 行だけ添えて終えます。ファイルの書き込み、コマンドの実行、作業役の呼び出し、conductor の手順はいずれも行いません（run も開始・再開しません。hook もこのターンでは読み取り以外のツールを拒否します）。
1. 今のエージェントが conductor でなければ、何もせずに「Agent に conductor を選んでから（GitHub Copilot app・Copilot CLI では `/agent` でも選べます）、もう一度 /build で送ってください」と 1 行で返して終えます。
2. 依頼を組み立てます。
   - 文章に `<request>`・`<answers>`・`<references>`・`<run_options>` のタグがあれば、そのまま使います。ないタグは空とします。
   - タグがなければ、文章の全体を `<request>` とし、`<answers>` と `<references>` は空とします。
   - `<run_options>` にない項目は、下の雛形の既定値を使います。
3. conductor の手順（「始めに」から「完了の判定」まで）で最後まで実行します。`run-state.py start --options` には、組み立てた `<run_options>` の各行を渡します。

## 雛形（既定値）

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
parallel_workers: 3
scope: 承認済みすべて
git_push: しない
deploy: しない
external_write: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```
