あなたは親 Step.{parent_step_id} (Custom Agent: {parent_custom_agent}) の SPLIT_REQUIRED
判定により分割された **サブタスク Sub-{index:03d}** を実行します。

== 重要ルール ==
- これは単一責務サブタスクです。**SPLIT_REQUIRED を再発させてはなりません**。
- 親タスクの context_size 制約により分割されたため、本タスクは self-contained に完遂すること。
- 完了時は下記「出力先（厳守）」のパスに以下を必ず作成すること:
  1. completion-report.md
  2. completion-report.md 内に検証マーカー `<!-- validation-confirmed -->` を含める
  3. completion-report.md 内に「## 検証」または「## 検証結果」セクションを含める

== サブタスク定義 ==
- index: Sub-{index:03d}
- title: {title}
- depends_on: {depends_on_str}
- labels: {labels_str}

== サブタスク本文 ==
{body}

== 出力先（厳守）==
- 正規パス（絶対パス）: **`{abs_output_dir}`**
- 正規パス（リポジトリ相対）: `{rel_output_dir}`
- CWD は親 runner によりリポジトリルート `{repo_root}` に固定されています（LLM 側で `cd` する必要はありません）。
- 例:
    - ✅ 正例: `{rel_output_dir}completion-report.md`
  - ❌ 誤例: `hve/work/{work_subdir}/completion-report.md`（このリポジトリには `hve/work/` という別ディレクトリも存在しますが、完了判定は参照しません）
- 全ての成果物（completion-report.md および本文内で言及するスライス／フラグメント等）を上記の正規パス配下に出力すること。

上記を遵守してサブタスクを完遂してください。
