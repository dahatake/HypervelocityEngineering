# Windows 11 x64 オフライン導入ガイド

Windows 11 x64 のオンライン準備機で移送キットを作り、媒体でオフライン運用機へ運び、VS Code の Chat / Agent をローカル LLM で使えるところまでを説明する。
対象読者は、このリポジトリで初めて作業するソフトウェアエンジニアである。

> **検証範囲**
> 2026-08-16 に Windows 11 x64 のオンライン準備機で、実ダウンロード、`qwen3:8b` / context `8192` のAgent endpoint検証、自己完結キット生成まで完走した。
> クリーンな別のオフライン運用機への媒体移送、dry-run、Apply、VS Code のモデルピッカー / Chat / Agent の実操作は行っていない。
> コマンド、ファイル名、引数、停止条件は `tools/airgap-kit/Prepare-Windows.cmd`、`tools/airgap-kit/install-windows.cmd`、`Export-OfflineKit.ps1`、`Import-OfflineKit.ps1` と契約テストから確認した。
> 詳細は [VALIDATION.md](VALIDATION.md) を参照し、まず検証用端末で最後まで確認してから業務端末へ展開すること。

## できること・できないこと

| 機能 | この手順での扱い |
|---|---|
| VS Code Chat | `qwen3:8b` を Ollama の Custom Endpoint として使用する |
| VS Code Agent | Ollama の構造化 tool calling を導入前後に必須検証して使用する |
| インライン補完（ghost text / Tab 補完） | **使用不可** |
| セマンティック検索、埋め込み依存機能 | **使用不可** |
| Foundry Local | 任意。本 Windows キットには含まれず、採用しても **Chat 専用**とし Agent の合格経路には使わない |

