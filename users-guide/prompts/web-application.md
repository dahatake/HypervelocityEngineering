# Web アプリケーションの Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `aad-web`（設計） / `asdw-web`（実装・デプロイ）

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## 設計と実装の境界

| Workflow | やること | Azure を触るか |
|---|---|---|
| `aad-web` | 画面・API・テスト仕様の設計書を作る | 触らない |
| `asdw-web` | ソースコードとテストを実装し、Azure へデプロイする | 触る（Step による） |

`asdw-web` は `aad-web` の成果物（`docs/screen/*.md` / `docs/services/*.md` /
`docs/test-specs/*-test-spec.md`）を必須の前提とします。

---

## `aad-web` — Web 画面・API の設計

主な成果物: `docs/catalog/screen-catalog.md` / `docs/catalog/service-catalog-matrix.md` /
`docs/screen/` / `docs/services/` / `docs/test-specs/`

Step ID: `1`, `2.1`, `2.2`, `2.3`, `2.4`, `2.5`, `2.6`, `3`

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の Web 画面と API の設計書を作りたい
- Workflow: aad-web
- パラメータ: app_ids=APP-NNN
- 制約: Azure リソースの作成・変更はしないこと。設計書の生成まで
- 期待する成果物: docs/catalog/screen-catalog.md、docs/screen/、docs/services/、docs/test-specs/

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

画面一覧だけを先に見たい場合:

```text
- Workflow: aad-web
- Step: 1
- パラメータ: app_ids=APP-NNN
- 制約: 画面一覧の作成までで止めること
```

---

## `asdw-web` — Web アプリの実装とデプロイ

主な成果物: `src/` / `src/test/` / Azure リソース関連成果物

Step ID は `1`〜`5` の表示グループと、その配下の `1.1`〜`5.3` で構成されます。
正本は `hve/workflow_registry.py` を参照してください。

### 実装だけを行う（デプロイしない）

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の Web アプリを実装したい
- Workflow: asdw-web
- Step: 1.1, 1.2, 1.3
- パラメータ: app_ids=APP-NNN
- 制約: Azure へのデプロイは含めないこと。実装とローカルテストまで
- 期待する成果物: src/ と src/test/ 配下のコード

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

### デプロイまで行う

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の Web アプリを実装して Azure にデプロイしたい
- Workflow: asdw-web
- パラメータ:
  - app_ids=APP-NNN
  - resource_group=<resource-group>
- 制約: 既存の権限ゲート・承認ゲートを緩めないこと
- 期待する成果物: src/、src/test/、および Azure 上にデプロイされたリソース

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
計画に含まれる Step の範囲を、私が読んで確認します。
```

> **デプロイを含む計画は、承認前に Step の範囲を必ず確認してください。**
> Prompt 版は既存の権限ゲートを迂回しません。Azure 側の承認・認証は従来どおり必要です。

---

## 関連

- 詳細ガイド: [03-app-design-microservice-azure.md](../03-app-design-microservice-azure.md) / [05-app-dev-microservice-azure.md](../05-app-dev-microservice-azure.md)
- 設計 → 実装をまとめて計画する: [cross-workflow.md](cross-workflow.md)
- 入力ファイル名が canonical と違う場合: [custom-inputs.md](custom-inputs.md)
