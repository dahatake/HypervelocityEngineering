---
name: tdd-green-retry-strategy
description: >
  TDD GREEN フェーズの多層・異アプローチ・公式情報駆動リトライ規律。GREEN 化ループ
  を持つ全 Step 共通で、同一アプローチの単純反復を禁止し、失敗の都度に根本原因を特定
  して公式技術情報 MCP から解決策を得てから次の異なるアプローチを試す。
  USE FOR: TDD GREEN retry strategy, multi-layer retry, different-approach retry,
  root-cause-driven retry, official-docs-driven fix. DO NOT USE FOR: RED phase test
  code generation (Dev-*-TestCoding が担当), test strategy pyramid (test-strategy-template),
  RED/GREEN reality proof (tdd-red-green-reality), generic error recovery (harness-error-recovery).
  WHEN: 検証/テストを PASS させるまで反復する GREEN 化ループを実行するとき、
  リトライ回数を消費する前に異なるアプローチと根本原因調査を行うとき。
metadata:
  origin: user
  version: 1.0.0
---

# tdd-green-retry-strategy

## 目的

TDD GREEN フェーズ（テスト/検証を PASS させるまで反復する Step）で、リトライを
「**同じアプローチの単純な繰り返し**」にせず、「**回ごとに異なるアプローチ**」＋
「**失敗の都度、根本原因を特定し公式技術情報からの解決策で次手を決める**」規律に
統一するための共通原則を一元管理する。

> 背景: 同一の取得/実装アプローチを N 回繰り返すだけのリトライは、その手段自体に
> 構造的な弱点がある場合に N 回とも同じ失敗に当たり続け、リトライ回数を消費しても
> GREEN に到達できない。回数ではなく「アプローチの多様性」と「失敗ごとの原因究明」
> が GREEN 到達率を決める。

---

## Non-goals

- **RED フェーズのテストコード生成** — `Dev-*-TestCoding` 系 Agent が担当
- **RED/GREEN を実出力で証明する原則** — Skill `tdd-red-green-reality` が担当
- **テストピラミッド・カバレッジ方針** — Skill `test-strategy-template` が担当
- **エラー分類テンプレート（3 要素出力）** — Skill `harness-error-recovery` が担当（本 Skill と併用可）
- **特定データストア/言語の具体コマンドの網羅** — 実行時に公式技術情報 MCP から確定する（本 Skill にはハードコードしない）

---

## 1) 多層リトライの原則（内側から外側へ）

GREEN 化の失敗は、可能な限り**内側の層で回復**を試み、外側の層へ伝播させない。

| 層 | 対象 | この層でのリトライの意味 |
|---|---|---|
| **Layer 1: 検証/取得手段そのもの** | 件数取得・状態取得・ビルド・単一テストコマンド等の 1 手段 | その手段の内部で異なる方法を試す（例: 出力の抽出方法を変える、待機して再取得する、代替コマンド/経路へ切替） |
| **Layer 2: GREEN 化ループ** | 「検証/テスト実行 → 修正 → 再実行」の反復 | 各反復で前回と異なる修正アプローチを選ぶ |
| **Layer 3: Step 全体** | Step の再実行（HVE の fork-on-retry 等、環境が提供する場合） | 環境が提供する範囲で利用する。本 Skill は Layer 1/2 の規律を主対象とする |

- **各層は最大 5 回**を上限とする（Step 固有の prompt に別の上限が明記されている場合はそれに従う）。
- 上限に達したら次の外側の層へ回復を委ねる。最外層でも未達なら §4 の打ち切り規律に従う。

---

## 2) 「異なるアプローチ」の原則（同一手段の単純反復を禁止）

- **各試行は、直前の試行と異なる観点**を選ぶ。同じコマンド・同じ抽出方法・同じ修正を
  そのまま繰り返してはならない。
