# Copilot instructions

<!-- hve-conductor:begin -->
## conductor toolkit（要求定義書・カタログ・System Test の一貫性）

- 長時間の開発の依頼は、custom agent `conductor` に 1 回で渡します（VS Code・GitHub Copilot app では `/build`）。手順は `.github/agents/` と `.github/skills/` にあります。
- 検証は `python scripts/verify.py`（`scripts/verify.ps1` / `scripts/verify.sh`）。exit 0 が合格です。
- 要求の正本は `docs/requirements-definition.md` で、編集は rd-author だけが行います。ID は `python scripts/next-id.py <種別>` でだけ採番します。
- System Test の台帳 `tests/system/ledger.json` は `python scripts/ledger.py` でだけ更新します。
- 一時ファイル（ログ・証跡・実行結果・作業メモ）は `/work` に置きます（git の管理対象外。14 日で削除）。
<!-- hve-conductor:end -->
