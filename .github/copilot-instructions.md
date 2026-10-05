# Copilot 共通ルール

本ファイルはリポジトリ共通の入口。作業に該当する Skill だけを参照し、詳細手順をここへ複製しない。

## 実行・参照の境界

- **曖昧なリポジトリ内 HVE 実行意図の優先ルーティング（必須）**: 「Azure にデプロイして」「APP の Web アプリを作って」「バッチを実装して」のように Workflow / Step / APP-ID / resource group が未確定な依頼は、`hve-prompt-edition` の作成前ゲートへ渡す。外部 Azure Skill の実行、tool call、ファイル書き込みより前に不足値を解決する。依頼文と registry から一意に決まる値は、選んだ理由を記録して使う。inline で確認するのは、資格情報と、依頼で宣言されていないデプロイ先・課金・外部公開に関わる値だけにする（無人で実行されることが多く、確認しても答える人がいないため）。一意に決まらない値を推測で埋めて request / plan / run を開始しない。明示的な direct Azure（`azd` / `azure.yaml`）は Prompt Edition の対象外として、該当する既存の安全・承認規則に従う。
- **HVE の版管理と変更履歴（必須）**: 変更対象の独立ライフサイクルを確認し、完了時に対象パッケージの PATCH を1回だけ更新する。既存の Unreleased エントリーを保持して変更概要を追加する。詳細は `hve-dev/hve-app-tools.md`。
- **実行面と分割**: 分割するかは作業内容から判断し、分割する場合は独立して検証できる単位で分ける（`task-dag-planning`）。standalone / Cloud / CLI-GUI の適用条件は `.github/skills/_hve-plan-artifacts/hve-binding.md` を確認する。
  - **Prompt 版承認後の委譲（限定例外）**: 提示した計画への明示承認後、controller は SHA-256 を渡して `hve prompt run` へ委譲する。利用者の最初の依頼が無人実行と事前承認の範囲（`execution_policy`）を宣言し、計画の提示後に確認を待たないことを求めている場合は、その宣言を計画の承認として扱う（FR-PROMPT-13）。HVE が再計算した SHA-256 の一致を確認した場合だけ実行する。計画の規模や分割の有無を理由に承認済み委譲を止めない。controller は対象成果物を直接実装・編集してはならない。stale は再plan・再提示・再承認とし、既存の権限・認証・デプロイ承認と `output_paths` gate を維持する。
  - **Cloud Agent Orchestrator 配下モード**: Cloud の既存 Issue / PR / 分割手順を使い、Prompt Edition の実行経路へ読み替えない。

## 検索と検証

- ソースコードの所在・定義・参照は `code-query` を優先する（`python -m cq search`）。Markdown の要件・設計検索は `markdown-query` を使い、既知パスの編集前確認とは区別する。
- 完了は、要求定義から導いたコマンドの exit code で判定する。合否を文章だけで主張すると後から検証できないためである。検証コマンドの選び方は `harness-verification-loop` に従う。敵対的レビュー（marker / label / 明示的な敵対的レビュー依頼 / HVE Phase 3 のみ）は `adversarial-review` の発動規則に従う。
- Windows 自動化は最新の PowerShell 7+（`pwsh.exe -NoLogo -NoProfile`）を使う。Windows PowerShell 5.1 の直接実行・フォールバックは禁止。
- **テスト範囲**: 反復中に実行するのは対象テストのみとし、引数なしの全件実行をローカルで行わない。全件回帰は PR の CI で 1 回だけ確認する。層の選択は `tdd-red-green-reality` §1.7 のテストピラミッド定義、実行対象の限定は `harness-verification-loop` に従う。
- **着手条件**: 着手時に `git status --porcelain` と `git rev-parse --short HEAD`、対象テストの PASS / FAIL を baseline として記録する。
- **既存失敗の扱い**: 着手時点で失敗しているテストは修正対象にしない。完了判定コマンドは対象テストへ限定して exit 0 を目指し、baseline に既存 FAIL を含む場合に限り「baseline に無い新規 FAIL が 0 件」で判定する。
- 作業ファイルは `work/run/<run-id>/.../artifacts/`、原本 `docs-original/` は読み取り専用。秘密値を報告・コード・作業記録へ保存しない。
- **HVE 自己テスト限定の例外（FR-MAINT-12）**: 通常の `work/` 配置・保持規約より [tests/README.md](../tests/README.md) を優先する。全 controller 生成物は元リポジトリの `tests/run/<run-id>/<task>/` へ最初から保持し、指定ルートを子 session へ引き継ぐ。元リポジトリの `work/` へ自己テストの新規出力をしない。

