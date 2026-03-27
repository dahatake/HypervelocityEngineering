{root_ref}
## 目的
ドメイン分析結果とデバイス接続性定義を根拠に、IoT 固有のデータモデル（デバイステレメトリ・時系列データ・エッジキャッシュ含む）を設計する。

## 入力
- `docs/domain-analytics.md`
- `docs/device-connectivity.md`

## 出力
- `docs/data-model.md`
- `src/data/sample-data.json`

## Custom Agent
`Arch-DataModeling` を使用

## 依存
- Step.1.1（IoT ドメイン分析）が `aid:done` であること
- Step.1.2（デバイスプロファイル＋接続性分析）が `aid:done` であること

## 完了条件
- `docs/data-model.md` と `src/data/sample-data.json` が作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
