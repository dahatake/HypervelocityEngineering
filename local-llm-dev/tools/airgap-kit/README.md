# airgap-kit 技術リファレンス

`airgap-kit` は、オンライン準備機で Windows または macOS 用の自己完結した移送キットを生成し、同じ OS / CPU 系統のオフライン運用機で検証・導入するためのツール群である。

利用者向けの入口は、先にトップレベルの OS 別ガイドを参照する。

- Windows: [WINDOWS.md](../../WINDOWS.md)
- macOS: [MACOS.md](../../MACOS.md)

本書はスクリプトの実行契約、安全境界、生成物を説明する保守者向けリファレンスである。固定契約は [CONTRACT.md](CONTRACT.md)、実際の振る舞いは各スクリプトを正本とする。

## 保証範囲

| 項目 | Windows | macOS |
|---|---|---|
| 保証対象 | Windows 11 build 22000 以降 / x64 | macOS 14 以降 / Apple Silicon (`arm64`) |
| オンライン準備機 | 対象 OS / CPU と同じ | 対象 OS / CPU と同じ |
| 必須 LLM ランタイム | Ollama | Ollama |
| 既定モデル | `qwen3:8b` | `qwen3:8b` |
| 既定コンテキスト長 | 8192 tokens | 8192 tokens |
| VS Code 接続 | Custom Endpoint / OpenAI Chat Completions 互換 | 同左 |
| Agent 条件 | 準備機と導入後の `verify_endpoint.py --require-agent --expected-context <値>` が成功すること | 同左 |
| 任意 Foundry Local | 現行の Windows 生成・導入スクリプトでは扱わない | 明示指定時だけ同梱・導入する |

Windows ARM64、Intel Mac、Linux、WSL、Docker、プロジェクト固有の言語 SDK は保証対象外である。異なる OS / CPU 向けにキットを流用できない。

Foundry Local は契約上の任意ランタイムであり、Ollama の代替となる必須経路ではない。現行実装で自動同梱できるのは macOS だけで、runtime と取得済み model cache を移送する。VS Code 接続設定は自動生成せず、BYOK Agent の保証対象にも含めない。

## スクリプトと実行場所

### オンライン準備機

| OS | スクリプト | 役割 |
|---|---|---|
| Windows | `Prepare-Windows.cmd` | `winget` で準備機の PowerShell 7、Python Install Manager、Python 3.14 x64、Ollama を用意し、モデルを取得して `Export-OfflineKit.ps1` を呼ぶ入口 |
| Windows | `Export-OfflineKit.ps1` | PowerShell 7 x64 MSI、Python の manager と offline index、VS Code x64 User Setup、Ollama installer、指定モデル、設定、検証ツールを収集して `manifest.json` を最後に生成する |
| macOS | `Prepare-macOS.sh` | Python Universal2 `.pkg`、VS Code Apple Silicon `.zip`、Ollama `.dmg`、指定モデル、設定、検証ツールを収集し、必要なら Foundry Local を加えて `manifest.json` を最後に生成する |

既定のオンライン入口は次のとおりである。

| OS | 実行形式 |
|---|---|
| Windows | `Prepare-Windows.cmd --destination D:\offline-kit [--model NAME] [--context-length TOKENS]` |
| macOS | `./Prepare-macOS.sh --destination /path/to/offline-kit [--model NAME] [--context-length TOKENS]` |

出力先は存在しないか、隠し項目を含めて空でなければならない。必須取得、版・architecture 確認、モデルキャッシュ特定、Agent endpoint 検証のいずれかが失敗した場合、完成キットとして扱わず `manifest.json` を生成しない。

準備スクリプトはオンライン準備機を完全な read-only では扱わない。Windows は前提ツールを導入してモデルを pull し、macOS も必要に応じて検証済み Python / Ollama を準備機へ導入してモデルを取得する。

両producerはAgent検証時に既存の既定Ollama daemonを再利用せず、`127.0.0.1:11435`へ選択contextを設定した専用serverを起動する。このportが使用中ならfail-closedで停止し、検証後は専用processを終了する。

### オフライン運用機

| OS | キット内の入口 | 導入実装 |
|---|---|---|
| Windows | 生成された `install-windows.cmd` | 同梱された `Import-OfflineKit.ps1` |
| macOS | 同梱された `install-macos.sh` | `install-macos.sh` 本体 |

