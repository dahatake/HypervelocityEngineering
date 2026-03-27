{root_ref}
## 目的
ユースケース文書を根拠に、対象デバイスのHWプロファイル・センサー/アクチュエーター仕様・接続性・オフライン分類・消費電力・AI推論要件・状態遷移・フェイルセーフ設計を整理し、docs/device-connectivity.md を作成する。

## 入力
- `docs/usecase-list.md`

## 出力
- `docs/device-connectivity.md`

## Custom Agent
`Arch-IoT-DeviceConnectivity` を使用

## 依存
- なし（ルートノード。Step.1.1 と並列実行可能）

## 完了条件
- `docs/device-connectivity.md` が作成されている
- 完了時に自身に `aid:done` ラベルを付与すること{additional_section}
