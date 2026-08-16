# macOS オフライン Local LLM 開発環境 — はじめての一本道

オンラインの準備機で移送キットを作り、媒体でオフライン運用機へ移し、VS Code の Chat / Agent を Ollama のローカルモデルで確認する手順です。

> [!IMPORTANT]
> **macOS 実機での端から端までの E2E（準備 → 媒体移送 → dry-run → `--apply` → VS Code Chat / Agent）は未実施です。**
> 本書は `Prepare-macOS.sh`、`install-macos.sh`、静的契約テスト、公式資料を照合して作成しています。採用前に、管理下の実機で本書どおりに確認してください。

## 0. 対象と、先に知るべき制約

| 項目 | この手順の契約 |
|---|---|
| 準備機 | インターネット接続済みの **macOS 14 以降 / Apple Silicon (`arm64`)** |
| 運用機 | オフラインの **macOS 14 以降 / Apple Silicon (`arm64`)** |
| 通常ルート | Ollama + `qwen3:8b` + コンテキスト長 `8192` |
| VS Code 接続 | 組み込みの BYOK Custom Endpoint（OpenAI Chat Completions 互換） |
| PowerShell | **不要**。macOS ルートは Bash スクリプトと macOS 標準コマンドで完結 |
| 任意追加 | Foundry Local。ランタイム URL とモデルキャッシュ元は利用者が実値を指定 |

