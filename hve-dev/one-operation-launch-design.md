# HVE OS-only 1操作起動 設計書

## 1. 目的と適用範囲

本書は `FR-LOCAL-SURFACE-04` を実装するための技術設計正本である。

### T07 採択結果

- 採択方式: **A — private source ZIP＋既存 setup＋共通 verifier**
- 採択日: 2026-09-06
- Windows 根拠: System32-only の隔離条件から固定 PowerShell ZIPを取得・検証し、通常 pathと`'` / `!`を含むpathの双方でPowerShell Core 7.6.5を起動。WinGet client packageのredirect・hash・実module/command所有・cleanupを確認。実repair / clean OSは未実施。
- macOS 根拠: canonical probeの構文、Darwin fake harness 4件、workflow契約13件、固定Homebrew installer、macOS 15/26 runner資料を確認。GitHub-hosted native runとclean OSは未実施。
- 採択の意味: product test / implementation を開始してよいという意味ではない。T03のmapping、T08〜T11のRED、T12のinventory照合を満たした後に限る。
- 最終合格条件: T22のWindows 11 x64、T24のmacOS 15 arm64 / macOS 26 arm64の全3セル。未実行セルを他の成功で補わない。
- 不採択: Bは公開または取得認証を追加するため、C/Dは子process・QtWebEngine・署名等の変更が大きいため、既定条件では採らない。

### 採用条件

- 対象アプリ: HVE CLI / GUI 本体
- 配布: 認証済み利用者へ private ZIP を渡す
- 1操作の開始点: ZIP を書き込み可能なローカルディレクトリへ展開した後、ZIP 直下の OS 別ランチャーを起動する時点
- 1操作から除外: ZIP の取得・展開、OS が直接表示する UAC / `sudo` / Command Line Tools / Gatekeeper の確認、GUI 表示後の GitHub CLI / GitHub Copilot 認証
- 対象環境: Windows 11 x64、Apple Silicon macOS 15 / 26
- 初回 network: 必須
- 完了点: HVE GUI の MainWindow が表示され、Markdown preview / GitHub CLI ログイン用 PTY / Copilot CLI の既存導線を利用できる状態
- 配布段階: private trial。installer、単体 exe / `.app`、署名・公証、公開匿名配布は対象外

## 2. 設計原則

1. **既存 setup を導入処理の唯一の正本にする。** Python extras、SDK runtime、外部 Copilot CLI、gh、PTY、翻訳、preview assets の導入を新ランチャーへ複製しない。
2. **Python がない段階と、Python が使える段階を分離する。** 最上位ランチャーは OS 標準機能だけで PowerShell 7 / Homebrew までを解決し、その後は既存 setup と Python verifier へ委譲する。
3. **高速経路を先に判定する。** 既存 `.venv` が現在の必須検証に合格する場合は package manager と setup を呼ばず、GUI だけを起動する。
4. **成功条件を単一 verifier に集約する。** setup の終了コードやファイルの存在だけを成功条件にしない。
5. **認証と起動を分離する。** setup / verifier はログイン、token 永続化、MCP 構成変更を行わない。
6. **利用者所有物を保護する。** source、設定、生成成果物を自動削除・上書きしない。HVE 所有の `.venv` と一時 bootstrap ファイルだけを検証付きで再生成できる。
7. **新しい設定面を作らない。** 新規 CLI option、GUI setting、環境変数、daemon、service、updater、plugin framework を追加しない。

## 3. コンポーネント

| コンポーネント | 種別 | 責務 | 非責務 |
|---|---|---|---|
| `Start-HVE.cmd` | ZIP 直下の生成物 | Windows 高速経路、PowerShell 7 の native bootstrap、`Start-HVE.ps1` 委譲 | Python package 導入、認証、Workflow 実行 |
| `Start-HVE.command` | ZIP 直下の生成物 | macOS 高速経路、CLT / Homebrew bootstrap、既存 setup / verifier / GUI の順序制御 | shell profile 永続変更、認証、Workflow 実行 |
| `hve/bootstrap/Start-HVE.cmd.in` | planned source template（T14） | Windows 生成物の正本 | 実行時の platform 判定 |
| `hve/bootstrap/Start-HVE.ps1` | planned source（T14） | PowerShell 7 / WinGet 解決後の Windows setup / verify / launch | Windows PowerShell 5.1 対応 |
| `hve/bootstrap/Start-HVE.command.in` | planned source template（T15） | macOS 生成物の正本 | Linux 対応、Intel / Rosetta 対応 |
| `hve/bootstrap_verify.py` | planned source / 共通 core（T13） | setup と top-level launcher が共有する readiness predicate、現在環境の GUI 起動可否、外部 PATH 上の Copilot CLI 解決を構造化結果で判定 | package install、network、認証、修復 |
| `.github/scripts/build-hve-bootstrap.py` | planned 開発時 script（T16） | allowlist 収集、manifest と OS 別 ZIP の決定的生成 | Release 公開、署名、installer 生成 |
| `hve/setup-hve.ps1` / `.sh` | 既存 | Python / tools / venv / extras / assets の導入 | GUI の自動起動、GitHub / Copilot 認証 |
| `hve.cmd` / `hve.sh` | 既存 | `.venv` の Python から HVE を起動 | 初回 OS bootstrap |

