# レビュー発動条件・統合ルール

> 本ファイルは `adversarial-review/SKILL.md` の §7 統合セクション詳細を収容する参照資料です。

---

## 実施条件・例外・誤適用防止

### 実施条件（明示時のみ実施）

以下のいずれかを満たす場合のみ実施する:

- Issue/PR body に `<!-- adversarial-review: true -->` を記載している場合
- `adversarial-review` ラベルが付与されている場合
- ユーザーが敵対的レビューを明示的に依頼した場合
- HVE CLI / GUI で `auto_contents_review=true` が選択され、Runner の Phase 3 として実行される場合

> ⚠️ **`auto-context-review` は敵対的レビューの実行条件に含めない**。

Cloud 経路で PR body に `<!-- adversarial-review: false -->` が明示されている場合は、専用ラベルまたは `true` marker より opt-out を優先する。同じ PR body に `true` / `false` が併記された場合も fail-closed で実施しない。

### 実行経路ごとの明示トリガー表現

- **Cloud Issue Form**: 「敵対的レビューを有効にする」のチェックを producer が `true` marker と Issue の `adversarial-review` ラベルへ変換し、PR作成時に専用ラベルへ同期する。
- **Cloud PR**: PR body の `true` marker を `copilot-auto-feedback.yml` が専用ラベルへ正規化する。ユーザーがPRへ専用ラベルを直接付与してもよい。
- **対話中のユーザー依頼**: Agent は「敵対的レビューを実施して」等の明示依頼を直接解釈して本スキルを発動する。
- **HVE CLI / GUI**: `auto_contents_review=true` を Runner が Phase 3 の発動条件として扱う。

HVE の Python Issue producer（`template_engine.py` / `orchestrator.py`）は `auto_contents_review` を Cloud marker / label へ変換しない。HVE のレビュー所有者はローカル Phase 3 であり、同じ選択を Cloud へ複製すると二重発動になるためである。HVE が作成した Issue / PR に別途 marker / label が明示されていない場合、Cloud resolver は default-disabled としてレビューを起動しない。

Cloud workflow は一般的な「レビューして」「品質を確認して」等の任意コメントを自然言語判定しない。曖昧な通常レビューを誤って敵対的レビューへ昇格させないため、CloudではIssue Form・marker・専用ラベルのいずれかで明示する。

### 通常時のセルフチェック

- 通常時は、Prompt 固有の観点を1回のインライン・セルフチェックとしてまとめて確認する。
- Prompt のレビュー観点は敵対的レビューの発動条件ではない。
- 通常時は Review Sub-agent を起動しない。
- HVE CLI / GUI では `auto_contents_review=true` の場合だけ Phase 3 が実施する。メインタスク内で別の Review Sub-agent を起動しない。
- 通常時のセルフチェックでは、敵対的レビュー用の成果物や再レビューサイクルを作成しない。

### 例外（省略）

§2.3 分割モード（Plan-Only）で、上記の明示トリガーがない場合は、本スキルの敵対的レビューを **省略する**。
明示トリガーがない場合は `plan.md` と `subissues.md` の簡易セルフチェックのみ実施する。marker / label / ユーザー依頼 / HVE Phase 3 のいずれかが明示された場合は、Plan-Only でも本スキルを実施する。

Plan-Only は第5の runtime trigger ではなく、Runner に専用の抑止分岐を追加しない。Cloud は marker / label resolver、対話中はユーザーの明示依頼、HVE CLI / GUI は `auto_contents_review` による Phase 3 がそれぞれ発動を所有する。これらの明示トリガーがなければ本スキル自体が呼ばれないため省略となる。`task_scope` だけで Runner を抑止すると、明示された HVE Phase 3 まで誤って無効化するため禁止する。

### 誤適用の防止

以下の場合であっても、ユーザーが上記の実施条件を明示していない限り、敵対的レビューは**不要**:

- PR に実装ファイル（.sh, .py, .sql, .ts, .js, .html, .css 等）の**作成または変更**が含まれる場合
- Sub Issue 由来の PR であっても、実装を含む場合
- PR のステータスが WIP / Partial / Blocked であっても、実装ファイルがコミットされている場合
- Prompt に「最終品質レビュー」「3つの観点」等のチェック観点が記載されている場合

### 判定基準

`git diff --name-only` の結果に `work/` 配下以外の実装ファイルが1つでも含まれる場合、敵対的レビューは**推奨（ユーザー選択時のみ実行）**。

```bash
git diff --name-only <base>...HEAD | grep -v '^work/'
```

## §7.1 セルフレビューとの違い

| 項目 | 旧・セルフレビュー | 敵対的レビュー（現行） |
|------|-------------------|----------------------|
| ペルソナ | 作成者自身 | 「敵対的レビュアー」（作成者ではないと明示） |
| KPI | 改善する | **問題を発見する** |
| 検証軸 | 3観点（機能/ユーザー/保守性） | 6軸（要件充足性/技術的正確性/整合性/非機能品質/捏造検出/オーバーエンジニアリング検出） |
| 重大度分類 | なし | Critical / Major / Minor |
| 合否ゲート | なし | Critical > 0 で FAIL |
| 再レビュー | なし | FAIL 時に修正→再レビュー（最大2サイクル） |
