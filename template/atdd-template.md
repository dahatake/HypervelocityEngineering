# ATDD テンプレート

本テンプレートは `Arch-TDD-TestSpec` Agent が生成する `docs/test-specs/*-test-spec.md` の **§1.5 ATDD セクション** に適用する正本フォーマットを定義する。

- **適用範囲**: サービス別 (API) / 画面別 (UI) / AI Agent 別 (AI Agent) の 3 領域。
- **根拠**: `.github/prompts/Arch-TDD-TestSpec.prompt.md` `<output_contract>` の章立て要件（§1.5 ATDD(API) / §1.5 ATDD(UI) / §1.5 ATDD(AI Agent)）。
- **形式**: AC-ID × Given / When / Then の 1 行 1 受入条件テーブル。

---

## 1. 記述ルール（全領域共通）

1. **AC-ID 命名**:
   - サービス別: `AC-{serviceId}-{NN}`（例: `AC-SVC19-01`）
   - 画面別: `AC-{screenId}-{NN}`（例: `AC-SCR-01-01`）
   - AI Agent 別: `AC-{agentId}-{NN}`（例: `AC-AGT-RECO-01`）
   - `NN` はゼロパディング 2 桁から開始、書き込み単位内で一意。
2. **双方向トレーサビリティ**: 本表の全 AC-ID は test-spec §2.5（AC→Test）および §9（Test→AC）と双方向に整合させる。未紐づけは禁止。
3. **出典の明示**: 「起点機能 / API」「画面/操作」「起点機能 / Tool」列にサービス定義書・画面定義書・テスト戦略書・カタログの該当節（ファイル#見出し）を可能な限り併記する。
4. **推測の扱い**: 確証不能な値は `TBD（推論: 根拠）` または `TBD（要確認）` と明示し、確定値を捏造しない。
5. **最小差分**: 既存 test-spec を再生成する場合も、本表の構造（列定義）は維持し、追加・更新行のみ差分マージする。

---

## 2. サービス別 ATDD(API)

> Agent: `Arch-TDD-TestSpec` がサービス定義書（`docs/services/{key}-description.md`、`{key}` = `SVC-*`）から API・イベント・状態遷移を抽出して記述する。

| AC-ID | 起点機能 / API | Given | When | Then |
|---|---|---|---|---|
| AC-{serviceId}-01 | <機能名> / <API-ID または HTTP メソッド + パス> | <前提条件（データ・状態・認可）> | <操作（API 呼び出し・イベント受信等）> | <期待結果（応答・状態遷移・イベント発行）> |

---

## 3. 画面別 ATDD(UI)

> Agent: `Arch-TDD-TestSpec` が画面定義書（`docs/screen/{key}-description.md`、`{key}` = `APP-NN-S###`）から操作シナリオ・バリデーション・API 呼び出しを抽出して記述する。

| AC-ID | 画面 / 操作 | Given | When | Then |
|---|---|---|---|---|
| AC-{screenId}-01 | <画面ID> / <操作名> | <前提条件（画面状態・ログイン状態・データ）> | <操作（クリック・入力・遷移）> | <期待結果（表示・遷移・API 呼び出し・バリデーション）> |

---

## 4. AI Agent 別 ATDD(AI Agent)

> Agent: `Arch-TDD-TestSpec` が AI Agent 定義書・テスト戦略書 §3.1（I/O 契約・Tool モック・Guardrails・状態遷移・プロンプト回帰）を根拠に記述する。

| AC-ID | 起点機能 / Tool | Given | When | Then |
|---|---|---|---|---|
| AC-{agentId}-01 | <機能名> / <Tool 名 または プロンプト経路> | <前提条件（入力・コンテキスト・Tool 設定）> | <操作（プロンプト実行・Tool 呼び出し）> | <期待結果（I/O スキーマ適合・Guardrails 拒否・状態遷移・プロンプト回帰類似度）> |

---

## 5. 検証チェックリスト

test-spec 生成時に以下を満たすこと:

- [ ] 該当領域の表が §1.5 に存在する（API / UI / AI Agent のいずれか、または複数）。
- [ ] AC-ID が書き込み単位内で一意。
- [ ] 全 AC-ID が §2.5 順引き表に出現。
- [ ] 全 AC-ID が §9 逆引き表からも参照される（未紐づけは Q セクションに記録）。
- [ ] 推測値は `TBD（推論: 根拠）` 形式で明示。