このキットは `uname -m` が `arm64` でなければ停止します。**Intel Mac は対象外**です。VS Code や Ollama 自体が Intel Mac を部分的にサポートしていても、この移送キットの保証対象にはなりません。Ollama の公式 macOS 要件も [macOS Sonoma 14+ と Apple M series](https://docs.ollama.com/macos#system-requirements) を案内しています。

macOS 用スクリプトは [`Prepare-macOS.sh`](tools/airgap-kit/Prepare-macOS.sh) と [`install-macos.sh`](tools/airgap-kit/install-macos.sh) です。`pwsh`、Windows PowerShell、PowerShell 7 のいずれも呼び出しません。プロジェクト内の固定契約でも macOS の PowerShell は「不要」です（[`CONTRACT.md`](tools/airgap-kit/CONTRACT.md)）。

VS Code の BYOK はローカルモデルを完全オフラインで Chat に利用でき、GitHub へのサインインや Copilot プランも不要です。ただし次は BYOK オフライン構成では利用できません。

- **インライン補完**（Tab 補完 / ghost text）
- セマンティック検索
- 埋め込みに依存する機能

`inlineChat.defaultModel` が設定されても、それは **インライン Chat** 用であり、インライン補完を有効にする設定ではありません。根拠は VS Code 公式の [AI language models in VS Code — BYOK と FAQ](https://code.visualstudio.com/docs/agent-customization/language-models#_bring-your-own-language-model-key) です。

## 1. 全体の流れ

次の順番を変えないでください。

1. オンライン準備機の OS / CPU を確認する。
2. `Prepare-macOS.sh` でキットを作る。
3. キットをアーカイブし、媒体へコピーして SHA-256 を確認する。
4. オフライン運用機へ展開する。
5. `install-macos.sh` を引数なしで実行し、dry-run を確認する。
6. 問題がなければ `install-macos.sh --apply` を実行する。
7. CLI、Ollama エンドポイント、VS Code Chat、VS Code Agent の順に確認する。

途中で `ERROR:`、SHA-256 不一致、版競合、設定競合、`[ WARN ]`、`[FAILED]` のいずれかが出た場合は停止してください。検証を回避するオプションはありません。

## 2. オンライン準備機でキットを作る

### 2.1 OS と CPU を確認する

Terminal を開き、次を実行します。

```bash
sw_vers -productVersion
uname -m
/bin/bash --version | head -n 1
```

**期待結果**

- `sw_vers` の先頭の整数が `14` 以上
- `uname -m` が正確に `arm64`
- Bash の版が表示される

VS Code の公式 macOS 導入方法と Apple Silicon ビルドについては [Installing Visual Studio Code on macOS](https://code.visualstudio.com/docs/setup/mac) を参照してください。

**トラブル**

| 表示・状態 | 対処 |
|---|---|
| macOS 13 以下 | OS を 14 以降へ更新するまで進めない |
| `uname -m` が `x86_64` | Intel Mac は対象外。Apple Silicon で Terminal を Rosetta 起動している場合はネイティブ Terminal でやり直す |
| `unsupported operating system` / `unsupported architecture` | スクリプトの安全停止。回避せず対象機を見直す |

### 2.2 リポジトリのスクリプト位置へ移動する

Finder でこのリポジトリのルートフォルダーを表示します。Terminal に `cd ` と末尾の空白まで入力し、そのフォルダーを Terminal へドラッグして Enter を押します。その後、次を実行します。

```bash
pwd
test -f local-llm-dev/tools/airgap-kit/Prepare-macOS.sh
cd local-llm-dev/tools/airgap-kit
chmod 0755 Prepare-macOS.sh install-macos.sh
./Prepare-macOS.sh --help
```

**期待結果**

- `test` が無言で終了する
- `Prepare-macOS.sh --destination PATH [options]` から始まるヘルプが表示される

**トラブル**

- `test` の終了コードが 0 でない、または `No such file or directory` の場合は、リポジトリのルートではありません。
- `Permission denied` の場合は `chmod 0755 Prepare-macOS.sh install-macos.sh` を再確認します。
- `Prepare-macOS.sh` だけを別の場所へコピーして実行してはいけません。同じディレクトリの `install-macos.sh` と一つ上の `verify_endpoint.py` が必須です。

### 2.3 通常ルートを実行する

本書では出力先を `$HOME/offline-kit-qwen3-8b` とします。出力先は、存在しないか空でなければなりません。既存データを削除して使い回さず、内容がある場合は別名を選んでください。

```bash
KIT_DIR="$HOME/offline-kit-qwen3-8b"
if [ -e "$KIT_DIR" ]; then
  printf '出力先は既に存在します。空であることを確認してください: %s\n' "$KIT_DIR"
  ls -A "$KIT_DIR"
else
  printf '出力先は未作成です: %s\n' "$KIT_DIR"
fi
```

空または未作成であることを確認したら実行します。既定値を曖昧にしないため、モデルとコンテキスト長も明記します。

```bash
./Prepare-macOS.sh \
  --destination "$KIT_DIR" \
  --model qwen3:8b \
  --context-length 8192
```

実行中は次の処理が行われます。

1. Python `3.14.7` Universal 2 `.pkg` を取得し、固定 SHA-256、版、`arm64` / `x86_64` を検証する。
2. 最新の VS Code Apple Silicon `.zip` を取得し、実際の版と `arm64` バイナリを検証する。
3. 最新の Ollama `.dmg` を取得し、実際の版と `arm64` バイナリを検証する。
4. 準備機に Python 3.10 以上がなければ、検証済み Python を自動 bootstrap する。
5. 利用可能な Ollama CLI がなければ、検証済み Ollama.app を自動 bootstrap する。
6. 専用の `127.0.0.1:11435` Ollama serverを選択contextで起動する。portが使用中なら停止し、既存serverは再利用しない。
7. `qwen3:8b` がなければ専用server経由で `ollama pull` し、Chat、streaming、構造化 tool call、tool 引数、実効contextを `--require-agent` 付きで検証する。
8. 選択モデルの manifest と参照 blob だけを収集する。
9. 設定と全ファイルの SHA-256 を記録し、`manifest.json` を最後に生成する。

Python 公式は、python.org が macOS 用の署名・notarize 済み Universal 2 `.pkg` を提供することを説明しています（[Using Python on macOS](https://docs.python.org/3/using/mac.html#installation-steps)）。Ollama の公式 macOS 導入方法は `.dmg` から `/Applications` へ配置する方式です（[Ollama for macOS](https://docs.ollama.com/macos#filesystem-requirements)）。

**Python / Ollama の自動 bootstrap**

- Python: 準備処理に使える Python 3.10 以上が見つからない場合だけ、`sudo installer` で Python `3.14.7` を導入します。既存の 3.10 以上があれば準備処理にはそれを使いますが、キットには検証済み `3.14.7` の `.pkg` を収録します。
- Ollama: `ollama` または `/Applications/Ollama.app/Contents/Resources/ollama` が利用できない場合だけ、`sudo ditto` で Ollama.app を配置します。利用不能な `/Applications/Ollama.app` が既にある場合は上書きせず停止します。

**成功時の期待結果**

- 検証途中に `結果: すべて OK。Chat / Agent の両方で使えます。` が表示される。
- 最後に `Offline kit prepared successfully:` が表示される。
- 続くモデル行が `qwen3:8b` と `context length: 8192` を示す。digest は準備機で `ollama list` が返した実値です。

`8192` の場合、生成される VS Code モデル設定は `maxInputTokens=6144`、`maxOutputTokens=2048` です。Ollama 側には運用機で `OLLAMA_CONTEXT_LENGTH=8192` を設定します。Ollama 公式 FAQ は、既定コンテキスト長が 4096 で、macOS アプリの環境変数は `launchctl` で設定するよう案内しています（[Ollama FAQ — context window / Mac environment variables](https://docs.ollama.com/faq#how-can-i-specify-the-context-window-size)）。

### 2.4 準備機で `sudo` が使われる場所

`Prepare-macOS.sh` が `sudo` を実行するのは不足コンポーネントの bootstrap 時だけです。

| 条件 | 実行内容 | 変更先 |
|---|---|---|
| Python 3.10 以上が見つからない | `sudo installer -pkg ... -target /` | `/Library/Frameworks/Python.framework` など公式 `.pkg` の固定先 |
| 利用可能な Ollama CLI がない | `sudo ditto ... /Applications/Ollama.app` | `/Applications/Ollama.app` |

ダウンロード、モデル取得、キット生成、VS Code 資材の収集には `sudo` を使いません。認証を求めるダイアログや Terminal のパスが上表と異なる場合は、パスワードを入力せず中断してください。

### 2.5 キットの内容を確認する

```bash
plutil -lint "$KIT_DIR/manifest.json"
find "$KIT_DIR" -type d -print
```

**期待結果**

- `manifest.json: OK` と表示される。
- 少なくとも `runtime`、`models/ollama`、`config`、`tools`、`docs` がある。
- `config/chatLanguageModels.json` は Ollama の `http://127.0.0.1:11434/v1/chat/completions` を登録する。
- `config/settings.offline.json` は拡張更新を止め、utility model と inline Chat の既定を選択モデルにする。
- `config/ollama-server.json` は `{ "disable_ollama_cloud": true }` を設定する。

Ollama 公式 FAQ は local-only 設定と `~/.ollama/server.json` を説明しています（[Disable Ollama Cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)）。この設定は OS ファイアウォール規則を作りません。運用機はオフラインのまま使うか、組織のネットワーク制御を別途適用してください。

### 2.6 準備機のトラブル

| 表示・症状 | 意味と対処 |
|---|---|
| `non-empty Destination is forbidden` | 出力先に内容がある。削除せず、新しい空の出力先を選ぶ |
| `required command is unavailable` | 表示された macOS 標準コマンドがない。OS の状態を修復してから再実行 |
| Python の SHA-256 / metadata エラー | 取得物が固定契約と一致しない。再試行で直らなければスクリプト更新が必要。検証を回避しない |
| `an unusable /Applications/Ollama.app already exists` | 既存 Ollama が壊れているか CLI を実行できない。手動で調査し、勝手に上書きしない |
| `Ollama validation port 11435 is already in use` | そのportを使うprocessを確認して終了する。既存serverを検証済みとして再利用しない |
| `dedicated ollama serve ...` | 直前に表示される専用server log末尾を確認し、port、権限、cache、空き容量を調査する |
| `ollama pull failed` | ネットワーク、空き容量、Ollama のログを確認して準備機で再実行 |
| `verify_endpoint.py --require-agent rejected` / `[ WARN ]` | Chat / Agent 契約を満たしていない。そのキットは使用しない |
| model manifest / blob の不足 | `OLLAMA_MODELS` または既定 `~/.ollama/models` が不完全。`ollama list` と `ollama pull qwen3:8b` を確認 |

### 2.7 任意: Foundry Local も含める場合

通常ルートには不要です。この分岐を選ぶ場合は、§2.3 の通常コマンドの**代わりに**この節のコマンドを実行します。作成済みキットへ後から追加することはできません。Foundry Local を含めても、生成される VS Code 設定と Agent 検証は Ollama を使います。この任意分岐が自動化するのは Foundry Local runtime と取得済み model cache の移送・導入までで、VS Code 接続設定は生成しません。本プロジェクトの限定的な実測では Foundry Local の OpenAI 互換経路が構造化 `tool_calls` を返さなかったため、**BYOK Agent 用とは扱いません。**

Foundry Local CLI は Public Preview です。Apple Silicon への導入、モデルの事前ダウンロード、キャッシュ場所の確認は Microsoft 公式の [Foundry Local CLI reference](https://learn.microsoft.com/azure/foundry-local/reference/reference-cli) と [Use the Foundry Local CLI](https://learn.microsoft.com/azure/foundry-local/how-to/how-to-use-foundry-local-cli) を参照してください。

1. 公式ページの [Foundry Local CLI release assets](https://aka.ms/foundry-local-installer) を開く。
2. 利用者が採用する **macOS arm64 の `.pkg` または `.zip`** を選ぶ。
3. リダイレクト後の `microsoft/Foundry-Local` GitHub Release の **直接 URL** を控える。
4. Foundry CLI をオンライン準備機に導入し、利用者が選んだモデルをダウンロードする。

モデル名を本書から決め打ちしません。公式 CLI で候補を確認し、採用する alias または model ID を利用者が入力します。

```bash
foundry --version
foundry model list
printf '採用する Foundry model alias または model ID: '
IFS= read -r FOUNDRY_MODEL
foundry model download "$FOUNDRY_MODEL"
foundry cache list
foundry cache location
```

次に、公式 Release の直接 URL と、`foundry cache location` で確認した非空のモデルキャッシュディレクトリを入力します。`https://aka.ms/foundry-local-installer` 自体ではなく、その先の直接 Release asset URL が必要です。

```bash
printf 'Foundry Local の公式 GitHub Release asset 直接 URL: '
IFS= read -r FOUNDRY_RELEASE_URL
printf 'ダウンロード済み Foundry model cache の絶対パス: '
IFS= read -r FOUNDRY_MODEL_SOURCE

test -n "$FOUNDRY_RELEASE_URL"
test -d "$FOUNDRY_MODEL_SOURCE"
find "$FOUNDRY_MODEL_SOURCE" -type f -print -quit
```

§2.3 と同じく、未作成または空の `KIT_DIR="$HOME/offline-kit-qwen3-8b"` を使います。§2.3 を既に実行した場合は、既存キットを変更せず別の新しい出力先を選んでください。

```bash
./Prepare-macOS.sh \
  --destination "$KIT_DIR" \
  --model qwen3:8b \
  --context-length 8192 \
  --include-foundry-local \
  --foundry-local-url "$FOUNDRY_RELEASE_URL" \
  --foundry-model-source "$FOUNDRY_MODEL_SOURCE"
```

**引数の固定契約**

- `--include-foundry-local` を付けた場合、残り 2 引数は両方必須です。
- `--foundry-local-url` は `https://github.com/microsoft/Foundry-Local/releases/download/` 配下の `.pkg` または `.zip` 直接 URL だけを受け付けます。query、fragment、資格情報を含む URL は拒否します。
- `--foundry-model-source` は、利用者が事前取得した非空の実ディレクトリです。シンボリックリンクを含むディレクトリは拒否します。
- URL、release tag、asset 名、model source を本書の架空値で補いません。

Foundry CLI を `.pkg` で準備機へ導入する際は macOS の管理者認証が発生し得ます。これは Foundry 公式インストーラーの操作であり、`Prepare-macOS.sh` 自身による Foundry の準備機インストールではありません。

## 3. 媒体で運ぶ

キット内に 1 ファイルでも追加すると、運用機の installer は「manifest 未記載ファイル」として停止します。Finder のメタデータ混入や誤編集を避けるため、キットを 1 個の zip にして運びます。

### 3.1 準備機でアーカイブする

同名アーカイブが既にある場合は上書きせず、別名を選んでください。

```bash
KIT_ARCHIVE="$HOME/offline-kit-qwen3-8b.zip"
test ! -e "$KIT_ARCHIVE" || {
  printf '既存アーカイブがあります。別名を選んでください: %s\n' "$KIT_ARCHIVE" >&2
  exit 1
}

ditto -c -k --keepParent "$KIT_DIR" "$KIT_ARCHIVE"
(
  cd "$(dirname "$KIT_ARCHIVE")"
  shasum -a 256 "$(basename "$KIT_ARCHIVE")" > "$(basename "$KIT_ARCHIVE").sha256"
)
ls -lh "$KIT_ARCHIVE" "$KIT_ARCHIVE.sha256"
cat "$KIT_ARCHIVE.sha256"
```

**期待結果**

- zip と `.sha256` の 2 ファイルが作られる。
- `.sha256` には 64 桁の SHA-256 と zip のファイル名が表示される。

### 3.2 媒体へコピーして確認する

媒体を接続し、マウント先を確認します。入力するのは `/Volumes` 配下に実在する媒体ルートです。

```bash
ls -la /Volumes
printf '媒体のマウント先を入力: '
IFS= read -r MEDIA_ROOT
test -d "$MEDIA_ROOT"

ditto "$KIT_ARCHIVE" "$MEDIA_ROOT/$(basename "$KIT_ARCHIVE")"
ditto "$KIT_ARCHIVE.sha256" "$MEDIA_ROOT/$(basename "$KIT_ARCHIVE.sha256")"
(
  cd "$MEDIA_ROOT"
  shasum -a 256 -c "$(basename "$KIT_ARCHIVE.sha256")"
)
sync
```

**期待結果**

- `offline-kit-qwen3-8b.zip: OK` と表示される。
- `sync` が終了した後に Finder から媒体を取り出せる。

**トラブル**

- `FAILED` の場合は媒体上の 2 ファイルを使用せず、媒体や接続を確認して最初からコピーし直します。
- SHA-256 ファイルは偶発的なコピー破損の確認用です。キットの `manifest.json` に署名はないため、zip と checksum と manifest を同時に置換する攻撃への真正性は保証しません。媒体と移送経路を信頼できる管理下に置いてください。

## 4. オフライン運用機で dry-run と導入を行う

### 4.1 OS / CPU を再確認する

```bash
sw_vers -productVersion
uname -m
```

**期待結果**は準備機と同じく macOS 14 以降、`arm64` です。Intel Mac、古い macOS、異なる platform の manifest は installer が拒否します。

### 4.2 媒体を検証して、新しいディレクトリへ展開する

本書どおりのアーカイブ名を使った例です。媒体ルートは実在値を入力します。

```bash
ls -la /Volumes
printf '媒体のマウント先を入力: '
IFS= read -r MEDIA_ROOT
test -d "$MEDIA_ROOT"

(
  cd "$MEDIA_ROOT"
  shasum -a 256 -c offline-kit-qwen3-8b.zip.sha256
)

IMPORT_ROOT="$HOME/offline-kit-import"
test ! -e "$IMPORT_ROOT" || {
  printf '展開先が既にあります。別の新しい展開先を選んでください: %s\n' "$IMPORT_ROOT" >&2
  exit 1
}
mkdir "$IMPORT_ROOT"
ditto -x -k "$MEDIA_ROOT/offline-kit-qwen3-8b.zip" "$IMPORT_ROOT"
cd "$IMPORT_ROOT/offline-kit-qwen3-8b"
chmod 0755 install-macos.sh
pwd
```

**期待結果**

- checksum が `OK`。
- `pwd` が新しい展開先の `offline-kit-qwen3-8b` を示す。
- 直下に `manifest.json` と `install-macos.sh` がある。

**トラブル**

- 展開先を Finder で編集したり、メモファイルをキット内へ追加したりしないでください。
- 後続で `extra unlisted file detected` が出た場合は、追加ファイルだけを消して続行せず、信頼済み zip を新しい空ディレクトリへ再展開します。

### 4.3 dry-run を実行する

引数なしが dry-run です。`--source` を省略すると、`install-macos.sh` が置かれているキットルートを使います。
既存のOllamaがある場合は、メニューバーのOllamaから **Quit Ollama** を選び、完全終了してから実行します。`127.0.0.1:11434` の既存listenerは、別daemonへの偽検証を防ぐためdry-runでも拒否されます。

```bash
./install-macos.sh
```

同じキットルートを `--source` で明示する形式は次です。

```bash
./install-macos.sh --source "$PWD"
```

**期待結果**

- `Verified offline kit:`
- `model: qwen3:8b (` で始まるモデルと実 digest
- `contextLength: 8192`
- Python、VS Code、Ollama、モデルキャッシュ、3 設定、`launchctl` の各 `[PLAN]`
- 最後に `DRY-RUN complete: no installation, copy, environment change, or application launch was performed.`

この段階ではインストール、コピー、環境変数変更、アプリ起動を行わず、`sudo` も実行しません。manifest の全ファイル、byte 数、SHA-256、余分なファイル、OS / CPU、既存版、既存設定を先に検査します。

### 4.4 既存設定・版の競合を確認する

同一版・同一内容は `skip` できますが、異なる既存物は **自動上書きせず停止**します。

| 対象 | 同一なら | 異なる場合 |
|---|---|---|
| Python | キット版と完全一致なら `skip` | `existing Python ... conflicts` で停止 |
| `/Applications/Visual Studio Code.app` | bundle 版一致なら `skip` | 版競合で停止 |
| `/Applications/Ollama.app` | bundle 版一致なら `skip` | 版競合で停止 |
| `~/.ollama/models` | manifest 対象とファイル・SHA-256 が完全一致なら `skip` | モデルキャッシュ競合で停止 |
| VS Code `chatLanguageModels.json` / `settings.json` | byte 単位で同一なら `skip` | 手動マージが必要として停止 |
| `~/.ollama/server.json` | byte 単位で同一なら `skip` | 手動マージが必要として停止 |
| `OLLAMA_CONTEXT_LENGTH` | 未設定なら `set`、`8192` なら `skip` | shell または `launchctl` の値が異なれば停止 |
| 任意 Foundry runtime / cache | 版・内容一致なら `skip` | 競合で停止 |

macOS に別版 Python が既にあると、システム用途か利用者用途かを installer は判断できないため停止します。既存物を削除する自動処理はありません。必要なデータをバックアップし、所有者と用途を確認してから手動で統合方針を決めてください。競合を無理に回避するより、OS 導入直後の専用機・専用ユーザーで実行する方が安全です。

### 4.5 `--apply` で導入する

dry-run の全 `[PLAN]` を確認した後だけ実行します。

```bash
./install-macos.sh --apply
```

`--apply` は次を行います。

1. 不足している Python `3.14.7`、VS Code、Ollama を検証済み資材から導入する。
2. `qwen3:8b` の選択済み manifest / blob を `~/.ollama/models` へ配置する。
3. VS Code の BYOK / offline 設定と Ollama local-only 設定を、宛先が未作成の場合だけ配置する。
4. `launchctl setenv OLLAMA_CONTEXT_LENGTH 8192` を設定する。
5. 任意選択時だけ Foundry Local runtime とモデルキャッシュを配置する。
6. 導入後の版とファイルを再検証する。
7. Ollama.app を起動し、loopback 応答を最大 60 回待つ。
8. `verify_endpoint.py --timeout 600 --require-agent --expected-context 8192` を実行する。

**成功時の期待結果**

- 5 種類（models、Chat、streaming、tool calling、実効 context）の endpoint 検証が `[  OK  ]`。
- `結果: すべて OK。Chat / Agent の両方で使えます。`
- 最後に `Installation and automated Agent endpoint verification completed successfully.`
- 続いて VS Code の手動確認を促す行が表示される。

### 4.6 運用機で `sudo` が使われる場所

`sudo` は `--apply` の不足コンポーネント導入時だけ使います。dry-run では使いません。

| 条件 | `sudo` の用途 |
|---|---|
| Python が未導入 | 公式 `.pkg` を `installer -target /` で導入 |
| VS Code が未導入 | 検証済み `.app` を `/Applications` へ `ditto` |
| Ollama が未導入 | 検証済み `.app` を `/Applications` へ `ditto` |
| 任意 Foundry が `.pkg` | `installer -target /` で導入 |
| 任意 Foundry が `.zip` | `/usr/local/libexec/foundrylocal` と `/usr/local/bin` の作成、コピー、実行権限、`foundry` symlink |

次には `sudo` を使いません。

- `~/.ollama/models` と `~/.foundry/cache/models` の配置
- `~/Library/Application Support/Code/User` の設定配置
- `~/.ollama/server.json` の配置
- `launchctl setenv`
- Ollama の起動と endpoint 検証

### 4.7 dry-run / Apply のトラブル

| 表示・症状 | 対処 |
|---|---|
| `SHA-256 mismatch` / `byte-count mismatch` | その媒体コピーを使わない。準備機の信頼済み zip から新しい展開先へコピーし直す |
| `extra unlisted file detected` | キットにファイルが混入。新しい空ディレクトリへ再展開する |
| `existing ... conflicts` | 自動上書き不可。既存版・設定・キャッシュをバックアップして手動判断する |
| `current OLLAMA_CONTEXT_LENGTH conflicts` | 現在の shell 環境を確認する。`launchctl getenv OLLAMA_CONTEXT_LENGTH` も確認し、別用途の設定を勝手に消さない |
| `Ollama endpoint port 11434 is already in use` | メニューバーからOllamaを終了する。他processが使用している場合は所有者と用途を確認し、停止後にdry-runからやり直す |
| `Ollama loopback endpoint did not become ready` | `~/.ollama/logs/server.log` と `~/.ollama/logs/app.log` を確認する。公式の保存場所は [Ollama macOS troubleshooting](https://docs.ollama.com/macos#troubleshooting) に記載 |
| endpoint 検証がタイムアウト | 他の推論を止め、Ollama が空いてから再実行。タイムアウト結果でモデル適合性を判断しない |
| `[ WARN ]` または tool arguments 不一致 | Agent 用として失敗。警告を成功扱いしない |
| Foundry の `Request to local service failed` | `foundry server status`、`foundry server restart` を実行。公式 CLI リファレンスを確認 |

## 5. 導入後に CLI を確認する

PATH や symlink の状態に依存しないよう、最初はアプリ内の実体を直接実行します。

```bash
if [ -x /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 ]; then
  PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
else
  PYTHON_BIN="$(command -v python3)"
fi
"$PYTHON_BIN" --version
"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" --version
"/Applications/Ollama.app/Contents/Resources/ollama" --version
"/Applications/Ollama.app/Contents/Resources/ollama" list
launchctl getenv OLLAMA_CONTEXT_LENGTH
```

**期待結果**

- Python は `3.14.7`。
- VS Code と Ollama は dry-run / manifest に記録された実版と一致する。
- `ollama list` に `qwen3:8b` がある。
- `launchctl getenv` は `8192`。

モデルをロードした後は、実効コンテキストも確認できます。

```bash
"/Applications/Ollama.app/Contents/Resources/ollama" ps
```

`CONTEXT` 列が `8192` であることを確認します。違う場合は Ollama を終了して再起動し、`launchctl getenv OLLAMA_CONTEXT_LENGTH` を再確認してください。

VS Code の `code` コマンドを通常の PATH で使いたい場合は、VS Code を起動して Command Palette から `Shell Command: Install 'code' command in PATH` を実行し、Terminal を開き直します。これは VS Code 公式の [Launch VS Code from the command line](https://code.visualstudio.com/docs/setup/mac#_launch-vs-code-from-the-command-line) の手順です。

endpoint 検証を明示的に再実行します。

```bash
"$PYTHON_BIN" \
  tools/verify_endpoint.py \
  --url http://127.0.0.1:11434 \
  --model qwen3:8b \
  --timeout 600 \
  --require-agent \
  --expected-context 8192
```

**期待結果**

1. モデル一覧が `[  OK  ]`
2. チャット補完が `[  OK  ]`
3. streaming が `[  OK  ]`
4. tool calling と `city="Tokyo"` の引数が `[  OK  ]`
5. `/api/ps` の実効 context が `8192` で `[  OK  ]`
6. 最後が `結果: すべて OK。Chat / Agent の両方で使えます。`

任意 Foundry を含めた場合は、利用者が選択したモデルがキャッシュにあることだけを別に確認します。モデル名は実値を使ってください。

```bash
foundry --version
foundry cache list
foundry server status
```

## 6. VS Code の Chat / Agent を手動確認する

この節は実機で人が行う最終 E2E です。本タスクでは実行していません。

### 6.1 読み取り専用の確認用 workspace を作る

```bash
TEST_WORKSPACE="$HOME/offline-vscode-agent-test"
mkdir -p "$TEST_WORKSPACE"
printf 'hello from offline macOS\n' > "$TEST_WORKSPACE/hello.txt"
open -a "Visual Studio Code" "$TEST_WORKSPACE"
```

初回に Workspace Trust が表示されたら、この自分で作成したフォルダーだけを信頼します。Restricted Mode ではモデルピッカーが `Auto` だけになることがあります。

### 6.2 モデルを選ぶ

1. VS Code の Chat ビューを開く。
2. 入力欄のモデルピッカーを開く。
3. `Ollama (local)` グループの `qwen3:8b (Ollama)` を選ぶ。
4. 見つからない場合はモデルピッカーの歯車から `Manage Language Models` を開く。

キットは次の設定を既に配置しています。

- `~/Library/Application Support/Code/User/chatLanguageModels.json`
- `~/Library/Application Support/Code/User/settings.json`
- endpoint: `http://127.0.0.1:11434/v1/chat/completions`
- `vendor`: `customendpoint`
- `toolCalling`: `true`
- `apiKey`: ローカル endpoint 用の非秘密ダミー値

Custom Endpoint の設定項目と、Agent に表示するには tool calling が必要であることは VS Code 公式の [Add a custom endpoint model](https://code.visualstudio.com/docs/agent-customization/language-models#_add-a-custom-endpoint-model) に記載されています。

### 6.3 Chat を確認する

Chat モードで次を入力します。

```text
日本語で「Chat OK」とだけ答えてください。
```

**期待結果**

- ネットワーク接続なしで応答が返る。
- VS Code の応答に選択モデルとして `qwen3:8b` が使われる。

小型モデルは指示に完全追従しない場合があります。文字列が完全一致しなくても、ローカル応答自体が返るかを先に確認し、意味品質は別途評価してください。

### 6.4 Agent を確認する

Chat のモードを Agent に切り替え、次を入力します。

```text
ワークスペースの hello.txt を読み取り専用で確認し、内容を1行で答えてください。ファイルは変更しないでください。
```

**期待結果**

- Agent がファイル読み取り用 tool を呼び出す。承認 UI が出た場合は内容を確認して承認する。
- 応答に `hello from offline macOS` が含まれる。
- `hello.txt` の内容が変更されない。

ここで確認する Agent は Chat ビュー内の Agent モードです。別の **Agents window / Agent Host** で BYOK を使う場合は、VS Code 公式記載どおり実験的設定 `chat.agentHost.byokModels.enabled` を有効にして Agent Host を再起動する必要があります。この設定は生成済み `settings.json` には含まれません。

### 6.5 VS Code のトラブル

| 症状 | 確認 |
|---|---|
| モデルピッカーが `Auto` だけ | workspace が Restricted Mode でないか確認する |
| `qwen3:8b (Ollama)` がない | VS Code を再起動し、`chatLanguageModels.json` の存在と JSON を確認する |
| Chat が接続エラー | `curl --noproxy '*' http://127.0.0.1:11434/api/tags` と Ollama ログを確認する |
| Agent モードにモデルが出ない | `verify_endpoint.py --require-agent` が無警告で成功するか、`toolCalling: true` か確認する |
| Agent が tool を呼ばない / 引数を誤る | endpoint 検証を再実行する。`[ WARN ]` を成功扱いしない |
| title や commit message 生成がサインインを求める | `chat.utilityModel`、`chat.utilitySmallModel`、`chat.byokUtilityModelDefault` が生成済み設定と一致するか確認する |
| Tab 補完が出ない | 正常な制約。BYOK ローカルモデルはインライン補完を提供しない |

## 7. 完了条件と検証範囲

次のすべてを満たしたら、この手順の導入確認は完了です。

- [ ] 準備機と運用機が macOS 14+ / `arm64`
- [ ] キット生成時に `qwen3:8b` / `8192` / Agent endpoint 検証が成功
- [ ] 媒体上の zip SHA-256 が一致
- [ ] 運用機 dry-run が変更なしで完了
- [ ] `--apply` と自動 endpoint 検証が成功
- [ ] Python、VS Code、Ollama、モデル、コンテキスト長を確認
- [ ] VS Code Chat のローカル応答を人手確認
- [ ] VS Code Agent の読み取り tool call を人手確認
- [ ] インライン補完、セマンティック検索、埋め込み機能を完了条件に含めていない

**本書作成時点の未検証事項**

- macOS 実機での `Prepare-macOS.sh` 通し実行
- 物理媒体を介した別 Mac への移送
- クリーンな macOS での `install-macos.sh --apply`
- VS Code のモデルピッカー、Chat、Agent の実往復
- 任意 Foundry Local の `.pkg` / `.zip` と利用者指定モデルキャッシュの通し導入

したがって、本書は実装契約に基づく導入ガイドであり、実機 E2E 成功の実績を表明するものではありません。

## 8. 実装と公式資料

公式リンクは各手順の記述近傍にも示しています。まとめて確認する場合は次を参照してください。

| 目的 | 参照先 |
|---|---|
| macOS 準備処理の正確な引数・動作 | [`tools/airgap-kit/Prepare-macOS.sh`](tools/airgap-kit/Prepare-macOS.sh) |
| macOS dry-run / Apply / 競合停止 | [`tools/airgap-kit/install-macos.sh`](tools/airgap-kit/install-macos.sh) |
| 固定契約 | [`tools/airgap-kit/CONTRACT.md`](tools/airgap-kit/CONTRACT.md) |
| Agent endpoint 判定 | [`tools/verify_endpoint.py`](tools/verify_endpoint.py) |
| VS Code macOS | <https://code.visualstudio.com/docs/setup/mac> |
| VS Code BYOK / Custom Endpoint / 非対応機能 | <https://code.visualstudio.com/docs/agent-customization/language-models> |
| Python macOS Universal 2 `.pkg` | <https://docs.python.org/3/using/mac.html> |
| Ollama macOS | <https://docs.ollama.com/macos> |
| Ollama context / local-only / cache / 環境変数 | <https://docs.ollama.com/faq> |
| Foundry Local CLI reference | <https://learn.microsoft.com/azure/foundry-local/reference/reference-cli> |
| Foundry Local CLI how-to | <https://learn.microsoft.com/azure/foundry-local/how-to/how-to-use-foundry-local-cli> |

公式資料確認日: 2026-08-16
