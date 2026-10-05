# 検証記録の最小例

この参照は、完了判定を後から確認できるようにするための記録例である。
固定の検証段階や全件実行順序は定義しない。

---

## 対象コマンドの選び方

| 対象 | 例 | 成功条件 |
|---|---|---|
| Python の対象テスト | `.venv\Scripts\python.exe -m pytest {テストファイルパス} -q` | exit code 0 |
| Python の対象構文確認 | `.venv\Scripts\python.exe -m py_compile {ファイルパス}` | exit code 0 |
| JSON | `.venv\Scripts\python.exe -c "import json; json.load(open('{ファイルパス}', encoding='utf-8-sig'))"` | exit code 0 |
| YAML | `.venv\Scripts\python.exe -c "import yaml; yaml.safe_load(open('{ファイルパス}', encoding='utf-8-sig'))"` | exit code 0 |
| JavaScript / UI | 既存 `package.json` script に対象テストファイルを渡す | exit code 0 |

- コマンドは対象変更に対応する明示 path へ絞る。
- Unit / 実装コード向け TDD RED / TDD GREEN で環境依存が出る場合は、テストダブル化漏れを疑い、Mock / Stub / Emulator / Testcontainers へ切り分ける。
- 外部サービス用 Integration / Post-deploy / E2E の必須設定（Endpoint / base URL / Resource 名 / 認証経路）が不足する場合は `FAIL(環境ブロッカー)` または Step 固有の blocked として記録し、未実行のまま成功扱いしない。
- 秘密情報を確認する必要がある場合も値を表示しない。

---

## 検証レポート例

汎用検証サマリーは `{WORK}verification-report.md` に置く。

TDD RED/GREEN Step の実テスト結果は、汎用検証レポートとは別に次の TDD 専用レポートへ記録する:

`tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`

- `verification-report.md`: 要求定義から導いた受入条件、対象コマンド、exit code、実出力要約を記録する。
- `tdd-test-report.md`: RED/GREEN の実行コマンド、期待結果、実結果、`TDD-Judgement`、`Secret-Redaction`、`Test-Files-Changed` を含む TDD 専用証跡。
- 同一内容を `docs/` や `src/` に追記しない。

```markdown
# VERIFICATION REPORT

Agent:     {Agent名}
Issue:     #{Issue番号}
Timestamp: {UTC timestamp - 例: 2026-01-01T00:00:00Z}

## Acceptance Criteria

- {要求定義から導いた受入条件}

## Commands

| Command | Target | Exit-Code | Result |
|---|---|---:|---|
| `{実行コマンド}` | `{対象パス}` | `{exit code}` | `PASS/FAIL/BLOCKED` |

## Evidence

- Output-Summary: {実出力の要約}
- Baseline: {既存失敗がある場合の扱い。なければ N/A}
- Not-Run: {未実行事項と理由。なければ N/A}
```

---

## 失敗時

1. 失敗した対象コマンド、exit code、実出力の要点を記録する。
2. Skill `harness-error-recovery` に従い、原因、再試行条件、停止条件を記録する。
3. 再試行する場合は、同じ原因に同じ対処を重ねず、原因仮説または対処内容を変える。
