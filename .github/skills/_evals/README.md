# Skills Eval テストケース

## 目的

`.github/skills/_evals/` には、各 Skill の **発動正確性テストケース** を YAML 形式で格納する。

ここではリポジトリ同梱 Skill の契約を検証する。外部 Skill の旧同梱版に対する評価は保持せず、外部 Skill 自体の現行定義・評価へ委ねる。HVE 側の required / optional 境界は既存の routing 契約テストで検証する。

## 用途

- Skill の `description` / `WHEN:` 変更時に、既存のトリガーパターンが壊れていないかのリグレッション確認
- 新規 Skill 追加時に、既存 Skill との発動競合がないかの検証
- PR レビュー時に、Skill ルーティングの妥当性を確認するための参照資料

## ファイル命名規則

`<skill-name>.eval.yaml`

## テストケース構造

```yaml
skill: <skill-name>
skill_path: .github/skills/<category>/<skill-name>/SKILL.md
description: <Skill の簡潔な説明>

test_cases:
  # --- 正のテストケース（このSkillが発動すべき入力） ---
  - id: <kebab-case-id>
    input: "<ユーザーの入力例（日本語）>"
    expected_trigger: true
    verify:
      - type: <検証タイプ>
        detail: "<検証の詳細>"
    reason: "<このSkillが発動すべき理由>"

  # --- 負のテストケース（このSkillが発動すべきでない入力） ---
  - id: <kebab-case-id>
    input: "<ユーザーの入力例>"
    expected_trigger: false
    expected_skill: <代わりに発動すべきSkill名 or null>
    reason: "<このSkillが発動すべきでない理由>"

  # --- エッジケース ---
  - id: <kebab-case-id>
    input: "<曖昧な入力例>"
    expected_trigger: <true/false>
    reason: "<判断の根拠>"
```

## テストケース作成ルール

- **各 Skill につき最低 6 テストケース**: 正3件以上 + 負2件以上 + エッジ1件以上
- **各 SKILL.md を読み込んで** `description`、`WHEN:`、`Non-goals` から正確に導出すること
- **捏造禁止**: SKILL.md に記載のないトリガー条件や Non-goals を追加しない
- `verify` フィールドは、正のテストケースに対して「何が起きるべきか」を具体的に記述する
- `expected_skill` フィールドは、負のテストケースで「代わりにどの Skill が対応すべきか」を明示する

## 現在のカバレッジ

> テストケースを追加・変更した際は、対応する行の「テストケース数」と「最終更新」を必ず更新すること。

| Skill | テストケース数 | 最終更新 |
|-------|-------------|---------|
| task-dag-planning | 8 | 2026-04-10 |
| task-questionnaire | 7 | 2026-04-10 |
| adversarial-review | 7 | 2026-04-10 |
| harness-verification-loop | 7 | 2026-04-10 |
| harness-safety-guard | 7 | 2026-04-10 |
| harness-error-recovery | 7 | 2026-04-10 |
| large-output-chunking | 7 | 2026-04-10 |
| work-artifacts-layout | 7 | 2026-04-10 |
| app-scope-resolution | 6 | 2026-04-10 |
| architecture-questionnaire | 6 | 2026-04-10 |
| dataflow-design-guide | 6 | 2026-04-10 |
| input-file-validation | 6 | 2026-04-10 |
| knowledge-management | 6 | 2026-04-10 |
| microservice-design-guide | 6 | 2026-04-10 |
| docs-output-format | 6 | 2026-09-11 |
| github-actions-cicd | 6 | 2026-04-10 |
| repo-onboarding-fast | 6 | 2026-04-10 |
| ai-agent-capability-contract | 9 | 2026-09-11 |
| hve-prompt-edition | 33 | 2026-09-12 |

## 判定結果の読み方

- `NOT RUN` は未実施を示す。静的 schema / 参照検査の PASS は、実モデルの Skill 発動・完了確認の代替ではない。
- 1024 文字は Skill の `description` の仕様上限であり、評価ケースの入力文字数の制限や、実モデルでの動作保証ではない。
