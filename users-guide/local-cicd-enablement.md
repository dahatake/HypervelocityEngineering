# ローカル（GUI / CLI）からの CI/CD 有効化ガイド

← [README](../README.md)

> **対象読者**: GUI / CLI Orchestrator（`python -m hve` / `python -m hve cli`）をローカル PC で実行し、生成された GitHub Actions デプロイワークフロー（例: `.github/workflows/deploy-*.yml` 等）を GitHub 上で実際に動かして CI/CD を有効化したい方
> **前提**: [hve-cli-getting-started.md](./hve-cli-getting-started.md) または [hve-gui-getting-started.md](./hve-gui-getting-started.md) のセットアップが完了していること
> **Cloud をお使いの場合**: このガイドは不要です。Cloud は最初から GitHub.com 上でワークフローが生成・反映されるため、[hve-cloud-getting-started.md](./hve-cloud-getting-started.md) のみで完結します。

---

## 目次

- [なぜローカル実行では追加手順が必要か](#なぜローカル実行では追加手順が必要か)
- [前提: Azure OIDC Secrets の登録](#前提-azure-oidc-secrets-の登録)
- [CI/CD 有効化フロー（GUI / CLI 共通）](#cicd-有効化フローgui--cli-共通)
- [ワークフローの手動発火（workflow_dispatch）](#ワークフローの手動発火workflow_dispatch)
- [対象ワークフローと生成物](#対象ワークフローと生成物)
- [注意点・既知の制約](#注意点既知の制約)
- [検証手順](#検証手順)
- [関連ドキュメント](#関連ドキュメント)

---

## なぜローカル実行では追加手順が必要か

GUI / CLI Orchestrator は、デプロイ系ワークフロー（例: `asdw-web` の Azure Functions / Static Web Apps デプロイ）を実行すると、GitHub Actions のデプロイワークフロー（例: `.github/workflows/deploy-*.yml` 等）を**ローカルの作業ツリーに生成**します。

一方で、GitHub Actions の CI/CD が実際に動くのは **GitHub.com 上にワークフローが存在するとき**です。ローカルに生成しただけでは GitHub 側は何も実行しません。そのため、ローカル実行では「生成したワークフローを GitHub のデフォルトブランチ（`main`）へ反映する」手順が別途必要になります。

> **補足**: アプリの Azure リソース作成・デプロイ自体は、各デプロイエージェントがローカルの `az` CLI スクリプト（`src/infra/azure/create-azure-*.sh` 等）で実行します。本ガイドが扱うのは「GitHub Actions による継続的デプロイ（CI/CD）を有効化する」手順です。

---

## 前提: Azure OIDC Secrets の登録

生成されるデプロイワークフローは OIDC 認証（`azure/login@v2`）を使用するため、以下の 3 つの Secrets を GitHub リポジトリに登録してください（初回のみ）。

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

これらは Cloud でのデプロイと**同一の Secrets** です。登録手順は重複を避けるため、[hve-cloud-getting-started.md](./hve-cloud-getting-started.md#3-azure-static-web-apps-デプロイ用-secretsswa-デプロイ時) の Step.4「Azure Static Web Apps デプロイ用 Secrets」を参照してください（GitHub リポジトリへの Secrets 登録手順は Cloud・ローカルで共通です。すでに Cloud 用に設定済みであれば追加作業は不要です）。

Secrets の値をコマンド引数、ワークフローファイル、Issue、PR、ログへ記録してはいけません。OIDC の Federated Credential と GitHub Environment を設定正本とし、生成された各ワークフローではジョブ単位の `permissions:` を必要最小限にします。GitHub Actions の `GITHUB_TOKEN` は既定権限に頼らず、必要な権限だけを明示してください。

---

## CI/CD 有効化フロー（GUI / CLI 共通）

GUI / CLI Orchestrator は既定ではコミット・push を行いません。生成物を GitHub に反映するには `--create-pr`（または `--create-issues`）を指定します。

1. **OIDC Secrets を登録**（上記「前提」、初回のみ）
2. **`--create-pr` を付けて実行**（`GH_TOKEN` または `GITHUB_TOKEN`、`--repo` / `REPO`、`origin` に実在するベースブランチが必要）

   ```bash
   python -m hve orchestrate --workflow asdw-web ... --create-pr --repo <owner>/<repo>
   ```

   この実行は GitHub 書込み startup preflight の対象です。HVE は開始前に `owner/repo`、token の存在、有効な Git branch 名、`origin`、完全一致する `refs/heads/<branch>` を検査し、不整合時は `main` やローカル branch へ補正せず停止します。`--dry-run` も同じ検査対象です。GitHub 書込みを要求しない通常 run では token・remote を検査しません。終了 status の区別と実行順序は [CLI ガイドの startup preflight](./hve-cli-orchestrator-guide.md#github-書込み-startup-preflightfr-cli-3182) を参照してください。

   実行後、`copilot-sdk/<prefix>-<uuid>` ブランチが push され、PR が作成されます。
3. **PR をレビューして `main` にマージ**

   > GUI / CLI の `--create-pr` は PR を作成するだけで、**自動マージは行いません**。マージはご自身で実施してください（完全自動マージが必要な場合は Cloud の Issue Template を使用します）。
4. **マージで CI/CD が発火**

   多くの生成ワークフローは `on: push:` の `branches: [main]` を含むため、`main` へのマージで自動的に実行されます。push トリガーを持たないワークフローの場合は、次節の手動発火（`workflow_dispatch`）を使用してください。

入力は、対象リポジトリ、登録済みの OIDC Secrets、生成されたワークフローファイルです。出力は GitHub 上の PR と、マージ後または手動発火後の workflow run です。Actions の run が成功し、必要な Azure リソースへ期待どおり反映された時点を完了とします。

---

## ワークフローの手動発火（workflow_dispatch）

生成ワークフローには `workflow_dispatch` トリガーも含まれます。`main` 反映後は手動でも実行できます。

- GitHub の **Actions** タブ → 対象ワークフロー → **Run workflow**
- または CLI: `gh workflow run <ワークフローファイル名> --ref main`

---

## 対象ワークフローと生成物

`asdw-web` ワークフローおよび `adfdv` ワークフローが、デプロイ系の GitHub Actions ワークフローを生成します。デプロイ対象ごとに、生成されるワークフローと担当ステップは以下のとおりです。

| ワークフロー | デプロイ対象 | 生成される GitHub Actions ワークフロー | 担当ステップ（エージェント） |
|---|---|---|---|
| `asdw-web` | API（Azure Functions） | Functions デプロイ用ワークフロー（例: `.github/workflows/deploy-app009-functions.yml` 等） | Step 3.4（`Dev-Microservice-Azure-ComputeDeploy-AzureFunctions`） |
| `asdw-web` | UI（Azure Static Web Apps） | `.github/workflows/azure-static-web-apps-*.yml` | Step 4.3（`Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps`） |
| `adfdv` | データフロー（Azure Functions） | `.github/workflows/deploy-batch-functions.yml` | Step 3（`Dev-Dataflow-FunctionsDeploy`） |

> **データリソースのデプロイについて**: データストア作成ステップ（`asdw-web` の Step 1.3、`adfdv` の Step 1.2）は、ローカルの `az` CLI スクリプトで Azure リソースを作成します。これらのステップは GitHub Actions の CI/CD ワークフローを生成しません。

> **条件付き生成について**: どのデプロイステップが実行されるかは、アプリの構成や実行時に選択したステップによって異なります。実行されなかったステップに対応するワークフローは生成されません。

---

## 注意点・既知の制約

- **ローカル実行中はその場で CI/CD が発火しない**: デプロイステップ実行時点では生成ワークフローがまだリモートの `main` に存在しないため、その場での GitHub Actions 発火は行われません。CI/CD は `main` マージ後に有効化されます（この挙動は「ワークフローはデフォルトブランチに存在する必要がある」という GitHub Actions の仕様に基づく説明です）。
- **`--create-pr` は自動マージしない**: 前述のとおりマージは手動です。
- **OIDC Secrets 未登録時はデプロイジョブが失敗**: `azure/login` が認証情報を取得できず失敗します。
- **権限不足で失敗した場合**: run の失敗ログから不足した GitHub Actions 権限または Azure RBAC を確認し、対象ジョブまたは対象スコープに限定して追加します。リポジトリ全体への書込み権限や Azure の Owner 権限を回避してください。

## HVE カスタマイズと回帰確認

- **設定正本**: 生成後の `.github/workflows/deploy-*.yml` と、各デプロイステップの現行テンプレート／I/O 契約です。値を別の手順書へ複製して管理しません。
- **拡張手順**: まず既存の workflow を 1 本だけ変更し、必要な `permissions:`、Environment、`runs-on` をジョブ単位で確認します。秘密値は GitHub Secrets または Azure 側の ID 参照だけを使います。
- **回帰検証**: PR で workflow 構文と既存トリガーを確認し、マージ後は対象 run の成功とデプロイ結果を確認してから次の workflow へ展開します。
- **互換性**: GUI / CLI の `--create-pr` は PR 作成までです。既存の `push` または `workflow_dispatch` トリガーを削除・変更する場合は、既存の運用手順への影響を要確認とします。

---

## 検証手順

1. PR マージ後、**Actions** タブで対象ワークフローの run が成功（緑）していることを確認します。
2. または `gh run watch --exit-status` で完了を待機します。
3. Static Web Apps の場合は本番切替スクリプト（`src/infra/azure/switch-swa-to-main.sh`）の案内に従います。

---

## 関連ドキュメント

- [hve-cli-getting-started.md](./hve-cli-getting-started.md) / [hve-gui-getting-started.md](./hve-gui-getting-started.md) — ローカル環境のセットアップ
- [hve-cloud-getting-started.md](./hve-cloud-getting-started.md) — Azure OIDC Secrets の登録手順
- [README.md](../README.md) — 全体像
- [Use GITHUB_TOKEN for authentication in workflows](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token) — `permissions:` による最小権限
