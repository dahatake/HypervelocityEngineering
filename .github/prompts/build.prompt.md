---
description: conductor に依頼を 1 回で渡す雛形（要求定義 → 独立監査 → System Test の設計 → 並行実装 → 統合 → 最終監査 → 報告）
agent: conductor
---
次の依頼を、conductor の手順で最後まで実行してください。私は途中で応答しません。

<request>
${input:request:やりたいこと（新規・追加・変更・削除のどれでもよい。外部の文章は <pasted_content id="任意"> で囲む）}
</request>
<answers>
${input:answers:前回の報告の質問票・承認依頼への回答（例: Q-003: B / FR-031: 承認 / 残りは推奨どおり）。初回は空}
</answers>
<references>
${input:references:任意: 資料のパス、URL}
</references>
<run_options>
max_hours: 24
approval_policy: 安全範囲は推奨どおり
parallel_workers: 3
scope: 承認済みすべて
git_push: しない
deploy: しない
paid_services: 使わない
external_exposure: 公開しない
</run_options>
