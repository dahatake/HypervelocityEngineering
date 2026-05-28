# `.github/io-contracts/` Schema

> **適用範囲**: `.github/io-contracts/*.yaml` 全件
>
> **検証**: `.github/scripts/validate-io-contract.py` が読み取り、producer 不在の必須入力を ERROR 化

各 YAML ファイルは Agent 単位（ファイル名: `<AgentName>.yaml`）に作成し、トップレベルに `inputs:` / `outputs:` を持つ。

## 構造

```yaml
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

## キー仕様

| キー | 型 | 必須 | 説明 |
|---|---|---|---|
| `inputs[].path` | string | ✅ | 入力ファイル/ディレクトリのパス（原文表記） |
| `inputs[].required` | bool | ✅ | `true` = 必須入力、`false` = 任意 |
| `inputs[].kind` | enum | ✅ | `agent_artifact`（他 Agent 生成物、`producer` 必須） / `static`（リポジトリ同梱） / `runtime_param`（実行時パラメータ） / `external`（外部システム入力 / 複数 Agent が生成する集約ディレクトリ・ワイルドカード等で単一 producer が特定できないもの。producer 検査をスキップ） |
| `inputs[].producer` | string | △ | `required=true` かつ `kind=agent_artifact` のみ必須。当該 path を `outputs` に持つ Agent 名 |
| `outputs[].path` | string | ✅ | 出力ファイル/ディレクトリのパス |
| `outputs[].required` | bool | ✅ | `true` = 必須出力 |
| `outputs[].mode` | enum | ✅ | `create`（新規） / `append`（追記） / `overwrite`（上書き） / `upsert`（新規 or 更新） |

## 命名規約

- **変数記法**: `{...}` 中括弧で統一（ファイル名・パス断片内の置換変数はすべて中括弧）
  - 例: `docs/screen/{screenId}-{screenNameSlug}-description.md`、`docs/test-specs/{serviceId}-test-spec.md`
- **例外**: 以下の山括弧 `<...>` は work-artifacts-layout / 共通行動規約由来の確立済み命名規約のため許容する:
  - `Issue-<識別子>/`（`work/<Agent>/Issue-<識別子>/...` 配下の作業ディレクトリ）
  - `<NNN>`（`issue-prompt-<NNN>.md` 等の連番）
  - `<run_id>`（HVE オーケストレーター ID）
  - その他、`{WORK}` 配下のパスに含まれる規約由来の山括弧
- **画面パス**: `docs/screen/{screenId}-{screenNameSlug}-description.md`
- **テストディレクトリ**: `test/`（単数）統一
- **azure-service-catalog**: `docs/azure/azure-service-catalog.md`（`docs/catalog/service-catalog.md` との命名衝突回避）

詳細は `knowledge/D19-ソフトウェアアーキテクチャ-ADRパック.md` の ADR-001 を参照。

## 例外設定

`.github/io-contract-exceptions.yaml` で以下を制御:
- `static_paths`: 整合性チェックから除外する静的入力パス
- `external_paths`: 外部システム入力として除外するパス
- `skip_agents`: 整合性チェックから除外する Agent

## 例

実例は `.github/io-contracts/*.yaml`（77 ファイル）を参照。