## 4. ディレクトリとデータ所有権

### 配布 root

ZIP を展開したディレクトリを `distribution_root` とする。次を同じ root から解決する。

- `pyproject.toml`
- `hve/`, `mdq/`, `cq/`, `tools/`
- `.github/` の runtime 契約
- `template/`, `users-guide/`
- `hve.cmd`, `hve.sh`, OS 別 `Start-HVE.*`
- `.venv/`（利用先で生成）
- `hve-bootstrap-manifest.json`

カレントディレクトリ、ユーザーの `PYTHONPATH`、別 checkout を root 解決に使用しない。

### mutable path

| Path | 所有者 | 方針 |
|---|---|---|
| `.venv/` | HVE setup | 検証不合格時に既存 setup が修復または明示的に再生成できる |
| `.hve-bootstrap/` | 最上位ランチャー | PowerShell / installer script 等の一時取得。秘密を置かない。再実行可能 |
| `hve/.settings.txt` | 利用者 / GUI | ZIP に含めず、利用者の値を削除しない |
| `.mdq/`, `.cq/`, `.toolsearch/` | HVE runtime | ZIP に含めず、実行時に必要に応じ生成 |
| `work/`, `gui-logs/` | HVE runtime | ZIP に含めず、実行時に生成 |
| `docs/`, `docs-generated/`, `knowledge/`, `qa/`, `src/` | 利用者 / 生成アプリ | ZIP に実データを含めない。既存内容を bootstrap が変更しない |
| user state directory | HVE runtime | 既存 `platformdirs` 契約を維持。bootstrap が初期化・削除しない |

## 5. 処理フロー

### 5.1 共通状態

| 状態 | 判定 | 次の処理 |
|---|---|---|
| Ready | `.venv` Python で verifier が合格 | 既存 GUI entrypoint を1回起動 |
| NeedsSetup | `.venv` 不在、または verifier が修復可能な不合格 | OS bootstrap → 既存 setup → verifier |
| NeedsVersionDecision | source version と distribution metadata が不一致 | FR-LOCAL-SURFACE-03 の既存 entrypoint へ委譲し、`-Yes` / `--yes` を付けずに利用者判断を受ける |
| Blocked | platform / architecture 対象外、manifest 不正、取得物 hash 不一致、必須依存の修復失敗 | GUI を起動せず非0終了 |

verifier の JSON は closed schema とし、top-level は `schema_version: 1`、必須 `state`（`ready` / `needs_setup` / `needs_version_decision` / `blocked`）、順序付き `checks` だけを持つ。各 check は機械可読 `check_id`、真偽値 `passed`、非空の固定 `reason_code` だけを持ち、未知・欠落・重複・型違反を拒否する。秘密を含み得る例外本文を持たない。exit は `ready=0`、`needs_setup=10`、`needs_version_decision=11`、通常の`blocked=12`、verifier 自身の引数またはmanifest schemaを結果として構成できないerror=`2` とする。exit 2のJSONを出せる場合は`state=blocked`かつ`manifest` checkの固定schema error reasonを持つ。ランチャーは個別 check から依存判定を再実装せず、`state` / reasonとexitの許可対応だけを検証して処理する。

verifier の実行所有者は次の 2 経路に限定する。構築済み `.venv` を見つけた最上位ランチャーは setup より前に1回実行する。setup を実行する経路では最上位ランチャーは実行せず、既存 setup が全導入後に1回実行し、`ready` の場合だけ exit 0 を返す。setup の exit 0 を受けた最上位ランチャーは verifier を重ねて実行せず GUI を起動する。setup 後の `needs_setup` / `needs_version_decision` / `blocked` は setup の非0へ変換し、GUI を起動しない。

### 5.2 Windows

