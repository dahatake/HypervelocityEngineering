> マイクロサービス定義書から全てのサービスの Azure Functions を実装し、テスト/最小ドキュメント/設定雛形まで揃える

> **WORK**: `/work/Dev-Microservice-Azure-ServiceCoding-AzureFunctions/Issue-<識別子>/`

# 目的（スコープ固定）
- 対象は **1サービス分のみ**：`{serviceId}-{serviceNameSlug}`。
- 目的は「定義書どおりに動く *最小の本実装*」＋「CIで決定的に通る単体テスト」＋「利用者が実行/検証できる最小ドキュメント」。
- “全サービス対応”“設計刷新”“横断リファクタ”は範囲外（必要なら Skill task-dag-planning の分割ルールで別タスク化）。

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。


## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`original-docs/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。

## Agent 固有の Skills 依存

- `microservice-design-guide` — サービス実装時の API/イベント契約参照
- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `harness-verification-loop` — Build/Lint/Test/Security/Diff の 5 段階検証
- `harness-error-recovery` — ビルド・テスト失敗時の E-01〜E-05 リカバリ
- `harness-safety-guard` — ツール実行時の破壊的操作検出と中断
- `karpathy-guidelines` — 実装時の LLM 共通ミス防止指針

# 入力（不足なら Questions：必要な項目をすべて）
最低限ほしい情報：
- マイクロサービス定義書（例）：
  - `docs/services/{serviceId}-{serviceNameSlug}-description.md`
  - Azure Functionsのプログラミング言語: `C#（最新版のAzure Functionsでサポートされているもの）`
- TDD テスト仕様書（Step.2.3T の成果物）：
  - `docs/test-specs/{serviceId}-test-spec.md`
