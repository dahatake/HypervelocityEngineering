# 検証記録

この文書は、`local-llm-dev` の実装に対して実際に行った検証と、まだ行っていない検証を分離して記録する。
自動テストやオンライン準備機での成功を、別のオフライン運用機での導入成功として読み替えてはならない。

## 2026-08-16 Windows オンライン収集

### 実行条件

| 項目 | 実値 |
|---|---|
| 準備機 | Windows 11 x64（.NET が報告した OS version: `10.0.29639.0`） |
| モデル | `qwen3:8b` |
| モデル digest | `500a1f067a9f` |
| context | `8192` |
| producer検証endpoint | 専用 `http://127.0.0.1:11435` |
| manifest作成時刻 | `2026-08-16T13:09:36.7936842Z` |

この準備機はOS導入直後のクリーン端末ではない。既存のPython、Ollama、モデルcacheなどがある状態で、最終実装の `Prepare-Windows.cmd` を新しい空の出力先に対して実行した。
キットへ収録するinstallerとruntimeは、その実行で改めて取得した。

### 成功した処理

1. `qwen3:8b` を取得した。
2. 既存の既定Ollama daemonを再利用せず、`OLLAMA_CONTEXT_LENGTH=8192` を設定したproducer専用serverを `127.0.0.1:11435` で起動した。
3. `verify_endpoint.py --require-agent --expected-context 8192` で次をすべて確認した。
   - models
   - Chat completion
   - streaming SSE
   - 構造化tool callingと `city="Tokyo"` の引数
   - `/api/ps` の実効context `8192`
4. PowerShell、Python Install Manager、Python offline runtime、VS Code、Ollama installer、選択モデル、設定、導入・検証スクリプトを収集した。
5. 全payloadのbyte数とSHA-256を記録したschema version 1のmanifestを最後に生成した。

Endpoint検証の最終結果は `結果: すべて OK。Chat / Agent の両方で使えます。` だった。
これはHTTP APIレベルの合格であり、VS Code GUIの合格ではない。

### 生成キットの実測値

| 項目 | 実値 |
|---|---:|
| manifest-listed files | 22 |
| manifest-listed payload合計 | 7,224,380,925 bytes |
| `model.supportsToolCalling` | `true` |
| `contextLength` | `8192` |

| component | manifest version |
|---|---|
| PowerShell | `7.6.5.0` |
| Python Install Manager | `26.3.240.0` |
| Python runtime | `3.14.7` |
| VS Code | `1.133.0` |
| Ollama | `0.32.13` |
| Ollama model | `qwen3:8b` |

`winget download` がPowerShellとOllamaの配布ファイル名を変更することを実測したため、producerは孤立したcomponentディレクトリ内の一意な候補を検査し、Ollama installerをキット固定名 `OllamaSetup.exe` へ正規化する。

### 生成物自身からのdry-run

生成した `install-windows.cmd` を、そのキットのルートから引数なしで実行した。

- manifest schemaとcanonical UTC `createdAt` の検証: 成功
- 22ファイルのmissing / extra / bytes / SHA-256検証: 成功
- `install-windows.cmd` から `Import-OfflineKit.ps1` へのキットroot引き渡し: 成功
- 現在の準備機に対する導入先preflight: **期待どおり競合停止**

停止理由は、キットと異なる既存Ollama版、既存のVS Code設定、実行中Ollama、使用中のloopback port `11434` だった。
既存内容を上書きしなかった。この結果はfail-closedな競合検出の実測であり、クリーンなオフライン運用機でdry-runが成功した証明ではない。

## 自動検証

最終ソースに対して次を実行し、すべて成功した。

- Windows `Prepare-Windows.cmd` 静的契約
- Windows `Export-OfflineKit.ps1`: 18契約
- Windows `install-windows.cmd` 静的契約と実 `cmd.exe` root引き渡し
- Windows `Import-OfflineKit.ps1`: 24契約。temporary fixtureのみを使い、Apply・network・実installerは実行しない
- macOS `Prepare-macOS.sh`: 71静的契約と `bash -n`
- macOS `install-macos.sh`: 8静的契約groupと `bash -n`
- Endpoint verifier: 8 unittest。ローカルHTTP fixtureを使い、timeout、HTTP error、tool引数、context不一致、proxy非依存を検証
- 日本語評価ツールの回帰テスト
- Python全ファイルのAST parse
- `Prepare-macOS.sh` 内の埋め込みPython 2ブロックのAST parse
- JSON全ファイルのparse
- Markdown 11ファイルのcode fence検査: 問題0件

静的契約はmacOS実機の代替ではない。

## 実測中に検出して修正した問題

最終成功までの中間実行では、次をfail-closedで検出して修正した。途中生成物は完成キットとして扱っていない。

- 既存Ollama daemonが実効context `4096` で、選択値 `8192` と不一致
- `winget download` がPowerShell MSIを `PowerShell_<version>_Machine_X64_wix_<locale>.msi` へ改名
- `winget download` がOllama installerを `Ollama_<version>_User_X64_inno_<locale>.exe` へ改名
- Windows batchの末尾separator付き `%~dp0` が、native引数の `Source` へ余分な引用符を混入
- Windows producerのUTC `+00:00` timestampがPowerShell JSON round-trip後にlocal `DateTime`へ変換され、importerのUTC判定と不一致

## 未実施

次は成功したと表明しない。

- 物理媒体を介した別端末への移送
- OS導入直後のクリーンな別Windows 11 x64運用機でのPowerShell bootstrap
- 完全にオフラインの別Windows運用機でのdry-run成功と `-Apply`
- 導入後のWindows CLI・Ollama endpoint再検証
- Windows VS Codeのモデルピッカー、Chat、Chatビュー内Agentの実操作
- macOS 14+ / Apple Silicon実機でのオンライン収集、媒体移送、dry-run、`--apply`、VS Code GUI
- macOSの任意Foundry Local分岐
- EDR、AppLocker、MDM、企業proxy、特殊filesystem policy下の全組合せ
- すべての将来installer versionとhardware構成

採用判定には、[WINDOWS.md](WINDOWS.md) または [MACOS.md](MACOS.md) の完了条件を、対象OS・CPU、実媒体、組織policyを使って別途満たす必要がある。
