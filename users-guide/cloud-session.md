# Cloud Sessions

GitHub Copilot SDK 1.0.0+ の Cloud Sessions を使うと、HVE の一部セッションを Mission Control 上で実行できます。既定は OFF です。

> 注記: 本ページの Cloud Sessions は Copilot SDK の実行先オプションです。HVE の「Cloud版」（Issue Template → GitHub Actions → GitHub Copilot Cloud Agent / Coding Agent）とは別機能です。

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

## Mission Control URL

Cloud Session が開始され、SDK から Mission Control URL が通知されると、Workbench にリンクが表示されます。ステータスバーにも URL 取得済みの状態が表示されます。

## フォールバック

以下の場合はローカル Copilot CLI セッションにフォールバックします。

- SDK が Cloud Sessions 型を提供していない
- `cloud` 引数が SDK で未サポート
- repository owner/name を解決できない

ただし、`policy_blocked` は組織ポリシーによる拒否として扱い、ローカル fallback せず停止します。

## 注意事項

- `GITHUB_COPILOT_INTEGRATION_ID` は識別子として扱います。トークンや秘密情報を入力しないでください。
- `COPILOT_MC_BASE_URL` には token、Basic 認証情報、署名付き query、API key を含めないでください。
- GUI Autopilot で複数プロセスが起動する場合、Cloud Session 同時実行上限は各プロセス内で適用されます。全体上限は概ね `autopilot_max_parallel × cloud_session_max_concurrency` になります。
