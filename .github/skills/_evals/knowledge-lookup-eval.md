# knowledge-lookup Skill 検証シナリオ

## 概要

`knowledge-lookup` Skill が期待通りに動作するかを検証するためのシナリオ一覧。

## シナリオ一覧

### シナリオ 1: 補完的参照の発火

- **前提**: `Arch-Batch-DataModel` Agent に対し、D06（業務ルール）に関する不明点がある指示を出す（D06 は既存の直接参照セクションにない）
- **期待結果**: `knowledge-lookup` Skill が発火し、D06 を参照して情報を取得する
- **確認ポイント**: 既存の直接参照（D07, D08）はそのまま維持される

### シナリオ 2: ソースコード専用 Agent での非発火

- **前提**: `Doc-FileSummary` Agent にソースコード1ファイルの要約を依頼する
- **期待結果**: `knowledge-lookup` Skill が発火 **しない**
- **確認ポイント**: knowledge/ への参照が発生せず、ソースコードのみで作業が完結する

### シナリオ 3: knowledge/ 未整備時のフォールバック

- **前提**: knowledge/ が空の状態で `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` Agent にタスクを指示する
- **期待結果**: Step 5 の「knowledge/ 未整備」パスが動作し、入力ファイルの情報のみで継続。不明点は `TBD（要確認）` が出力される
- **確認ポイント**: Agent が処理停止せず、TBD 付きで作業を継続する

### シナリオ 4: knowledge/business-requirement-document-status.md 未存在時のフォールバック

- **前提**: `knowledge/business-requirement-document-status.md` が存在しないが、`knowledge/D07-*.md` は存在する状態で用語の確認が必要になる
- **期待結果**: フォールバック（ディレクトリ直接確認）が動作し、D07 ファイルが参照される
- **確認ポイント**: `knowledge/business-requirement-document-status.md` の不存在でエラーにならない

## 検証方法

- 手動テストで上記シナリオを順次実施
- 安定を確認後、自動評価への移行を検討
