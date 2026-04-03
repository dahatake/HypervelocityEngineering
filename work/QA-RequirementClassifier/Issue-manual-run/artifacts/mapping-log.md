# 詳細マッピングログ — QA-RequirementClassifier Issue-manual-run

**作成日**: 2025-07-18
**エージェント**: QA-RequirementClassifier

---

## 1. D01〜D21 マスターリスト サマリー

`template/business-requirement-document-master-list.md` から取得した D クラス定義のサマリー。

| D クラス | 文書名 | 必須度 | 不足判定基準 |
|---------|--------|--------|------------|
| D01 | 事業意図・成功条件定義書 | Core | KPI と成功条件がない場合は不足 |
| D02 | スコープ・対象境界定義書 | Core | Out of scope、変更禁止、依存条件の3つが欠けていれば不足 |
| D03 | ステークホルダー・承認権限・責任分担表 | Core | C-13 と C-14 を分けて持っていなければ不足 |
| D04 | 業務プロセス仕様書 | Core | To-Be と分岐条件がなければ不足 |
| D05 | ユースケース・シナリオカタログ | Core | 正常系だけで異常系がなければ不足 |
| D06 | 業務ルール・判定表仕様書 | Core | 判定表か計算式のどちらかが欠ければ不足 |
| D07 | 用語集・ドメインモデル定義書 | Core | 状態と不変条件がなければ不足 |
| D08 | データモデル・SoR/SoT・データ品質仕様書 | Core | SoR、保持/削除条件、PII分類がなければ不足 |
| D09 | システムコンテキスト・責任境界・再利用方針書 | Core | コンテキスト図と責任境界の両方がなければ不足 |
| D10 | API / Event / File 連携契約パック | Core（連携がある場合） | スキーマとエラー契約がなければ不足 |
| D11 | 画面・UX・操作意味仕様書 | Conditional | フィールド定義だけで操作意味がなければ不足 |
| D12 | 権限・認可・職務分掌設計書 | Core | SoD とスコープ権限のどちらかが欠ければ不足 |
| D13 | セキュリティ・プライバシー・監査・法規マトリクス | Core | 監査証跡、保持、越境移転のいずれかが欠ければ不足 |
| D14 | 国際化・地域差分仕様書 | Conditional | 税制・TZ・休日差分があるのに文書がなければ不足 |
| D15 | 非機能・運用・監視・DR 仕様書 | Core | SLO と DR 条件がなければ不足 |
| D16 | 移行・導入・ロールアウト計画書 | Conditional | 既存システム置換やデータ引継ぎがあるのに照合条件・ロールバックがなければ不足 |
| D17 | 品質保証・UAT・受入パッケージ | Core | 業務試験だけで権限・監査・契約試験がなければ不足 |
| D18 | Prompt ガバナンス・入力統制パック | Core（Vibe Coding 前提では必須） | SoT 一覧、投入可否、廃止仕様禁止の3つがなければ不足 |
| D19 | ソフトウェアアーキテクチャ・ADR パック | Core | Context 図しかなく、Container/Component/Runtime/Deployment/ADR がない場合は不足 |
| D20 | セキュア設計・実装ガードレール | Core | M章の要件はあるが、threat model と実装規約がなければ不足 |
| D21 | CI/CD・ビルド・リリース・供給網管理仕様書 | Core | コード生成を行うのに、CI 品質ゲート・依存スキャン・artifact 管理がなければ不足 |

---

## 2. 入力ファイル収集結果

### qa/ ディレクトリ

```
ディレクトリ: /home/runner/work/HypervelocityEngineering/HypervelocityEngineering/qa/
状態: 存在しない（ディレクトリ未作成）
ファイル数: 0
```

> `qa/` ディレクトリが存在しないため、処理する質問項目が **0 件** となる。

---

## 3. 質問項目の抽出結果

| 質問ID | ソースファイル | 質問テキスト | 採用回答 | 状態 | Primary D | Contributing D |
|--------|--------------|------------|---------|------|-----------|----------------|
| （なし） | — | — | — | — | — | — |

> `qa/` ファイルが存在しないため、質問項目は **0 件** である。

---

## 4. D01〜D21 マッピング結果

全 D クラスについて、マッピングされた質問数は 0 件。

| D クラス | Primary 質問数 | Contributing 質問数 | 総合状態 |
|---------|--------------|-------------------|---------|
| D01 | 0 | 0 | NotStarted |
| D02 | 0 | 0 | NotStarted |
| D03 | 0 | 0 | NotStarted |
| D04 | 0 | 0 | NotStarted |
| D05 | 0 | 0 | NotStarted |
| D06 | 0 | 0 | NotStarted |
| D07 | 0 | 0 | NotStarted |
| D08 | 0 | 0 | NotStarted |
| D09 | 0 | 0 | NotStarted |
| D10 | 0 | 0 | NotStarted |
| D11 | 0 | 0 | NotStarted |
| D12 | 0 | 0 | NotStarted |
| D13 | 0 | 0 | NotStarted |
| D14 | 0 | 0 | NotStarted |
| D15 | 0 | 0 | NotStarted |
| D16 | 0 | 0 | NotStarted |
| D17 | 0 | 0 | NotStarted |
| D18 | 0 | 0 | NotStarted |
| D19 | 0 | 0 | NotStarted |
| D20 | 0 | 0 | NotStarted |
| D21 | 0 | 0 | NotStarted |

---

## 5. 根拠・備考

- `qa/` ディレクトリが存在しないことを `find` コマンドで確認済み（実行日: 2025-07-18）
- `template/business-requirement-document-master-list.md` および `.github/instructions/requirement-classification.instructions.md` は存在し、参照・読み込み完了
- 捏造禁止ルールに従い、存在しない質問に基づくマッピングは一切行わない
- 全 D クラスの状態を `NotStarted` として記録する（マッピング質問 0 件のため、`§3 D クラス単位の総合状態` ルール準拠）