VS Code の BYOK は、GitHub アカウントや Copilot プランなしでもローカルモデルをオフラインの Chat で利用できる。一方、インライン補完、セマンティック検索、埋め込み依存機能は BYOK の対象外である（[VS Code 公式: AI language models in VS Code](https://code.visualstudio.com/docs/agent-customization/language-models)）。
Foundry Local は別途導入できるローカル推論ランタイムだが、このリポジトリで確認した BYOK 経路では構造化 `tool_calls` を返さないため、本手順では Chat 専用とする（[ローカル検証結果](TUTORIAL.md#2-モデルを選ぶ)、[Microsoft 公式: Foundry Local とは](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local)）。

## 全体の流れ

1. オンラインの Windows 11 x64 準備機で `Prepare-Windows.cmd` を実行する。
2. 生成されたキットを、ディレクトリ構造を変えずに承認済み媒体へコピーする。
3. オフラインの Windows 11 x64 運用機に `pwsh.exe` がなければ、`install-windows.cmd -BootstrapPowerShell` を明示実行する。同梱 MSI の一意検出と対話導入後、自動的に dry-run まで進む。
4. `install-windows.cmd` を引数なしで実行し、dry-run を通す。
5. `install-windows.cmd -Apply` を実行する。
6. コマンド、VS Code のモデルピッカー、Chat、Agent の順で確認する。

## 1. 前提を確認する

### 対象と権限

- 本線は、Windows Update と組織標準設定を終えた **OS セットアップ直後のオンライン準備機**を前提とする。
- 準備機と運用機は **Windows 11 x64**。Windows ARM64、Windows 10、WSL、Docker はこのキットの保証対象外である。
- 準備機にはインターネット接続と `winget.exe`（App Installer）が必要である。
- 初めから「管理者として実行」でコマンドプロンプトを開く必要はない。PowerShell 7 x64 MSI が必要な場面では UAC が表示されるため、組織で承認された管理者資格情報を使う。
- Python Install Manager、VS Code User Setup、Ollama はユーザー単位で導入される。組織ポリシーで MSIX やユーザーインストールが禁止されている場合は回避せず、管理者へ依頼する。
- GPU は任意であり、CPU でも実行できる。対応 GPU があれば高速化されるが、必要な RAM / VRAM はモデルとコンテキスト長に依存する（[Ollama 公式: Windows](https://docs.ollama.com/windows)）。

PowerShell 7 の Windows 向け WinGet / MSI 手順は [Microsoft 公式: Windows への PowerShell のインストール](https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows)、VS Code User Setup の権限と配置先は [VS Code 公式: Installing Visual Studio Code on Windows](https://code.visualstudio.com/docs/setup/windows) を参照する。

準備機の通常のコマンドプロンプトで確認する。

```batch
ver
echo %PROCESSOR_ARCHITECTURE%
where winget.exe
```

期待結果:

- Windows 11 である。
- `%PROCESSOR_ARCHITECTURE%` が `AMD64` である。
- `winget.exe` のパスが表示される。

失敗時:

- Windows 11 x64 でなければ、この手順を続行しない。
- `winget.exe` が見つからなければ、オンラインのまま Windows Update と App Installer を整備してから再確認する。

### 既定モデルと必要容量

引数を省略した既定値は次のとおりである。

| 項目 | 既定値 |
|---|---|
| Ollama モデル | `qwen3:8b` |
| コンテキスト長 | `8192` tokens |
| エンドポイント | `http://127.0.0.1:11434/v1/chat/completions` |

`8192` は `OLLAMA_CONTEXT_LENGTH` と VS Code の入力・出力 token 合計へ反映される。Ollama は環境変数でコンテキスト長を変更できる（[Ollama 公式 FAQ: context window size](https://docs.ollama.com/faq#how-can-i-specify-the-context-window-size)）。

必要容量を固定値で見積もってはいけない。少なくとも次を実測して確保する。

- 準備機: 選択モデルの Ollama cache と、生成キット全体の両方。
- 移送媒体: 生成キット全体。
- 運用機: キットの一時配置、各 installer / Python runtime の導入先、Ollama model cache。

`Prepare-Windows.cmd` 完了後に、`ollama list` の `SIZE` と `dir /a /s` の総 byte 数を確認する。

```batch
ollama list
dir /a /s "C:\OfflineKitBuild\qwen3-8b-8192"
```

容量不足時はモデルやキットを途中まで作らず、十分な空き容量がある別ドライブを出力先に選び直す。

## 2. オンライン準備機でキットを作る

### 実在する引数

`Prepare-Windows.cmd` が受け付ける引数は次だけである。

| 引数 | 必須 | 内容 |
|---|---|---|
| `--destination PATH` | 必須 | 存在しないか、隠し項目を含めて空の出力先 |
| `--model NAME` | 任意 | 既定 `qwen3:8b` |
| `--context-length TOKENS` | 任意 | 2 以上の 10 進整数。既定 `8192` |
| `--help` / `-h` | 任意 | 使用方法を表示 |

Windows 版には Foundry Local を含める引数はない。`--include-foundry-local` など、実装にない引数を追加しないこと。

### 実行する

通常のコマンドプロンプトを開き、リポジトリ内の実装ディレクトリへ移動する。

```batch
cd /d C:\GitHub\RoyalytyService2ndGen\local-llm-dev\tools\airgap-kit
Prepare-Windows.cmd --help
Prepare-Windows.cmd --destination "C:\OfflineKitBuild\qwen3-8b-8192"
```

明示的に既定値を書く場合も、構文は次のとおりである。

```batch
Prepare-Windows.cmd --destination "C:\OfflineKitBuild\qwen3-8b-8192" --model qwen3:8b --context-length 8192
```

スクリプトは次の順で処理する。

1. `winget.exe` を確認する。
2. PowerShell 7 x64 MSI、Python Install Manager、準備機用 Python `3.14-64`、Ollama を必要に応じて導入する。
3. Ollama を loopback で起動し、`qwen3:8b` を pull する。
4. Export専用の `127.0.0.1:11435` Ollama serverを `OLLAMA_CONTEXT_LENGTH=8192` で起動する。portが使用中なら停止し、既存serverは再利用しない。
5. 専用serverへ `verify_endpoint.py --require-agent --expected-context 8192` を実行し、models / Chat / streaming / tool calling、引数、実効 context を検証してからserverを停止する。
6. PowerShell、Python offline index、VS Code User Setup、Ollama installer、対象モデル、固定設定を収集する。
7. 全 payload の byte 数と SHA-256 を持つ `manifest.json` を最後に生成する。

Python はオンライン側で `pymanager install --download=<PATH> 3.14-64` により offline index を作り、運用機で `pymanager install --source=<PATH>\index.json 3.14-64` により導入する。`pymanager` は旧 `py.exe` launcher と衝突しない明示コマンドである（[Python 公式: Offline installs](https://docs.python.org/3/using/windows.html#offline-installs)）。

期待結果:

- 最後に `Windows 11 x64 オフラインキットを作成しました` と表示される。
- `Destination`、`Model`、`Context`、`Files` が表示される。
- コマンドの終了コードが `0` である。

失敗時:

| 症状 | 対処 |
|---|---|
| `--destination PATH is required` | `--destination` と空の出力先を指定する |
| `Destination は空でなければなりません` | 既存ファイルを消さず、新しい空の出力先を使う |
| `winget.exe is required` | Windows Update / App Installer をオンラインで整備する |
| UAC または installer が拒否された | 組織の管理者へ承認を依頼し、承認後に最初から再実行する |
| Ollama loopback が準備完了にならない | `%TEMP%\local-llm-dev-ollama-serve.log` を確認し、Ollama を終了・再起動してから再試行する |
| `Ollama 検証用 port 11435 が使用中` | そのportを使うprocessを確認して終了する。別serverを検証済みとして再利用しない |
| `専用 Ollama server` の起動失敗 | 表示されたstdout / stderr末尾を確認する。検証ログは画面へ表示された後、一時ファイルから削除される |
| model pull が失敗する | ネットワーク、proxy、空き容量を確認し、`ollama pull qwen3:8b` が成功してから再試行する |
| `verify_endpoint.py --require-agent` が失敗する | 他の推論要求を止めて再試行する。tool calling が不合格ならそのモデルで Agent 用キットを作らない |

途中失敗した出力先は完成キットではない。媒体へ移さず、内容を確認してから失敗した出力先を手動で片付けるか、別の新しい空ディレクトリで再実行する。

### 生成物を確認する

```batch
dir /a "C:\OfflineKitBuild\qwen3-8b-8192"
dir /a /s "C:\OfflineKitBuild\qwen3-8b-8192"
pwsh.exe -NoLogo -NoProfile -Command "$m=Get-Content -Raw 'C:\OfflineKitBuild\qwen3-8b-8192\manifest.json'|ConvertFrom-Json; $m.model; 'contextLength=' + $m.contextLength"
```

期待結果:

- ルートに `manifest.json`、`install-windows.cmd`、`Import-OfflineKit.ps1` がある。
- `runtime`、`models`、`config`、`tools`、`docs` がある。
- manifest の model name が `qwen3:8b`、`supportsToolCalling` が `True`、`contextLength` が `8192` である。
- `dir /a /s` の総 byte 数が移送媒体と運用機の必要容量を判断する実測値になる。

欠落や想定外の値があれば、ファイルや manifest を手編集しない。新しい空の出力先へキットを作り直す。

## 3. 媒体で移送する

以下では、承認済み媒体を `E:` とする。実際のドライブ文字へ読み替える。媒体側の `E:\offline-kit` は、存在しないか空でなければならない。

準備機でコピーする。

```batch
robocopy "C:\OfflineKitBuild\qwen3-8b-8192" "E:\offline-kit" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1
```

期待結果:

- `robocopy` の集計で `FAILED` が `0` になる。
- 終了コード `0` から `7` はコピー完了を表し、`8` 以上は失敗を表す。
- 媒体を OS の取り外し操作で安全に取り外せる。

失敗時:

- `FAILED` が 0 でない、または終了コードが 8 以上なら移送を中止し、媒体の空き容量、書込み権限、媒体エラーを確認する。
- キット内へメモ、ウイルススキャン結果、`desktop.ini` などを追加しない。Import は manifest 未記載ファイルも拒否する。
- SHA-256 は manifest と payload の不一致を検出するが、manifest 自体の署名ではない。準備機から運用機まで承認済み媒体と管理手順で保護する。

運用機では、媒体からローカルディスクの新しい空ディレクトリへコピーする。

```batch
robocopy "E:\offline-kit" "C:\OfflineKit" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1
cd /d C:\OfflineKit
dir /a
```

期待結果:

- `FAILED` が `0` になる。
- `manifest.json`、`install-windows.cmd`、`Import-OfflineKit.ps1` が表示される。

コピー失敗または欠落時は、個別ファイルを補修せず、運用機側の不完全なコピーを退避または削除してディレクトリ全体をコピーし直す。

## 4. オフライン運用機へ導入する

### 4.1 `pwsh.exe` がなければ明示的に bootstrap する

`install-windows.cmd` は、まず `where pwsh.exe`、次に `%ProgramFiles%\PowerShell\7\pwsh.exe` で PowerShell 7 を検索する。運用機に `pwsh.exe` があるか、通常のコマンドプロンプトで確認する。

```batch
cd /d C:\OfflineKit
where pwsh.exe
```

パスが表示された場合は bootstrap せず、[4.2](#42-dry-run-を必ず先に通す)へ進む。表示されない場合だけ、次を明示実行する。

```batch
install-windows.cmd -BootstrapPowerShell
```

このコマンドは次の順で処理する。

1. `runtime\powershell` 配下から `.msi` を再帰検索し、manifestで検証済みの該当ファイルが 1 件だけであることを確認する。
2. 一意に特定した同梱 MSI を対話モードで起動し、終了まで待つ。
3. UAC が表示された場合は、組織で承認された管理者資格情報で導入を完了する。
4. `pwsh.exe` を再検索する。
5. 検出に成功すると、`Import-OfflineKit.ps1` を `-Apply` なしで呼び出し、自動的に dry-run まで実行する。

MSI を `dir` / `for` / `start` で手動起動しない。PowerShell 7 の bootstrap を許可するのは `-BootstrapPowerShell` と `-Apply` だけである。引数なしの `install-windows.cmd` は、`pwsh.exe` がなければ何も変更せず終了コード `2` で停止する。

期待結果:

- `Installing the verified PowerShell 7 x64 MSI from the offline kit...` と表示され、同梱 MSI の対話導入が開始する。
- 導入後は dry-run の `[予定]` 行と `dry-run 完了（書込み・外部プロセス実行なし）` が表示される。
- 終了コードが `0` である。

bootstrap 経路の失敗コード:

| 終了コード | 条件 | 対処 |
|---:|---|---|
| `2` | `pwsh.exe` がなく、引数なしで実行したため、明示 bootstrap が必要 | 変更は行われていない。`install-windows.cmd -BootstrapPowerShell` を実行する |
| `3` | 同梱の `runtime\powershell` 配下の `.msi` が 0 件または複数件で、一意に特定できない | キットを編集せず、承認済み元媒体から全体を再コピーする。元キットも同じなら準備機で作り直す |
| `4` | MSI 導入後も `pwsh.exe` を `where` または `%ProgramFiles%\PowerShell\7\pwsh.exe` で発見できない | 権限を迂回せず、MSI の導入結果と組織ポリシーを管理者と確認する |

MSI が非ゼロで終了した場合は、その終了コードをそのまま返して停止する。警告として無視せず、installer 画面、UAC、組織ポリシー、空き容量を確認する。

`-Apply` も `pwsh.exe` がない場合の bootstrap を許可するが、導入後すぐ Apply へ進み、独立した通常 dry-run を先行できない。したがって初回導入には推奨しない。推奨順は `-BootstrapPowerShell`、引数なしの通常 dry-run、`-Apply` である。

### 4.2 dry-run を必ず先に通す

PowerShell 7 が既にあった場合も、4.1 の bootstrap と自動 dry-run が成功した場合も、Apply 前の独立した確認ゲートとして引数なしの通常 dry-run を実行する。
既存のOllamaがある場合は、dry-runの前からタスクトレイの **Quit Ollama** で完全終了する。実行中processを再利用すると、キットのcontextとlocal-only設定を確実に反映した検証にならないため、dry-runもfail-closedで停止する。

```batch
cd /d C:\OfflineKit
install-windows.cmd
```

引数なしが dry-run である。manifest schema、Windows 11 x64、全 listed file の欠落 / 余分 / byte 数 / SHA-256、導入先、既存設定、既存版を検証し、インストーラーや製品コマンドを実行せず予定だけを表示する。

期待結果:

- `[予定]` 行に導入またはスキップ予定が表示される。
- 最後に `dry-run 完了（書込み・外部プロセス実行なし）` と表示される。
- 終了コードが `0` である。

失敗時:

| 症状 | 対処 |
|---|---|
| manifest 欠落、extra file、byte / SHA-256 不一致 | キットを編集せず、承認済み元媒体から新しい空ディレクトリへ全体を再コピーする |
| Windows / x64 不一致 | 非対応端末なので停止する |
| VS Code / Ollama に異なる既存版がある | 自動更新・上書きはしない。専用の新規 Windows ユーザーを使うか、管理者承認の下で既存版を整理する |
| VS Code / Ollama 設定に異なる既存内容がある | 自動 merge はしない。下記の競合対応を行ってから dry-run をやり直す |
| `OLLAMA_MODELS` が既定 cache と異なる | 既存モデル配置を保護し、専用ユーザーを使うか環境変数を手動で整理する |
| `OLLAMA_CONTEXT_LENGTH` が `8192` 以外 | 既存用途への影響を確認し、専用ユーザーを使うか値を手動で整理する |
| `Ollama が実行中です` | タスクトレイから **Quit Ollama** を選び、processが終了してからdry-runをやり直す |

#### 既存設定の競合対応

Import は次のファイルを JSON merge せず、**不存在なら新規配置、同一内容ならスキップ、異なる内容なら停止**する。

- `%APPDATA%\Code\User\chatLanguageModels.json`
- `%APPDATA%\Code\User\settings.json`
- `%USERPROFILE%\.ollama\server.json`

最も安全なのは、専用の新規 Windows ユーザーで導入する方法である。既存ユーザーを使う必要がある場合は、競合ファイルを承認済みの場所へバックアップし、元の場所から退避して dry-run と Apply を通した後、キットが配置した値を失わないようキー単位で手動 merge する。キット側のファイルや `manifest.json` を編集すると完全性検証に失敗するため、編集してはならない。

手動 merge 後のファイルはキットと同一内容ではなくなるので、同じキットの再 Apply は競合停止する。再実行前に必ず設定を再調整する。

### 4.3 Apply する

VS Code を閉じる。既存の Ollama がある場合は、タスクトレイから **Quit Ollama** を選び、プロセスを終了してから実行する。

`pwsh.exe` がない状態で `-Apply` を実行すると bootstrap 後にそのまま Apply へ進めるが、dry-run 先行原則を満たさないため推奨しない。4.1 と 4.2 を順に完了してから実行する。

```batch
cd /d C:\OfflineKit
install-windows.cmd -Apply
```

`-Apply` は `install-windows.cmd` から `Import-OfflineKit.ps1 -Apply` へ渡される実在引数である。Apply は次を行う。

1. Python Install Manager と Python `3.14-64` を offline index から導入する。
2. 競合のない VS Code / Ollama 設定を配置する。
3. `qwen3:8b` の cache を SHA-256 再確認付きで配置する。
4. ユーザー環境変数 `OLLAMA_CONTEXT_LENGTH=8192` を設定する。
5. VS Code User Setup と OllamaSetup を必要に応じて対話実行する。
6. Ollama を `127.0.0.1:11434` で起動する。
7. 導入した Python で `verify_endpoint.py --require-agent --expected-context 8192` を実行する。

期待結果:

- 各 installer が終了コード `0` で終わる。
- endpoint 検証が `結果: すべて OK。Chat / Agent の両方で使えます。` になる。
- 最後に `Offline Kit の導入と Agent endpoint 検証が完了しました` と表示される。

失敗時:

- `Ollama が実行中です` ならタスクトレイから終了し、プロセスが消えてから Apply をやり直す。
- installer が非ゼロ終了なら、その installer の画面・組織ポリシー・空き容量を確認する。警告だけで継続しない。
- endpoint が timeout なら他の推論要求を止め、Ollama を再起動して手動検証する。
- Ollama の詳細は `%LOCALAPPDATA%\Ollama\server.log` を確認する（[Ollama 公式: Troubleshooting](https://docs.ollama.com/troubleshooting)）。
- 部分適用後は、まず `install-windows.cmd` の dry-run を再実行する。同一内容はスキップされるが、異なる内容は競合として停止する。

Ollama の `server.json` には `disable_ollama_cloud=true` が配置される。これは cloud 機能を無効化する公式設定であり、変更後は再起動が必要である（[Ollama 公式 FAQ: disable Ollama Cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)）。本手順の運用機はネットワーク自体を遮断し、Ollama の既定 loopback 公開を変更しない。

## 5. コマンドで導入結果を確認する

Apply 完了後、新しいコマンドプロンプトを開く。

```batch
pwsh.exe --version
pymanager exec -V:3.14-64 --version
code --version
ollama --version
ollama list
set OLLAMA_CONTEXT_LENGTH
```

期待結果:

- PowerShell、Python、VS Code、Ollama の版が表示される。
- `ollama list` に `qwen3:8b` がある。
- `OLLAMA_CONTEXT_LENGTH=8192` が表示される。

次に、キット同梱の厳格な endpoint 検証を再実行する。

```batch
cd /d C:\OfflineKit
pymanager exec -V:3.14-64 tools\verify_endpoint.py --url http://127.0.0.1:11434 --model qwen3:8b --require-agent --expected-context 8192
ollama ps
```

期待結果:

- models、Chat、streaming、tool calling、実効 context の 5 項目が `[  OK  ]` になる。
- `結果: すべて OK。Chat / Agent の両方で使えます。` と表示される。
- `ollama ps` の `CONTEXT` が `8192` になる。

失敗時:

- `pymanager` が見つからなければ `%LOCALAPPDATA%\Microsoft\WindowsApps` がユーザー PATH にあるか、Windows の「アプリ実行エイリアス」で Python Install Manager が有効か確認する（[Python 公式: Troubleshooting](https://docs.python.org/3/using/windows.html#troubleshooting)）。
- `code` が見つからなければコマンドプロンプトを開き直す。VS Code User Setup はユーザー PATH へ `code` を追加する（[VS Code 公式: Windows setup](https://code.visualstudio.com/docs/setup/windows)）。
- model が一覧にない場合は model cache を手作業で変更せず、Apply のエラーと manifest 検証からやり直す。
- tool calling が失敗または警告なら Agent 合格にしない。Chat だけの成功として扱わず、原因を解消する。
- `CONTEXT` が `8192` でなければ Ollama を完全終了し、新しいユーザー環境変数を読み込ませて再起動する。Windows での環境変数反映手順は [Ollama 公式 FAQ](https://docs.ollama.com/faq#setting-environment-variables-on-windows) を参照する。

## 6. VS Code のモデルピッカー、Chat、Agent を確認する

ここでいう Agent は **VS Code の Chat ビュー内で選ぶ Agent** である。別 UI の Agents window / Agent Host は、この一本道の確認対象に含めない。

### 6.1 安全な確認用フォルダーを開く

自分で作成した空フォルダーだけを使う。

```batch
mkdir C:\LocalLlmCheck
code C:\LocalLlmCheck
```

VS Code を Apply 後に初めて起動した場合、設定と環境変数を確実に読み込むため、一度すべての VS Code ウィンドウを閉じて再起動する。

Agent はファイル変更やコマンド実行を行えるため、内容を確認済みのフォルダーだけを信頼する。Restricted Mode では Agent が無効になり、モデルピッカーが `Auto` だけになる場合がある。コマンドパレットの `Workspaces: Manage Workspace Trust` で、この確認用フォルダーだけを Trust にする（[VS Code 公式: Workspace Trust](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust)）。

### 6.2 モデルピッカーを確認する

1. Chat ビューを開く。
2. Chat 入力欄のモデルピッカーを開く。
3. `Ollama (local)` グループの `qwen3:8b (Ollama)` を選ぶ。
4. 必要ならコマンドパレットから `Chat: Manage Language Models` を開き、Custom Endpoint を確認する。

キットは `%APPDATA%\Code\User\chatLanguageModels.json` に `vendor: customendpoint`、`apiType: chat-completions`、loopback URL、`toolCalling: true` を配置する。Marketplace の Ollama 拡張を追加導入する経路ではなく、VS Code 標準の Custom Endpoint 経路である（[VS Code 公式: Add a custom endpoint model](https://code.visualstudio.com/docs/agent-customization/language-models#_add-a-custom-endpoint-model)）。

期待結果:

- モデルピッカーに `qwen3:8b (Ollama)` が表示され、選択できる。

失敗時:

- `Auto` しか表示されなければ Workspace Trust を確認する。
- `qwen3:8b (Ollama)` がなければ VS Code を再起動し、`Chat: Manage Language Models` と `%APPDATA%\Code\User\chatLanguageModels.json` の存在を確認する。
- endpoint の到達性は、先に `verify_endpoint.py --require-agent` で再確認する。
- 設定ファイルをその場で上書きせず、競合がある場合はバックアップと手動 merge の手順へ戻る。

### 6.3 Chat を確認する

モデルピッカーで `qwen3:8b (Ollama)` を選び、Chat に次を送る。

```text
LOCAL-CHAT-OK とだけ返してください。
```

期待結果:

- ローカルモデルから応答が返る。
- 応答文の厳密な一致より、選択したローカルモデルで往復できたことを確認する。

失敗時:

- GitHub サインインを求められたら、`Auto` や GitHub 提供モデルではなく `qwen3:8b (Ollama)` が選択されているか確認する。BYOK Chat 自体には GitHub アカウントや Copilot プランは不要である。
- 応答がない場合は `ollama list`、`ollama ps`、`verify_endpoint.py`、`%LOCALAPPDATA%\Ollama\server.log` の順で確認する。

### 6.4 Agent を確認する

同じ確認用フォルダーで Agent を選び、次を送る。

```text
このフォルダーに agent-check.txt を作成し、内容を LOCAL-AGENT-OK の1行だけにしてください。
```

編集の承認が表示された場合は、対象が `C:\LocalLlmCheck\agent-check.txt` だけであることを確認して承認する。

期待結果:

- Agent がファイル作成ツールを呼び出す。
- `agent-check.txt` が作成され、内容が `LOCAL-AGENT-OK` の 1 行になる。
- 確認後、テストファイルは削除する。

失敗時:

- Agent が選べなければ Workspace Trust とモデルピッカーを確認する。
- 会話はできるがツールを呼ばなければ、`verify_endpoint.py --require-agent` を再実行する。`tool_calls` または引数が不正なら Agent 用として使用しない。
- endpoint 検証が成功しても VS Code UI だけ失敗する場合は、VS Code を再起動し、Language Models editor と Chat のログを確認する。API 検証成功だけで UI E2E 成功とは判定しない。

## 7. 完了条件

次をすべて満たしたときだけ完了とする。

- [ ] 運用機に `pwsh.exe` がなかった場合、`install-windows.cmd -BootstrapPowerShell` が終了コード `0` で自動 dry-run まで完了。
- [ ] `install-windows.cmd` の dry-run が終了コード `0`。
- [ ] `install-windows.cmd -Apply` が最後まで成功。
- [ ] PowerShell、Python、VS Code、Ollama の版を確認済み。
- [ ] `ollama list` に `qwen3:8b` が存在。
- [ ] `OLLAMA_CONTEXT_LENGTH=8192` と `ollama ps` の context を確認済み。
- [ ] `verify_endpoint.py --require-agent --expected-context 8192` が 5 項目すべて OK。
- [ ] VS Code モデルピッカーで `qwen3:8b (Ollama)` を選択可能。
- [ ] VS Code Chat の実往復に成功。
- [ ] 信頼済みの確認用フォルダーで Agent のファイル作成に成功。
- [ ] インライン補完、セマンティック検索、埋め込み依存機能は対象外と関係者へ共有済み。
- [ ] Foundry Local は任意かつ Chat 専用で、Agent の合格判定に使っていない。

このチェックリストのうち別のオフライン運用機でのdry-run / Applyと VS Code UI の3項目は、運用機で実行して初めて完了になる。本書更新時点では未実施である。
