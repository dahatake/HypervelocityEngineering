# Agent 開発コントリビューションガイド

> **対象**: `.github/agents/*.agent.md` を新規作成・更新する開発者

## frontmatter スキーマ（確定）

- **必須**
  - `name`
  - `description`
  - `metadata.version`（SemVer: `MAJOR.MINOR.PATCH`、例: `1.0.0`）
- **推奨**
  - `model`
  - `tools`
- **廃止**
  - `metadata.version` なしの旧 frontmatter 形式は受け入れない（互換 fallback なし）

## 例

```yaml
---
name: Example-Agent
description: 例示用の Agent 定義。
tools: ["*"]
metadata:
  version: "1.0.0"
---
```

## io_contract スキーマ（Phase 1.1 確定・任意→必須化予定）

> **目的**: 各 Agent の必須入出力ファイルを機械可読化し、producer/consumer 整合性を CI で検証する。
>
> **適用範囲**: `.github/agents/*.agent.md` 全件（テンプレ `_template.md` 除く）。
>
> **検証**: `.github/scripts/validate-io-contract.py`（Phase 4 で追加）が読み取り、producer 不在の必須入力を ERROR 化。

### frontmatter 構造

```yaml
io_contract:
  inputs:
    - path: "docs/catalog/use-case-catalog.md"   # 原文表記をそのまま記載（変数記法は {} 中括弧で統一）
      required: true                              # true | false
      kind: "agent_artifact"                      # agent_artifact | static | runtime_param | external
      producer: "Arch-ARD-UseCaseCatalog"         # required=true && kind=agent_artifact のみ必須
  outputs:
    - path: "docs/agent/agent-application-definition.md"
      required: true
      mode: "create"                              # create | append | overwrite | upsert
```

### キー仕様

| キー | 型 | 必須 | 説明 |
|---|---|---|---|
| `inputs[].path` | string | ✅ | 入力ファイル/ディレクトリのパス（原文表記） |
| `inputs[].required` | bool | ✅ | `true` = 必須入力、`false` = 任意 |
| `inputs[].kind` | enum | ✅ | `agent_artifact`（他 Agent 生成物） / `static`（リポジトリ同梱） / `runtime_param`（実行時パラメータ） / `external`（外部システム） |
| `inputs[].producer` | string | △ | `required=true` かつ `kind=agent_artifact` のみ必須。当該 path を `outputs` に持つ Agent 名 |
| `outputs[].path` | string | ✅ | 出力ファイル/ディレクトリのパス |
| `outputs[].required` | bool | ✅ | `true` = 必須出力 |
| `outputs[].mode` | enum | ✅ | `create`（新規） / `append`（追記） / `overwrite`（上書き） / `upsert`（新規 or 更新） |

### 命名規約

- **変数記法**: `{...}` 中括弧で統一（`<...>` 山括弧は禁止）
- **画面パス**: `docs/screen/{画面ID}-{画面名スラッグ}-description.md`
- **テストディレクトリ**: `test/`（単数）統一
- **azure-service-catalog**: `docs/azure/azure-service-catalog.md`（`docs/catalog/service-catalog.md` との命名衝突回避）

詳細は `knowledge/D19-ソフトウェアアーキテクチャ-ADRパック.md` の ADR-001 を参照。