- アプローチの選び方の**一般的な軸**（データストア/言語非依存。具体コマンドは各 Step の
  prompt と公式技術情報 MCP から確定する）:

  | 軸 | 内容の一般例 |
  |---|---|
  | 出力/結果の取得方法 | 結果の抽出・パース方法を変える（末尾行のみ→全体走査、単一行→複数行検索 等） |
  | タイミング | 完了検知直後の取得で空/不整合なら、短時間待機して再取得する |
  | 実行単位の再生成 | 一過性の個体不良が疑われる場合、実行環境/一時リソースを作り直して全体をやり直す |
  | 認証/接続経路 | 認証トークン・資格情報・接続経路（直接 / フォールバック）を切り替える |
  | 代替手段 | 使用中のコマンド/SDK/API に構造的欠陥・非対応がある場合、公式が示す別手段へ切替 |
  | 修正の粒度 | 実装修正で解決しない場合、設定・依存・フィクスチャなど別レイヤーの原因を疑う |

- 各試行の**採用アプローチと結果**を作業ログ（`work-status.md` 等）に短く記録し、
  次の試行が異なる軸を選べるようにする。

---

## 3) 失敗の都度、公式技術情報から解決策を得る（必須）

各失敗時は、次のアプローチを決める前に以下を行う:

1. **根本原因の特定**: 失敗の実出力（exit code / エラーメッセージ / ログ）から原因を特定する。
   推測で次手を決めない。
  - 必須の外部サービス設定（Endpoint / base URL / Resource 名 / 認証経路）が不足している場合は、
    テストを緩めたり skip したりせず、設定補完または環境ブロッカーとして扱う。
2. **公式技術情報 MCP で解決策を取得**（優先順位順）:
   - **Azure / C# / .NET / Azure CLI / SDK / REST API**: **Microsoft Learn MCP** を必ず参照する。
   - **Python / Python ライブラリ**: 利用可能な **Python 技術情報 MCP**（Python の公式ドキュメント・
     ライブラリ API を提供する MCP）を参照する。
   - **その他の言語 / フレームワーク / ライブラリ（JavaScript / TypeScript / Node.js 等）**:
     利用可能な**当該技術の公式ドキュメント・ライブラリ API を提供する MCP** を参照する。
   - 上記で解決できない場合に限り Web 検索を用いる（WorkIQ は現時点で使用しない）。
3. **参照した公式情報の記録**: 参照した **title / URL / 確認事項** を作業ログまたは AC 証跡に記録し、
   採用した解決策の根拠を残す（`tdd-red-green-reality` §3 の記録規律と整合）。
4. MCP を利用できない場合は `要確認（公式技術情報 MCP 未取得）` と記録し、**推測で確定しない**。
   `... -h` / 公式 CLI help を補助確認として使う。

---

## 4) 打ち切りと証跡

- 各層で最大 5 回（または Step 固有 prompt の上限）を試しても GREEN 未達の場合、追加の
  同一検証リトライを続けず打ち切る。
- 打ち切りの終端が**テスト側/共有設定側の確定ブロッカー**（実装だけでは GREEN 化不能）に
  よる場合、TDD テスト結果レポートの `TDD-Judgement` は `FAIL` ではなく `BLOCKED` とする。
  HVE の gate は GREEN の `BLOCKED` を受理し、当該 Step は「成功扱い＋ブロッカー記録」として
  下流を止めない（実装未達など自ステップ起因の失敗は `FAIL`）。
- GREEN 化ループの各試行は、TDD テスト結果レポート
  `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
  に記録する。最低限、失敗テスト、Root-Cause（根本原因）、前回と異なるアプローチ、
  参照した公式情報、次の対応を残す。
- 打ち切り時は、**試した各アプローチ・各失敗の根本原因・参照した公式情報の URL**を
  作業ログ（`work-status.md`）および必要に応じて `ac-verification.md` / `completion-report.md`
  に記録する。
- Step 固有の blocked 規律（`<workflow>:blocked` ラベル付与・フィードバック先 Step への
  報告・AC-1 を `❌` で証跡付き fail 化 等）が prompt に定義されている場合はそれに従う。

---

## 参照元

- RED/GREEN を実出力で証明する原則: Skill `tdd-red-green-reality`
- 失敗時のエラー分類・3 要素出力: Skill `harness-error-recovery`
- 検証パイプライン（Build/Lint/Test/Security/Diff）: Skill `harness-verification-loop`
