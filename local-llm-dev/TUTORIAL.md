# オフライン Vibe Coding 環境 構築チュートリアル

オンラインの **準備機**で必要資材を集め、移送キットをオフラインの **運用機**へ運び、
VS Code の Chat と Chat ビュー内の Agent をローカル LLM で使うための共通入口である。

> [!IMPORTANT]
> 初めて作業する場合は、この共通入口で対象 OS と制約を確認した後、
> [Windows 11 x64 ガイド](WINDOWS.md) または
> [macOS 14+ / Apple Silicon ガイド](MACOS.md) のどちらか一方へ進むこと。
> 実際の導入コマンドとOS固有の復旧手順は、OSガイドおよび現行スクリプトを正とする。

---

## 0. 検証範囲と OS を確認する

### 0.1 この手順が確認済みの範囲

この共通入口は、[固定契約](tools/airgap-kit/CONTRACT.md)、
[Windows ガイド](WINDOWS.md)、[macOS ガイド](MACOS.md)、および次の現行実装を照合している。

- Windows: `Prepare-Windows.cmd`、`Export-OfflineKit.ps1`、`Import-OfflineKit.ps1`
- macOS: `Prepare-macOS.sh`、`install-macos.sh`
- 共通検証: [`tools/verify_endpoint.py`](tools/verify_endpoint.py)