1. `Start-HVE.cmd` は自身の親を `distribution_root` として固定し、`ver`、`PROCESSOR_ARCHITECTURE`、`PROCESSOR_ARCHITEW6432` で Windows 11 x64 を Python / PowerShell / package manager より先に確認する。Windows 10 / ARM64 / 判定不能では何も導入せず終了する。
2. private 配布工程で ZIP に隣接して渡した信頼済み SHA-256 との一致を取得・展開時に確認済みであることを前提とする。展開後は Windows 標準 `certutil.exe` で `hve-bootstrap-critical.sha256` が列挙する bootstrap-critical files（manifest、setup、pyproject、`hve/__init__.py`、`hve/bootstrap_verify.py`、verifier の import closure として固定した modules）の現在 bytes を setup 前に検証する。critical list 自身と top-level launcher は循環を避けるため list へ含めず、各 launcher template が critical list bytes の SHA-256 を固定して先に検証する。これは署名ではなく、信頼済み ZIP digest を前提とした破損検知である。
3. `.venv\Scripts\python.exe` がある場合、`PYTHONHOME` / `PYTHONPATH` / user site を current child environment から除き、absolute path の interpreterへ `-I -m hve.bootstrap_verify --json` を渡す。
4. 合格なら `hve.cmd gui` を1回起動し、その終了コードを返す。`NeedsVersionDecision` は既存 entrypoint へ委譲する。
5. 不合格または `.venv` 不在なら PowerShell 7 を解決する。
6. インストール済み `pwsh.exe` は `PSEdition=Core` かつ major 7 以上を native command として検証する。
7. `pwsh.exe` 不在で WinGet がある場合は `Microsoft.PowerShell` の current stable を user scope 優先で導入し、同一 process の PATH を更新する。
8. WinGet もない場合は、Windows 11 の `%SystemRoot%\System32\curl.exe` / `tar.exe` / `certutil.exe` を absolute path で用い、公式 PowerShell release `v7.6.5` の `PowerShell-7.6.5-win-x64.zip`（`https://github.com/PowerShell/PowerShell/releases/download/v7.6.5/PowerShell-7.6.5-win-x64.zip`、SHA-256 `32eb8f6cdce08f86e987d625a2733e54ac3e289ae7e1621b14c0b5bcec2434ea`）を `.hve-bootstrap/` へ取得する。redirect protocol は HTTPS だけ、最終 host は `github.com` または `release-assets.githubusercontent.com` だけを許可し、signed query を記録しない。checksum 一致後だけ展開する。portable `pwsh.exe` は path を PowerShell code へ埋め込まず、companion `.ps1` へ独立 argv として渡す。absolute path で起動し、その親を current process の `PATH` 先頭へ追加して子 setup と HVE SDK が同じ binary を解決できるようにする。path を扱う cmd 範囲では delayed expansion を無効にする。T05 の System32 cwd / PATH probe では pwsh / WinGet 非可視の状態から metadata size 106,319,290 bytes と一致する file を取得し、上記 digest、実 process path、`PSEdition=Core` / `7.6.5` を確認した。同じ probe は `'` / `!` を含む展開 path でも成功した。成功・失敗の全経路は共通 cleanup で一時 ZIP / runtime directory の不存在を確認し、cleanup 後にだけ最終 PASS を出力する。cleanup 失敗も非0とする。
9. `Start-HVE.ps1` は PowerShell 7 と Windows 11 x64 を再検証する。WinGet 不在または壊れている場合は、PowerShell Gallery の `Microsoft.WinGet.Client` `1.29.280` package（`https://www.powershellgallery.com/api/v2/package/Microsoft.WinGet.Client/1.29.280`、SHA-256 `726602001e6137efff66aa73c197c6ab6396ae2f9634d0adaada17ec5068ee46`）を取得・検証・展開する。redirect protocol は HTTPS、最終 host は `www.powershellgallery.com` / `cdn.powershellgallery.com` だけを許可する。展開 root の `Microsoft.WinGet.Client.psd1` を absolute path で別の PowerShell 7 child へ import し、実 module version / ModuleBase と `Repair-WinGetPackageManager` の module / version / ModuleBase / `Force` / `Latest` parameter を照合する。child 終了後に親が package / 展開 directory の不存在を確認し、その後だけ構造化 PASS を出力する。T05 では package 20,883,488 bytes、actual module `1.29.280`、final host `cdn.powershellgallery.com`、全所有関係、cleanup を確認した。`Repair-WinGetPackageManager -Force -Latest` は実装候補とし、ここでの `-Force` は WinGet repair cmdlet の取得指定であって HVE setup の `.venv` 再構築用 `-Force` ではない。T09 の契約テストと T22 の clean Windows 実行後に確定する。事後条件は `winget --version` が0で、同じ processから package install を実行できることとする。
10. 既存 `hve/setup-hve.ps1` を `-Yes -NoGlobalCleanup` で実行する。`-Force` は自動付与しない。
11. setup 自身が全導入後に verifier を1回実行し、`ready` の場合だけ0を返す。
12. setup が0の場合だけ `hve.cmd gui` を1回起動する。setup 前 verifier の `NeedsVersionDecision` は setup を実行せず既存 entrypoint へ委譲する。

Windows PowerShell 5.1、`powershell.exe`、`powershell` を起動しない。取得前に `.ps1` を実行しない。UAC は OS が直接提示し、credential を HVE が受け取らない。

### 5.3 macOS

