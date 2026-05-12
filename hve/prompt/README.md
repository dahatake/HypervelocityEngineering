# hve/prompt — hve パッケージ専用プロンプトテンプレート

このディレクトリは **hve パッケージ専用** のプロンプトテンプレートを格納します。  
`template/`（単数形、業務要件マスター定義・ADR 集）とは全く別の用途です。

## ディレクトリ構造

```
hve/prompt/
└── fanout/
    └── {wf}/
        └── _common.md   # fan-out per-key プロンプトテンプレート
```

## 命名規約

- `{wf}` は `hve/workflow_registry.py` の `WorkflowDef.id` と一致する文字列（例: `akm`, `aas`, `aad-web`, `asdw-web` 等）
- ファイル名は `_common.md` 固定（ワークフロー内で共通の fan-out テンプレートを示す）

## 参照元

- `hve/workflow_registry.py` の `StepDef.additional_prompt_template_path` フィールド
- `hve/runner.py` の `_apply_fanout_prompt_template()` 関数

## プレースホルダ

テンプレート本文中の `{{key}}` プレースホルダは、実行時に fan-out キー（例: `D01`, `APP-01`）に置換されます。  
置換処理は `hve/runner.py` の `_apply_fanout_prompt_template()` 内 `addendum.replace("{{key}}", key)` で実装されています。
