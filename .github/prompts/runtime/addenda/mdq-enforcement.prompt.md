# Markdown-Query Skill 強制利用ルール (GUI 設定由来)
以下のフォルダ配下の Markdown ファイル (.md) を参照する必要が生じた場合は、`read_file` や `grep_search` を使う前に、必ず `markdown-query` Skill (`python -m mdq search --q "<キーワード>" --top-k 5 --max-tokens 800`) を最優先で使用すること。

対象フォルダ:

例外:
  - `python -m mdq search` のヒットが 0 件のとき、または対象が `.md` 以外のときに限り、`grep_search` / `read_file` へフォールバックしてよい。
  - 索引未生成・索引が古いと判定された場合は `python -m mdq index` を実行してから再検索する。