1. `Start-HVE.command` は自身の実 path の親を `distribution_root` とする。Finder の cwd を使用しない。
2. private 配布工程で信頼済み ZIP SHA-256 の一致を取得・展開時に確認済みであることを前提とする。launcher template が `hve-bootstrap-critical.sha256` 自身の SHA-256 を検証した後、`/usr/bin/shasum -a 256 -c hve-bootstrap-critical.sha256` で Windows と同じ bootstrap-critical files を setup 前に検証する。これは署名ではなく破損検知である。
3. `.venv/bin/python` が実行可能なら、`PYTHONHOME` / `PYTHONPATH` / user site を child environment から除き、absolute path の interpreter へ `-I -m hve.bootstrap_verify --json` を渡す。
4. 合格なら `hve.sh gui` を1回起動して終了コードを返す。`NeedsVersionDecision` は既存 entrypoint へ委譲する。
5. `uname -s == Darwin`、`uname -m == arm64`、`sw_vers -productVersion` の major が15または26であることを確認する。対象外は非0終了。
6. `/opt/homebrew/bin/brew` が実行可能なら、その absolute path の `brew shellenv` を current process に適用してから `command -v brew` を再確認する。shell profile の PATH だけを根拠に brew 不在と判定しない。
7. `xcode-select -p` が失敗する場合は `xcode-select --install` を1回起動する。OS dialog の処理完了を有限時間で監視し、拒否 / timeout は非0終了とする。HVE 独自の Enter 確認は追加しない。
8. Homebrew がなお不在の場合は `sudo -v` により OS credential prompt を利用者へ直接提示する。失敗時は停止する。
9. Homebrew 公式 installer を immutable commit `7a133dcc74051ee4efc79467ed215dfedf45aea2` の URL `https://raw.githubusercontent.com/Homebrew/install/7a133dcc74051ee4efc79467ed215dfedf45aea2/install.sh` から `.hve-bootstrap/` へ取得し、SHA-256 `12479a24be3f5307eecac7cde670fad7118640f031229e964f544b1367b52a41` と一致する場合だけ `NONINTERACTIVE=1 /bin/bash` で実行する。T06 では 33,763 bytes を取得して hash を照合した。redirect protocol は HTTPS、最終 host は `raw.githubusercontent.com` だけを許可する。GitHub-hosted runner は Homebrew / Xcode Command Line Tools / Python 等を導入済みのため、installer 実行と `sudo` / CLT dialog は clean Mac の T24 でのみ合否を確定する。
10. Apple Silicon の既定 prefix `/opt/homebrew` から `brew shellenv` を current process にだけ適用する。dotfile を変更しない。
11. 既存 `hve/setup-hve.sh --yes --no-global-cleanup` を実行する。`--force` を自動付与しない。setup 自身が全導入後に verifier を1回実行し、`ready` の場合だけ0を返す。
12. setup が0の場合だけ `hve.sh gui` を1回起動する。setup 前 verifier の `NeedsVersionDecision` は setup を実行せず既存 entrypoint へ委譲する。

Homebrew / CLT が既に使える場合は再導入しない。Gatekeeper / quarantine / TCC を変更しない。

## 6. 共通 verifier

### 公開形

- 実行: distribution の `.venv` Python から `python -m hve.bootstrap_verify`
- 既定出力: 人間向けの成功 / 失敗要約
- `--json`: ランチャー・CI 用の構造化結果
- exit 0: `state=ready`
- exit 10: `state=needs_setup`
- exit 11: `state=needs_version_decision`
- exit 12: `state=blocked`
- exit 2: verifier の引数 / manifest schema 不正

`--json` は module 内部の bootstrap interface であり、トップレベル HVE CLI の公開 option には追加しない。

### check 一覧

| Check ID | 検査 | 再利用する実装 |
|---|---|---|
| `platform` | Windows 11 x64 / macOS 15・26 arm64 | Python `platform` / `sys` |
| `manifest` | schema / version / source commit / required files / SHA-256 | 本 module の単一 reader |
| `python` | current interpreter >= 3.11、distribution `.venv` 配下 | `sys.version_info`, resolved path |
| `hve-version` | source version と distribution metadata の一致。不一致は `NeedsVersionDecision` | `hve.startup_version` から副作用のない版比較 helper を共有 |
| `source-imports` | `hve`, `mdq`, `cq` が distribution root から解決 | imported module `__file__` |
| `pip-check` | dependency metadata consistency | current interpreter の `-m pip check` |
| `gui-imports` | PySide6 / QtWebEngine import | import machinery |
| `gh` | `gh` executable 解決 | `shutil.which` |
| `pty` | OS 別 backend | `hve.gui.pty_backend.is_pty_available()` |
| `pwsh` | Windows の Core 7+ | `hve.copilot_client_factory._require_pwsh7_on_windows()` |
| `sdk-runtime` | GUI / SDK session が実際に使用する SDK pin、cache path、binary version | `CopilotCliBridge.find_binary()` が委譲する既存 `hve.auth.find_copilot_binary()` と setup から抽出する pure version check を共有 |
| `external-copilot-cli` | FR-MODEL-08 が別途要求する PATH 上の外部 Copilot CLI。SDK cache / `COPILOT_CLI_PATH` を代替として受理しない | 本 module の `resolve_external_copilot_cli()` を setup の最終検証と共有し、`shutil.which("copilot")` の結果を実ファイル / OS shim として検証 |

