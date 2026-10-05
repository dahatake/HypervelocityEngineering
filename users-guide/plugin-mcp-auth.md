# Plugin / MCP Server 認証ガイド

← [README](../README.md)

> **要点**
>
> - MCP Server や Plugin の登録・有効化・認証は **GitHub Copilot CLI 側**で行います。
> - HVE は登録済み構成を **GitHub Copilot SDK 経由で確認**し、実働 session の初期化・公開範囲の制限を行います。永続設定の変更や認証開始は行いません。
> - Work IQ を使う場合も同じです。HVE は Work IQ の設定・認証を実行しません。

---

## 1. 役割分担

### 1.1 GitHub Copilot CLI 側で行うこと

- 利用したい **Plugin または MCP Server** を選ぶ
- 登録・有効化・認証を完了する
- 対話セッションの ``/mcp`` で接続状態と公開ツールを確認する

HVE は配布元、Plugin ID、remote transport の詳細、raw config の保存形式を仮定しません。利用者が GitHub Copilot CLI に設定した構成だけを前提にします。exact `workiq` は、大文字小文字を区別した server 名の完全一致を意味します。

### 1.2 HVE 側で行うこと

HVE は GitHub Copilot SDK 1.0.11 の `client.rpc.mcp.discover(MCPDiscoverRequest(working_directory=...))` を含む共通 ResourceSnapshot から、対象 working directory の exact `workiq` が enabled かを確認します。文書上の状態名は次の 3 つです。

- `ready`
- `not-configured`
- `unverified`

判定基準は次のとおりです。

| 状態 | 判定 |
|---|---|
| `ready` | discovery 結果に exact `workiq` が enabled で存在する |
| `not-configured` | exact `workiq` が存在しない、disabled、または alias しか見えない |
| `unverified` | SDK import、client start、`mcp.discover`、response schema、working directory 解決のいずれかを確認できない |

discovery の `ready` は runtime の `connected` を意味しません。設定の存在・有効状態の確認であり、認証済みや知識探索で使う tool 公開済みの証拠ではありません。Prompt plan と no-prompt inventory では MCP の初期化・接続を行わず、実働 session で §3 の検証を行います。

HVE は raw config の複製、OAuth 開始、ブラウザ起動、テナント切替、診断 query の自動実行を行いません。M365 の診断クエリを自動実行しません。

### 1.3 Plugin / MCP / Skill の ResourceSnapshot

Install / config / auth は **Copilot CLI の責務**です。HVE が一覧表示・policy route の解決に使うのは、process ごとに取得した
**ResourceSnapshot** の safe field だけです。GUI の `C7` と Tool-Search の `SDK Resources` タブは、同じ snapshot を表示します。

| field | 意味 |
|---|---|
| `kind` | `plugin` / `mcp_server` / `skill` |
| `name` | model-facing の resource 名 |
| `source_kind` | `marketplace` / `plugin` / `direct` などの安全な出所種別 |
| `plugin_marketplace` | owner plugin が一意に確認できた場合だけ表示する marketplace 名 |
| `owner_plugin` | MCP / Skill の所有元 plugin。unverified なら使わない |
| `enabled` | snapshot 取得時に enabled と観測できたか（runtime の接続状態とは別） |
| `effective_category` | policy route が解決した `knowledge` / `software-engineering` / `both` / `unclassified` |
| `individual_override` | exact resource classification の上書き |

`snapshot projection` は上表の metadata だけを使います。raw config、path、credential、OAuth state、transport detail は表示も保存もしません。

---

## 2. Copilot CLI での登録と認証

登録・認証手順は GitHub Copilot CLI 公式ドキュメントに従ってください。

- MCP Server 追加: <https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers>
- Copilot CLI 認証: <https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli>

### 2.1 対話 UI で登録する場合

1. `copilot` を起動する
2. 対話セッションで ``/mcp`` を開く
3. 使いたい Plugin または MCP Server の登録・有効化・認証を完了する

Work IQ を使う場合は、Copilot CLI 側で次を満たしてください。

1. server 名が exact `workiq` で `connected` になっている
2. exact `workiq` が読み取り用 tool（既定 allowlist は `retrieve` / `ask` / `fetch` / `search_paths` / `get_schema` / `list_agents`）を公開している

認証は GitHub Copilot CLI 側で行います。HVE の実働 session では、次節の SDK 初期化と接続確認を別途行います。

---

## 3. HVE が参照する最小情報

HVE が知識探索 session を組み立てるときに使う公開情報は最小限です。

- `enable_config_discovery=True`
- usable ではない enabled server を `disabled_mcp_servers` へ入れる
- `available_tools` は知識探索 custom tool と `hve/toolsearch/policy.json` の `knowledge_tool_allowlists` に含まれる読み取り専用 MCP tool だけにする

既定の `workiq` allowlist は `retrieve` / `ask` / `fetch` / `search_paths` / `get_schema` / `list_agents` です。`create_entity` / `update_entity` / `delete_entity` / `do_action` / `call_function` / `fetch_blob` は公開しません。raw config、remote URL、header、credential を複製しません。

事前 QA で usable な知識源がある場合、未回答質問票を `qa/<run_id>-<step_id>-pre-execution-qa.md` へ保存し、知識探索 session が `調査回答` / `調査状態` / `調査出典` を埋めます。探索を行う場合、CLI / GUI / IPC の人への回答待ちは行いません。usable な知識源が 0 件の場合だけ従来の回答収集に戻ります。

