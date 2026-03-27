{root_ref}
## 目的
ドメイン分析結果、データモデル、画面一覧を統合して、IoT 固有サービス（デバイス管理・テレメトリ収集・OTA更新・エッジ推論サービス含む）のサービスカタログを作成する。

## 入力
- `docs/domain-analytics.md`
- `docs/device-connectivity.md`
- `docs/data-model.md`
- `docs/screen-list.md`

## 出力
- `docs/service-catalog.md`

## Custom Agent
`Arch-Microservice-ServiceCatalog` を使用

## 依存
- Step.3（画面一覧/構造）が `aid:done` であること

## 完了条件
- `docs/service-catalog.md` が作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