check は credential / auth status、MCP / Plugin、remote、Workflow input、Azure を検査しない。例外本文は秘密を含み得るため、構造化結果には例外型と固定理由だけを記録する。

### setup との重複解消

既存 setup がインストール判断のために行う事前検出は保持するが、導入後の readiness predicate を OS 別 script と verifier に重複させない。SDK runtime の pin / cached binary / `--no-auto-update --version`、gh、PTY、pip、GUI import、source isolation、FR-MODEL-08 の外部 PATH 上 Copilot CLI の最終判定を `hve/bootstrap_verify.py` の副作用のない helper 群へ集約する。GUI の実セッション / login binary は既存 `CopilotCliBridge.find_binary()` の単一規則を維持し、外部 PATH CLI と同一物だと扱わない。既存 setup は全導入後に `.venv` Python で同 module を1回呼ぶ。download・install・修復は引き続き setup の責務とする。

## 7. 配布 allowlist

### root files（exact）

- `LICENSE`
- `README.md`
- `CHANGELOG.md`
- `pyproject.toml`
- `hve.cmd`, `hve.sh`
- `mdq.toml`, `cq.toml`
- `.gitattributes`, `.gitignore`

### source trees（prefix＋明示除外）

- `hve/**`（`hve/tests/**`, `hve/gui/tests/**`, cache / local settings を除く）
- `mdq/**`（`mdq/tests/**`, cache を除く）
- `cq/**`（`cq/tests/**`, cache を除く）
- `tools/**`（`pyproject.toml` の `tools*` package discovery、full-source trial の portable skill / self-hosted runner / users-guide リンクを維持する。下記除外を優先）
- `template/**`
- `users-guide/**`

### runtime repository contracts（prefix / exact）

- `.github/copilot-instructions.md`
- `.github/instructions/**`
- `.github/prompts/**`
- `.github/skills/**`
- `.github/io-contracts/**`
- `.github/io-contract-exceptions.yaml`
- `.github/scripts/**`（local HVE が参照する helper と配布 generator。下記 test / cache 除外を優先）
- `.github/pull_request_template.md`
- `.github/labels.json`
- `hve-dev/requirement-definition.md`
- `hve-dev/requirement-test-mapping.md`
- `hve-dev/hve-feature-inventory.csv`, `hve-dev/hve-test-inventory.csv`, `hve-dev/hve-surface-inventory.csv`
- `hve-dev/hve-app-tools.md`, `hve-dev/hve-tdd-change-policy.md`

### 除外（全allow prefixより優先）

- `.git/**`, `.venv/**`, `hve.egg-info/**`, `node_modules/**`, `__pycache__/**`, `*.pyc`
- `.env`, `.env.*`、basenameが `credentials.json` / `secrets.json` / `.npmrc` / `.pypirc`、suffixが `.pem` / `.key` / `.pfx` / `.p12` / `.jks` / `.keystore` の file
- `work/**`, `gui-logs/**`, `.mdq/**`, `.cq/**`, `.toolsearch/**`
- `hve/.settings.txt`, `hve/.settings.txt.tmp`
- `docs/**`, `docs-generated/**`, `docs-original/**`, `knowledge/**`, `qa/**`, `src/**`, `sample/**`, `tests/**`
- 前節で明示したファイル以外の `hve-dev/**`
- `tools/**/tests/**`, `tools/**/results/**`, `tools/**/__pycache__/**`
- `tools/**/test_*.py`, `tools/**/conftest.py`, `tools/**/.pytest_cache/**`
- `.github/scripts/**/tests/**`, `.github/scripts/**/__pycache__/**`
- `.github/workflows/**`, `.github/ISSUE_TEMPLATE/**`（local GUI runtime に不要。remote repository 側の workflow / template は利用者が明示した GitHub repository が所有する）
- `.vscode/**`, build / coverage / pytest cache

### allowlist 判定規則