Windows の入口は既定では PowerShell 7 を自動導入しない。`pwsh.exe` が無い場合だけ、`-BootstrapPowerShell` を明示すると `runtime\powershell` の一意なx64 MSIを対話導入し、その後dry-runへ進む。

## 標準フロー

1. 対象 OS / CPU と同じオンライン準備機でキットを生成する。
2. `manifest.json` を含むディレクトリ全体を、構造を変えずに信頼済み媒体へコピーする。
3. オフライン運用機で既定の dry-run を実行する。
4. manifest、全 payload、対象 OS / CPU、既存導入先、実行予定を確認する。
5. 問題がない場合だけ明示的に Apply する。
6. 自動 endpoint 検証後、VS Code のモデルピッカー、Chat、Agent の実往復を人手確認する。

## 生成キット

OS 固有ファイルは一方だけを含む。Foundry Local の 2 ディレクトリは macOS で明示指定した場合だけ含む。

```text
offline-kit/
├── manifest.json
├── install-windows.cmd             # Windows のみ
├── Import-OfflineKit.ps1           # Windows のみ
├── install-macos.sh                # macOS のみ
├── runtime/
│   ├── powershell/                 # Windows のみ
│   ├── python/                     # manager + offline index、または Universal2 pkg
│   ├── vscode/
│   ├── ollama/
│   └── foundry-local/              # macOS、任意
├── models/
│   ├── ollama/                     # 選択モデルの manifest と参照 blobs
│   └── foundry-local/              # macOS、任意
├── config/
│   ├── chatLanguageModels.json
│   ├── settings.offline.json
│   └── ollama-server.json
├── tools/
│   └── verify_endpoint.py
└── docs/
    └── WINDOWS.md または MACOS.md
```

生成キットはリポジトリを別途取得せず、そのディレクトリ単体で検証・導入できる構造とする。`docs/WINDOWS.md` または `docs/MACOS.md` は生成時のモデル名とコンテキスト長を含む、キット内の運用手順である。

## `manifest.json` schema version 1

| フィールド | 型 / 契約 |
|---|---|
| `schemaVersion` | 整数 `1` |
| `createdAt` | UTC の ISO 8601。producer は manifest 最終化時刻を記録する |
| `platform` | `windows` または `macos` |
| `architecture` | Windows は `x64`、macOS は `arm64` |
| `model.name` | `ollama list` で確定した完全なモデル名 |
| `model.digest` | `ollama list` で取得した digest |
| `model.supportsToolCalling` | Agent キットでは boolean `true` が必須 |
| `contextLength` | 正の整数。producer の入力では 2 以上 |
| `components[]` | `name`、`required`、実際の `version`、キット内相対 `path` |
| `files[]` | payload の相対 `path`、`bytes`、64 桁の `sha256` |

`manifest.json` 自身は `files[]` に含めない。それ以外の payload は全件列挙する。準備機名、ユーザー名、絶対パス、credential、token、secret を manifest に記録しない。

component 名と固定 path は OS ごとに validator が確認する。現在の producer は、同梱した component を `required=true` として記録する。任意の Foundry Local も、選択してキットへ含めた後は runtime と model cache の両方が必須 component になる。

Windows importer は `createdAt` が UTC であること、既知 component 名、固定 path、Python offline index とその archive hash、設定内のモデル・token 合計まで検証する。macOS installer は schema の型、固定 platform / architecture、必須 component、設定・runtime・model payload の存在を検証し、`createdAt` は空でない文字列として読む。

## dry-run と Apply

| OS | dry-run | Apply |
|---|---|---|
| Windows | `install-windows.cmd` | `install-windows.cmd -Apply` |
| macOS | `./install-macos.sh` | `./install-macos.sh --apply` |

dry-run は既定動作である。

- Windows: 書込みと外部プロセス実行を行わず、検証結果と導入予定を表示する。
- macOS: install、copy、環境変数変更、application 起動を行わず、検証結果と導入予定を表示する。
- manifest と全 payload の検証、OS / CPU 判定、既存導入先の競合 preflight は Apply の有無に関係なく先に完了させる。
- 既存のOllama processまたは既定endpoint listenerはdry-run / Apply前に停止させる。installerは既存daemonを検証対象として再利用しない。
- Apply は検証を省略する別経路ではなく、同じ preflight に成功した後だけ変更を実行する。
- installer、CLI、導入後 verifier の非ゼロ終了は成功へ変換せず、その終了コードまたは失敗として停止する。

