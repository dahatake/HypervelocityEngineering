# task-dag-planning（詳細）

このファイルは `SKILL.md` から移設した詳細手順・コマンド例・トラブルシューティングを保持します。

---


# task-dag-planning

## 目的
- DAG（依存関係）で分解し、タスク粒度とコンテキストサイズで分割判断を行う。

## Non-goals
- **実装の実行** / **テストの実行**（harness-verification-loop）/ **Sub Issue の GitHub 直接作成** / **コンテキスト収集**（task-questionnaire）

## 手順
1) AC と非対象を箇条書きで固定
2) 最小棚卸し（対象一覧 / 根拠 / 検証手段）
3) DAG作成（ノード=レビュー可能な成果物）
4) 各ノードに成果物 / 参照元 / 変更候補パス / 検証 / 参照ファイル数（context_size算定用）を付与
5) 分割判定: 下記のいずれかに該当する場合 **SPLIT_REQUIRED**、すべて非該当なら **PROCEED**（詳細: `dag-rules-detail.md` §2.2）
   - task_scope=multi（独立して検証可能な成果物が 2 つ以上）
   - context_size=large（参照ファイル 9 件以上、または単一ファイル 500 行超）
   （PROCEED = task_scope=single **かつ** context_size=small または medium のみ）

**注意（過去の誤判断事例）**: ❌ context_size=large で「分割不要」と判断し全実装 → ✅ context_size=large = SPLIT_REQUIRED

## plan.md の最小フォーマット
概要（目的/非対象/根拠）・AC（チェックボックス）・DAG（ノード一覧と依存）・task_scope/context_size と分割判定・検証計画・次に実装するSub

## subissues.md の最小フォーマット
Title・背景（1〜3行）・AC・根拠（パス/箇所）・変更候補パス・検証・context_size / 依存

SPLIT_REQUIRED の場合は `subissues-template.md` を `read` してコピーし、各 `<!-- subissue -->` ブロック内に `<!-- title: ... -->` を必ず配置すること（空値禁止）。テンプレート準拠のため、`<!-- subissue -->` の直後に置くことを推奨する。

---

## §2.1.2 plan.md メタデータ必須手順（全 Custom Agent 共通 — 省略禁止）

> ⚠️ メタデータと `## 分割判定` セクションのない plan.md は CI (`validate-plan.yml`) で自動的に拒否される。

**手順 1**: plan.md の冒頭 5 行に以下の HTML コメントを記載する（CI 自動検証に使用）。
テンプレートファイル `plan-template.md` を `read` してコピーすること:

```
<!-- task_scope: single|multi -->
<!-- context_size: small|medium|large -->
<!-- split_decision: PROCEED or SPLIT_REQUIRED -->
<!-- subissues_count: N -->
<!-- implementation_files: true or false -->
```

**手順 2**: plan.md 本文に `## 分割判定（必須）` セクションを含める:

```
## 分割判定（必須）
- task_scope: single|multi
- context_size: small|medium|large（参照ファイル数: small=1-3, medium=4-8, large=9以上または 500行超ファイル含む）
- 判定結果: PROCEED / SPLIT_REQUIRED
- 判定根拠: 以下のいずれかを列挙
    - task_scope=multi に該当（独立成果物が 2 つ以上）
    - context_size=large に該当（参照ファイル 9 件以上または 500 行超）
    - 上記いずれも非該当 → PROCEED（task_scope=single、context_size=small または medium）
- （SPLIT_REQUIRED の場合）subissues.md: 作成済み / 未作成
- （PROCEED の場合）実装に進む理由: task_scope=single、context_size=XX
```

> ⚠️ task_scope=multi または context_size=large で「判定結果: PROCEED」と記載することは禁止。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `dag-rules-detail.md` | §2.1 DAG+見積の作成ルール、§2.1.1 見積の最低基準、§2.2 分割判定（疑似コード＋禁止事項）、§2.3 分割モード（Plan-Only）全ルール |
| `plan-template.md` | plan.md のコピペ用テンプレート。メタデータ4行 + `## 分割判定` セクションを含む。Agent は plan.md 作成時にこのテンプレートを `read` してから書き始めること。 |
| `subissues-template.md` | subissues.md のコピペ用テンプレート。各 `<!-- subissue -->` に対する `<!-- title: ... -->` 必須ルール、`labels/custom_agent/depends_on` の記法、置換時の注意事項を含む。 |

---

## 直列/並列の判断と共有

### 直列（同一 Sub に寄せる）

- 同じファイル/同じ公開 I/F（API/スキーマ/設定キー）を高確率で触る
- 移行/互換/後戻り困難な変更
- 仕様確定→実装の依存が強い

### 並列（別 Sub/別 PR に分離）

- 対象ディレクトリ/サービスが分離している
- 追記中心で衝突しにくい（例：モジュール別ドキュメント）
- テスト追加が独立

### 共有方法（必須）

- 共有すべき前提（契約/一覧/決定事項）は **PR コメントではなくファイル** に残す（後続が確実に読める形）。

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（PROCEED）**: `<!-- task_scope: single -->` `<!-- context_size: medium -->` `<!-- split_decision: PROCEED -->` → 判定結果: PROCEED（task_scope=single、context_size=medium）

**例2（SPLIT_REQUIRED by task_scope）**: `<!-- task_scope: multi -->` `<!-- split_decision: SPLIT_REQUIRED -->` `<!-- subissues_count: 3 -->` → task_scope=multi = SPLIT_REQUIRED

**例3（SPLIT_REQUIRED by context_size）**: `<!-- task_scope: single -->` `<!-- context_size: large -->` `<!-- split_decision: SPLIT_REQUIRED -->` → context_size=large に該当

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-questionnaire` | 前提 | コンテキスト収集完了後に本Skillへ遷移 |
| `work-artifacts-layout` | 出力先 | plan.md / subissues.md の配置パス |
| `harness-verification-loop` | 後続 | 実装後の検証パイプライン |
| `adversarial-review` | 後続 | レビュー（ユーザー指定時のみ） |
