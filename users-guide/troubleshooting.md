# トラブルシューティング

← [README](../README.md)

---

## 目次

- [Web UI 方式のトラブル](#web-ui-方式のトラブル)
  - [Bootstrap ワークフローが起動しない](#bootstrap-ワークフローが起動しない)
  - [Sub Issue API が失敗する](#sub-issue-api-が失敗する)
  - [Copilot が assign されない](#copilot-が-assign-されない)
  - [ワークフローがエラーで終了する](#ワークフローがエラーで終了する)
  - [Coding Agent のタスク実行エラー](#coding-agent-のタスク実行エラー)
- [SDK 版のトラブル](#sdk-版のトラブル)

---

## Web UI 方式のトラブル

### Bootstrap ワークフローが起動しない

**症状**: Issue にラベルを付与しても GitHub Actions が起動しない。

**確認事項**:

1. 対応するトリガーラベルが正しく付与されているか確認
   - ラベル名のスペルミスがないか確認
   - ラベルがリポジトリに存在するか確認（[ラベル一覧](./workflow-reference.md#ワークフロートリガー系ラベル)を参照）
2. Actions タブでワークフローが有効になっているか確認
   - **Settings → Actions → General → Actions permissions** が適切に設定されているか確認
3. リポジトリの Workflow permissions が "Read and write" になっているか確認
   - **Settings → Actions → General → Workflow permissions** を確認

---

### Sub Issue API が失敗する

**症状**: Sub Issue が作成されず、エラーログに API エラーが記録されている。

**原因と対応**:

- Sub Issue API は GitHub の一部プランでのみ利用可能です
- **フォールバック動作**: 失敗した場合でも、親 Issue にチェックリストコメントが自動投稿されます
- 手動で Sub Issue を作成する場合は、チェックリストコメントの内容をもとに個別に Issue を作成してください

---

### Copilot が assign されない

**症状**: Sub Issue が作成されたが、Copilot が自動アサインされない。

**確認事項**:

1. Actions ログを確認してください
2. Copilot が利用可能なプランであることを確認してください
3. `COPILOT_PAT` シークレットが正しく設定されているか確認してください
   - **Settings → Secrets and variables → Actions** で `COPILOT_PAT` が存在するか確認
   - PAT の有効期限が切れていないか確認
4. **手動アサインする場合**: Issue 右サイドバーの「Assignees」から `@copilot` を選択

---

### ワークフローがエラーで終了する

**症状**: GitHub Actions のジョブが失敗している。

**確認事項**:

1. **Actions タブ**で失敗したジョブのログを確認してください
2. `GITHUB_TOKEN` の権限が `issues: write` になっているか確認してください
   - **Settings → Actions → General → Workflow permissions** で確認
3. ワークフロー権限が **Read and write** になっているか確認

---

### Coding Agent のタスク実行エラー

**症状**: Pull Request の Session の中で `Run Bash command` が繰り返され、何も処理が行われていない。

> [!IMPORTANT]
> この状況になったら、即座にジョブを停止させてください。GitHub Actions の課金に影響が考えられます。

**対応策**: 以下のプロンプトを PR コメントで Copilot に送信してください。

```text
@copilot ジョブの途中でコマンド文字列を生成できずに、ジョブを実行しようとして{エラーメッセージ}が表示されています。原因を究明して、対応策を検討して、問題を修正してください。
対応策が、うまくいかない場合は、`段階的アプローチ - 各セクションを個別のコミットで追加`を試してみてください。

### エラーメッセージ
Run Bash command
$ undefined
No command provided. Please supply a valid command to execute.
```

その他の便利なプロンプトは [prompt-examples.md](./prompt-examples.md) を参照してください。

---

## SDK 版のトラブル

SDK 版（ローカル実行方式）のトラブルシューティングは [SDK-Guide.md 付録D](./SDK-Guide.md#付録d-トラブルシューティング) を参照してください。

主なトラブルと対応:

| 症状 | 参照箇所 |
|------|---------|
| `copilot: command not found` | [付録D: Copilot CLI が見つからない](./SDK-Guide.md#copilot-cli-が見つからない) |
| `ModuleNotFoundError: No module named 'copilot'` | [付録D: SDK がインストールされていない](./SDK-Guide.md#sdk-がインストールされていない--python--m-hve-が動かない) |
| セッションタイムアウト | [付録D: セッションタイムアウト](./SDK-Guide.md#セッションタイムアウト) |
| MCP Server が接続できない | [付録D: MCP Server が接続できない](./SDK-Guide.md#mcp-server-が接続できない) |
| 並列実行でメモリ不足 | [付録D: 並列実行でメモリ不足](./SDK-Guide.md#並列実行でメモリ不足) |
| PR 作成時に HTTP 422 エラー | [付録D: PR 作成時に HTTP 422 エラー](./SDK-Guide.md#pr-作成時に-http-422-エラー) |