静的契約と実装では、OS / CPU、必須ファイル、byte 数、SHA-256、設定競合を
fail-closed で検査し、モデル名、コンテキスト長、Chat、streaming、tool calling も確認する。
endpoint の合格条件は [§2.2](#22-別モデルを指定する場合は名前だけで合格にしない) に示す。

> [!WARNING]
> **クリーンな準備機と運用機を使った実機 E2E は未実施である。**
> Windows 11 x64ではオンライン資材取得、専用serverでのAgent検証、キット生成まで実測した。
> 物理媒体での別端末移送、オフライン運用機での Apply、VS Code のモデルピッカー / Chat / Agent の実往復と、macOS実機は、
> 採用前に管理下の 2 台で確認すること。既存の性能値は Windows 1 台の参考実測であり、
> Ollama ランタイムとモデルを個別に測った値である。現行キット全体の E2E 成功を表すものではない。

Foundry Local の tool calling について確認したのは、**CLI 0.10.3、qwen3-4b、
HTTP 要求 1 回**だけである（[付録 A.4](#a4-tool-calling-の実測)）。
その組み合わせでは構造化 `tool_calls` が空で、本文に
`<tool_call>` が返った。他モデル、他バージョン、Foundry Toolkit 経由へ一般化してはならない。

### 0.2 保証対象 OS を選ぶ

| 準備機と運用機 | このキットの保証 | 次に読む手順 |
|---|---|---|
| **Windows 11 x64** | 対象 | [WINDOWS.md](WINDOWS.md) |
| **macOS 14 以降 / Apple Silicon (`arm64`)** | 対象 | [MACOS.md](MACOS.md) |
| Windows ARM64、Windows 10、Intel Mac、Linux、WSL、Docker | **対象外** | 続行せず、別途設計・検証する |

これは製品一般の対応 OS ではなく、**このリポジトリの移送キットが保証する範囲**である。
たとえば Ollama 自体の要件は [Windows 公式ガイド](https://docs.ollama.com/windows) と
[macOS 公式ガイド](https://docs.ollama.com/macos#system-requirements) に記載されているが、
製品が動作しても、このキットの対象外 OS を保証済みとは扱わない。

---

## 1. 用語と機能の境界を理解する

### 1.1 用語集

| 用語 | この手順での意味 |
|---|---|
| **BYOK** | Bring Your Own Key。自分で用意したモデルプロバイダーや互換エンドポイントを VS Code Chat に接続する仕組み。ローカルモデルでは秘密鍵を必要としない構成もある |
| **LLM** | Large Language Model。入力文脈から応答やコードを生成するモデル |
| **runtime** | LLM を読み込み、CPU / GPU で推論し、API を公開する実行基盤。本手順では Ollama、任意追加として Foundry Local |
| **tool calling** | モデルが Agent に「どのツールを、どの引数で呼ぶか」を構造化して返す機能 |
| **Agent** | この文書では **VS Code Chat ビュー内の Agent モード**。会話だけでなく、承認されたファイル操作やコマンドなどのツールを使う |
| **context** | 1 回の要求でモデルが扱う入力と出力の token 枠。長くすると多くの履歴を渡せるが、必要メモリも増える |
| **VRAM** | GPU 専用メモリ。モデルや context の一部または全部を GPU に置く容量 |
| **移送キット** | installer、runtime、モデル、設定、検証ツール、全 payload の SHA-256 を記録した `manifest.json` をまとめたディレクトリ |
| **準備機** | インターネット接続があり、資材取得と endpoint 検証を行って移送キットを作る端末 |
| **運用機** | 移送キットを導入し、ネットワーク非接続で VS Code とローカル LLM を使う端末 |

### 1.2 できること・できないこと

| VS Code の機能 | BYOK ローカルモデルでの扱い | 条件と本書の検証状態 |
|---|---|---|
| Chat | **使用可能** | VS Code 公式仕様。現行キットは API を自動検証するが、VS Code GUI の実往復は未確認 |
| Chat ビュー内の Agent | **条件付きで使用可能** | 構造化 tool calling と正しい引数の自動検証、および運用機での GUI E2E を完了してから使用する |
| インライン Chat | **使用可能** | `inlineChat.defaultModel` で選択可能。現行キットは設定するが、GUI 実操作は未確認 |
| title / commit message などの utility | **使用可能** | BYOK モデルを utility model に設定する。GUI 実操作は未確認 |
| インライン補完（Tab / ghost text） | **使用不可** | BYOK ローカルモデルを inline suggestions へ接続できない |
| セマンティック検索 | **使用不可** | GitHub アカウントとサービス接続を要する機能で、BYOK / 完全オフラインの対象外 |
| embedding に依存する機能 | **使用不可** | BYOK / 完全オフラインの対象外 |

根拠は VS Code 公式の
[AI language models in VS Code](https://code.visualstudio.com/docs/agent-customization/language-models) である。
同ページは、ローカル BYOK が GitHub アカウント、Copilot プラン、インターネット接続なしで
Chat に使えること、Agent には tool calling が必要なこと、インライン Chat のモデルを選べること、
一方で inline suggestions、semantic search、embeddings は BYOK の対象外であることを明記している。

> [!CAUTION]
> **インライン Chat とインライン補完は別機能である。**
> `inlineChat.defaultModel` を設定しても、Tab 補完や ghost text は有効にならない。
> インライン補完が必須要件なら、この構成を採用しないこと。

### 1.3 runtime の選び方

- **通常経路は Ollama が必須**。移送キット、VS Code の Custom Endpoint、Agent 合格判定は
  Ollama を基準に実装されている。
- **Foundry Local は任意追加**。Windows の現行キットには追加オプションがなく、
  macOS だけが利用者指定の公式 runtime URL と取得済みモデル cache を任意収録できる。
  VS Code 接続設定は自動生成せず、BYOK Agent の合格経路にも使わない。
- Foundry Local は公式には、モデル管理、ハードウェア高速化、ローカル推論、OpenAI 互換 API を提供する
  オンデバイス runtime である（[Microsoft 公式: Foundry Local とは](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local)）。
  ただし本リポジトリでは、前述の限定的な tool calling 実測を根拠に **Agent の合格経路へ使わない**。

「Foundry Local は常に Agent 非対応」と一般化するのではなく、現在の固定契約が安全側に
Chat 専用としている、と理解すること。

---

## 2. 既定モデルとハードウェアを選ぶ

### 2.1 まず既定値で進める

| 項目 | 固定契約の既定値 |
|---|---|
| 必須 runtime | Ollama |
| モデル | `qwen3:8b` |
| context | `8192` tokens |
| endpoint | `http://127.0.0.1:11434/v1/chat/completions` |

これらは [固定契約](tools/airgap-kit/CONTRACT.md) と Windows / macOS の準備スクリプトで一致している。
Ollama 自体の既定 context は 4096 だが、本キットは `OLLAMA_CONTEXT_LENGTH=8192` と
VS Code の token 枠を同じ合計へ設定する
（[Ollama 公式 FAQ: context window size](https://docs.ollama.com/faq#how-can-i-specify-the-context-window-size)）。

### 2.2 別モデルを指定する場合は名前だけで合格にしない

`--model` で別モデルを指定しても、同じシリーズや同じ parameter 数だから使えるとは判定しない。
準備機でその**完全なモデル名**に対して [`verify_endpoint.py`](tools/verify_endpoint.py) を
`--require-agent` 付きで実行し、次をすべて検証する。

1. `GET /v1/models` に指定モデルがある。
2. Chat completion が成功する。
3. streaming が SSE 形式で返る。
4. 構造化 `tool_calls` が返り、tool 引数の `city` が文字列 `Tokyo` になる。

Windows / macOS の現行準備スクリプトは非ゼロ終了を拒否する。さらに採用条件は
**`[ WARN ]` が 0 件で、最終結果が「すべて OK」**であることとする。macOS スクリプトは
この文字列条件も自動で拒否する。Windows ではコンソール出力を確認し、警告があればキットを使わない。
運用機への導入後も、manifest に記録された同じモデル名で再検証する。

### 2.3 ハードウェアは実機測定で決める

1. **最初に OS / CPU 契約を満たす端末を選ぶ。** Windows 11 x64 または macOS 14+ / `arm64` 以外は対象外。
2. **GPU は必須ではない。** CPU 推論もできるが、速度は端末、モデル、量子化、context に大きく依存する。
3. **モデルが RAM / VRAM に収まるか確認する。** `ollama ps` の `PROCESSOR` と実効 `CONTEXT` を運用機で確認する。
4. **context と並列数を増やすほどメモリが増える。** Ollama は並列要求数と context に応じて必要 RAM を増やす
   （[Ollama 公式 FAQ: concurrent requests](https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests)）。
5. **ディスクは runtime だけでなくモデルとキット複製分を確保する。** モデルは数十〜数百 GB になり得るため、
   `ollama list` と生成後のキット総 byte 数を基準にする
   （[Ollama Windows の容量説明](https://docs.ollama.com/windows#filesystem-requirements)、
   [Ollama macOS の容量説明](https://docs.ollama.com/macos#filesystem-requirements)）。
6. **準備機だけで性能判定しない。** 最終判断は、採用するモデルと context を運用機で実行して行う。

#### 参考: Windows 1 台だけの実測（一般化不可）

次は Windows 11 x64、RTX 4060 Laptop 8,188 MiB、context 8192 で 2026-08-14 に測った値である。
**macOS の見積り、最低要件、同じ VRAM 容量の別 GPU、調達保証へ流用してはならない。**

| モデル | 推論ピーク VRAM | CPU / GPU 配置 | 生成速度 |
|---|---:|---|---:|
| qwen3:4b | 3,797 MiB | 100% GPU | 56.7 tok/s |
| phi4-mini | 3,633 MiB | 100% GPU | 45.7 tok/s |
| qwen2.5:7b | 4,861 MiB | 100% GPU | 37.0 tok/s |
| **qwen3:8b** | **6,015 MiB** | **100% GPU** | **31.0 tok/s** |
| gpt-oss:20b | 6,119 MiB | 56% CPU / 44% GPU | 23.8 tok/s |

ディスク上のモデルサイズだけから VRAM 使用量を決め打ちしない。GPU への配置は
`ollama ps` で確認できる（[Ollama 公式 FAQ: GPU へのロード確認](https://docs.ollama.com/faq#how-can-i-tell-if-my-model-was-loaded-onto-the-gpu)）。

### 2.4 ライセンスは採用するモデルごとに確認する

runtime のライセンス、モデルのライセンス、再配布条件、商用利用条件は別である。
カタログ全体や同系列モデルから推測せず、**実際に固定するモデル名・tag・版**について、
配布元のモデルカードとライセンスを確認する。本書は個別モデルの商用利用可否を保証しない。

---

## 3. OS ガイドを選び、準備機でキットを作る

準備機と運用機で同じ対象 OS / CPU 系統を使い、次の OS ガイドを正本として進める。

| OS | 利用者向けガイド | オンライン準備の入口 |
|---|---|---|
| Windows 11 x64 | [WINDOWS.md](WINDOWS.md) | `Prepare-Windows.cmd` |
| macOS 14+ / Apple Silicon | [MACOS.md](MACOS.md) | `Prepare-macOS.sh` |

両入口で通常利用する引数は次のとおりである。出力先は存在しないか、隠し項目を含めて空でなければならない。

| 引数 | 必須 | 内容 / 既定値 |
|---|---|---|
| `--destination PATH` | 必須 | 生成キットの出力先 |
| `--model NAME` | 任意 | Ollama の完全なモデル名。既定 `qwen3:8b` |
| `--context-length TOKENS` | 任意 | 2 以上の整数。既定 `8192` |
| `--help` / `-h` | 任意 | 実装されている使用方法を表示 |

Windows は通常のコマンドプロンプトで、リポジトリルートから実行する。

```batch
cd /d C:\GitHub\RoyalytyService2ndGen\local-llm-dev\tools\airgap-kit
Prepare-Windows.cmd --destination "C:\OfflineKitBuild\qwen3-8b-8192"
```

macOS は Terminal で、リポジトリルートから実行する。

```bash
cd local-llm-dev/tools/airgap-kit
./Prepare-macOS.sh --destination "$HOME/offline-kit-qwen3-8b"
```

別モデルを指定する場合も、[§2.2](#22-別モデルを指定する場合は名前だけで合格にしない) の endpoint 合格条件を変えない。
macOS で Foundry Local を任意追加する場合だけ、[MACOS.md の任意手順](MACOS.md#27-任意-foundry-local-も含める場合)を参照する。
Windows の現行入口には Foundry Local 用引数がない。OS と runtime の要件は
[Ollama Windows 公式](https://docs.ollama.com/windows)、
[Ollama macOS 公式](https://docs.ollama.com/macos)も併せて確認する。

---

## 4. 生成キットと信頼境界を確認する

準備処理が終了コード `0` で完了し、[§2.2](#22-別モデルを指定する場合は名前だけで合格にしない)の
警告ゼロ条件も満たした後、OS ガイドの確認コマンドで生成先を検査する。
少なくとも次が揃い、値が選択内容と一致することを確認する。

- ルートの `manifest.json` と OS 固有の導入入口
  （Windows は `install-windows.cmd` と `Import-OfflineKit.ps1`、macOS は `install-macos.sh`）。
- `runtime/`、`models/ollama/`、`config/`、`tools/`、`docs/`。
- manifest の `platform`、`architecture`、`model.name`、`model.digest`、
  `model.supportsToolCalling=true`、`contextLength`、`components[]`、`files[]`。
- `files[]` に記録された各 payload の byte 数と SHA-256。

欠落や値の不一致があれば、キットや manifest を手編集しない。新しい空の出力先で準備処理をやり直す。
固定 schema と生成物の詳細は [固定契約](tools/airgap-kit/CONTRACT.md) と
[airgap-kit 技術リファレンス](tools/airgap-kit/README.md)を正とする。

信頼境界は、準備機、公式配布元、キット生成までの経路、`manifest.json`、移送媒体である。
manifest は credential、token、秘密鍵を格納せず、payload の完全性検査に使う。
発行者真正性や chain of custody が必要なら、本キット外で組織の署名・PKI・媒体管理を追加する。

---

## 5. 承認済み媒体で移送する

媒体へのコピー、checksum 作成、運用機への展開は OS 固有である。コマンドを混ぜず、
[WINDOWS.md の媒体手順](WINDOWS.md#3-媒体で移送する)または
[MACOS.md の媒体手順](MACOS.md#3-媒体で運ぶ)をそのまま使う。

- キットのディレクトリ構造を変えない。macOS は OS ガイドどおり zip とその checksum を運ぶ。
- キット内へメモ、スキャン結果、Finder / Explorer の補助ファイルなどを追加しない。
  manifest 未記載ファイルが 1 件でもあれば installer は停止する。
- checksum が一致しない媒体コピーは使わず、新しい空のコピー先へ全体をコピーし直す。
- SHA-256 は、信頼済み manifest に対する破損・欠落・変更の検出であり、電子署名ではない。
  manifest と payload の同時置換に対する真正性は保証しないため、媒体と移送経路を管理下に置く。

---

## 6. 運用機で dry-run してから Apply する

運用機が manifest の OS / CPU と一致することを確認し、媒体から OS ガイドどおり新しいローカルディレクトリへ展開する。
**引数なしの dry-run を終了コード `0` で通し、全予定を確認するまで Apply しない。**

Windows の運用機では次を実行する。

```batch
cd /d C:\OfflineKit
install-windows.cmd -BootstrapPowerShell
install-windows.cmd
install-windows.cmd -Apply
```

最初の `-BootstrapPowerShell` は `pwsh.exe` が無い場合だけ実行し、同梱 MSI を一意に検証して
対話導入した後に dry-run を行う。PowerShell 7 が既にある場合はこの行を省略する。
終了条件は [WINDOWS.md の PowerShell 7 bootstrap](WINDOWS.md#41-powershell-7-を先に用意する)に従う。
PowerShell の一般的な導入要件は
[Microsoft 公式](https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows)を参照する。

macOS の運用機では、OS ガイドどおり checksum を確認して展開したキットルートで実行する。

```bash
cd "$HOME/offline-kit-import/offline-kit-qwen3-8b"
./install-macos.sh
./install-macos.sh --apply
```

dry-run と Apply は同じ完全性・platform・競合 preflight を通る。再実行時の扱いも両 OS で fail-closed である。
Apply の引数形式は OS ごとに異なり、Windows は `-Apply`、macOS は `--apply` である。

| 対象 | 既存状態が同一 | 既存状態が異なる |
|---|---|---|
| Python、VS Code、Ollama | 検証できた同一版を `skip` | 自動更新せず `stop` |
| VS Code / Ollama 設定 | 同一内容を `skip` | 上書きせず `stop` |
| Ollama model cache | 同一 hash を `skip` | 混在・置換せず `stop` |
| `OLLAMA_CONTEXT_LENGTH` | manifest と同じ値を `skip` | 値を変えず `stop` |

競合時はキットや manifest を変更せず、[WINDOWS.md](WINDOWS.md) または [MACOS.md](MACOS.md) の競合対応へ戻る。
手動設定サンプルを使う別経路は [templates/README.md](templates/README.md) を参照し、sample JSON を生成キットへ追加しない。
hash 検証を省略するオプション、異なる既存物を強制上書きするオプションはない。

---

## 7. 自動 endpoint 検証と CLI を確認する

Apply は最後にキット同梱の `tools/verify_endpoint.py` を `--require-agent --expected-context <manifest値>` 付きで実行する。
自動実行の出力を確認し、運用機でも次の exact command で再確認する。
既定値以外で作ったキットでは、モデル名と context の期待値を manifest の実値へ読み替える。

Windows:

```batch
cd /d C:\OfflineKit
pwsh.exe --version
pymanager exec -V:3.14-64 --version
code --version
ollama --version
ollama list
set OLLAMA_CONTEXT_LENGTH
pymanager exec -V:3.14-64 tools\verify_endpoint.py --url http://127.0.0.1:11434 --model qwen3:8b --timeout 600 --require-agent --expected-context 8192
ollama ps
```

macOS:

```bash
cd "$HOME/offline-kit-import/offline-kit-qwen3-8b"
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
"$PYTHON_BIN" tools/verify_endpoint.py --url http://127.0.0.1:11434 --model qwen3:8b --timeout 600 --require-agent --expected-context 8192
"/Applications/Ollama.app/Contents/Resources/ollama" ps
```

strict な合格条件は次のすべてである。

1. model 一覧、Chat completion、SSE streaming、tool calling、実効 context の 5 項目がすべて `[  OK  ]`。
2. tool calling が構造化 `tool_calls` を返し、`city` が文字列 `Tokyo`。
3. `[ WARN ]` がなく、最終行が `結果: すべて OK。Chat / Agent の両方で使えます。`。
4. 終了コードが `0`。

timeout は「モデル不適合」とは判定できない状態だが、検証としては失敗であり `verify_endpoint.py` は終了コード `1` を返す。
同じサーバーを使う他の推論を止め、Ollama を再起動してから再実行する。timeout の実行を完了扱いにしない。
実効 context は `ollama ps` の `CONTEXT` と manifest を比較する
（[Ollama 公式 FAQ](https://docs.ollama.com/faq#how-can-i-specify-the-context-window-size)）。

---

## 8. VS Code のモデルピッカー、Chat、Agent を手動確認する

API 検証だけでは GUI E2E の代わりにならない。運用機で
[WINDOWS.md の VS Code 手順](WINDOWS.md#6-vs-code-のモデルピッカーchatagent-を確認する)または
[MACOS.md の VS Code 手順](MACOS.md)に従い、人が次を確認する。

1. 自分で作った確認専用 workspace だけを開き、Workspace Trust の対象を確認する。
2. Chat ビューのモデルピッカーで、manifest の Ollama モデルを選ぶ。
3. Chat モードで短い日本語 prompt を送り、選択したローカルモデルから応答が返ることを確認する。
4. **同じ Chat ビュー内で Agent モードへ切り替え**、確認用 `hello.txt` の読み取りなど限定した tool 操作を依頼する。
5. Agent が正しい tool と対象を選び、意図しない変更を行っていないことを確認する。

Agents window / Agent Host はこの E2E の対象ではない。モデルが `Auto` しか出ない場合は Workspace Trust、
モデルが出ても Agent が tool を使わない場合は [§7](#7-自動-endpoint-検証と-cli-を確認する)へ戻る。
Custom Endpoint、tool calling、Workspace Trust の根拠は
[VS Code 公式: AI language models in VS Code](https://code.visualstudio.com/docs/agent-customization/language-models) と
[VS Code 公式: Workspace Trust](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust)を参照する。

次の 3 機能は混同しない。

- **utility**: title、要約、commit message などの補助処理。生成キットはローカルモデルを設定するが、必要な操作を人手確認する。
- **インライン Chat**: editor 内で明示的に prompt を送る機能。`inlineChat.defaultModel` の対象。
- **インライン補完**: 入力中の ghost text / Tab 補完。インライン Chat とは別で、BYOK ローカルモデルの対象外。

生成キットは BYOK、utility、インライン Chat の設定を自動生成する。手動設定や sample の使い方は
[templates/README.md](templates/README.md)だけを参照する。
日本語 custom instructions は [日本語 instructions テンプレート](templates/copilot-instructions.ja.md)、
採用モデルでの再評価は [jp-eval の手順](tools/jp-eval/README.md)へ進む。
付録の参考値を自環境の合格実績として流用しない。

---

## 9. 外部通信を統制し、トラブルを切り分ける

### 9.1 外部通信は OS / network 側でも止める

生成キットは VS Code 拡張の自動更新を抑止し、Ollama の `server.json` に
`disable_ollama_cloud=true` を配置する。ただし、これは cloud 機能の設定であり、
firewall、egress policy、物理的なネットワーク遮断の代替ではない。

運用機はネットワーク非接続のまま使うか、組織承認済みの OS / network 制御を別途適用する。
キットは firewall 規則を作成しない。設定の公式仕様は
[Ollama FAQ: disable Ollama Cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features)、
VS Code の通信設計は [VS Code Network Connections](https://code.visualstudio.com/docs/setup/network)を参照する。

### 9.2 症状ごとの正本へ戻る

この共通入口では個別環境の原因を推測せず、次の正本で停止条件と復旧手順を確認する。

| 主な症状 | 参照先 |
|---|---|
| manifest 欠落、SHA-256 / byte 不一致、extra file | [Windows 媒体・dry-run](WINDOWS.md#3-媒体で移送する) / [macOS 媒体・dry-run](MACOS.md#3-媒体で運ぶ) / [airgap-kit の fail-closed 条件](tools/airgap-kit/README.md#fail-closed-条件) |
| 既存 runtime、設定、model cache、context の競合 | [WINDOWS.md](WINDOWS.md) または [MACOS.md](MACOS.md) の dry-run / 競合対応 |
| Ollama loopback 不通、endpoint timeout、`[ WARN ]`、tool 引数不一致 | 各 OS ガイドの導入後検証と [Ollama Troubleshooting](https://docs.ollama.com/troubleshooting) |
| モデルピッカーが `Auto` だけ、Chat 接続失敗、Agent が tool を使わない | 各 OS ガイドの VS Code 手動確認。先に [§7](#7-自動-endpoint-検証と-cli-を確認する)を再実行 |
| macOS の任意 Foundry Local で service / cache の問題 | [MACOS.md の任意手順](MACOS.md#27-任意-foundry-local-も含める場合)と [Foundry Local CLI 公式 troubleshooting](https://learn.microsoft.com/azure/foundry-local/reference/reference-best-practice) |

Foundry Local に関する本リポジトリの実測は、[付録 A.4](#a4-tool-calling-の実測)と
[付録 A.7](#a7-測定の限界重要)の測定条件付き事実として扱う。
個別の不安定事象や 1 回の結果から、別 OS、別モデル、別版の一般原因を断定しない。

### 9.3 完了判定

次をすべて満たした場合だけ、この導入を完了とする。

- [ ] 対象 OS の prepare が終了コード `0` で完了し、生成キットと manifest を手編集していない。
- [ ] 承認済み媒体で完全性を確認し、extra file のないコピーで dry-run と Apply を順番に完了した。
- [ ] CLI で runtime の版、manifest のモデル、context を確認した。
- [ ] `verify_endpoint.py --require-agent --expected-context <manifest値>` が警告なし・5 項目 OK・終了コード `0` で完了した。
- [ ] VS Code のモデルピッカー、Chat、Chat ビュー内 Agent を運用機で人手 E2E 確認した。
- [ ] `disable_ollama_cloud` とは別に、運用機のネットワーク遮断または組織の egress 制御を確認した。

---

## 付録 A. 実測データと測定条件

> [!IMPORTANT]
> この付録は、**2026-08-14 に Windows 1 台で行った旧ランタイム／移送実験**の記録であり、
> **今回の Windows / macOS 自己完結キット E2E ではない。**

本書の数値はすべて下記 1 台での実測値である。**文献からの引用ではない。**
VRAM 容量・実行プロバイダー・ドライバが異なれば結果は変わる。

### A.1 検証環境

| 項目 | 値 |
|---|---|
| OS | Windows 11 Enterprise Insider Preview 10.0.29639 (x64) |
| CPU | Intel Core i7-13800H（14 物理 / 20 論理） |
| RAM | 63.8 GB |
| GPU | NVIDIA GeForce RTX 4060 Laptop **8,188 MiB VRAM**（driver 610.88）／ Intel Iris Xe |
| NPU | なし |
| Foundry Local | CLI 0.10.3 / Core 1.0.0 / ONNX Runtime 1.26.0 |
| Ollama | 0.32.9（性能測定時）。検証中に 0.32.11 へ自動更新された |
| 測定日 | 2026-08-14 |

### A.2 VRAM と生成速度

1 モデルずつロードし、`nvidia-smi` の VRAM 増分と `ollama ps` の配分を測定した。
ロードは既定コンテキスト（4096）、推論時は `num_ctx: 8192`。

| モデル | ライセンス | ディスク | ロード時 | 推論ピーク | GPU/CPU 配分 | tok/s |
|---|---|---|---|---|---|---|
| qwen3:4b | apache-2.0 | 2.5 GB | 3,127 MiB | 3,797 MiB | 100% GPU | 56.7 |
| phi4-mini | MIT | 2.5 GB | 3,049 MiB | 3,633 MiB | 100% GPU | 45.7 |
| qwen2.5:7b | apache-2.0 | 4.7 GB | 4,633 MiB | 4,861 MiB | 100% GPU | 37.0 |
| qwen3:8b | apache-2.0 | 5.2 GB | 5,423 MiB | 6,015 MiB | 100% GPU | 31.0 |
| gpt-oss:20b | apache-2.0 | 13 GB | 6,119 MiB | 6,119 MiB | **56% CPU / 44% GPU** | 23.8 |

- この 5 モデルを本機で測ったディスクサイズに対する VRAM 実測比は **約 1.1〜1.6 倍**。KV キャッシュがコンテキスト長に比例して増える（qwen3:8b は 4096→8192 で +592 MiB）。
- 本機の **8,188 MiB VRAM** と今回の 5 モデルでは、100% GPU に載った最大が **8B クラス**だった。他モデルや別量子化の上限を示す値ではない。
- gpt-oss-20b のモデルカードは「16 GB のメモリ内で動作」と記載しており、**16 GB VRAM を要件とはしていない**。本機での CPU / GPU 配分は上表の実測値として別に扱う。

### A.3 Foundry Local のモデルカタログ

`foundry model list --verbose -o json` の結果。本機で選択可能なバリアントは **47 件**
（`foundry status` は全体で 129 件と報告）。

| license | バリアント数 |
|---|---|
| apache-2.0 | 34 |
| MIT | 13 |

→ **本機で返った `license` field が全 47 件で Apache-2.0 / MIT だった、という観測に限る。**
この field だけで商用利用可否や再配布条件を保証しない。採用時に、固定するモデル ID・版・配布物ごとの個別条件を確認すること。
タスク種別は Chat 28 / Speech 9 / Multimodal 8 / Embedding 2。

`supportsToolCalling` field の観測: gpt-oss-20b = **false** / phi-4 = **false** /
phi-4-mini = true / qwen2.5-coder-14b = true / qwen3-8b = true / qwen3-14b = true。

### A.4 tool calling の実測

**次表は、A.1 の旧ランタイム版と記載モデルに限定し、各ランタイム / モデルの組合せを HTTP 要求 1 回だけ測った結果である。**
反復測定や別モデルによる再現確認は行っていない。

| ランタイム / モデル | 構造化 `tool_calls` | 引数 |
|---|---|---|
| Ollama / qwen3:8b | 返る | 正しい（`{"city":"Tokyo"}`） |
| **Ollama / qwen3:4b** | **返る** | **正しい** |
| Ollama / phi4-mini | 返る | **壊れている**（`{"type":{"type":"string","value":"Tokyo"}}`） |
| **Foundry Local / qwen3-4b** | **返らない** | 本文に `<tool_call>` 生テキストとして出現 |

**各行は単一回のモデル限定観測であり、別 tag、別量子化、別 prompt、別ランタイム版、SDK、VS Code 拡張経由へ一般化できない。**
特に Foundry Local で確認したモデルは qwen3-4b だけである。

Foundry Local の応答は `finish_reason: stop` / `completion_tokens: 95` であり、
打ち切りではない。この 1 応答では、本文の `<tool_call>` が構造化 field へ変換されていなかった。

> **同一モデルでの単一回の直接比較**: `qwen3-4b` は **Ollama 経由では構造化して返り、
> Foundry Local 経由では返らなかった**。同じモデル名でも、runtime、配布 artifact / 量子化、
> prompt template、設定などの条件差があり得るため、この 1 回から原因は特定できない。

### A.5 旧 Windows Foundry Local 移送実験

> [!WARNING]
> これは Windows 1 台で Foundry Local の資材とキャッシュを移した旧実験である。
> **Ollama 必須の現行自己完結キットの Windows 成功実績ではなく、macOS の成功実績でもない。**
> 現行キットの保証範囲や手順は [固定契約](tools/airgap-kit/CONTRACT.md)、
> [Windows ガイド](WINDOWS.md)、[macOS ガイド](MACOS.md)を正とする。

| 内訳 | サイズ |
|---|---|
| winget バンドル（msix + 依存 + マニフェスト） | 76.5 MB |
| 実行プロバイダー `.foundry\ep`（cuda-ep 2,311.5 + webgpu-ep 27.0） | 2,338.5 MB |
| **小計（モデル本体を除く）** | **2,414.9 MB** |

- モデルキャッシュ（`.foundry\cache\models`）は**ディレクトリごとコピーして移送でき、移送先から推論できる**ことを実証（ロード 6.57 秒）。キャッシュ内に絶対パス・ユーザー名は含まれない。
- **実行プロバイダーはモデルキャッシュの外**にあり、`foundry cache cd` の移送対象に含まれない。
- 取得した msix の SHA256 はマニフェスト記載値と一致。`Add-AppxPackage -Path <msix>` のみで導入成功。

### A.6 日本語タスクと指示追従率

この節も、A.1 の旧 Windows 1 台・記載モデル・記載条件で行った評価であり、現行自己完結キットの E2E 結果ではない。

`temperature=0, seed=42` 固定。**判定したのは形式遵守・出力言語・速度のみで、
意味的な正確さ・日本語としての自然さは測定していない**（人手評価が必要）。

日本語タスク（8 問）: 5 モデルすべて 96〜100% で、**有意差を検出できなかった**（天井効果）。
簡体字の混入は 1 件も検出されなかった。
→ **「Qwen3 が日本語で優れている」という主張は本検証では裏付けられていない。**

指示追従率（10 問 × 5 ルール）:

| モデル | 総合追従率 | 「日本語で回答」の遵守 |
|---|---|---|
| qwen3:8b | 86% | 9/10 |
| phi4-mini | 85% | 7/10 |
| qwen3:4b | 81% | **3/10** |
| qwen2.5:7b | 74% | 8/10 |
| gpt-oss:20b | 74% | 6/10 |

> **この表の再現について（重要）**
>
> この 74〜86% は、日本語 / 接頭辞 / フェンス / 「不明」/ 見出し禁止の **5 ルール**で
> 測定した値である。一方、同梱の [tools/jp-eval](tools/jp-eval/) は
> **接頭辞ルールを含まない 4 ルール**で実装しているため、
> **この表の数値を同梱ツールでそのまま再現することはできない。**
> また生データは `results/` に置かれるが、実行のたびに生成されるため
> リポジトリには含めていない（`.gitignore`）。
> 旧 5 ルール測定をそのまま再実行するハーネスと生データは、現行リポジトリに同梱されていない。
>
> 従ってこの表は **「ローカル小型モデルの追従率は 10 割には遠く及ばない」という
> 規模感を示すもの**として扱い、採用判断に使う値は自分のルールで測り直すこと。
>
> ```powershell
> cd tools\jp-eval
> python jp_eval.py run --models <モデル名> --suites INSTR   # 4 ルールで測定
> python jp_eval.py score
> ```

→ この旧 5 ルール評価は、旧記録で **「ルールの 15〜25% は無視される前提」と概算した**。この割合を現行モデルや別 prompt の固定値にしないこと。
→ **qwen3:4b は日本語指示でも 10 問中 7 問を英語で回答した。** この 10 問だけから「8B 以上」を一般要件にせず、採用候補を現行ツールと業務 prompt で再評価すること。

否定形と肯定形の比較結果は [templates/copilot-instructions.ja.md](templates/copilot-instructions.ja.md) を参照。
**この比較は指示文の小さな変更で結論が反転したため、安定した知見として扱わないこと。**

### A.7 測定の限界（重要）

- 数値は**1 台の実測値**であり、一般化できない。
- **現行自己完結キットは、Windows / macOS ともクリーンな準備機と運用機を使った全E2Eを実施していない。**
  Windowsのオンライン収集とキット生成は実測済みだが、媒体移送、別のオフライン運用機でのdry-run / Apply、オフライン動作までを一続きに通した成功実績はない。macOS実機は未実施である。
- **現行自己完結キットによる VS Code GUI E2E も Windows / macOS とも未実施である。**
  モデルピッカーへの表示、Chat / Agent の往復、ユーティリティ設定の効果は実機操作で確かめていない。
- 旧実験で**検証したのは CLI と HTTP API レベルまで**である。
- **tool calling の結果（A.4）は各ランタイム / モデル組合せにつき 1 回の測定である。**
  特に Foundry Local について確かめたのは qwen3-4b のみで、他モデル・他バージョンや
  Foundry Toolkit / Ollama の VS Code 拡張経由での振る舞いは**未検証**である。
- 日本語タスクは設問が 8 問と少なく難易度も低かったため**天井効果**が生じた。
- 自動判定しているのは形式面のみ。**意味的正確さは測定していない。**
- 指示追従率（A.6）は 5 ルールでの測定であり、**同梱ツール（4 ルール）ではそのまま再現できない。**
- 測定中に判定ロジックの欠陥を複数自己発見し修正した（コードフェンス内の `#` を見出しと誤検出、「点・会・来」を簡体字と誤検出、否定形バリアントが構造的に合格不可能だった等）。**生出力を正本とし、判定は集計時に再計算する設計**にしてある。

### A.8 主要な出典

次は **2026-08-16 に本文を取得して存在確認した、発行元またはプロジェクト公式 URL** である。
モデルの採用時は、この一覧だけでなく固定する tag・版・配布物のライセンス本文も確認すること。

| 内容 | URL |
|---|---|
| VS Code の BYOK・Custom Endpoint・オフライン動作・制約 | <https://code.visualstudio.com/docs/agent-customization/language-models> |
| VS Code Windows | <https://code.visualstudio.com/docs/setup/windows> |
| VS Code macOS | <https://code.visualstudio.com/docs/setup/mac> |
| VS Code 拡張の VSIX 取得・オフライン導入 | <https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_install-from-a-vsix> |
| VS Code のネットワーク要件・プロキシ | <https://code.visualstudio.com/docs/setup/network> |
| VS Code custom instructions | <https://code.visualstudio.com/docs/agent-customization/custom-instructions> |
| Foundry Local 概要 | <https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local> |
| Foundry Local CLI リファレンス | <https://learn.microsoft.com/azure/foundry-local/reference/reference-cli> |
| Foundry Local リポジトリ（ライセンス条項） | <https://github.com/microsoft/Foundry-Local> |
| Windows ML | <https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/overview> |
| `winget download` | <https://learn.microsoft.com/en-us/windows/package-manager/winget/download> |
| PowerShell 7 の Windows 導入 | <https://learn.microsoft.com/powershell/scripting/install/install-powershell-on-windows> |
| Python Install Manager の Windows offline index | <https://docs.python.org/3/using/windows.html#offline-installs> |
| Python macOS Universal 2 `.pkg` | <https://docs.python.org/3/using/mac.html> |
| Copilot の通信先許可リスト | <https://docs.github.com/en/copilot/reference/allowlist-reference> |
| Ollama Windows | <https://docs.ollama.com/windows> |
| Ollama macOS | <https://docs.ollama.com/macos> |
| Ollama FAQ（context、model path、local-only 等） | <https://docs.ollama.com/faq> |
| Ollama VS Code 拡張（参考。現行キットには非同梱） | <https://marketplace.visualstudio.com/items?itemName=Ollama.ollama> |
| Ollama リポジトリ（MIT） | <https://github.com/ollama/ollama> |
| Qwen3（119 言語・Apache-2.0） | <https://qwen.ai/blog?id=qwen3> |
| Qwen3-4B 上流モデルカード | <https://huggingface.co/Qwen/Qwen3-4B> |
| Qwen3-8B 上流モデルカード | <https://huggingface.co/Qwen/Qwen3-8B> |
| Qwen2.5-7B-Instruct 上流モデルカード | <https://huggingface.co/Qwen/Qwen2.5-7B-Instruct> |
| Phi-4-mini-instruct 上流モデルカード | <https://huggingface.co/microsoft/Phi-4-mini-instruct> |
| gpt-oss-20b モデルカード | <https://huggingface.co/openai/gpt-oss-20b> |
| 日本語 LLM 評価リーダーボード | <https://swallow-llm.github.io/evaluation/index.ja.html> |

---

## 関連ファイル

| パス | 内容 |
|---|---|
| [README.md](README.md) | フォルダの入口 |
| [WINDOWS.md](WINDOWS.md) | 現行 Windows 11 x64 の準備・移送・導入・確認ガイド |
| [MACOS.md](MACOS.md) | 現行 macOS 14+ / Apple Silicon の準備・移送・導入・確認ガイド |
| [tools/airgap-kit/CONTRACT.md](tools/airgap-kit/CONTRACT.md) | Windows / macOS 自己完結キットの固定契約 |
| [tools/airgap-kit/Prepare-Windows.cmd](tools/airgap-kit/Prepare-Windows.cmd) | Windows オンライン準備入口 |
| [tools/airgap-kit/install-windows.cmd](tools/airgap-kit/install-windows.cmd) | Windows オフライン導入入口 |
| [tools/airgap-kit/Export-OfflineKit.ps1](tools/airgap-kit/Export-OfflineKit.ps1) | Windows キット生成実装 |
| [tools/airgap-kit/Import-OfflineKit.ps1](tools/airgap-kit/Import-OfflineKit.ps1) | Windows キット検証・導入実装 |
| [tools/airgap-kit/Prepare-macOS.sh](tools/airgap-kit/Prepare-macOS.sh) | macOS オンライン準備入口 |
| [tools/airgap-kit/install-macos.sh](tools/airgap-kit/install-macos.sh) | macOS dry-run / Apply 実装 |
| [templates/README.md](templates/README.md) | 設定テンプレートの使い方と注意点 |
| [templates/copilot-instructions.ja.md](templates/copilot-instructions.ja.md) | 日本語 custom instructions テンプレート |
| [templates/chatLanguageModels.sample.json](templates/chatLanguageModels.sample.json) | BYOK Custom Endpoint 設定サンプル |
| [templates/settings.offline.sample.json](templates/settings.offline.sample.json) | VS Code オフライン設定サンプル |
| [templates/ollama-server.sample.json](templates/ollama-server.sample.json) | Ollama local-only 設定サンプル |
| [tools/verify_endpoint.py](tools/verify_endpoint.py) | エンドポイントと tool calling の動作確認 |
| [tools/test_verify_endpoint.py](tools/test_verify_endpoint.py) | endpoint verifier の単体テスト |
| [tools/airgap-kit/tests/](tools/airgap-kit/tests/) | Windows / macOS キット契約テスト |
| [tools/check_fences.py](tools/check_fences.py) | Markdown fence 整合性検査 |
| [tools/jp-eval/README.md](tools/jp-eval/README.md) | 日本語評価ツールの実行・再現条件 |
| [tools/jp-eval/jp_eval.py](tools/jp-eval/jp_eval.py) | 日本語評価ツール本体 |
| [tools/jp-eval/test_jp_eval.py](tools/jp-eval/test_jp_eval.py) | 日本語評価ツールの単体テスト |
