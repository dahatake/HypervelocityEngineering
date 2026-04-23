# Knowledge Management（AKM）ガイド

← [README](../README.md)

---

## 目次

- [概要](#概要)
- [Agent チェーン図（AKM）](#agent-チェーン図akm)
- [前提条件](#前提条件)
- [完了条件](#完了条件)
- [反復精緻化サイクル](#反復精緻化サイクル)
- [Issue Template 入力](#issue-template-入力)
- [CLI 例](#cli-例)
- [状態判定](#状態判定)
- [自動実行ガイド（ワークフロー）](#自動実行ガイドワークフロー)
- [セットアップ・トラブルシューティング](#セットアップトラブルシューティング)

---
## 概要
AKM は `qa` / `original-docs` / `both` を選択して、`knowledge/` の D01〜D21 を生成・更新する統合フローです。

![AKM の知識統合フロー。Issue Template から auto-knowledge-management ワークフローが起動し、sources に応じて qa、original-docs、または両方を処理して KnowledgeManager に渡し、knowledge 配下のステータスファイルと D01〜D21 を生成・更新する。](./images/knowledge-interface-flow.svg)

![AKM アーキテクチャ。sources に応じて qa、original-docs、または両方を入力し、auto-knowledge-management ワークフローで KnowledgeManager が統合処理を実行、knowledge 配下の D01〜D21 とステータスファイルを生成・更新し、反復精緻化ループで再取り込みする。](./images/infographic-akm.svg)

AKM は 1 回実行して終わりではなく、`aqod` で生成した質問票を `qa/` に蓄積し、再度 `akm` で統合する反復精緻化ループを前提に運用します。

## Agent チェーン図（AKM）

以下の図は、このワークフローで使用される Custom Agent がファイルの入出力を介してどのように連鎖するかを示します。

![AKM: KnowledgeManager の1ステップチェーン（並列0箇所含む）](./images/chain-akm.svg)


## 前提条件

- `qa/` または `original-docs/` に対象ファイルが存在すること
- GitHub Copilot が有効であること
- セットアップ手順は [getting-started.md](./getting-started.md) を参照

## 完了条件

- `knowledge/business-requirement-document-status.md` が生成または更新されていること
- 対象 D 分類のファイルが `knowledge/` に生成されていること

## 反復精緻化サイクル

AKM は一度きりではなく、初回作成 → 不足補完 → 開発中の気づき反映 → 既存資産取り込みを繰り返して `knowledge/` を継続的に精緻化します。
詳細は [overview.md の反復精緻化サイクル](./overview.md#反復精緻化サイクル) を参照してください。

## Issue Template 入力
- `sources`: `qa のみ` / `original-docs のみ` / `両方`
- `target_files`: サブセット指定（任意）
- `additional_comment`: `custom_source_dir: <path>` を指定可
- `force_refresh`: 完全再生成

## CLI 例
```bash
python -m hve orchestrate --workflow akm --sources qa
python -m hve orchestrate --workflow akm --sources original-docs
python -m hve orchestrate --workflow akm --sources both
python -m hve orchestrate --workflow akm --sources qa --custom-source-dir docs/specs
```

## 状態判定
- `Confirmed` / `Tentative` / `Unknown` / `Conflict`
- `Conflict` は original-docs を含む場合に利用

## 自動実行ガイド（ワークフロー）

### ラベル体系
- `akm:initialized`
- `akm:ready`
- `akm:running`
- `akm:done`
- `akm:blocked`

### 冪等性
- 同一入力で再実行しても重複生成を避ける設計です
- `force_refresh` を有効化した場合のみ既存ファイルを再生成します

### 使い方（Issue 作成手順）
1. **Issues** → **New Issue** を開く
2. **Knowledge Management** テンプレートを選択
3. `sources`（`qa` / `original-docs` / `both`）を選択
4. **Submit** して実行

## original-docs モード追加処理
- STALENESS CHECK
- 矛盾検出（同一 D / D 間 / qa vs original-docs / 用語）

## トラブルシューティング
- `custom_source_dir` は相対パスのみ（`/`, `..`, `~` を禁止）
- `knowledge/` / `.github/` / `src/` など禁止パス配下は拒否


## セットアップ・トラブルシューティング

共通手順は [getting-started.md](./getting-started.md) を参照してください。