設定ファイルは JSON merge しない。新規配置または完全一致の skip だけを許し、異なる既存設定があれば Apply 前に停止して手動マージを要求する。

## fail-closed 条件

### キット生成

次のいずれかを検出した場合は完成扱いにしない。

- 対象外 OS / CPU、Windows 11 build 22000 未満、macOS 14 未満
- 必須コマンド、repository source、installer、verifier の欠落・空ファイル・不正形式
- 出力先が非空。macOS では symlink、または収集元 cache の配下も拒否
- 必須 download の失敗または空 artifact。macOS は固定した Python SHA-256 と各 artifact の metadata / architecture、Windows は取得物の実版と Python offline index の SHA-256 も検証
- 指定モデルが取得できない、Ollama manifest を一意に特定できない、参照 blob が欠落している
- `verify_endpoint.py --require-agent` の失敗
- macOS で verifier が `[ WARN ]` を返す、または無条件の「すべて OK」を返さない
- 任意 Foundry Local の URL、asset、architecture、version、model cache が契約を満たさない
- 生成 path がキット外を指す状態。macOS は payload 内の symlink、control character、secret-bearing manifest field も拒否

必須資材の取得失敗や Agent 検証不合格を、警告だけで継続するモードはない。

### キット検証・導入

次のいずれかを検出した場合は Apply 前、または該当操作直後に停止する。

- `manifest.json` の欠落、JSON 不正、schema / 型 / platform / architecture / Agent 条件の不一致
- 絶対 path、path traversal、非 canonical path、Windows unsafe path
- Windows の reparse point、macOS の symlink または特殊 filesystem node
- manifest-listed file の欠落、重複、byte 数不一致、SHA-256 不一致
- `manifest.json` 以外の未記載ファイル混入
- 必須 component、runtime、model、設定、verifier の欠落または固定 path 不一致
- 設定モデル、endpoint、tool calling、context token 合計の不一致
- 既存 runtime、設定、model cache、環境変数がキットと競合する
- installer / CLI の失敗、導入後 version 不一致、Ollama loopback timeout
- 導入後の `verify_endpoint.py --require-agent` 失敗または不完全な成功

ハッシュ検証を無効化するオプション、競合を強制上書きするオプション、検証失敗を警告へ降格するオプションは提供しない。

## 再実行: 同一なら skip、競合なら stop

| 対象 | 同一状態 | 異なる既存状態 |
|---|---|---|
| VS Code / Ollama | validator が同一版と確認できれば skip | version を確認できない、または異なる場合は stop |
| Python | Windows は同一 Python Manager、macOS は同一 Python 版なら skip | 異なる既存版や unsafe path は stop |
| 設定ファイル | 同一 content なら skip | 既存 content を上書きせず stop |
| Ollama model cache | 同一 hash なら skip | 同じ行先に異なる content があれば stop |
| `OLLAMA_CONTEXT_LENGTH` | manifest と同じ値なら skip | 異なる値なら stop |
| Foundry Local（macOS、任意） | runtime と model subtree が同一なら skip | 片方だけ存在、異なる版・content、unsafe path は stop |

Windows はキットから配置する各 model file を比較し、一致する file を skip する。macOS は既存 model subtree 全体が manifest と一致する場合だけ skip し、追加・欠落・差異があれば手動マージを要求する。

## SHA-256 の保証と限界

SHA-256 は次だけを保証する。

- 信頼済み `manifest.json` に記録された payload と、運用機上の payload が byte 単位で一致すること
- 移送中の破損、欠落、追加、信頼済み manifest に対する file 変更を検出すること

SHA-256 は真正性署名ではない。`manifest.json` 自身は署名されず、攻撃者が manifest と payload を同時に置換した場合、キット内の hash 検証だけでは検出できない。したがって、準備機、取得元、manifest を媒体へ書き出すまでの経路、媒体の保管を信頼できることが前提である。

発行者真正性や chain of custody が必要な場合は、組織の code signing、署名付き manifest、PKI、媒体管理などを本キットの外側で追加する。vendor installer の署名や個別 download 検証は、キット全体の署名を代替しない。

## Foundry Local は任意

