# Cloud Sessions

← [README](../README.md)

> **対象読者**: CLI / GUI Orchestrator を既に実行できる方で、Step セッションの実行先を Copilot SDK の Cloud Sessions へ振り分けたい方
> **前提**: [hve-cli-getting-started.md](./hve-cli-getting-started.md) または [hve-gui-getting-started.md](./hve-gui-getting-started.md) のセットアップ完了、`python -m hve login` 済み、Cloud Session を実行する repository への権限、Copilot の Cloud Agent entitlement が有効であること、組織ポリシーで Cloud Sessions が許可されていること
> **スコープ**: Cloud Sessions の有効化・振り分け・確認・失敗時対応・設定正本
> **非対象**: HVE Cloud 版（Issue Template → GitHub Actions → Copilot Cloud Agent）の設定。これは [hve-cloud-getting-started.md](./hve-cloud-getting-started.md) を参照してください。

GitHub Copilot SDK 1.0.0+ の Cloud Sessions を使うと、HVE の一部セッションを Mission Control 上で実行できます。既定は OFF です。

> 注記: 本ページの Cloud Sessions は Copilot SDK の実行先オプションです。HVE の「Cloud版」（Issue Template → GitHub Actions → GitHub Copilot Cloud Agent / Coding Agent）とは別機能です。

## 2 つの「Cloud」の違い

| 観点 | 本ページ: Cloud Sessions | HVE Cloud 版 |
|---|---|---|
| 起動元 | ローカルの CLI / GUI Orchestrator | GitHub.com の Issue Template |
| 実行主体 | Copilot SDK が作成する Cloud Session | GitHub Actions + Copilot Cloud Agent |
| 設定場所 | `--cloud-session*` 引数 / 環境変数 / GUI 設定 | リポジトリの Secrets・ラベル・Workflow |
| 既定 | OFF | 該当なし（Issue 起票が起点） |
| 正典 | 本ページ | [hve-cloud-getting-started.md](./hve-cloud-getting-started.md) |

## CLI で有効化する

```powershell
python -m hve orchestrate --workflow akm --cloud-session --repo owner/repo
```

主なオプション:

| オプション | 説明 |
| --- | --- |
| `--cloud-session` / `--no-cloud-session` | Cloud Session の既定 ON/OFF |
| `--cloud-session-owner` | Cloud repository owner。空時は `--repo owner/repo` から補完 |
| `--cloud-session-repository-name` | Cloud repository name。空時は `--repo owner/repo` から補完 |
| `--cloud-session-branch` | Cloud repository branch。空時は `--branch` を使用 |
| `--cloud-session-max-concurrency` | 1 プロセス内の Cloud Session 同時実行上限。既定 5 |
| `--cloud-session-integration-id` | `GITHUB_COPILOT_INTEGRATION_ID` に渡す識別子 |
| `--cloud-session-mc-base-url` | `COPILOT_MC_BASE_URL` に渡す Mission Control base URL |
| `--cloud-session-step-overrides` | Step 単位の ON/OFF 上書き JSON |
| `--cloud-session-subtask-overrides` | サブタスク単位の ON/OFF 上書き JSON |

例:

```powershell
python -m hve orchestrate --workflow akm --cloud-session --repo owner/repo --cloud-session-step-overrides '{"1": true, "2": false}'
```

## GUI で設定する

1. HVE GUI を起動します。
2. 設定画面の「一般 > 基本設定」を開きます。
3. `Cloud Session` を ON にします。
4. 必要に応じて repository owner/name/branch と同時実行上限を設定します。
5. Step 選択画面では各 Step 行の `☁ 継承 / ☁ ON / ☁ OFF` で Step 単位の上書きを指定できます。
6. サブタスク単位の上書きは「基本設定」の `Cloud サブタスク上書き JSON` に指定します。例: `{"pre_qa": true, "review": false}`。

## 自動振り分け

`Cloud Session` を ON にしている場合でも、HVE はすべての Step を Cloud に送るのではなく、DAG の実行 wave ごとに local / Cloud を自動振り分けします。

- 1 度に実行可能な Step が 1 件だけの場合、または `--max-parallel 1` のように実効並列数が 1 の場合は、原則として local 実行にします。
- 複数 Step を並列実行できる wave では、local を最低 1 件残したうえで、最大で wave の約半数を Cloud に割り当てます。
- `--max-parallel` が小さい場合は、実効並列バッチごとに local が 1 件残るよう Cloud 数を抑えます。
- Cloud 側は `--cloud-session-max-concurrency` の同時実行上限を超えないようにします。
- Step 単位 / サブタスク単位の明示上書きは、自動振り分けより優先されます。

優先順位は以下です。

1. サブタスク単位の上書き
2. Step 単位の上書き
3. 実行 wave 単位の自動振り分け
4. Cloud Session 全体設定

## 完了確認（有効化できたことを確かめる）

1. Workbench のログに Cloud Session 関連のイベント行が出力される。
2. Mission Control URL が通知されると、Workbench にリンクが表示される（次節）。
3. 想定どおりに local / Cloud が分かれたかは、Step 単位の実行ログで確認する。1 Step ずつしか走らない構成では、設定が ON でも local になるのが正常挙動です（「自動振り分け」節）。

Cloud に振り分けられた Step が 1 件も無い場合、まず `--max-parallel` と wave 内の Step 数を確認してください。設定不備ではなく自動振り分けの結果であることが多くあります。

## Mission Control URL

