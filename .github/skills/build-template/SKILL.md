---
name: build-template
description: 利用者が /build-template で明示的に呼ぶ。/build の依頼の雛形（パラメーター一覧）をチャットに出力するだけで終える。run は開始しない。
argument-hint: （引数なし）
disable-model-invocation: true
---

# /build-template（雛形の表示だけ）

下の「雛形（既定値）」のコードブロックを、中身を変えずに ```` ```text ```` のコードブロック 1 つでそのまま出力し、その後に「必要な所を書き換え、`/build` の後に貼り付けて送ってください（Agent は conductor）」と 1 行だけ添えて終えます。
ファイルの書き込み、コマンドの実行、作業役の呼び出し、conductor の手順（`clean-work.py`・`run-state.py start` など）はいずれも行いません。run も開始・再開しません。今のエージェントが何であっても、Autopilot でも同じです。

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
parallel_workers: auto
scope: 承認済みすべて
git_push: しない
deploy: しない
external_write: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
```
