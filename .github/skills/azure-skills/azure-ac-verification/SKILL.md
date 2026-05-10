---
name: azure-ac-verification
description: >
  Deploy 系 Agent 向けの AC 検証スクリプトパターン集を提供する。USE FOR: acceptance criteria verification, deploy verification script, provisioning state checks. DO NOT USE FOR: resource provisioning itself. WHEN: AddServiceDeploy や他 Deploy Agent の verify スクリプトを作成・更新するとき。
metadata:
  version: 1.0.0
---

# azure-ac-verification

## 目的
- AddServiceDeploy を含む Deploy 系 Agent で共通利用できる AC 検証パターンを定義する。
- verify スクリプトの判定ロジックと証跡の一貫性を担保する。

## Non-goals（このスキルの範囲外）
- Azure リソースの作成そのもの
- アプリケーション機能テストの詳細設計

## 1. リソース存在確認（provisioningState）
```bash
state=$(az resource show --ids "$RESOURCE_ID" --query properties.provisioningState -o tsv)
if [ "$state" != "Succeeded" ]; then
  echo "[FAIL] provisioningState=$state"
  exit 1
fi
```
- `Succeeded` を PASS 条件とする。

## 2. 冪等性確認（2回連続実行）
- 同一入力で deploy/create スクリプトを 2 回連続実行し、2 回目で差分が発生しないことを確認する。
- 2 回目が更新系 API を発火する場合は FAIL とする（意図的更新を除く）。

## 3. 秘密情報検査（AC-5/AC-7 系）
- 生成物・ログに対し、最低限以下を grep で検査する。
  - `grep -Eiq '(password|secret|token|connectionstring|private[_-]?key)'`
- 検出時は FAIL。誤検知除外は理由付きで明記する。

## 4. service-catalog 重複行検査（AC-5）
- `docs/catalog/service-catalog-matrix.md` で同一サービスID/サービス名の重複を禁止する。
- 追加前後で重複件数が増えていないことを検証する。

## 5. 終了コード規約
- `0`: 全 AC PASS
- `1`: AC 失敗
- `2`: 重大検出または環境エラー（例: `verify-secrets-expiry.sh` の「期限切れ検出」、認証不足、CLI 未導入、ネットワーク障害）

## 6. verify-secrets-expiry 連携（PR-7）
- Key Vault Secret 依存がある場合、`infra/azure/verify-secrets-expiry.sh` を verify から呼び出す。
- 依存がない場合は `N/A` を明記する。
- 呼び出し側では `verify-secrets-expiry.sh` の戻り値を正規化して扱う:
  - `0`: PASS
  - `1`: WARNING（しきい値未満/期限未設定）
  - `2`: FAIL（期限切れ検出）
  - `3+`: FAIL（環境エラー）

## 7. HTTP/要素スモーク連携（PR-2）
- Web UI 系の verify では HTTP 200 と主要 DOM 要素確認パターン（`verify-webui-resources.sh`）を参照する。
- E2E（SWA 実 URL）と混同しない。

## Related Skills
- `azure-cli-deploy-scripts`: deploy スクリプト雛形
- `harness-verification-loop`: 最終検証フェーズ
