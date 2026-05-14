---
name: app-scope-resolution
description: >
  APP-ID に基づくスコープ解決ルール。Issue body または <!-- app-id: XXX --> HTML コメントから APP-ID を取得し、docs/catalog/app-catalog.md との紐付けで 対象サービス・画面・エンティティを特定する。 USE FOR: APP-ID scope resolution, service identification, app-catalog lookup. DO NOT USE FOR: service implementation. WHEN: APP-ID のスコープ解決、Issue body 解析。
metadata:
  origin: user
  version: 1.1.0
---

# app-scope-resolution

## 目的

Issue body の `<!-- app-id: XXX -->` または `<!-- app-ids: ... -->` HTML コメントから APP-ID を取得し、
`docs/catalog/app-catalog.md` との紐付けで対象スコープを特定する。

## ファイルの役割整理

| ファイル | 役割 |
|---------|------|
| `docs/catalog/app-arch-catalog.md` | APP-ID が対象 workflow の範囲内かを判定する正本 |
| `docs/catalog/app-catalog.md` | 対象 APP-ID に紐づくサービス・画面・エンティティを特定するための参照 |

## APP-ID 取得手順

1. **Issue body を確認**:
   - `<!-- app-ids: XXX,YYY -->` または `<!-- app-id: XXX -->` 形式の HTML コメントを探す
2. **フォールバック**:
   - HTML コメントが見つからない場合 → Issue body 本文から APP-ID らしき記述を検索
   - それでも見つからない場合 → **推薦アーキテクチャによる自動選択**（後述）

## `docs/catalog/app-catalog.md` との紐付けルール

| APP × 関係 | 対応ルール |
|-----------|-----------|
| APP × サービス | N:N 関係（カンマ区切り）。1サービスが複数 APP に属し得る |
| APP × エンティティ | N:N 関係（カンマ区切り）。1エンティティが複数 APP に属し得る |
| APP × 画面 | 1:1 関係。1画面は1つの APP に所属 |

## APP-ID 未指定時の動作（新仕様）

AAD-WEB / ASDW-WEB / ABD / ABDV では、APP-ID 未指定時に全対象とはしない。

`docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` を参照し、
workflow に対応する推薦アーキテクチャの APP-ID のみを対象とする。

| workflow | 対象推薦アーキテクチャ |
|---------|---------------------|
| `aad-web` / `asdw-web` | `Webフロントエンド + クラウド` |
| `abd` / `abdv` | `データバッチ処理` または `バッチ` |

- `docs/catalog/app-arch-catalog.md` が存在しない場合 → fail-fast（非 dry-run）または warning 継続（dry-run）
- APP-ID が `docs/catalog/app-arch-catalog.md` に存在しない場合 → unknown として除外
- **見出し命名揺れの吸収**: `hve.app_arch_filter` は `## A) サマリ表（全APP横断）` を canonical とするが、`## A) 選定結果一覧（サマリ表）` 等の揺れも受理する（stderr に WARN を出力）。出力契約に従って canonical 見出しを使用することを推奨。
- 上記以外の workflow では後方互換（全サービス/全画面対象）を維持する

## スコープ確定後のアクション

1. 対象 APP-ID を `docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` で確認する
2. 対象サービス一覧を `docs/catalog/app-catalog.md` から取得する
3. 対象画面一覧を取得する（APP × 画面は 1:1）
4. 対象エンティティ一覧を取得する
5. 共有サービス（複数 APP で使われるサービス）も含める

## 成果物ファイル分割基準

スコープ確定後、成果物ファイルを APP-ID 単位で分割するか否かの基準:

- 設計エージェントは `docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照し、成果物に APP-ID との紐付けを行う。
- APP × サービス / APP × エンティティ: N:N 関係（カンマ区切りで記載、例: `APP-01, APP-03`）
- APP × 画面: 1:1 関係（1画面は1つの APP-ID に所属）
- 1つの APP のみ利用のサービス/エンティティ/画面 → 成果物ファイルのアプリケーション単位での分割を検討する。
- 複数 APP で共有されるものは統一ファイルのまま「利用APP」列/項目をカンマ区切りで記載する。

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `agent-common-preamble` | 参照元 | 全 Agent 共通 Skills 参照リストから本 Skill が呼び出される |
| `input-file-validation` | 併用 | docs/catalog/app-catalog.md の存在確認に input-file-validation を併用する |
| `task-questionnaire` | 後続 | スコープ確定後のコンテキスト収集に task-questionnaire へ遷移する |