caller の `disabled_mcp_servers` / `disabled_skills` と route の除外は和集合にし、exact 名の順序を保って重複を除きます。required MCP / Skill との衝突は `create_session` / `resume_session` より前に停止し、caller が除外した optional resource は再有効化しません。実効 route の検証対象からも外します。これは永続設定を変えない session 単位の除外です（[SDK v1.0.11 MCP ガイド](https://github.com/github/copilot-sdk/blob/v1.0.11/docs/features/mcp.md#disabling-configured-servers-per-session)）。

実効選択 MCP がある実働 session では、最初の `send` / query より前に **明示的な SDK 初期化 → 接続確認 → `list_tools`** の順で検証します。`session.rpc.tools.initialize_and_validate()` を MCP の `list` / `status` / `list_tools` より先に呼びます（[SDK v1.0.11 RPC 定義](https://github.com/github/copilot-sdk/blob/v1.0.11/python/copilot/generated/rpc.py)）。初期化の正常復帰だけでは接続済みと判定しません。

- `session.rpc.mcp.list()` で知識源 server の `connected` を確認する
- 接続後に `session.rpc.mcp.list_tools(server_name=<知識源名>)` で allowlist tool の公開を確認する

実効選択 MCP が 0 件なら MCP 初期化・接続待ち・`list_tools` は行いません。ただし required Skill の runtime 検証と、caller filter の適用確認は省略しません。この確認のために設定変更・認証・browser 起動・診断 query は行いません。

**時間予算**: セッション取得後の `apply_resource_route` の入口から出口までが **routing の共有 60 秒**です。required Skill 検証、初期化、接続確認、`list_tools`、options ACK、optional disable と poll 待機を含み、API / server ごとに予算を再付与しません。poll は 0.5 秒間隔で、残時間が短ければその範囲に縮め、caller の deadline が短ければ早い方を使います。残時間がなくなった場合は optional でも続行しません。失敗時の `disconnect` には別枠の上限 5 秒を適用し、disk 上の再開状態は削除しません。client 起動・session 作成／再開・client 停止はこの予算外であり、run 全体の timeout ではありません。実行全体が 65 秒以内に終わるという保証でもありません。

---

## 4. 利用不可時の扱い

HVE は保存済み設定を変更しません。以下は起動時の discovery で利用不可と判定した場合の、run 単位で知識源を外す扱いです。runtime の失敗を一律に続行する規則ではありません。

- GUI: 無効表示にし、保存設定と今回起動の実効状態を分けて表示
- CLI wizard: Work IQ の選択肢を表示しない
- 直接 CLI: 当該 run の該当知識源だけを除去して続行
- Prompt 版: 最終 argv から除去し、warning/comment だけを残す
- AKM の実効 source が Work IQ のみで 0 件になる場合: 開始しない

**runtime の適用確認（ACK）**: `session.rpc.options.update(...)` は必要な場合に全 server 分を集約して 1 回だけ行い、`success is True` だけを ACK 成功とします。`success=False`、不正・欠落応答、RPC 例外は更新失敗です。caller filter は `available_tools` / `excluded_tools` の非 `None` 指定（空リストも含む）で、route により許可を広げません。ACK 非成功時に required MCP または caller filter がある場合は fail-closed です。選択 MCP がすべて optional かつ caller filter がない場合は、共有 deadline の残時間内に全選択 MCP の disable が成功した場合だけ継続できます。disable 失敗・期限切れ・cancel は停止し、追加予算や 2 回目の options 更新で救済しません。接続・tool 検証で optional server が失敗した場合も、期限内にその server を disable できた場合だけ除外して続行します。

---

## 5. 利用者が確認するポイント

事前 QA の知識探索 session が準備・runtime 検証で拒否された場合は、探索を行わず警告付きで補助調査だけをスキップし、回答済み QA の保存とメイン処理を継続します。これは質問票／通常 Step の required 資源失敗を任意扱いに変える規則ではありません。

Work IQ を有効にしたい場合、利用者は GitHub Copilot CLI の対話セッションで ``/mcp`` を開き、以下を確認してください。

- exact `workiq`
- `connected`
- `retrieve` / `ask` / `fetch` / `search_paths` / `get_schema` / `list_agents` のいずれか

`MCP host not initialized` は初期化未完了であり、登録の不存在や認証エラーを確定するものではありません。一方、`needs-auth` は認証が必要な状態を示します。HVE は認証を開始しないため、`needs-auth` を `pending` のように再確認せず、直ちに失敗として扱います（required の server は停止、optional の server は session 内で無効化して続行）。認証は Copilot CLI の `/mcp` 側で行ってから再実行してください。

HVE は §3 の SDK 初期化と runtime 検証で利用条件を確認します。診断のための M365 query、OAuth 再試行、設定ファイルの再生成は行いません。新しい公開 flag・設定は追加しません。

---

## 6. セキュリティとログ

- HVE は Work IQ の設定・認証を実行しません。
- HVE は M365 の診断クエリを自動実行しません。
- MCP ログには **M365 の業務データが平文で含まれうる** ため、共有前に内容を確認してください。

---

## 7. 関連ドキュメント

- [HVE CLI Orchestrator ガイド](./hve-cli-orchestrator-guide.md)
- [トラブルシューティング](./troubleshooting.md)
