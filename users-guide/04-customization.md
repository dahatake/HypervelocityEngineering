**日本語** | [English](04-customization.en.md)

# 4. 設定とカスタマイズ

設定は `scripts/ebak.config.json` の 1 ファイルにまとまっています。インストーラで更新しても、利用者が設定した値は残ります。新しいキーだけが追加されます。

```json
{
  "management_files": { "requirements": "docs/requirements-definition.md", "catalog": "docs/catalog.md", "...": "..." },
  "base_branch": "main",
  "work": { "dir": "work" },
  "checks": { "profile": "lite", "lite_checks": ["CHK-01", "CHK-02", "CHK-03", "CHK-05", "CHK-09", "CHK-12", "CHK-17", "CHK-19", "CHK-24"] },
  "system_test": { "jobs": "auto", "batch_pytest": true, "budget": { "max_active_cases": 100, "...": "..." } },
  "verify": { "timeout_sec": 1800, "commands": [] },
  "extensions": { "checks": [] }
}
```

省略したキーには、`scripts/ebaklib.py` の `DEFAULT_CONFIG` の既定値が使われます。`_note` で始まるキーは説明文で、動作には影響しません。

## 4.1 依頼に毎回付けたい前提

EABK Lite には hook も定型文の自動付与もありません。毎回伝えたい前提は、自分の Copilot の instructions（`AGENTS.md` のブロックの外や、利用者ごとの instructions）に書きます。

## 4.2 管理データのパス（`management_files`）

| キー | 既定値 | 内容 |
|---|---|---|
| `requirements` | `docs/requirements-definition.md` | 要求定義書（正本） |
| `requirements_dir` | `docs/requirements` | 要求定義書を分割したときの置き場所 |
| `catalog` | `docs/catalog.md` | カタログ |
| `id_registry` | `docs/id-registry.md` | ID 台帳（`next-id.py` だけが書きます） |
| `ledger` | `tests/system/ledger.json` | System Test の台帳（`ledger.py` だけが書きます） |
| `manual_tests` | `docs/manual-tests.md` | 手動テストの記録 |
| `integrations` | `docs/integrations.md` | 外部連携カタログ |

既存のディレクトリ構成に合わせて変更できます。変更したら `python scripts/verify.py --docs-only` で、検査が新しいパスを読めるかを確かめます。

## 4.3 基準のブランチと作業フォルダー（`base_branch` / `work`）

| キー | 既定値 | 意味 |
|---|---|---|
| `base_branch` | `main` | 差分の検査（CHK-12 など）で比べる基準のブランチ。rd-auditor の差分の監査も、このブランチとの差分を見ます |
| `work.dir` | `work` | 一時ファイル（ログ・証跡・実行結果・監査の結果）の置き場所。git の管理対象外です。EABK Lite は `/work` を自動では消しません。不要になったら手で削除します |

## 4.4 検査の範囲（`checks`）

| キー | 既定値 | 意味 |
|---|---|---|
| `profile` | `lite` | `lite` は `lite_checks` の CHK だけを報告します。`full` は CHK-00〜34 をすべて報告します |
| `lite_checks` | `CHK-01, CHK-02, CHK-03, CHK-05, CHK-09, CHK-12, CHK-17, CHK-19, CHK-24` | lite で報告する CHK。構造と追跡性（ID・参照・AC・テストのつながり）の検査です |
| `ambiguous_words` | 適切、迅速、直感的 など | 曖昧な語のリスト（CHK-13。full のとき） |
| `unit_pattern` | 秒・件・% などの正規表現 | 直書きの数値と単位とみなすパターン（CHK-14。full のとき） |
| `id_scan_exclude` | `docs/**`、`scripts/**`、`EABK-Studio/**` など | コードから要求 ID を探すときに除くパス（CHK-17・CHK-19） |
| `test_path_pattern` | `tests/`、`*.test.*` など | テストコードとみなすパス（CHK-09） |
| `temp_file_pattern` | `*.log`、`test-results/` など | commit してはいけない一時ファイル（CHK-23） |