- 必須・既定の Agent endpoint は Ollama である。
- macOS では `--include-foundry-local` を指定した場合だけ Foundry Local を含める。
- その場合は、公式 `microsoft/Foundry-Local` GitHub release の exact `.pkg` / `.zip` URL と、事前取得済みで非空の model cache を両方指定する。
- 選択後は runtime と model cache の両方を manifest-listed required component として検証・導入する。
- Foundry Local の導入後 version と model cache は検証するが、同梱 `verify_endpoint.py` の Agent 合格判定は Ollama endpoint に対して行う。
- 現行 Windows の `Prepare-Windows.cmd`、`Export-OfflineKit.ps1`、`Import-OfflineKit.ps1` は Foundry Local を収集・導入しない。

## 非対象と運用上の限界

- OS firewall / egress policy の自動変更
- 言語 SDK、VS Code extension、汎用 package manager の一括同梱
- 既存 JSON の自動 merge、異なる version の upgrade / downgrade
- 署名鍵、PKI、媒体管理の構築
- Foundry Local の tool-call 変換 proxy
- Windows ARM64、Intel Mac、Linux、WSL、Docker

`config/ollama-server.json` は `disable_ollama_cloud=true` を設定するが、ネットワーク遮断そのものではない。真のエアギャップは OS / network 側の統制で保証する。

## 検証状況

repository のテストは、引数契約、生成 tree、manifest、path / hash、dry-run、競合、終了コード、構文などを fixture 上で検証する。2026-08-16にはWindows 11 x64のオンライン準備機で、実資材取得、`qwen3:8b` / context `8192`のAgent検証、22ファイルのキット生成まで完走した。詳細は [../../VALIDATION.md](../../VALIDATION.md) を参照する。しかし、次は未実施である。

- **Windows / macOS とも、クリーンな別の実機を完全にオフラインにし、媒体移送、dry-run、Apply、VS Code のモデルピッカー / Chat / Agent 実往復まで通した E2E**
- **macOS実機でのオンライン収集とキット生成**
- 異なる企業 endpoint 制御、EDR、AppLocker、MDM、filesystem policy 下での Apply
- すべての installer version と hardware 組み合わせ

自動テストの成功は実機 E2E の代替ではない。採用前に対象 OS / CPU、組織 policy、実媒体を使って検証する。

## 実装正本

- [CONTRACT.md](CONTRACT.md): 固定保証と安全契約
- [Prepare-Windows.cmd](Prepare-Windows.cmd): Windows オンライン入口
- [Export-OfflineKit.ps1](Export-OfflineKit.ps1): Windows kit producer
- [Import-OfflineKit.ps1](Import-OfflineKit.ps1): Windows kit validator / installer
- [Prepare-macOS.sh](Prepare-macOS.sh): macOS kit producer
- [install-macos.sh](install-macos.sh): macOS kit validator / installer

## 公式出典

| 内容 | 公式資料 |
|---|---|
| VS Code BYOK、Custom Endpoint、オフライン機能と制約 | [AI language models in VS Code](https://code.visualstudio.com/docs/agent-customization/language-models) |
| VS Code Windows User Setup | [Installing Visual Studio Code on Windows](https://code.visualstudio.com/docs/setup/windows) |
| VS Code macOS / Apple Silicon | [Installing Visual Studio Code on macOS](https://code.visualstudio.com/docs/setup/mac) |
| `winget download` と architecture / installer 指定 | [`download` command](https://learn.microsoft.com/windows/package-manager/winget/download) |
| PowerShell 7 の Windows 導入 | [Installing PowerShell on Windows](https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows) |
| Python Install Manager の offline index | [Using Python on Windows — Offline installs](https://docs.python.org/3/using/windows.html#offline-installs) |
| Python Universal2 `.pkg` | [Using Python on macOS](https://docs.python.org/3/using/mac.html) |
| Ollama Windows 要件と配置 | [Ollama on Windows](https://docs.ollama.com/windows) |
| Ollama macOS 要件と配置 | [Ollama on macOS](https://docs.ollama.com/macos) |
| Ollama local-only、model path、context 環境変数 | [Ollama FAQ](https://docs.ollama.com/faq) |
| Foundry Local の位置づけとオフライン利用 | [What is Foundry Local?](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local) |
| Foundry Local CLI、macOS release asset、cache / server | [Foundry Local CLI reference](https://learn.microsoft.com/azure/foundry-local/reference/reference-cli) |
