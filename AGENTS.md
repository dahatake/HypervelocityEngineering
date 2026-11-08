# AGENTS.md

<!-- ebak-abk:begin -->
## Enterprise App Build Kit Lite（要求定義書・カタログ・System Test の一貫性）

- 振る舞いを変える変更（機能の追加・変更・削除）では、同じ変更の中で `docs/requirements-definition.md` の要求と受入基準（AC）を更新します。誰が編集してもかまいません（手順は skill `requirement-definition`）。
- 新しい ID は `python scripts/next-id.py <種別>` でだけ採番します。手で番号を振りません（複数の人・PC で並行しても重複させないため）。
- テストの名前かコメントに、検証する要求 ID と AC ID を書きます（例: `FR-012 AC-031`）。System Test の台帳 `tests/system/ledger.json` は `python scripts/ledger.py` でだけ更新し、テストを消す・弱めるときは `--reason` で理由を残します。
- ファイルを足す・名前を変える・消すときは、`docs/catalog.md` の行も直します（`python scripts/rdfix.py --apply` で追従できます）。
- 完了の前に `python scripts/verify.py` を実行して exit 0 にします（CI の `ebak-verify` も同じ検査をします）。
- 一時ファイル（ログ・証跡・作業メモ）は `/work` に置きます（git の管理対象外）。
<!-- ebak-abk:end -->

## このリポジトリ（toolkit の配布元）の保守

- toolkit のテスト: `python -m pytest tests/toolkit -q`
- 配布物の一覧は `tools/install.py` の `MANAGED` / `TEMPLATES` にあります。ファイルを追加・改名したら、ここと `users-guide/` を合わせて直します。
- 配布物（`MANAGED`・`TEMPLATES` の一覧か、配布するファイルの内容。`users-guide/` も配布物）を変えたら `python tools/build-uninstall-catalog.py` でアンインストーラーのカタログ `tools/uninstall-catalog.json` を作り直します（古いと `tests/toolkit/test_uninstall.py` が失敗します）。
- 版は `scripts/ebaklib.py` の `TOOLKIT_VERSION` で管理します。