## 完了条件と停止境界

- **承認済みの計画は利用者の要求定義**とする。完了条件は要求定義から導き、exit 0 で判定できるコマンドにする。要求定義の抜け漏れ・矛盾・曖昧さは、目的に最も適う合理的な判断で補い、判断と理由を記録して続行する。
- **停止してよいのは**次の 2 つだけとする。(1) 破壊的・不可逆・外部公開の操作（削除、force push、push、デプロイ、課金、権限変更など）に既存の明示承認が必要な場合。(2) 資格情報など利用者しか持たない情報が無いと進められない場合。その場合も、依存しない作業を先に終える。依頼で宣言された範囲（デプロイ先 `resource_group`・外部公開の可否・予算の注記）の操作は承認済みとして扱う。
- **ターンの終え方**: 作業が残っているのに次の形でターンを終えない。済んだことのまとめと次の手順の予告だけで終える、「希望が無ければ続けます」と申し出て返事を待つ、残りの作業を止めない判断事項の一覧を利用者に渡す、ターンが長くなったことや区切りが付いたことを理由に報告へ切り替える。途中経過や未決事項への推奨は、次のツール呼び出しと同じメッセージに書いて作業を続ける。答える人がいない状況で止まると、依頼した作業が進まないためである。危険な操作・破壊的な操作の確認の必要性は変わらない。
- **判定の根拠**: 合否を自然言語で主張せず、コマンドの実出力と exit code を根拠として提示する。要求定義から導いた受入基準と根拠を完了報告へ記録する。既存の `harness-verification-loop`・`tdd-red-green-reality` の検証規則と偽 PASS 禁止はそのまま適用する。
- **範囲**: 完了条件が要求する品質を満たす変更を行い、要求にない追加改善は未着手として報告へ分離する。

## 続行規則
- 次の安全な操作が明確で、承認境界・停止規則に触れない場合は、利用者の判断待ちにせず続行する。

## VS Code での対話作業（モデル・コンテキスト・委譲）

本節は VS Code などで利用者と対話しながら作業する場合の規則である。HVE が起動する SDK セッション（Workflow の各 Step）はモデル・context・委譲・承認を HVE の設定で決めるため、本節の対象ではない。

- **モデル選択**: 作業を `routine implementation` / `lightweight investigation` / `deep reasoning` に分類する。model picker で利用可能な最小十分のモデルの提案は、利用者がモデル選択を尋ねたとき、または作業を `deep reasoning` と判断したときだけ行い、それ以外では提案しない（作業に関係しない出力を増やさないため）。`deep reasoning` は通常モデルの有限な1試行で解消しない設計判断・根本原因だけに限定する。Agent は model picker を自動変更できないと明示し、利用可能なモデル名を推測しない。
- **context**: context の蓄積はモデルの context window と harness の自動 compaction に任せ、token 数・request 数・経過時間を理由に session を分割・停止しない。
- **委譲**: 多ファイルのread-only調査は `Explore`、長いone-shot commandは `execution_subagent` へ委譲し、親セッションへは要約だけを返す。密結合な実装や同じファイル群の編集を速度だけのために分割せず、本文脈に中間結果が必要な作業は親で行う。
- **承認境界**: terminal auto-approvalは `.vscode/settings.json` のread-only allowlistだけを使用する。test command、file write、Git状態変更、cloud／deployment commandは明示承認を維持し、auto-approvalをsecurity boundaryとして扱わない。

## §12 HVE アプリケーション保守ルーティング

- HVE 対象変更・不具合調査では `.github/skills/hve-requirement-traceability/SKILL.md` を使用する。
- HVE コアパスでは `.github/instructions/hve-maintenance.instructions.md` も適用する。
- `hve-dev/requirement-definition.md` 全文を既定の入力にしない。