Cloud Session が開始され、SDK から Mission Control URL が通知されると、Workbench にリンクが表示されます。ステータスバーにも URL 取得済みの状態が表示されます。

## フォールバック

以下の場合はローカル Copilot CLI セッションにフォールバックします。

- SDK が Cloud Sessions 型を提供していない
- `cloud` 引数が SDK で未サポート
- repository owner/name を解決できない

ただし、`policy_blocked` は組織ポリシーによる拒否として扱い、ローカル fallback せず停止します。

## 失敗時対応

| 症状 | 最初に確認すること | 対応 |
|---|---|---|
| Cloud に振り分けられない | 実効並列数と wave 内 Step 数 | 1 並列では local が既定。`--max-parallel` を増やすか、Step 単位上書きで明示的に ON にする |
| repository が解決できない | `--repo owner/repo`、`--cloud-session-owner`、`--cloud-session-repository-name` | いずれかで owner/name を明示する。解決できない場合はローカルセッションへフォールバックする |
| `policy_blocked` で停止する | 組織の Copilot ポリシー | 組織管理者へ確認する。HVE 側の設定変更では回避できない（意図的に fallback しない） |
| Mission Control URL が出ない | Cloud 関連ログと URL 通知イベントの購読・表示 | Cloud Session 実行ログで実行先が Cloud かを先に確認する。Cloud 実行が確認できる場合は URL 通知イベント（`session.info`）の購読・表示経路を確認する |
| 上書き JSON が効かない | JSON の構文とキー | Step 上書きのキーは Step ID、サブタスク上書きのキーはサブタスク種別。優先順位は「サブタスク > Step > 自動振り分け > 全体設定」 |

一般的な CLI / GUI の障害切り分けは [troubleshooting.md](./troubleshooting.md) を参照してください。

## 設定の正本（HVE をカスタマイズする方へ）

| 対象 | 正本 |
|---|---|
| CLI 引数定義（`--cloud-session*`） | `hve/__main__.py` の `orchestrate` パーサー |
| 設定値・既定値・環境変数の解決 | `hve/config.py`（`cloud_session_*` フィールド） |
| 有効判定・自動振り分け・SDK オプション生成・フォールバック判定 | `hve/cloud_session.py` |
| GUI 設定項目の永続化 | `hve/gui/settings_store.py`（`hve/.settings.txt`） |

環境変数から設定する場合のキー（`hve/config.py`）:

| 環境変数 | 対応する設定 |
|---|---|
| `HVE_CLOUD_SESSION_ENABLED` | 全体の ON/OFF（既定 OFF） |
| `HVE_CLOUD_SESSION_REPOSITORY_OWNER` / `..._NAME` / `..._BRANCH` | repository の owner / name / branch |
| `HVE_CLOUD_SESSION_MAX_CONCURRENCY` | 同時実行上限（既定 5） |
| `GITHUB_COPILOT_INTEGRATION_ID` | integration ID |
| `COPILOT_MC_BASE_URL` | Mission Control base URL |
| `HVE_CLOUD_SESSION_STEP_OVERRIDES` / `HVE_CLOUD_SESSION_SUBTASK_OVERRIDES` | 上書き JSON |

優先順位は「CLI 引数 > 環境変数 / GUI 設定」です。CLI で未指定（`None`）の項目は環境変数・設定値を継承します。

### 拡張手順と回帰検証

1. 引数を増やす場合は `hve/__main__.py` の定義と `hve/config.py` のフィールドを対で追加する。既定値は `config.py` 側に置く。
2. 振り分けルールを変える場合は `hve/cloud_session.py` の `compute_cloud_session_routing()` を変更する。優先順位を変える場合は `should_use_cloud_session()` も併せて確認する。
3. GUI から設定可能にする場合は `hve/gui/settings_store.py` の既定値に項目を追加する。
4. 回帰検証には次のテストを実行する。

```bash
python -m pytest hve/tests/test_cloud_session.py hve/tests/test_cloud_session_cli.py hve/tests/test_cloud_session_runtime.py
```

### 互換性・安全性

- Cloud Sessions は Copilot SDK 1.0.0+ の機能です。SDK 側が型・引数を提供しない環境では、機能を落とさずローカルセッションへフォールバックします。
- `policy_blocked` だけは意図的にフォールバックしません。ポリシー拒否を黙って迂回しないための設計です。
- 既定は OFF です。既定値を変更する場合は、この文書と `hve/config.py` の双方を更新してください。

## 注意事項

- `GITHUB_COPILOT_INTEGRATION_ID` は識別子として扱います。トークンや秘密情報を入力しないでください。
- `COPILOT_MC_BASE_URL` には token、Basic 認証情報、署名付き query、API key を含めないでください。
- GUI Autopilot で複数プロセスが起動する場合、Cloud Session 同時実行上限は各プロセス内で適用されます。全体上限は概ね `autopilot_max_parallel × cloud_session_max_concurrency` になります。

## 次のステップ

- CLI の全オプション: [hve-cli-orchestrator-guide.md](./hve-cli-orchestrator-guide.md)
- GUI の設定画面: [hve-gui-orchestrator-guide.md](./hve-gui-orchestrator-guide.md)
- HVE Cloud 版（Issue Template 起点）: [hve-cloud-getting-started.md](./hve-cloud-getting-started.md)

## 公式出典

- Cloud sessions（GitHub Copilot SDK） — <https://github.com/github/copilot-sdk/blob/main/docs/features/cloud-sessions.md>
- github/copilot-sdk（リポジトリ） — <https://github.com/github/copilot-sdk>
