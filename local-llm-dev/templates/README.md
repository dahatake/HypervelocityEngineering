# templates/

VS Code の BYOK（Custom Endpoint）からローカル Ollama を使うための手動設定サンプルです。
既定構成は `qwen3:8b`、コンテキスト長 `8192` tokens です。Foundry はこの3サンプルの対象外です。

> [!IMPORTANT]
> オフラインキットを使う場合、producer が選択したモデル名とコンテキスト長から3設定を生成します。
> sample JSON の手動コピーは不要です。Windows は [WINDOWS.md](../WINDOWS.md)、macOS は
> [MACOS.md](../MACOS.md) の dry-run、競合停止、導入手順に従ってください。

## 3つの JSON サンプル

| ファイル | 用途 | 配置先のファイル名 |
|---|---|---|
| [chatLanguageModels.sample.json](chatLanguageModels.sample.json) | Ollama の OpenAI Chat Completions 互換 endpoint を VS Code の Custom Endpoint として登録する | `chatLanguageModels.json` |
| [settings.offline.sample.json](settings.offline.sample.json) | 拡張機能の自動更新を止め、utility model と inline Chat の既定モデルをローカルモデルへ向ける | `settings.json` |
| [ollama-server.sample.json](ollama-server.sample.json) | Ollama Cloud 機能を無効化して local-only にする | `server.json` |

`disable_ollama_cloud=true` は Ollama Cloud 機能を無効化しますが、OS のネットワーク遮断、firewall、
server の bind 制御を代替しません。オフライン性は端末・ネットワーク側でも保証してください。

[copilot-instructions.ja.md](copilot-instructions.ja.md) は日本語 custom instructions の別テンプレートであり、
上記3つの JSON 設定には含まれません。

## Windows / macOS の配置先

次は VS Code の既定 User profile と、通常の Ollama ユーザー設定の配置先です。

| 設定 | Windows | macOS |
|---|---|---|
| VS Code language models | `%APPDATA%\Code\User\chatLanguageModels.json` | `~/Library/Application Support/Code/User/chatLanguageModels.json` |
| VS Code user settings | `%APPDATA%\Code\User\settings.json` | `~/Library/Application Support/Code/User/settings.json` |
| Ollama server settings | `%USERPROFILE%\.ollama\server.json` | `~/.ollama/server.json` |

`chatLanguageModels.json` はコマンドパレットの `Chat: Manage Language Models` から
`Add Models` → `Custom Endpoint` を選んでも開けます。`settings.json` は
`Preferences: Open User Settings (JSON)` から開けます。

## 既存 JSON は上書きせず手動マージする

既存ファイルへ sample 全体を無条件に上書きしないでください。バックアップを取得し、次の単位でマージします。

- `chatLanguageModels.json`: トップレベルは配列です。既存の provider を残し、sample の provider オブジェクトを配列へ追加または同じ provider 内で統合します。別のキーで包みません。
- `settings.json`: 既存設定を残し、sample にあるキーだけを JSON オブジェクトへ追加または更新します。
- `server.json`: 既存設定を残し、`"disable_ollama_cloud": true` を追加または更新します。

マージ後は JSON の構文エラーがないことを確認し、VS Code と Ollama を再起動します。
オフラインキットの installer は異なる既存設定を自動マージせず停止するため、各 OS ガイドの競合対応に従ってください。

## 既定モデルとコンテキスト長

3サンプルの既定値は次のとおりです。

| 項目 | 既定値 |
|---|---|
| Ollama model ID | `qwen3:8b` |
| endpoint | `http://127.0.0.1:11434/v1/chat/completions` |
| `maxInputTokens` | `6144` |
| `maxOutputTokens` | `2048` |
| VS Code が扱う token 合計 | `6144 + 2048 = 8192` |
| Ollama の実効コンテキスト長 | `OLLAMA_CONTEXT_LENGTH=8192` |

Ollama の既定コンテキスト長は `4096` です。sample の token 合計と実効コンテキストを一致させるため、
Ollama を停止してから次のようにユーザー環境へ `8192` を設定し、Ollama を再起動します。

| OS | 設定方法 |
|---|---|
| Windows | ユーザー環境変数 `OLLAMA_CONTEXT_LENGTH` を `8192` に設定する |
| macOS | `launchctl setenv OLLAMA_CONTEXT_LENGTH 8192` を実行する |

モデルをロードした後、`ollama ps` の `CONTEXT` 列が `8192` であることを確認してください。

モデルまたは token 値を変更する場合は、次を同時に更新します。

