# local-llm-dev

Windows または macOS のオンライン準備機で必要資材を収集し、オフライン運用機へ
**VS Code Chat / Chat ビュー内 Agent + Ollama** を導入するためのドキュメントとツール群です。

## 最短の入口

| 環境 | 最初に読むファイル | 保証対象 |
|---|---|---|
| Windows | [WINDOWS.md](WINDOWS.md) | Windows 11 x64 |
| macOS | [MACOS.md](MACOS.md) | macOS 14 以降 / Apple Silicon (`arm64`) |
| 共通の背景・制約 | [TUTORIAL.md](TUTORIAL.md) | 上記2環境 |

固定契約と保守者向け詳細は [tools/airgap-kit/CONTRACT.md](tools/airgap-kit/CONTRACT.md) と
[tools/airgap-kit/README.md](tools/airgap-kit/README.md) を参照してください。
実行済み検証と未実施範囲は [VALIDATION.md](VALIDATION.md) に記録しています。

## 先に知るべき制約

1. 通常の Agent 経路は **Ollama 必須**です。既定は `qwen3:8b`、context `8192` です。
2. Agent は、構造化 tool calling、正しい引数、実効 context の自動検証に合格した場合だけ使用します。
3. BYOK ローカルモデルは Chat、Chat ビュー内 Agent、インライン Chat、utility 処理に利用できます。
4. インライン補完（Tab / ghost text）、セマンティック検索、embedding 依存機能は利用できません。
5. `disable_ollama_cloud=true` はネットワーク遮断の代替ではありません。運用機はオフラインのまま使うか、組織の egress 制御を適用します。
6. Foundry Local は macOS でのみ runtime と取得済みcacheを任意同梱できます。VS Code設定は自動生成せず、Agentの合格経路にも使いません。

機能境界の根拠は [VS Code 公式 BYOK ドキュメント](https://code.visualstudio.com/docs/agent-customization/language-models)、
Ollama の設定は [Ollama FAQ](https://docs.ollama.com/faq) を参照してください。

## 検証状況

- PowerShell / Bash / Python の構文、manifest、path、bytes、SHA-256、dry-run、競合停止、終了コード、
   Agent endpoint をローカル契約テストで検証しています。
- 2026-08-16 に Windows 11 x64 のオンライン準備機で、`qwen3:8b` / context `8192` の
  資材取得、専用Ollama serverでの5項目のAgent検証、22ファイルのキット生成まで実行しました。
- 旧性能値と旧 Foundry Local 移送実験は Windows 1 台の記録です。条件と限界は
   [TUTORIAL.md 付録 A](TUTORIAL.md#付録-a-実測データと測定条件) に分離しています。
- **クリーンな別のオフラインWindows運用機でのApply、物理媒体移送、WindowsのVS Code GUI、
  およびmacOS実機E2Eは未実施です。** 採用前にOS別ガイドの完了条件を実機で確認してください。

## 主なファイル

```text
local-llm-dev/
├── README.md
├── TUTORIAL.md
├── WINDOWS.md
├── MACOS.md
├── VALIDATION.md
├── templates/
│   ├── README.md
│   ├── chatLanguageModels.sample.json
│   ├── settings.offline.sample.json
│   ├── ollama-server.sample.json
│   └── copilot-instructions.ja.md
└── tools/
      ├── verify_endpoint.py
      ├── test_verify_endpoint.py
      ├── check_fences.py
      ├── airgap-kit/
      │   ├── CONTRACT.md
      │   ├── Prepare-Windows.cmd
      │   ├── Export-OfflineKit.ps1
      │   ├── install-windows.cmd
      │   ├── Import-OfflineKit.ps1
      │   ├── Prepare-macOS.sh
      │   ├── install-macos.sh
      │   ├── README.md
      │   └── tests/
      └── jp-eval/
            ├── README.md
            ├── jp_eval.py
            ├── prompts.json
            └── test_jp_eval.py
```

## 用途別

| 目的 | 参照先 |
|---|---|
| モデルが Agent に使えるか確認 | [tools/verify_endpoint.py](tools/verify_endpoint.py) |
| 手動で VS Code / Ollama 設定 | [templates/README.md](templates/README.md) |
| 日本語 custom instructions | [templates/copilot-instructions.ja.md](templates/copilot-instructions.ja.md) |
| 日本語形式追従を再評価 | [tools/jp-eval/README.md](tools/jp-eval/README.md) |

`<モデル名>` などの山括弧は実値へ置き換えるプレースホルダーです。そのまま実行しないでください。
