---
name: task-dag-planning
description: >
  タスクの依存関係（DAG）で分解し、分単位の見積と分割判断を行うスキル。
  plan.md / subissues.md を作成し、15分超のタスクを安全に分割する。
  USE FOR: create plan, estimate task, split issue, DAG planning,
  dependency analysis, plan.md creation, subissues.md generation,
  15-minute threshold check, SPLIT_REQUIRED decision, PROCEED decision.
  DO NOT USE FOR: implementation execution (agents do that separately),
  running tests (use harness-verification-loop),
  creating GitHub issues directly (use create-subissues workflow),
  context gathering (use task-questionnaire).
  WHEN: 計画を立てたい、見積をしたい、タスクを分割したい、
  plan.md を作成したい、subissues.md を作成したい、
  DAG を作成、依存関係を整理、15分超の作業、
  分割判定、SPLIT_REQUIRED、PROCEED 判定。
metadata:
  origin: user
  version: "2.0.0"
---

# task-dag-planning

## 目的
- DAG（依存関係）で分解し、分単位の見積と分割判断を行う。

## Non-goals
- **実装の実行** / **テストの実行**（harness-verification-loop）/ **Sub Issue の GitHub 直接作成** / **コンテキスト収集**（task-questionnaire）

## 手順
1) AC と非対象を箇条書きで固定
2) 最小棚卸し（対象一覧 / 根拠 / 検証手段）
3) DAG作成（ノード=レビュー可能な成果物）
4) 各ノードに成果物 / 参照元 / 変更候補パス / 検証 / 見積（R+P+I+V+F）/ 不確実性（低中高）を付与
5) 分割判定: 下記のいずれかに該当する場合 **SPLIT_REQUIRED**、すべて非該当なら **PROCEED**（詳細: `references/dag-rules-detail.md` §2.2）
   - 見積合計 > 15分
   - 見積合計 ≤ 15分 **かつ** 不確実性「中」または「高」
   （PROCEED = 見積合計 ≤ 15分 **かつ** 不確実性「低」のみ）

**注意（過去の誤判断事例）**: ❌ 見積33分で「分割不要」と判断し全実装 → ✅ 33 > 15 = SPLIT_REQUIRED

## plan.md の最小フォーマット
概要（目的/非対象/根拠）・AC（チェックボックス）・DAG（ノード一覧と依存）・見積合計と分割判定・検証計画・次に実装するSub

## subissues.md の最小フォーマット
Title・背景（1〜3行）・AC・根拠（パス/箇所）・変更候補パス・検証・見積（<=15）/ 不確実性 / 依存

SPLIT_REQUIRED の場合は `references/subissues-template.md` を `read` してコピーし、各 `<!-- subissue -->` ブロック内に `<!-- title: ... -->` を必ず配置すること（空値禁止）。テンプレート準拠のため、`<!-- subissue -->` の直後に置くことを推奨する。

---

## §2.1.2 plan.md メタデータ必須手順（全 Custom Agent 共通 — 省略禁止）

> ⚠️ メタデータと `## 分割判定` セクションのない plan.md は CI (`validate-plan.yml`) で自動的に拒否される。

**手順 1**: plan.md の冒頭 4 行に以下の HTML コメントを記載する（CI 自動検証に使用）。
テンプレートファイル `references/plan-template.md` を `read` してコピーすること:

```
<!-- estimate_total: XX -->
<!-- split_decision: PROCEED or SPLIT_REQUIRED -->
<!-- subissues_count: N -->
<!-- implementation_files: true or false -->
```

**手順 2**: plan.md 本文に `## 分割判定（必須）` セクションを含める:

```
## 分割判定（必須）
- 見積合計: XX 分 / 15分以下か: YES/NO / 不確実性: 低/中/高
- 判定結果: PROCEED / SPLIT_REQUIRED
- 判定根拠: 以下のいずれかを列挙
    - 「見積合計 > 15分」に該当（XX分 > 15分）
    - 「見積合計 ≤ 15分 かつ 不確実性 中/高」に該当
    - 上記いずれも非該当 → PROCEED（見積 XX分 ≤ 15分、不確実性: 低）
- （SPLIT_REQUIRED の場合）subissues.md: 作成済み / 未作成
- （PROCEED の場合）実装に進む理由: 見積 XX分 ≤ 15分、不確実性: 低
```

> ⚠️ 見積合計 > 15分で「判定結果: PROCEED」と記載することは禁止。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/dag-rules-detail.md` | §2.1 DAG+見積の作成ルール、§2.1.1 見積の最低基準、§2.2 分割判定（疑似コード＋禁止事項）、§2.3 分割モード（Plan-Only）全ルール |
| `references/plan-template.md` | plan.md のコピペ用テンプレート。メタデータ4行 + `## 分割判定` セクションを含む。Agent は plan.md 作成時にこのテンプレートを `read` してから書き始めること。 |
| `references/subissues-template.md` | subissues.md のコピペ用テンプレート。各 `<!-- subissue -->` に対する `<!-- title: ... -->` 必須ルール、`labels/custom_agent/depends_on` の記法、置換時の注意事項を含む。 |

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（PROCEED）**: `<!-- estimate_total: 11 -->` `<!-- split_decision: PROCEED -->` → 判定結果: PROCEED（11 ≤ 15、不確実性: 低）

**例2（SPLIT_REQUIRED）**: `<!-- estimate_total: 30 -->` `<!-- split_decision: SPLIT_REQUIRED -->` `<!-- subissues_count: 3 -->` → 30 > 15 = SPLIT_REQUIRED

**例3（エッジ: 不確実性「中」で12分 → SPLIT_REQUIRED）**: `<!-- estimate_total: 12 -->` `<!-- split_decision: SPLIT_REQUIRED -->` → 不確実性 == 中 に該当

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-questionnaire` | 前提 | コンテキスト収集完了後に本Skillへ遷移 |
| `work-artifacts-layout` | 出力先 | plan.md / subissues.md の配置パス |
| `harness-verification-loop` | 後続 | 実装後の検証パイプライン |
| `adversarial-review` | 後続 | レビュー（ユーザー指定時のみ） |
