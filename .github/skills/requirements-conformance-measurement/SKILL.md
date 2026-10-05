---
name: requirements-conformance-measurement
description: >
  デプロイ済み成果物を既存資産で実測し、固定フォーマットで要件適合と余裕度を報告する手順。
  USE FOR: requirements conformance measurement, performance target verification, NFR evidence report,
  headroom and over-provisioning detection. DO NOT USE FOR: test code generation (agents do that),
  TDD RED/GREEN evidence or HVE generated test policy (use tdd-red-green-reality §1.7), generic test strategy tutorial,
  design document review (use the WAF review steps). WHEN: ASDW-WEB 5.3 / ADFDV 4.3 / AAGD 5 / AAR 7 を実行するとき。
context: fork
metadata:
  origin: user
  version: 1.0.0
---

# requirements-conformance-measurement

## 目的

デプロイ済みの成果物を実際に動かして測り、**測定値だけ**を根拠に要件適合を判定する。
設計文書の照合で完結する既存のレビュー Step とは判定根拠が異なる。

正本の要件は `hve-dev/requirement-definition.md` §13.14（FR-WF-CONF-01〜06）。

## 用語・出典

出典: [Architecture strategies for performance testing](https://learn.microsoft.com/azure/well-architected/performance-efficiency/performance-test)（2026-08-17 確認）

- `Target` / `Threshold` / `Measured` / `Headroom` は、上記 WAF PE:06 の performance target / threshold / acceptance criteria の語彙に対応させる。
- 独自の性能用語や合否語彙を新設しない。固定レポートの列名と `Judgement` 4 値を正とする。

## 手順

1. **対象要件を抽出する**。入力の設計・カタログ成果物から `FR` / `NFR` を列挙する。
2. **目標値の有無を確認する**。設計成果物に数値目標があれば転記し、無ければ `NO_TARGET` として実測値だけを残す。
   目標を推測で補わない。実測値から逆算して目標を作らない。
3. **既存資産で測る**。当該 Workflow が既に生成したテスト資産とデプロイ済みエンドポイントを使い、本 Step のために Azure リソースを新規作成しない。Azure Load Testing 等を使った場合だけ `Measurement-Tool` へ記録する。
4. **実測値だけを記録する**。測定できなかった行は `NOT_MEASURED` とし、`Evidence` へ理由を書く。応答時間は p50 / p95 等で記録し、どのパーセンタイルかを明示する。
5. **余裕度を記録する**。`Headroom` に閾値と実測値の比を書き、どちらを分子にしたかを `Rationale` へ記す。過大な項目は推奨として `Simplification-Candidate` へ挙げるだけにし、構成変更・再デプロイは行わない。
6. **固定フォーマットで出力する**（下記）。

## レポート固定フォーマット

以下は HVE の artifact gate（`hve/artifact_validation.py`）が機械検証する固定値。変更しない。

```markdown
- Schema-Version: 1
- Workflow: <workflow-id>
- Step: <step-id>
- Agent: QA-RequirementsConformanceEval
- Measured-At: <ISO-8601 UTC>
- Target-Environment: <エンドポイントまたはリソーススコープ>
- Measurement-Tool: <ツール名とバージョン>
- Secret-Redaction: confirmed

| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |
|---|---|---|---|---|---|---|---|
| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | playwright-perf.log |

- Conclusion: <目標を満たしたか、満たさない項目は何か>
- Rationale: <測定条件と、その結論に至る根拠>
- Simplification-Candidate: <余裕が過大で簡素化余地がある項目。無ければ none>
```

## 判定語彙（4 値のみ）

| 値 | 条件 |
|---|---|
| `PASS` | 実測値が `Threshold` を満たした |
| `FAIL` | 実測値が `Threshold` を満たさなかった |
| `NOT_MEASURED` | 測定を実行できなかった。`Evidence` に理由必須 |
| `NO_TARGET` | 設計成果物に数値目標が無い。`Measured` は実測値で埋める |

`NO_TARGET` と `NOT_MEASURED` を同一視しない。前者は「目標が無い」、後者は「測っていない」であり、
次サイクルで取るべき行動が異なる（前者は目標の制定、後者は測定環境の整備）。

### PASS / FAIL 行の必須列

`PASS` / `FAIL` は `Target` / `Threshold` / `Headroom` / `Evidence` をすべて埋める。
いずれかが空の行は artifact gate が FAIL とする。目標・閉値なしの合否、もしくは証跡なしの合否は、
測定したことの証明にならないためである。`NOT_MEASURED` / `NO_TARGET` の行にはこの制約を適用しない。
全行で同じ `Req ID` を複数行に分割しない。

## 任意: Azure Load Testing の記録

Azure Load Testing 等のマネージド負荷試験サービスは任意であり、本 Step のための Azure リソース新規作成を必須化しない。
利用した場合だけ、ツール名・設定ファイル・実行ログを `Measurement-Tool` / `Evidence` / `Rationale` へ記録する。

出典: [Define fail criteria for load tests](https://learn.microsoft.com/azure/app-testing/load-testing/how-to-define-test-criteria)（2026-08-17 確認）

合否条件や `autoStop` の具体構文は採用時に公式ドキュメントで確認する。ここには規範ではない YAML 例を置かない。

## Non-goals

- テストコードの生成（各 Workflow の TDD Step の責務）
- RED / GREEN の証跡作成（Skill `tdd-red-green-reality`）
- HVE 生成テスト方針の管理（Skill `tdd-red-green-reality` §1.7）
- 測定結果に基づく構成変更・再デプロイ（本 Step は測定と報告まで）

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `tdd-red-green-reality` | 補完 | RED/GREEN の実出力証跡と HVE 生成テスト方針（§1.7）。本 Skill は deploy 後の適合測定を担う |
| `work-artifacts-layout` | 出力先 | 作業ログ `{WORK}work-status.md` の配置 |