1. repository-relative POSIX pathへ正規化できないpathを拒否する。
2. exact root file、source prefix、runtime contract exact / prefixのいずれかに一致する必要がある。
3. 除外 exact / prefix / suffixに一致した場合は、allow一致しても除外する。
4. symlink / junction / reparse point、submodule、Git LFS pointer、0 byte（意図的なpackage marker `__init__.py`だけ例外）は別検証へ送る。判定不能は除外せず buildをfail-closedにする。
5. source 候補集合は `git ls-files -s -z --cached` の NUL 区切り stage-0 entry `(mode, oid, stage, path)` だけを用い、regular file `100644` / executable file `100755` だけを受理する。gitlink、symlink、unmerged index、unknown modeを拒否する。payload bytes、SHA-256、LFS pointer、0 byte、秘密signatureの検査はいずれも working tree ではなく同じ `oid` の index blob bytes を正本とする。列挙を開始時とZIP書込み直前に2回行い、entry集合またはoidが変化した場合は停止する。ignored file、smudge後bytes、独自recursive walkを入力にしない。
6. 未追跡一覧は `git ls-files -z --others --exclude-standard` で取得し、root exact、include exact、include prefix、除外を同じ順で評価する共通 `is_allowed(path)` を適用する。`is_allowed=True` の未追跡fileが1件でもあれば正式candidate生成をfail-closedとする。実装前のlocal試験は、必要なworking-tree bootstrap sourceだけを明示的にコピーして一時staging repositoryのindexへ追加し、そのsnapshotをgenerator入力にする。generator自身にuntrackedを許可するoverrideを追加しない。
7. source path集合をsortし、case-insensitive collisionとUnicode NFC正規化後collisionを拒否する。index blobの先頭が exact `version https://git-lfs.github.com/spec/v1` であるLFS pointer、意図しない0 byte、秘密signatureを拒否する。0 byteを許可するのはbasename `__init__.py` かつPython package prefix配下だけとする。content signatureは private key header（`-----BEGIN ... PRIVATE KEY-----`）、GitHub token prefix（`ghp_` / `github_pat_`）、Azure storage connection string marker（`DefaultEndpointsProtocol=` と `AccountKey=` の同居）を固定定数として検査する。診断はpath、signature ID、件数だけを出し値を表示しない。
8. generatorが持つ`ROOT_FILES` / `INCLUDE_PREFIXES` / `INCLUDE_EXACT` / `EXCLUDE_PREFIXES` / `EXCLUDE_EXACT` / `EXCLUDE_BASENAMES` / `EXCLUDE_BASENAME_PREFIXES` / `EXCLUDE_SUFFIXES`をmachine-readable正本とし、本節との一致を契約テストで確認する。`EXCLUDE_BASENAME_PREFIXES=("test_",)` はsuffix `.py` と同時一致した場合だけ除外し、`test_data.json` 等を無条件に除外しない。

### 生成物集合

source allowlist とは別に、generator は `GENERATED_EXACT_BY_TARGET` が固定する次の生成物だけを ZIP root へ追加する。

- `windows-x64`: `Start-HVE.cmd`, `Start-HVE.ps1`, `hve-bootstrap-critical.sha256`, `hve-bootstrap-manifest.json`
- `macos-arm64`: `Start-HVE.command`, `hve-bootstrap-critical.sha256`, `hve-bootstrap-manifest.json`

生成物はsource pathと衝突してはならず、対象外targetのlauncherを含めない。source＋生成物の最終集合に対してpath安全性、case / NFC collision、mode、0 byte、hashを検証してからZIPへ格納する。

このallowlistはHVE engineと標準GUI/CLIのprivate full-source trialを対象とする。生成アプリの既存データは含めないため、展開直後に全Workflowが入力充足済みであるとは主張しない。

allowlist は `.github/scripts/build-hve-bootstrap.py` の単一 constant / function が所有する。test は design の見出し文字列ではなく generator の出力を検証する。

### generator 内部 test seam

generator は公開HVE APIではないが、決定的な検証のため次の内部境界を持つ。`IndexEntry(mode, oid, stage, path)`、`SourceEntry(path, mode, oid, data)`、`SourceSnapshot(entries, source_dirty)`、`BuildResult(zip_path, digest_path, archive_sha256)`、`scan_index(repo_root)`、`collect_source_snapshot(repo_root)`、`validate_source_entries(entries)`、`build_distribution(repo_root, target, output_dir, formal=True)`。`formal=True` はallow対象のtracked working-tree差分（index対HEADとworking tree対indexの双方）を拒否し、`formal=False`だけがindex blobをpayloadに使いながら`source_dirty=true`をmanifestへ記録する。buildは開始時とZIP書込前に`scan_index`を呼び、entry集合・mode・oidの不一致を`index-changed`で拒否する。CLI `main(argv)` は同じbuildを呼び、target / repo root / output directory / local candidateの指定だけを受ける。このseamはunit testとgenerator CLIだけが使用し、HVE runtime / GUIへ公開しない。