- 参照候補（存在すれば読む）：
  - `docs/catalog/service-catalog.md`
  - `docs/catalog/data-model.md`
  - `docs/catalog/service-catalog-matrix.md`
  - `docs/azure/azure-services-*.md`
  - `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）
不足があれば「何が足りない/なぜ必要か/代替案（仮置き）をするなら何か」を添えて Questions に必要な項目をすべて出す。捏造は禁止。

## APP-ID スコープ → Skill `app-scope-resolution` を参照
# 成果物（必須）
- 実装：
  - `src/api/{serviceId}-{serviceNameSlug}/` 配下に Azure Functionsを作成/更新
- テスト：
  - `src/test/api/` に単体テスト（外部I/Oはモック。CIで決定的に）
- 手動スモーク（任意だが推奨。自動テストに混ぜない）：
  - `src/test/api/smoke-ui/index.html`
- 作業ログ（Skill work-artifacts-layout 既定の `{WORK}` に従う）
  - 仕様要約（エンドポイント/入出力/エラー/依存/設定キー/認証）
  - 実行したコマンド（build/test/lint）

# 実行手順（この順で）
1) **リポジトリ慣習の特定（推測禁止）**
   - 既存の Functions 実装があれば構成/DI/ログ/例外処理/テストの“型”を踏襲する。
   - .NET/Functions の世代（isolated/in-process等）は、既存コード/設定から確定する。見つからなければ Questions。

2) **定義書→受入条件へ落とす（必須）**
   - 以下を「仕様要約」に短く確定（箇条書き/表）：
     - エンドポイント/トリガ/コマンド（入力・出力・HTTPコード・エラー）
     - 参照データモデル
     - 外部依存（“このサービスに必要なもののみ”）
     - 認証/認可（MI/Key Vault/トークン等。分からなければ明示して質問）
     - 設定キー（環境変数名）一覧

3) **テスト仕様書 → テストコード変換（TDD RED 準備）**
   - `docs/test-specs/{serviceId}-test-spec.md` のテストケース表（§2）を xUnit の `[Fact]`/`[Theory]` テストコードに変換する。
   - テストダブル設計（§4）に基づき、モック/スタブの構成を実装する。
   - テストデータ定義（§3）に基づき、テストデータを準備する。
   - 既存テスト（`src/test/api/` 配下）がある場合は保持し、仕様書ベースで不足分を追加する。
   - モッキングライブラリは既存テストプロジェクトの慣習に従う。慣習がない場合は xUnit + Moq（または NSubstitute）を既定とする。テスト戦略書（`docs/catalog/test-strategy.md` §4 テストダブル戦略）で別ライブラリが指定されている場合はそちらを優先する。

4) **RED 確認（TDD RED フェーズ）**
   - テストコードをビルドし、コンパイルが成功することを確認する。
   - `dotnet test` を実行し、全テストが **FAIL** であることを確認する（プロダクションコード未実装のため）。
   - RED 確認結果を作業ログに記録する。

5) **実装（TDD GREEN フェーズ）**
   - テスト仕様書のテストケースを GREEN にするための最小実装を行う。
   - 秘密情報のハードコード禁止。設定は環境変数（＋可能なら Key Vault 参照）で受ける。
   - 外部I/Oはタイムアウトを必ず設定し、無限リトライ禁止（必要なら上限付き・対象は外部I/Oのみ）。
   - 構造化ログと相関ID（要求単位）を入れる。

6) **GREEN 確認（TDD GREEN フェーズ）**
   - `dotnet test` を実行し、全テストが **PASS** であることを確認する。
   - PASS しないテストがある場合は実装を修正する（テストコード自体は原則変更しない）。

6.5) **REFACTOR（TDD REFACTOR フェーズ — 必須）**
   - テスト仕様書の「TDD 実行順序」（§6）の Refactor フェーズに記載された「回帰テスト確認ポイント」を参照し、重点的にリファクタリング対象を選定する。
   - GREEN 確認後、以下の観点でプロダクションコードのリファクタリングを行う：
     - **重複排除**: 同一ロジックの共通化（ヘルパー/ユーティリティメソッドへの抽出）
     - **命名改善**: 変数名・メソッド名の意図明確化
     - **責務分離**: 1クラス/1メソッドが単一責任原則（SRP）を満たすこと
     - **マジックナンバー/文字列の定数化**
     - **既存コードの型への準拠**: リポジトリ慣習の DI/ログ/例外処理パターンとの一貫性維持
   - リファクタリングは **テストの振る舞いを変更しない** 範囲で行う。
   - リファクタリング後、`dotnet test` を再実行し **全テストが引き続き PASS** であることを確認する（回帰テスト）。
   - PASS しないテストが発生した場合はリファクタリングを戻し、原因を特定してからやり直す。
   - リファクタリング内容を作業ログに記録する（変更前後の差分概要）。

7) **手動スモークUI（作る場合）**
   - `index.html` は「API URL」「入力」「実行」「結果表示」だけ。秘密情報は置かない。
   - 自動テストに混ぜない（手動検証専用）。

8) **ビルド/テストの実行と記録**
   - repo標準のコマンドで build/test を実行し、成功/失敗とコマンドを作業ログに残す。
   - 依存導入が不安定/遅い場合、`Azure MCP Server` または `az login`（必要なら `--use-device-code`）で認証確認後に導入を再実行する。

# 完了条件（DoD）
- `src/api/{serviceId}-{serviceNameSlug}/` がビルド可能
- `src/test/api/` の単体テストが決定的に実行可能
- `dotnet test` の全テストが **PASS** であること（TDD GREEN 確認済み）
- TDD REFACTOR フェーズを実施し、リファクタリング後も全テストが **PASS** であること
- テスト仕様書（`docs/test-specs/{serviceId}-test-spec.md`）のテストケースが、テストコードとしてすべて実装されていること
- 作業ログと README が更新され、設定キー/実行手順/検証手順が分かる

# 最終品質レビュー（Skill adversarial-review 準拠・3観点）

## 3つの異なる観点（Azure Functions 実装の場合）
- **1回目：技術妥当性・実装完全性**：コードが定義書に正しく基づいているか、エラーハンドリングは十分か、秘密情報/タイムアウト/リトライの設定は正しいか、構造化ログと相関IDが適切か、テストカバレッジは十分か、受入条件（入力/出力/エラー/HTTPコード）が実装・テスト・READMEで一致しているか
- **2回目：ユーザー/運用視点**：単体テストが実運用環境で再現可能か、スモークUIは手動検証に十分か、README/作業ログから設定・実行・検証手順が明確か、PR本文（または作業ログ）に「変更点」「設定キー」「実行/検証」が揃っているか、外部依存やセットアップ要件は文書化されているか
- **3回目：保守性・堅牢性・スケーラビリティ**：TDD REFACTOR フェーズで重複排除・命名改善・責務分離が実施されているか、コードの可読性と既存型への一貫性、設定の外部化とキー管理、ログ出力の品質と監査可能性、テスト拡張性と再利用可能性、他サービスへの波及リスク、スコープは1サービスのみか（他サービスへ波及していないか）

## 3) 出力フォーマット（Markdown固定スキーマ）
レビュー記録は `{WORK}` に保存（Skill work-artifacts-layout §4.1）。PR本文にも記載。最終版のみ成果物出力。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
