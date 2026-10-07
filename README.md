# HypervelocityEngineering — conductor toolkit

要求定義書・カタログ・System Test の一貫性を保ちながら、アプリケーションを**最高品質・最短時間・最小 Token** で実装するための、GitHub Copilot（VS Code の Agents ウィンドウ／Copilot CLI）向けの仕組みです。

利用者は、進行役エージェント `conductor` に依頼の Prompt を **1 回**書くだけです。conductor が、要求定義 → 独立監査 → System Test の先行設計 → 並行実装 → 直列の統合 → 最終監査 → 報告 を、最大 24〜48 時間、無人で進めます。品質の要の規則（要求の書き手は 1 つ、System Test は実装役が変えられない、終了前の検証、危険な操作の拒否）は hook と決定的スクリプトで強制します。

## 導入（自分のリポジトリのルートで 1 回）

```powershell
# Windows
irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.ps1 | iex
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.sh | bash
```

## 使い方

VS Code の Agents ウィンドウで Session Target=**Copilot**、Agent=**conductor**、モード=**Autopilot**、Code isolation=**New Worktree** を選び、`/build` でやりたいことを書いて送信します。

詳しくは [users-guide](users-guide/README.md) を読んでください。

| 内容 | 場所 |
|---|---|
| 利用者ガイド | [users-guide/](users-guide/README.md) |
| エージェント（進行役＋作業役 5） | [.github/agents/](.github/agents/) |
| 手順書（skills） | [.github/skills/](.github/skills/) |
| 強制ゲート（hooks） | [.github/hooks/quality-gates.json](.github/hooks/quality-gates.json)、[scripts/hooks/gate.py](scripts/hooks/gate.py) |
| 決定的スクリプト | [scripts/](scripts/) |
| 管理データの雛形 | [docs/](docs/)、[tests/system/ledger.json](tests/system/ledger.json) |
| 導入スクリプト | [tools/](tools/) |
| toolkit のテスト | [tests/toolkit/](tests/toolkit/)（`python -m pytest tests/toolkit -q`） |