- lite では、`lite_checks` にない CHK は出力にも終了コードにも影響しません。報告する CHK を増やすには、`lite_checks` に ID を足します。リストは既定値と結合されず、書いたもので置き換わります。
- 1 回だけ範囲を変えるには、`python scripts/verify.py --profile full` のように `--profile lite|full` を指定します（`rdcheck.py check` も同じ）。指定は設定より優先されます。要約の行の `profile=lite` で、どちらで検査したかが分かります。
- プロファイルは `rdcheck.py check`・`verify.py`・`rdfix.py`（`--full` を含む）に同じように効きます。`rdfix.py --full` は、同じプロファイルの `verify.py --docs-only` が合格するときに合格します（カタログの同期などの機械的な修復は、どのプロファイルでも同じように行います）。
- 書式の警告（CHK-13 の曖昧な語、CHK-14 の数値の直書き、CHK-15 の禁止同義語など）は full にだけあります。節目の監査や、見たいときに `python scripts/verify.py --docs-only --profile full --show-warnings` で確認します（[6.2](06-quality-gates.md#62-検査プロファイルlite-と-full)）。

## 4.5 System Test の実行（`system_test`）

| キー | 既定値 | 意味 |
|---|---|---|
| `jobs` | `auto` | `ledger.py run` で同時に実行するケースの数（`N` または `auto`。auto は CPU 数 ÷ 4、2〜6）。ポートやデータを共有しないケースだけで使います |
| `serial_patterns` | `["default_port"]` | command にこの文字列を含むケースは、並列の実行が終わってから単独で動きます。ケースに `"serial": true` を付けても同じです |
| `batch_pytest` | `true` | 同じ pytest ファイルを指すケースを 1 つの pytest プロセスにまとめます。失敗したケースだけを単独で再実行します。`ledger.py run --no-batch` でも止められます |
| `budget` | `max_active_cases: 100` など | `ledger.py cost --check` が見る上限（有効なケースの数、要求あたりのケースの数、1 ケースと全体の秒数）。超えると exit 1 です |

## 4.6 ビルド・静的解析・テストのコマンド（`verify.commands`）

`scripts/verify.py` は、管理データの検査の後に、ここに登録したコマンドを順に実行します。1 つでも失敗すると exit 1 です。CI の `ebak-verify` も同じコマンドを実行します。

```json
"verify": {
  "timeout_sec": 1800,
  "commands": [
    { "name": "install", "run": "npm ci", "cache_files": ["package.json", "package-lock.json"] },
    { "name": "build", "run": "npm run build" },
    { "name": "lint", "run": "npm run lint", "parallel": true },
    { "name": "unit", "run": "npm test -- --run", "parallel": true },
    { "name": "e2e-smoke", "run": "npx playwright test --grep @canary", "slow": true, "timeout_sec": 900 }
  ]
}
```

| キー | 意味 |
|---|---|
| `name` | 表示名。ログのファイル名にも使います |
| `run` | リポジトリのルートで実行するシェルコマンド |
| `slow` | `true` のコマンドは、`verify.py --quick` ではスキップします。手元で素早く確かめるときに使います（CI は `--quick` を付けないので実行します） |
| `parallel` | 連続する `parallel: true` のコマンドを同時に実行します（lint・型検査・単体テストなど）。前の工程が必要なもの（build）には付けません |
| `timeout_sec` | このコマンドのタイムアウト（既定は `verify.timeout_sec`） |
| `cache_files` | これらのファイルが前回の成功時から変わっていなければ、スキップします（依存の導入向け。`--no-cache` で無効） |

- `verify.retry_on`（正規表現）に一致する環境起因の失敗（vitest の `Timeout calling`、`ECONNRESET` など）は、1 回だけ自動で再実行します。止めるには `verify.retry_flaky: false` にします。
- `"commands": ["python -m pytest -q"]` のように文字列だけでも書けます（`name` はコマンドの先頭の語）。`run` のない要素や不正な要素は `FAIL config` で verify を失敗させます。
- ログの全文は `/work/logs/` に保存され、コンソールには失敗の要約だけが出ます。
- 新しく導入した直後の `verify.commands` は空（`[]`）です。導入先のビルド・テストのコマンドを自分で登録します（Copilot に「このスタックの標準のビルドとテストのコマンドを `verify.commands` に登録して」と頼んでもかまいません）。

| スタック | 例 |
|---|---|
| .NET | `dotnet build --nologo`、`dotnet test --nologo` |
| Python | `python -m ruff check .`、`python -m pytest -q` |
| Java (Gradle) | `./gradlew build` |
| Go | `go vet ./...`、`go test ./...` |

## 4.7 プロジェクト固有の検査（`extensions.checks` / `scripts/ext/`）

データ層の検査（`rdcheck.py`・`rdfix.py`・`verify.py`）にプロジェクト固有の検査を足すときは、toolkit のファイル（`scripts/*.py`・`scripts/metadata.json`）を編集せず、次のどちらかで登録します。登録は toolkit の更新（`--force` を含む）で上書きされません。

1. `extensions.checks` に `{"module": "project_checks", "function": "check_integrations", "target": "rdcheck"}` を書きます。`module` は `scripts/` から import できるモジュール名、`target` は `rdcheck`・`rdfix`・`both`（省略時）です。
2. `scripts/ext/*.py` に置きます。公開関数（`_` で始まらないもの。`CHECKS = [...]` があればそれだけ）を自動で読み込みます。対象は関数の属性 `target` かファイルの `TARGET` で決めます（既定 `both`）。

検査は `f(root, cfg)` の形で、指摘の一覧を返します。空（または `None`）なら合格です。指摘は `{"level": "ERROR", "chk": "PRJ-01", "loc": "docs/integrations.md:7", "msg": "…"}`、`(level, chk, loc, msg)` の組、または文字列で返します。出力は標準の検査と同じ `ERROR <検査項目> <位置> <内容>` の形式です。`WARN` は終了コードに影響しません。

`verify.py` は、呼んだ拡張ごとに `EXT <モジュール>.<関数> target=… result=pass|warn|fail …` の 1 行を出します。登録したのに呼ばれない拡張は `EXT-WARN` の行になります。読み込めない拡張や例外を出した拡張は、`ERROR EXT-LOAD` / `EXT-ERROR` で不合格になります。

toolkit の更新では、利用者が `scripts/*.py` に直接足した配線を `tools/install.py` が調べます。更新で脱落するものは `WARN-WIRING  <ファイル>:<行>` で表示します。表示されたら、上の方法で登録し直します。

## 4.8 撤去した設定のキー（0.5.x から更新した場合）

0.6.0（EABK Lite）では、run と hook を前提にした次のキーがなくなりました。インストーラは旧版の設定を書き換えません。通常の更新ではこれらのキーが残りますが、もう読みません。消すときは `--clean`（クリーンインストール）で設定を既定から作り直すか、手で削除します（[9.4](09-versioning.md#94-旧版から更新するクリーンインストール)）。

| 撤去したキー | 0.5.x での用途 |
|---|---|
| `gates` | 役割ごとの hook のゲート（G-1〜G-6）、終了前の verify、外部ツールの判定 |
| `limits` | run の時間予算（`max_hours` など） |
| `credits` | AI クレジットの推定 |
| `worktree_share` | 作業用 worktree の依存ディレクトリの共有 |
| `prompt_prefix` | hook による定型文の自動付与 |
| `work.retention_days` | `/work` の 14 日の清掃（もうありません） |
| `verify.commands` の `toolkit-unit` | 撤去した `clean-work.py` のテスト |
| `verify.commands` の `studio-ui`（`python -m pytest -q EABK-Studio/tests`） | EABK Studio のテスト。導入先には `EABK-Studio/tests/` を入れなくなりました |

`.github/ebak-prompt-prefix.md` と hook のファイル（`.github/hooks/quality-gates.json`・`.github/hooks/prompt-prefix.json`・`scripts/hooks/gate.py`）は、もう読みません。旧版から更新するときは `--clean` を使うと、これらも削除されます。

## 4.9 MCP Server・plugin・拡張機能を使う

利用者が GitHub Copilot に設定した MCP Server・plugin・拡張機能のツールと skill は、いつもの Copilot（既定のエージェント）と rd-auditor で、追加の設定なしに使えます。例は Work IQ（社内のメール・会議・チャット・ドキュメント）、Microsoft Learn、Azure MCP Server です。

- **設定する場所**: 利用者ごと（VS Code のユーザー設定、`~/.copilot/`、GitHub Copilot app の **カスタマイズ** → **MCP**）か、リポジトリ（`.vscode/mcp.json`、GitHub のリポジトリ設定）に登録します。認証情報はリポジトリに置かず、各利用者のサインインや環境変数で渡します。toolkit は MCP Server の設定を配布しません。
- **出典の記録**: 社内の情報から得た事実は、要求定義書の出典台帳（SRC-ID）に出典付きで記録します（skill `requirement-definition`）。同じツールを持たない人も、要求定義書だけで同じ情報をたどれます。
- **外部のシステムの変更**: EABK Lite は外部への変更（メール送信、チケット作成、リソースの作成、デプロイ）を止めません。Copilot の通常の確認（ツールの承認）で判断します。
- **rd-auditor の制限**: rd-auditor の `.github/agents/rd-auditor.agent.md` の frontmatter に `tools:` を書くと、列挙していないツール（MCP Server のツールを含む）は使えなくなります。足すときは `<サーバー名>/*` の形で列挙します。

## 4.10 規則・エージェント・手順書を変更する

- **規則**: インストーラは `AGENTS.md` と `.github/copilot-instructions.md` に、`<!-- ebak-abk:begin -->` 〜 `<!-- ebak-abk:end -->` の区切りで規則のブロックを書きます。区切りの中は更新のたびに書き直されます。プロジェクト独自の規則は、区切りの外に書きます。
- **画面の見た目**: EABK はデザインシステムを指定しません。使いたいもの（例: 「Web は Fluent 2」「社内のブランドガイドに従う」）は、要求定義書の既定制約に書くか、依頼に書きます。
- **エージェントと手順書**: `.github/agents/rd-auditor.agent.md` と `.github/skills/*/SKILL.md` は直接編集してかまいません。インストーラを再実行しても、ローカルで変更したファイルは上書きされません（`KEEP-LOCAL`）。新しい版を取り込むときは、`--dry-run` で確認してから、差分を手でマージするか `--force`（`.ebak-backup-*` を残します）を使います。
- **モデル**: EABK はモデルを指定しません。rd-auditor を特定のモデルに固定したい場合は、frontmatter に `model:` を書きます。

## 4.11 CI

`.github/workflows/ebak-verify.yml`（ebak-verify）は、pull request と main への push で `scripts/verify.sh --show-warnings` を実行します。検査の範囲は `checks.profile` に従います（既定は lite）。手元の `python scripts/verify.py` と同じ検査なので、AGENTS.md の規則が、人や PC に関係なく push のたびに確かめられます。アプリのビルドに必要なツールチェーン（`actions/setup-node` など）は、verify のステップの前に追加します。CodeQL や依存関係のスキャンも、このワークフローに追記できます。

### データ層の修復（CI では修復しない）

CI は検査だけを行い、データ層を修復しません（`ebak-verify` の権限は contents の read だけです）。データ層の検査が不合格なら、手元で共通の入口 `python scripts/rdfix.py --full --apply` を実行して再検査し、修復を同じ変更に含めて push します（終了コード 0/1/2 は [05](05-scripts-reference.md)）。要求定義書と `docs/integrations.md` は変更しません。インストーラも導入後にこの入口を 1 回呼びます。`--no-repair` で検査と計画だけ（書き込まない）、`--skip-verify` で検査も修復もしません。

CI が修復しない理由: 読むだけの CI には書き込みの権限が要りません。また、bot が誰かの PR のブランチへ修復を push すると、ほかの人・PC のブランチと食い違います。以前の版で配っていた `.github/workflows/ebak-data-layer.yml`（自動修復の commit と Issue）は、旧版から `--clean`（クリーンインストール）で更新すると削除されます（[9. 版の管理](09-versioning.md)）。ワークフローを入れたくない場合は、インストール時に `--no-ci` を指定します。
