{root_ref}
## 目的
ドメイン分析結果、データモデルを根拠に、IoT デバイス管理ダッシュボード・監視UI を含む画面一覧を設計する。

## 入力
- `docs/domain-analytics.md`
- `docs/device-connectivity.md`
- `docs/data-model.md`

## 出力
- `docs/screen-list.md`

## Custom Agent
`Arch-UI-List` を使用

## 依存
- Step.2（データモデル）が `aid:done` であること

## 完了条件
- `docs/screen-list.md` が作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
