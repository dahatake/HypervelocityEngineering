# AAS Fan-out per-APP 追加指示

このサブタスクは AAS Step 2 (`Arch-ArchitectureCandidateAnalyzer`) の fan-out 子であり、
**アプリ `{{key}}` のみ** を対象とする。他の APP は対象外。

## 対象ファイル
- 本体: `docs/architectural-requirements-app-{{key 数字部}}.md`（既存ファイル名規約に従う）
- 追記: `docs/catalog/app-arch-catalog.md` の `{{key}}` 行

## 必須参照
- `docs/catalog/app-catalog.md` の `{{key}}` 該当行
- `docs/catalog/use-case-catalog.md` で `{{key}}` が担当する UC

## 並列実行ルール
- 他 APP の成果物には書き込まない。
- `docs/catalog/app-arch-catalog.md` への追記は最終 join 後にまとめて行う場合がある（運用注: 後続 join ステップで統合する設計）。
