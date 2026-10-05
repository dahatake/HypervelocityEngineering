# エージェント共通ルール（補足）

共通ルールの正本は [copilot-instructions.md](copilot-instructions.md) と各 Skill（`.github/skills/*/SKILL.md`）。本ファイルはその補足で、記述が食い違う場合は copilot-instructions.md と Skill に従う。

## 一時作業ファイルの置き場所

調査スクリプト、デバッグ出力、ログ、プローブ、実験結果などの一時ファイルは `work/run/<run-id>/.../artifacts/` に作成する（Skill `work-artifacts-layout`）。リポジトリルート直下には置かない。`_tmp_*.py`・`tmp*`・`debug_*`・`*.out.txt`・`MagicMock/` なども同じ扱いで、`.gitignore` の対象かどうかは関係しない。

理由: ルート直下の新規ファイルは、PR の `protect-readonly-paths.yml`（`check-root-temp-files` ジョブ）で fail になる。ルートに追加できるのは、同ワークフローの `ROOT_FILE_ALLOWLIST` / `ROOT_DIR_ALLOWLIST` に載っているリポジトリ標準ファイルだけである。追加が必要な場合は、同じ PR で許可リストも更新する。