generator が起動できる外部processは `shell=False` / `cwd=repo_root` のlocal Gitだけとし、subcommandは `ls-files` / `cat-file` / `rev-parse` / `diff` の固定集合とする。Git aliasを有効化する `-c`、remote / URL、hook実行、network、upload、Release APIを使用しない。CLI `main(argv)` も同じ制限内でbuildを呼ぶ。

critical listのtarget別完全集合は次を正本とする。

- 共通: `hve-bootstrap-manifest.json`, `pyproject.toml`, `hve/__init__.py`, `hve/bootstrap_verify.py`, `hve/startup_version.py`, `hve/auth.py`, `hve/gui/copilot_cli_bridge.py`, `hve/gui/pty_backend.py`, `hve/bootstrap/bootstrap-sources.json`
- Windows追加: `hve/setup-hve.ps1`, `Start-HVE.ps1`, `hve/bootstrap/windows-pwsh-runtime-check.ps1`, `hve/bootstrap/winget-module-inspect.ps1`
- macOS追加: `hve/setup-hve.sh`

critical listの各行は `<sha256><半角空白2個><path>` とし、pathをkeyとする完全対応を検証する。同一digestを持つ複数pathを失ってはならない。

## 8. manifest

ZIP root に UTF-8 / LF / BOM なしの `hve-bootstrap-manifest.json` を置く。

| Field | 型 | 規則 |
|---|---|---|
| `schema_version` | integer | `1` のみ |
| `distribution_kind` | string | exact `hve-private-source` |
| `hve_version` | string | `pyproject.toml` の strict `MAJOR.MINOR.PATCH` |
| `source_commit` | string | build 時の `git rev-parse HEAD` 40 hex |
| `source_dirty` | boolean | tracked / untracked の package 対象差分がある場合 true。秘密ファイルの path は列挙しない |
| `target_platform` | string | Windows ZIP は exact `windows-x64`、macOS ZIP は exact `macos-arm64` |
| `launcher` | string | target に応じて exact `Start-HVE.cmd` または `Start-HVE.command` |
| `files` | object | repository-relative POSIX path → lowercase SHA-256。path 昇順 |

manifest 自身は `files` に含めない。生成順は非循環に固定する: (1) index blobからsource payload、(2) source payload hashを持つmanifest、(3) manifest・setup・pyproject・verifier / 固定import closureだけを列挙するcritical list、(4) critical list bytesのSHA-256を埋め込んだtarget launcher、(5) source＋生成物の最終集合、(6) ZIP、(7) ZIP隣接digest。critical listは自身とtop-level launcherを列挙せず、launcherはlistのhashを検証してからlistを消費する。archive 全体の SHA-256 は隣接する `<zip>.sha256` に記録し、private 配布工程が展開前に照合する。署名対象外のため、この hash は信頼済み配布元から別途渡された digest を前提とする整合性検査であり、配布元の真正性を単独で証明すると表記しない。配布前の正式 candidate は `source_dirty=false` を必要とするが、開発中の local candidate は true を明示して試験できる。dirty を無言で clean と記録しない。

## 9. ZIP 生成

- OS 別に `hve-windows-x64-<version>.zip` と `hve-macos-arm64-<version>.zip` を生成する。
- source payload は共通。各 ZIP は manifest の `target_platform` に対応する最上位 launcher 1件だけを持つ。
- path は `/`、時刻は固定値、列挙順は path 昇順、圧縮方式は固定し、同じ入力 bytes から同じ ZIP bytes を生成する。
- `Start-HVE.command` と既存 `hve.sh` / `hve/setup-hve.sh` は LF / BOM なし・Unix mode `0755` として格納する。Windows launcher / PowerShell は UTF-8 BOM なしとし、各 interpreter が要求する改行契約をテストで固定する。`.gitattributes` に `.command` / `.command.in` の LF 契約を追加する。
- symlink / junction / reparse point、absolute path、`..`、drive / UNC path、重複 path、case-insensitive collision を拒否する。
- source root 外を読まない。出力先は `work/run/.../artifacts/` の明示されたディレクトリに限定する。
- generator は upload、Release、GitHub API、signing を行わない。

## 10. 失敗と終了コード

| Code | 意味 | GUI 起動 |
|---:|---|:---:|
| 0 | GUI process が正常終了 | 1回 |
| 1 | 前提・setup・verifier・GUI のいずれかが失敗 | verifier 合格前は0回 |
| 2 | 対象外 platform / architecture / OS version、manifest / argument 不正 | 0回 |
| 3 | download / checksum / package manager bootstrap 失敗 | 0回 |

子プロセスの非0は0へ丸めない。失敗時は `stage`、固定された `reason_code`、再実行可否を出力し、credential、URL query、installer の生出力全文を要約へ含めない。詳細な native tool 出力は画面に直接流れてよいが、HVE 独自ファイルへ保存しない。

## 11. 冪等性と中断

