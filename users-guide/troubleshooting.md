# トラブルシューティング

← [README](../README.md)

---

## 目次

- [Web UI 方式のトラブル](#web-ui-方式のトラブル)
  - [Bootstrap ワークフローが起動しない](#bootstrap-ワークフローが起動しない)
  - [Sub Issue API が失敗する](#sub-issue-api-が失敗する)
  - [Copilot が assign されない](#copilot-が-assign-されない)
  - [ワークフローがエラーで終了する](#ワークフローがエラーで終了する)
  - [Azure Static Web Apps デプロイエラー](#azure-static-web-apps-デプロイエラー)
  - [Copilot cloud agent のタスク実行エラー](#copilot-cloud-agent-のタスク実行エラー)
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

### ADOC / AKM が起動しない

**症状**: `sourcecode-to-documentation.yml` または `knowledge-management.yml` から Issue を作成しても実行されない。

**確認事項**:

1. Issue に `auto-app-documentation` または `knowledge-management` ラベルが付いているか
2. **Actions** タブで `auto-app-documentation.yml` / `auto-knowledge-management.yml` が有効か
3. ラベル未作成の場合は [getting-started.md Step.5](./getting-started.md#step5-ラベル設定) を参照し、少なくとも `auto-app-documentation` と `knowledge-management` を明示的に作成

---

### PR 完全自動化が動かない（Auto Approve / Auto-merge）

**症状**: チェックボックスを有効化したのに自動 Approve / Auto-merge されない。

### 選択したモデルで 400 エラーになる

**症状**: Issue Template でモデル指定後、Copilot アサイン時に 400 系エラーになる。

**対処**:
- Issue Template のモデルを `Auto` に戻す
- SDK 実行時は `MODEL=claude-opus-4.6` などで一時固定して再実行する
- workflow 実行ログを確認し、必要に応じて `Auto`（既定）に戻して再実行する

> 命名規則メモ: 新規追加モデル（`claude-opus-4-7`）は公式表記のハイフン区切り、既存モデル（`claude-opus-4.6` など）は従来通りドット区切りです。これは意図した設計差分です。

**確認事項**:

1. PR に `auto-approve-ready` ラベルが付与されているか
2. PR が `split-mode` になっていないか（`split-mode` 付きは自動化対象外）
3. `auto-review-to-approve-transition.yml` / `auto-approve-and-merge.yml` の実行ログに失敗がないか

---

### Azure Static Web Apps デプロイエラー

**症状**: SWA デプロイ workflow が失敗する、または `::warning::` でスキップされる。

**確認事項（チェック順）**:

1. **`AZURE_STATIC_WEB_APPS_API_TOKEN` が設定されているか確認**
   ```bash
   gh secret list --repo <owner>/<repo>
   ```
   - `AZURE_STATIC_WEB_APPS_API_TOKEN` が一覧に表示されない場合、Secret 未設定です
   - **対処法**: `create-azure-webui-resources.sh` を `GITHUB_PAT` 付きで実行するか、手動で設定:
     ```bash
     # トークン取得
     TOKEN=$(az staticwebapp secrets list --name <SWA_NAME> -g <RESOURCE_GROUP> --query "properties.apiKey" -o tsv)
     # Secret 設定
     GH_TOKEN=$GITHUB_PAT gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN --repo <owner>/<repo> --body "$TOKEN"
     ```

2. **Azure リソースが存在するか確認**
   ```bash
   az staticwebapp show --name <SWA_NAME> --resource-group <RESOURCE_GROUP>
   ```
   - リソースが存在しない場合は `create-azure-webui-resources.sh` を実行してください

3. **`GITHUB_PAT` の権限不足（`gh secret set` が 403 エラー）**
   - Fine-grained PAT の場合: Repository Permission に **Secrets: Read and write** が必要
   - Classic PAT の場合: `repo` スコープが必要
   - PAT の有効期限が切れていないか確認

4. **デプロイトークンの期限切れ**
   - SWA のデプロイトークンは Azure リソース側で管理されます
   - トークンをリセットする場合:
     ```bash
     az staticwebapp secrets reset-api-key --name <SWA_NAME> -g <RESOURCE_GROUP>
     ```
   - リセット後は `AZURE_STATIC_WEB_APPS_API_TOKEN` を再設定してください

---

### Copilot cloud agent のタスク実行エラー

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

SDK 版（ローカル実行方式）のトラブルシューティングは [sdk-guide.md 付録D](./sdk-guide.md#付録d-トラブルシューティング) を参照してください。

主なトラブルと対応:

| 症状 | 参照箇所 |
|------|---------|
| `copilot: command not found` | [付録D: Copilot CLI が見つからない](./sdk-guide.md#copilot-cli-が見つからない) |
| `ModuleNotFoundError: No module named 'copilot'` | [付録D: SDK がインストールされていない](./sdk-guide.md#sdk-がインストールされていない--python--m-hve-が動かない) |
| セッションタイムアウト | [付録D: セッションタイムアウト](./sdk-guide.md#セッションタイムアウト) |
| MCP Server が接続できない | [付録D: MCP Server が接続できない](./sdk-guide.md#mcp-server-が接続できない) |
| 並列実行でメモリ不足 | [付録D: 並列実行でメモリ不足](./sdk-guide.md#並列実行でメモリ不足) |
| PR 作成時に HTTP 422 エラー | [付録D: PR 作成時に HTTP 422 エラー](./sdk-guide.md#pr-作成時に-http-422-エラー) |

## knowledge/ ドキュメント関連のトラブル

### knowledge/ フォルダーが空の場合

**症状**: Custom Agent の設計精度が低い、業務要件が反映されていない。

**対処法**:
1. `qa/` フォルダーに質問票ファイルが存在するか確認する
2. 質問票が存在する場合は `knowledge-management` ワークフローを実行する（[km-guide.md](./km-guide.md) 参照）
3. `knowledge/business-requirement-document-status.md` で D01〜D21 のカバレッジを確認する

### knowledge/ ファイルが期待通り参照されない

**症状**: Custom Agent が `knowledge/` の内容を無視して設計している。

**確認事項**:
1. 各 Custom Agent ファイル（`.github/agents/*.agent.md`）の `knowledge/ 参照（任意・存在する場合のみ）` セクションに対象ファイルが記載されているか確認する
2. `knowledge/` のファイル名が正しい形式（`D{NN}-<文書名>.md`）になっているか確認する
3. `knowledge/` ファイルの `**Prompt投入可否**:` フィールドが `Yes（Confirmed のみ）` になっているか確認する（`No（Draft）` の場合は未確定事項があります）