1. `chatLanguageModels.json` の model `id` / 表示用 `name` と、`settings.json` の3つの model 値を実際の Ollama model に合わせる。
2. `maxInputTokens` と `maxOutputTokens` をどちらも正の値にし、その合計を採用するコンテキスト長にする。
3. `OLLAMA_CONTEXT_LENGTH` を同じ合計値にする。合計はモデルが対応するコンテキスト長を超えないようにする。
4. Ollama を再起動し、`ollama ps` で実効値を確認する。
5. Agent で使う場合は、次節の endpoint 検証に合格してから `toolCalling` を `true` にする。

## Custom Endpoint と Agent の安全条件

### `apiKey`

sample の `"apiKey": "unused-but-required"` は、loopback のローカル Ollama では検証されないことを前提にした
**非秘密のダミー値**です。本物の API key、token、password を入れないでください。認証が必要な別 endpoint へ
転用する場合は、VS Code 公式の `${input:...}` による secret storage 参照を使用します。

### `toolCalling`

`toolCalling: true` はモデル名だけで判断しません。実際に使用するモデルと Ollama の組み合わせで、
[verify_endpoint.py](../tools/verify_endpoint.py) を `--require-agent` 付きで実行します。
sample にある `true` を現在の環境での合格証明とみなさず、手動設定では検証が終わるまで `false` にしてください。
リポジトリルートで実行し、`python` は利用環境の Python 3 コマンドへ読み替えます。

```shell
python local-llm-dev/tools/verify_endpoint.py --url http://127.0.0.1:11434 --model qwen3:8b --require-agent --expected-context 8192
```

終了コードが `0` で、最後が `結果: すべて OK。Chat / Agent の両方で使えます。` の場合だけ
`toolCalling` を `true` にします。失敗、警告、timeout がある場合は `false` のままにし、Agent 用モデルとして扱いません。
VS Code 公式でも、Chat の Agent で使うモデルには tool calling が必要とされています。

## モデル選択4設定の意味

`settings.offline.sample.json` では、次の4設定をすべて `qwen3:8b` のローカル利用へ揃えています。

| 設定 | 意味 |
|---|---|
| `chat.utilityModel` | タイトル、要約、Settings Search、Git review など一般的な utility flow のモデル |
| `chat.utilitySmallModel` | コミットメッセージ、rename 候補、branch 名、prompt 分類、intent 検出など高速・軽量な utility flow のモデル |
| `chat.byokUtilityModelDefault` | BYOK の main agent model を utility flow の既定にするかを選ぶ設定。sample の `Main Agent Model` は選択中の BYOK main model を使う。上の2つに明示したモデルがあれば、その値が優先される |
| `inlineChat.defaultModel` | エディター内で明示的に呼び出す inline Chat の既定モデル |

### inline Chat と inline completion は別機能

- **inline Chat**: エディター内でプロンプトを入力し、質問や編集を明示的に依頼する機能です。`inlineChat.defaultModel` が対象です。
- **inline completion / inline suggestions**: 入力中に表示される ghost text / Tab 補完です。`inlineChat.defaultModel` では有効になりません。現在、ローカル BYOK model はこの機能へ接続できず、この sample も設定しません。

## オフラインキット利用時

`Prepare-Windows.cmd` / Windows producer と `Prepare-macOS.sh` は、選択した model と context length から
`config/chatLanguageModels.json`、`config/settings.offline.json`、`config/ollama-server.json` を生成します。
model を変更した場合も producer が model ID、utility / inline Chat の値、token 配分を揃えるため、
このディレクトリの sample JSON をキットへ手動コピーしないでください。

## 公式出典

- [VS Code: AI language models in VS Code](https://code.visualstudio.com/docs/agent-customization/language-models)
  - BYOK、Custom Endpoint、`chatLanguageModels.json`、token 合計、tool calling、utility model、inline Chat、inline suggestions の仕様
- [VS Code: User and workspace settings](https://code.visualstudio.com/docs/configure/settings#_settings-file-locations)
  - Windows / macOS の User `settings.json` 配置先
- [Ollama FAQ: context window size](https://docs.ollama.com/faq#how-can-i-specify-the-context-window-size)
  - 既定 `4096` と `OLLAMA_CONTEXT_LENGTH`
- [Ollama FAQ: configure Ollama server](https://docs.ollama.com/faq#how-do-i-configure-ollama-server)
  - Windows のユーザー環境変数と macOS の `launchctl`
- [Ollama FAQ: disable Ollama Cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)
  - `~/.ollama/server.json` の `disable_ollama_cloud`

公式資料確認日: 2026-08-16