- verifier 合格なら setup call count は0。
- 初回 setup が非0なら GUI call count は0。
- 再実行は既存 setup の修復能力を使う。自動 `Force`、global HVE cleanup、source rollback はしない。
- checksum 不一致の取得物は実行せず、当該 `.hve-bootstrap` file だけを削除して非0終了する。
- 完全に展開した PowerShell / Homebrew installer script は content hash で再利用できる。
- 同時に同じ distribution root から2つの bootstrap を起動した場合は、`.hve-bootstrap/bootstrap.lock` の排他取得に失敗した後続を非0で停止する。待機 queue / daemon は作らない。
- lock は PID と開始時刻だけを保持し、credential / command line を保存しない。異常終了後の stale lock は PID の不在を確認した同じ launcher だけが除去できる。

## 12. セキュリティ

- HTTPS の公式配布元だけを使用する。
- native bootstrap で直接取得する実行物 / script は固定 version / commit と SHA-256 の双方を source に記録する。
- redirect protocol は HTTPS だけとし、取得物ごとに列挙した公式 host allowlist（PowerShell release は `github.com` / `release-assets.githubusercontent.com`、WinGet client package は `www.powershellgallery.com` / `cdn.powershellgallery.com`、Homebrew installer は `raw.githubusercontent.com`）以外の最終 host、空 file、hash 不一致を実行しない。
- shell 文字列連結で利用者入力を実行しない。root path は引用し、引数配列を使える層では配列を使う。
- admin / sudo credential、token、auth URL をファイルへ保存しない。
- package manager と setup の標準安全機構を無効化しない。
- Gatekeeper、quarantine、Smart App Control、execution policy、antivirus、TCC を無効化しない。
- private source を public Release / public artifact へ upload しない。

## 13. 検証計画

### 決定的テスト

- verifier の各 check と構造化結果
- Windows native bootstrap / PowerShell bootstrap の呼出し順、hash fail、PATH 更新、setup / GUI call count
- macOS CLT / brew / setup の呼出し順、prefix、profile 非変更、hash fail、GUI call count
- ZIP allowlist / exclusion / manifest / deterministic bytes / path safety
- 既存 FR-CLI-10 / FR-GUI-09 / 24 / FR-MODEL-07 / 08 / FR-LOCAL-SURFACE-03 の回帰

### native test

- Windows 11 x64: actual MainWindow と preview / PTY
- GitHub-hosted macOS 15 / 26 arm64: distribution ZIP から Cocoa smoke。FR-MAINT-10 の run 単位承認を維持

### clean-OS 受入マトリクス

| Environment | OS build | Architecture | Distribution version / SHA-256 | Initial tools | Result |
|---|---|---|---|---|---|
| Windows 11 | 実行時記録 | x64 | 実行時記録 | Python / Git / pwsh / WinGet / venv 未導入 | NOT_RUN |
| macOS 15 | 実行時記録 | arm64 | 実行時記録 | Python / brew / CLT 未導入 | NOT_RUN |
| macOS 26 | 実行時記録 | arm64 | 実行時記録 | Python / brew / CLT 未導入 | NOT_RUN |

各セルは独立。GitHub runner は clean-OS cell を代替しない。実環境を用意できないセルは NOT_RUN のまま完了を宣言しない。

WinGet が存在するが呼び出しに失敗するケースは、上記の対象環境セルを増やさず、Windows の決定的 recovery test と native test の異常系として検証する。

## 14. 実装開始ゲート

本設計書の完成だけでは実装を開始しない。`FR-LOCAL-SURFACE-04` を requirement-test mapping へ `要追加` として登録し、同 ID の受入テストを作成して期待する RED を確認し、feature / test inventory を再生成して `source=hve-dev/requirement-definition.md`、`active-or-described`、実在 test path を照合した後に限り product code へ進む。

## 15. 文書更新

- 新規利用者手順: `users-guide/hve-one-operation-start.md`
- 既存 GUI 導線: `users-guide/hve-gui-getting-started.md`, `users-guide/hve-gui-orchestrator-guide.md`
- CLI / 復旧: `users-guide/hve-cli-getting-started.md`, `users-guide/troubleshooting.md`
- 索引: `/README.md`, `hve-dev/hve-app-tools.md`
- `docs/**`: HVE 本体の配布機能ではなく生成アプリの設計出力なので変更しない。指定された `docs/requirement-definition.md` は存在せず、HVE の正本 `hve-dev/requirement-definition.md` を使用する。

## 16. 非対象

- Linux
- public distribution / anonymous download
- Intel Mac / Rosetta / Windows ARM64 / Windows 10 / macOS 14 以下
- offline / proxy / private package mirror
- installer / Store / package manager formula
- single executable / `.app` bundle / signing / notarization
- automatic update / migration / rollback
- automatic login / MCP setup / Workflow execution
- all-Workflow readiness certification
