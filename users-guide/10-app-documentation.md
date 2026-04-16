# App Documentation（ソースコードからの段階的ドキュメント生成）

---

## 概要（4層構造）

`adoc` ワークフローは、Context Window を小さく保つために、前段の要約のみを後段へ渡す 4 層構造で実行します。

- レイヤー1（Step.1〜2.x）: ファイルインベントリ + ファイル単位サマリー
- レイヤー2（Step.3.x）: コンポーネント/モジュール分析
- レイヤー2.5（Step.4）: レイヤー2成果物のインデックス
- レイヤー3〜4（Step.5.x〜6.x）: 横断分析 + 目的特化ドキュメント

---

## 前提条件

- `hve` CLI が実行可能であること
- GitHub Copilot cloud agent が利用可能であること
- 出力先は `docs-generated/`（既存 `docs/` と分離）

---

## 方法1: Copilot cloud agent 手動実行

1. Issue/Sub-issue を作成する
2. Step ごとに対応する `Doc-*` Custom Agent を選択して実行する
3. 各 Step 完了後に `adoc:done` ラベルが付与されることを確認する

---

## 方法2: ワークフローオーケストレーション（Web）

1. Issues → New issue で **App Documentation** を選択
2. `branch` / `target_dirs` / `doc_purpose` などを入力
3. Submit 後、`auto-app-documentation` ラベルでオーケストレーションを開始

---

## 方法3: ワークフローオーケストレーション（ローカル hve）

### CLI 実行例

```bash
python -m hve orchestrate \
  --workflow adoc \
  --branch main \
  --target-dirs src/,hve/ \
  --exclude-patterns "node_modules/,vendor/,dist/,*.lock,__pycache__/" \
  --doc-purpose all \
  --max-file-lines 500
```

目的別実行例:

```bash
python -m hve orchestrate --workflow adoc --doc-purpose onboarding
python -m hve orchestrate --workflow adoc --doc-purpose refactoring
python -m hve orchestrate --workflow adoc --doc-purpose migration
```

---

## 成果物出力先

- `docs-generated/inventory.md`
- `docs-generated/files/`
- `docs-generated/components/`
- `docs-generated/component-index.md`
- `docs-generated/architecture/`
- `docs-generated/guides/`

---

## DAG 実行の Wave 計画

```text
Wave 1: Step.1
Wave 2: Step.2.1 ‖ Step.2.2 ‖ Step.2.3 ‖ Step.2.4 ‖ Step.2.5
Wave 3: Step.3.1 ‖ Step.3.2 ‖ Step.3.3 ‖ Step.3.4 ‖ Step.3.5
Wave 4: Step.4
Wave 5: Step.5.1 ‖ Step.5.2 ‖ Step.5.3 ‖ Step.5.4
Wave 6: Step.6.1 ‖ Step.6.2 ‖ Step.6.3
```
