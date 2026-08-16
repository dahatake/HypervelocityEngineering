# Offline Kit Contract

Windows または macOS のオンライン準備機で移送キットを作成し、同じ OS / CPU 系統のオフライン運用機へローカル LLM 開発環境を導入するための固定契約。

## 1. 保証範囲

| 項目 | 保証対象 |
|---|---|
| Windows | Windows 11 x64 |
| macOS | macOS 14 以降 / Apple Silicon |
| 必須 LLM ランタイム | Ollama |
| 既定モデル | `qwen3:8b` |
| 既定コンテキスト長 | 8192 tokens |
| VS Code 接続 | Custom Endpoint（OpenAI Chat Completions 互換） |
| 任意ランタイム | Foundry Local（macOSでruntime/cacheを同梱。VS Code設定とBYOK Agentは保証しない） |

Windows ARM64 と Intel Mac は実機検証結果がないため保証対象外とする。Linux、WSL、Docker、プロジェクト固有の言語 SDK も保証対象外とする。

## 2. 必須コンポーネント

キット生成は次の全コンポーネントを取得できた場合だけ成功する。

| コンポーネント | Windows | macOS |
|---|---|---|
| OS 別オフライン導入エントリ | `install-windows.cmd` | `install-macos.sh` |
| 導入実装 | `Import-OfflineKit.ps1` | `install-macos.sh` 本体 |
| PowerShell 7 | x64 MSI | 不要 |
| Python | Python Install Manager と 3.10 以上のオフライン runtime | Universal 2 `.pkg` |
| VS Code | x64 User Setup | Universal / Apple Silicon `.zip` または `.dmg` |
| Ollama | Windows installer | macOS `.dmg` |
| Ollama model cache | `qwen3:8b` または明示指定モデル | 同左 |
| 設定 | BYOK、Utility model、Ollama local-only | 同左 |
| 検証 | `verify_endpoint.py` | 同左 |
| 手順 | 対象 OS の導入ガイド | 同左 |

任意 Foundry Local を指定した場合は、対象 OS 用インストーラーとダウンロード済みモデルも必須に昇格する。

## 3. 生成キット構造

```text
offline-kit/
├── manifest.json
├── install-windows.cmd または install-macos.sh
├── runtime/
│   ├── powershell/            # Windows のみ
│   ├── python/
│   ├── vscode/
│   ├── ollama/
│   └── foundry-local/         # 任意
├── models/
│   ├── ollama/
│   └── foundry-local/         # 任意
├── config/
│   ├── chatLanguageModels.json
│   ├── settings.offline.json
│   └── ollama-server.json
├── tools/
│   └── verify_endpoint.py
└── docs/
    └── WINDOWS.md または MACOS.md
```

キットはリポジトリを別途取得しなくても、上記ディレクトリ単体で検証・導入できなければならない。

## 4. manifest.json

必須フィールド:

- `schemaVersion`: 現行値 `1`
- `createdAt`: ISO 8601 canonical UTC `Z` 形式
- `platform`: `windows` または `macos`
- `architecture`: `platform=windows` では `x64`、`platform=macos` では `arm64`
- `model.name`: `ollama list` が返す完全なモデル名（例: `qwen3:8b`）
- `model.digest`: `ollama list` が返す digest
- `model.supportsToolCalling`: 準備機で構造化 tool call と引数を検証した結果。Agent 用キットでは `true` 必須
- `contextLength`: 正の整数
- `components`: コンポーネント名、必須区分、実際の版、キット内相対パス
- `files`: 全ファイルの相対パス、byte 数、SHA-256

準備機名、ユーザー名、絶対パス、秘密情報は記録しない。

## 5. 完全性契約

- 準備機、利用する配布元、manifest を媒体へ書き出すまでの経路は信頼済みであることを前提とする。
- manifest 自身を除く全ファイルを SHA-256 で検証する。
- 欠落、ハッシュ不一致、manifest 未記載ファイル、絶対パス、パストラバーサルは導入前に失敗させる。
- ハッシュ検証を省略するオプションは提供しない。
- SHA-256 は移送時の破損と、信頼済み manifest に対するファイル変更を検知するために使う。
- manifest には署名を付けないため、manifest とファイルを同時に置換する攻撃への真正性保証は行わない。

## 6. 実行契約

### 準備機

- 出力先は存在しないか空でなければならない。
- 必須コンポーネントを取得・確認してから manifest を最後に生成する。
- 取得失敗や必須モデル不在を警告だけで継続しない。
- 実際に取得した版とモデル digest を manifest に記録する。
- 指定モデルを準備機で起動し、構造化 tool call、引数、実効 context を検証する。Agent 用キットでは不合格を警告だけで継続しない。
- Agent検証では、既存daemonを再利用せず、`127.0.0.1:11435`へ選択contextを設定したproducer専用Ollama serverを起動する。port使用中は停止し、検証後は専用processを終了する。

### 運用機

- 既定動作は検証と導入予定の表示だけで、ファイル配置やインストールを行わない。
- 明示的な Apply 指定時だけ導入する。
- 対象 OS / CPU が manifest と一致しない場合は失敗する。
- 各インストーラーと検証コマンドの終了コードを伝播する。
- 既存のOllama processまたは既定endpoint listenerをdry-run / Apply前に拒否し、キット外daemonを導入後検証へ再利用しない。
- 既存のユーザー設定を無条件で上書きしない。空の新規環境には設定し、既存値との競合は停止して手動マージを案内する。
- 再実行時は同一版・同一内容を安全にスキップし、異なる既存内容を黙って置換しない。

## 7. 導入後の必須検証

1. Python、PowerShell（Windows）、VS Code、Ollama の版確認
2. `ollama list` に対象モデルが存在すること
3. Ollama が loopback で応答すること
4. `verify_endpoint.py` で models / chat / streaming / tool calling と引数 / 実効 context を確認すること
5. VS Code のモデルピッカー、Chat、Agent の実往復を人手確認すること

VS Code のインライン補完、セマンティック検索、埋め込み依存機能は BYOK オフライン構成の完了条件に含めない。

## 8. 非対象

- 任意言語 SDK の一括導入
- OS ファイアウォール規則の自動変更
- 署名鍵や PKI の構築
- Foundry Local の tool call 変換プロキシ
- 複数モデル管理、モデル自動選定、汎用パッケージ管理抽象層

## 9. 公式根拠

- VS Code BYOK: <https://code.visualstudio.com/docs/agent-customization/language-models>
- VS Code Windows: <https://code.visualstudio.com/docs/setup/windows>
- VS Code macOS: <https://code.visualstudio.com/docs/setup/mac>
- Foundry Local: <https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local>
- Foundry Local CLI: <https://learn.microsoft.com/azure/foundry-local/reference/reference-cli>
- Ollama Windows: <https://docs.ollama.com/windows>
- Ollama macOS: <https://docs.ollama.com/macos>
- Ollama FAQ: <https://docs.ollama.com/faq>
- PowerShell Windows: <https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows>
- Python Windows: <https://docs.python.org/3/using/windows.html#offline-installs>
- Python macOS: <https://docs.python.org/3/using/mac.html>
