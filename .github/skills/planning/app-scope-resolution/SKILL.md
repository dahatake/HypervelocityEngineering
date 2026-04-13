---
name: app-scope-resolution
description: >
  APP-ID に基づくスコープ解決ルール。Issue body または <!-- app-id: XXX -->
  HTML コメントから APP-ID を取得し、docs/catalog/app-catalog.md との紐付けで
  対象サービス・画面・エンティティを特定する。
  APP-ID 未指定時は全サービス/全画面対象（後方互換）。
  USE FOR: APP-ID scope resolution, service identification,
  app-catalog lookup, screen identification, entity identification.
  DO NOT USE FOR: service implementation, data modeling,
  architecture design, deployment.
  WHEN: APP-ID のスコープ解決、Issue body 解析、対象サービス特定、
  app-catalog.md との紐付け。
metadata:
  origin: user
  version: "1.0.0"
---

# app-scope-resolution

## 目的

Issue body の `<!-- app-id: XXX -->` HTML コメントから APP-ID を取得し、
`docs/catalog/app-catalog.md` との紐付けで対象スコープを特定する。

## APP-ID 取得手順

1. **Issue body を確認**:
   - `<!-- app-id: XXX -->` 形式の HTML コメントを探す
2. **フォールバック**:
   - HTML コメントが見つからない場合 → Issue body 本文から APP-ID らしき記述を検索
   - それでも見つからない場合 → **全サービス/全画面対象**（後方互換）

## `docs/catalog/app-catalog.md` との紐付けルール

| APP × 関係 | 対応ルール |
|-----------|-----------|
| APP × サービス | N:N 関係（カンマ区切り）。1サービスが複数 APP に属し得る |
| APP × エンティティ | N:N 関係（カンマ区切り）。1エンティティが複数 APP に属し得る |
| APP × 画面 | 1:1 関係。1画面は1つの APP に所属 |

## APP-ID 未指定時の動作

- `docs/catalog/app-catalog.md` が存在しない場合 → 全サービス/全画面対象
- APP-ID が未指定の場合 → 全サービス/全画面対象（後方互換）
- これは既存 Agent との後方互換性を保つための設計

## スコープ確定後のアクション

1. 対象サービス一覧を `docs/catalog/app-catalog.md` から取得する
2. 対象画面一覧を取得する（APP × 画面は 1:1）
3. 対象エンティティ一覧を取得する
4. 共有サービス（複数 APP で使われるサービス）も含める

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `agent-common-preamble` | 参照元 | 全 Agent 共通 Skills 参照リストから本 Skill が呼び出される |
| `input-file-validation` | 併用 | docs/catalog/app-catalog.md の存在確認に input-file-validation を併用する |
| `task-questionnaire` | 後続 | スコープ確定後のコンテキスト収集に task-questionnaire へ遷移する |
