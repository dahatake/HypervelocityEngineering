# HVE 開発ツール手順書

本書は `hve` アプリケーションを開発・リリースする際に利用する補助ツールの手順をまとめる。

---

## 目次

- [0. はじめに](#0-はじめに)
- [1. リリースサイクルの全体像](#1-リリースサイクルの全体像)
- [2. `hve` パッケージ構成](#2-hve-パッケージ構成)
- [3. バージョニング規約（SemVer + PEP 440）](#3-バージョニング規約semver--pep-440)
- [4. `CHANGELOG.md` の書き方](#4-changelogmd-の書き方)
- [5. バージョンアップ手順（`bump-my-version`）](#5-バージョンアップ手順bump-my-version)
- [6. リリース後の確認とロールバック](#6-リリース後の確認とロールバック)
- [7. 対象外パッケージ（`mdq` 等）の運用](#7-対象外パッケージmdq-等の運用)
- [8. トラブルシューティング](#8-トラブルシューティング)

---

## 0. はじめに

### 0.1 本書の位置づけ

本書は `hve` パッケージのリリース運用に関する **規約・前提知識・操作手順** をひとつにまとめたリファレンスである。Software Engineer が以下のいずれかの作業を行う際に参照することを想定する。

- リポジトリのソースを変更したあと、`CHANGELOG.md` へエントリを追記する
- 変更内容に応じてバージョン番号を決定し、`bump-my-version` でリリースを実行する
- リリース後に挙動を確認し、必要に応じてロールバックする
- 同梱パッケージ（`mdq` 等）のバージョンを独立して扱う

### 0.2 想定読者

| 読者 | 参照する章 |
|---|---|
| ソース変更を加える **全エンジニア** | [§1](#1-リリースサイクルの全体像) / [§3](#3-バージョニング規約semver--pep-440) / [§4](#4-changelogmd-の書き方) |
| **リリース担当者**（追加で必要な章） | [§5](#5-バージョンアップ手順bump-my-version) / [§6](#6-リリース後の確認とロールバック) / [§7](#7-対象外パッケージmdq-等の運用) |
| トラブル発生時 | [§8](#8-トラブルシューティング) |

CHANGELOG への追記は、変更を加えた当人がソース変更とあわせて行うことを推奨する。リリース時にまとめて書く運用は変更内容の取りこぼしを生むため、§3・§4 は全エンジニアの必須知識である。

> **Copilot が実行する HVE 関連ジョブ**では、[`.github/copilot-instructions.md`](../.github/copilot-instructions.md) の「HVE の版管理と変更履歴」が最優先です。HVE の実装・Prompt・Skill・Workflow・契約を変更した各ジョブは、完了報告前に PATCH を 1 回だけ増やし、変更履歴と同じ変更セットで同期します。MINOR 以上への更新はユーザーの明示判断だけで行います。ここで説明する `bump-my-version` の一括リリース手順は、既存の `[Unreleased]` エントリーを誤って別ジョブのリリースへ含めない場合にのみ使用してください。

### 0.3 前提とする運用形態

本書の手順は、現リポジトリの実態に即した以下の運用を前提とする。**この前提から外れる運用（PyPI 公開、CI による自動リリース等）は本書のスコープ外**。

- **配布形態**: PyPI 等への公開は行わず、リポジトリを `git clone` した上で `hve/setup-hve.{ps1,sh,cmd}` から editable install (`pip install -e .`) する社内運用
- **バージョン情報の保持箇所**: `pyproject.toml`（`[project].version` と `[tool.bumpversion].current_version`）と `hve/__init__.py` (`__version__`)
- **変更履歴**: リポジトリ直下の [CHANGELOG.md](../CHANGELOG.md) に集約。`bump-my-version` の見出し自動挿入は、`[Unreleased]` の全エントリーが同一リリースに属する明示的な一括リリースだけで使用する。Copilot ジョブでは既存の `[Unreleased]` エントリーを保持し、対象ジョブの版見出しをその内容の後ろへ手動配置する
- **同梱パッケージ**: リポジトリ直下の `mdq/` は `hve` 本体と同時にビルドされるが、`tools/skills/markdown_query/` 配下のスキル本体と vendored コピーは独立ライフサイクルで管理され、`bump-my-version` の対象外（詳細は [§7](#7-対象外パッケージmdq-等の運用)）

### 0.4 用語

| 用語 | 本書での意味 |
|---|---|
| **bump** | バージョン番号を上げる操作。`bump-my-version bump {patch,minor,major}` を指す |
| **リリース** | bump 結果を `git push --follow-tags` でリモートへ反映し、新バージョンを利用可能にする一連の作業 |
| **`hve` 本体** | `pyproject.toml` の `name = "hve"` に対応するパッケージ。`mdq` 等の同梱パッケージは含まない |
| **Unreleased エントリ** | `CHANGELOG.md` の `## [Unreleased]` 見出し直下に書かれた、次回リリース予定の変更項目 |

---

## 1. リリースサイクルの全体像

### 1.1 3 つの要素の関係

`hve` のリリース運用は **「変更内容 (CHANGELOG) → バージョン番号 (Version) → 配布物 (Package)」** という 3 要素が連動する一連のサイクルである。どれか 1 つだけを更新すると不整合が発生し、利用者側に「どのバージョンに何の変更が入っているか分からない」状態を生む。

```text
   ソース変更
       │
       ▼
 ┌─────────────────────────┐
 │ ① CHANGELOG.md          │  「何を変えたか」を Unreleased に追記
 │    （[Unreleased] 直下） │     ← §4 で書式を規定
 └──────────┬──────────────┘
            │
            ▼
 ┌─────────────────────────┐
 │ ② バージョン番号         │  変更の性質から patch / minor / major を判定
 │    (pyproject + __init__)│     ← §3 で判定基準
 └──────────┬──────────────┘
            │  bump-my-version bump {patch|minor|major}
            ▼
 ┌─────────────────────────┐
 │ ③ commit + tag + push   │  Git 履歴と editable install 経由で
 │    （Git タグ v{x.y.z}） │     利用者へ配布される
 └─────────────────────────┘
```

`bump-my-version` は、意図的にまとめたリリースに限り、上記 ①②③ のうち、`CHANGELOG.md` の見出し昇格・バージョン番号の同時更新・commit・Git タグ作成までを 1 コマンドで実行する。push のみ手動である（[§5.5](#55-リモートへの反映)）。Copilot ジョブでは、既存の `[Unreleased]` エントリーを含む場合にこの自動昇格を使わず、最優先規約どおり同じ変更セットで手動同期する。

### 1.2 `hve` における配布チャネル

`hve` は **PyPI 公開を行わない** 社内ツールである（[§0.3](#03-前提とする運用形態)）。そのため一般的な Python パッケージで使われる `python -m build` / `twine upload` の経路は本書のスコープ外であり、配布は以下の経路のみで成立する。

- **初回導入**: 利用者が `git clone` 後、`hve/setup-hve.{ps1,sh,cmd}` を実行して `.venv` を作成し `pip install -e .` を実行
- **更新**: 利用者が `git pull` を実行（editable install のため再インストール不要。コードは即反映）
- **バージョン番号の意味**: PyPI 等の外部依存解決経路には現れないが、`hve.__version__` / `pip show hve` で確認可能な「変更履歴との対応」を示すラベルとして機能する

このため `hve` でのバージョン番号の主用途は次の 2 点に絞られる。

1. 利用者が「現在使っているコードが CHANGELOG のどの行までを含むか」を確認する
2. リリース担当者が Git タグでリビジョンを参照する（不具合発生時の `git checkout v{x.y.z}` 等）

### 1.3 標準的なリリース手順（ハイレベル）

リリース担当者の作業フローは以下のとおり。各ステップの詳細は対応する章を参照。

| Step | 内容 | 詳細 |
|---|---|---|
| 1 | `CHANGELOG.md` の `## [Unreleased]` 配下のエントリを確認し、書式が整っているか確認 | [§4](#4-changelogmd-の書き方) |
| 2 | 変更の最大インパクトから `patch` / `minor` / `major` を判定（Copilot ジョブはユーザーが明示しない限り `patch`） | [§3.3](#33-patch--minor--major-の判定) |
| 3 | `git status` がクリーンであることを確認 | [§5.1](#51-前提条件) |
| 4 | （任意）dry-run で挙動確認 | [§5.4](#54-事前確認dry-run) |
| 5 | 一括リリース時だけ `bump-my-version bump {patch\|minor\|major}` を実行（Copilot ジョブは手動同期） | [§5.3](#53-バージョンアップの実行) |
| 6 | `git push --follow-tags` でリモートへ反映 | [§5.5](#55-リモートへの反映) |
| 7 | 動作確認（`hve.__version__` と `pip show hve` の一致） | [§6.1](#61-動作確認) |

Step 1 は変更を加えた **各エンジニアが PR / 作業の一環として行う**。通常の一括リリースでは Step 2 以降を **リリース担当者** が変更の集積を見て判定・実行する。Copilot が実行する HVE 関連ジョブでは、最優先規約により、完了前の PATCH 更新と変更履歴同期をジョブ自身が実施する。

---

## 2. `hve` パッケージ構成

リリース運用を理解するために必要な、最小限のパッケージ構成知識をまとめる。

### 2.1 `pyproject.toml` の中核項目

リポジトリ直下の [pyproject.toml](../pyproject.toml) が **唯一のビルド/メタデータ定義** である。`setup.py` / `setup.cfg` は存在しない。

| セクション | 役割 | リリース運用との関わり |
|---|---|---|
| `[build-system]` | `setuptools>=68` をビルドバックエンドに指定 | 直接は触らない |
| `[project]` | パッケージ名 `hve`、`version`、Python 要件 `>=3.11`、依存パッケージ | `version` が bump 対象 |
| `[project.optional-dependencies]` | extras（後述 [§2.3](#23-extras-extra-dependencies)）| 直接は触らない |
| `[project.scripts]` | CLI エントリポイント `hve` / `hve-mdq` / `mdq` | 直接は触らない |
| `[tool.setuptools.packages.find]` | 同梱対象パッケージ（`hve*` / `mdq*` / `cq*` / `tools*`、`hve.tests*` は除外）| `mdq` / `cq` が同梱されている事実を理解するうえで重要 |
| `[tool.setuptools.package-data]` | 非 Python ファイル同梱指定（GUI アセット等）| 直接は触らない |
| `[tool.bumpversion]` | `bump-my-version` 設定 | bump 対象ファイルの定義 |

### 2.2 バージョン番号の保持箱所

`hve` のバージョン番号は **3 箇所** にハードコードされている。`bump-my-version` はこの 3 箇所を 1 コマンドで同時更新する。

| # | ファイル | 該当行 |
|---|---|---|
| 1 | [pyproject.toml](../pyproject.toml) | `[project]` の `version = "x.y.z"` |
| 2 | [pyproject.toml](../pyproject.toml) | `[tool.bumpversion]` の `current_version = "x.y.z"` |
| 3 | [hve/\_\_init\_\_.py](../hve/__init__.py) | `__version__ = "x.y.z"` |

加えて、明示的な一括リリース時には [CHANGELOG.md](../CHANGELOG.md) の `## [Unreleased]` 見出し直下に `## [x.y.z] - YYYY-MM-DD` 見出しが自動挿入される（[§4.3](#43-bump-my-version-による自動昇格)）。Copilot ジョブでは、既存の `[Unreleased]` 内容を維持するためこの自動挿入を使わない。

> **補足**: `pyproject.toml` 内で `[project].version` と `[tool.bumpversion].current_version` の 2 箇所に同じ値が必要な理由は、前者がパッケージメタデータ用、後者が `bump-my-version` の差分計算用であり、ツール仕様上どちらも独立に解釈されるため。`bump-my-version` 1.x は `pyproject.toml` を暗黙の設定ファイルとして扱い両方を同時更新する。

### 2.3 extras (extra dependencies)

`[project.optional-dependencies]` には以下の extras が定義されている。各 extras はインストール時に `pip install -e .[extras_name]` で有効化される。**リリース運用とは独立** であり、bump 操作で extras の中身は変化しない。

| extras 名 | 用途 | 主要依存 |
|---|---|---|
| `mdq` | `mdq` 検索エンジン基本機能 | `rank_bm25`, `tiktoken` |
| `mdq-watch` | `mdq` の OS ファイル監視によるインデックス更新 | `watchdog` |
| `mdq-ja` | 日本語 Markdown 索引（プレースホルダー、現状追加 wheel なし）| —（将来 fugashi/sudachipy 等）|
| `semantic` | `--strategy semantic_paragraph` 用埋め込み検索 | `fastembed`, `nltk`, `numpy` |
| `gui` | HVE GUI Orchestrator (PySide6/Qt6) | `PySide6`, `markdown-it-py`, `mdit-py-plugins`, `Pygments` |
| `gui-pty` | GUI 内 PTY による対話 CLI 認証 | `pywinpty` (Windows) / `ptyprocess` (POSIX) |
| `gui-docconvert` | GUI D&D 添付ファイル → Markdown 変換 | `markitdown[pdf,docx,pptx,xlsx,xls,outlook]` |

`hve/setup-hve.{ps1,sh,cmd}` は既定で全 extras（`mdq-watch,mdq-ja,semantic,gui,gui-pty,gui-docconvert`）を導入する。最小構成にしたい場合は `--minimal` / `-Minimal` を指定する。

### 2.4 CLI エントリポイント

`[project.scripts]` の 3 エントリにより、`pip install -e .` 後は次の 3 コマンドが PATH に通る。

| コマンド | 実体 |
|---|---|
| `hve` | `hve.__main__:main` |
| `hve-mdq` | `mdq.cli:main` |
| `mdq` | `mdq.cli:main`（`hve-mdq` のエイリアス）|

### 2.5 同梱パッケージと独立ライフサイクル

`[tool.setuptools.packages.find]` の `include = ["hve*", "mdq*", "cq*", "tools*"]` により、リポジトリには `hve` と並んで以下のパッケージが**同梱されている**。

- `mdq/` — `hve-mdq` / `mdq` コマンドの実装
- `cq/` — Code Query の実装
- `tools/` — 補助ツール群（vendored コピーを含む）

`mdq/` と `cq/` は `hve` 本体と同時にビルドされる一方、それぞれ engine の `__version__` を持つ。**各 Skill、独立 GUI、移植用キット、および vendored コピーは HVE と独立したライフサイクル**で管理され、`bump-my-version` の対象外である。詳細と更新手順は [§7](#7-対象外パッケージmdq-等の運用) を参照。

ここでの「独立」は各コンポーネント固有の版番号を個別に管理する意味であり、HVE の実行契約を構成する Prompt・Skill・Workflow の変更を HVE パッケージ PATCH から除外する意味ではない。Copilot ジョブには [§0.2](#02-想定読者) の注記が示す最優先規約を適用する。

### 2.6 `setup-hve` スクリプトとの関係

リポジトリ直下の `hve/setup-hve.{ps1,sh,cmd}` は、初回環境構築（`.venv` 作成 → `pip install -e .[extras...]` → NLTK データ DL → GUI アセット DL 等）を担う。**バージョン操作とは独立** であり、bump 後に setup-hve を再実行する必要はない。ただし bump で extras 定義が変わった場合（本書スコープ外）は、利用者側で `pip install -e .[...] --upgrade` の再実行が必要となる。

---

## 3. バージョニング規約（SemVer + PEP 440）

### 3.1 採用する規約

`hve` は **Semantic Versioning 2.0.0**（SemVer; <https://semver.org/spec/v2.0.0.html>）に準拠する。Python パッケージとして PEP 440 互換である必要があるが、SemVer の基本形 `MAJOR.MINOR.PATCH` は PEP 440 のサブセットに収まるため、通常運用では SemVer のみを意識すれば十分である。

| 部分 | 上げるタイミング | 例 |
|---|---|---|
| `MAJOR` | **後方互換性を壊す変更** | `1.4.2` → `2.0.0` |
| `MINOR` | **後方互換性のある機能追加** | `1.4.2` → `1.5.0` |
| `PATCH` | **後方互換性のあるバグ修正** | `1.4.2` → `1.4.3` |

`MAJOR` / `MINOR` を上げた時点で、下位の桁は 0 にリセットされる（`bump-my-version` が自動で実施）。

### 3.2 SemVer §4 — 0.x 系の解釈

`hve` は 0.x 系（現在値の正本は [pyproject.toml](../pyproject.toml) の `[project].version`）であり、SemVer §4 の対象である。

> **SemVer §4**: メジャーバージョン 0 (0.y.z) は初期開発用である。いかなる時点でもパブリック API は変更されてよい。このバージョンのソフトウェアは安定とみなすべきではない。

本書ではこの規定に従い、**0.x 系の間は破壊的変更を含むリリースであっても `1.0.0` への昇格は要件としない**。0.x 系における判定は以下に従う。

| 0.x 系での変更 | 推奨される bump |
|---|---|
| 後方互換性を壊す変更 | `minor` （例: `0.1.0` → `0.2.0`）|
| 機能追加 | `minor` （例: `0.1.0` → `0.2.0`）|
| バグ修正のみ | `patch` （例: `0.1.0` → `0.1.1`）|

> **`1.0.0` への昇格判断**: パブリック API の安定が宣言可能になった時点で `bump major`（`0.x.y` → `1.0.0`）を実施する。これは本書の自動運用ルールでは決定せず、リリース担当者と関係者の合意で別途決める。

### 3.3 PATCH / MINOR / MAJOR の判定

複数の変更が混在する場合、**最もインパクトの大きい変更に合わせて** bump 種別を決定する（例: バグ修正 1 件と機能追加 1 件 → `minor`）。

ただし Copilot が実行する HVE 関連ジョブでは、ユーザーが MINOR / MAJOR を明示的に判断しない限り、変更内容にかかわらず PATCH を 1 回だけ増やす。この例外はジョブ単位の追跡可能性を優先する最優先規約であり、以下の判定フローは人間が管理する一括リリースの判断に使用する。

#### 1.x 以降での判定フロー

```text
変更内容を確認
   │
   ├─ パブリック API の削除・引数変更・挙動の非互換変更を含む?
   │       └─ Yes → major
   │       └─ No  ↓
   ├─ 後方互換のある機能追加（新コマンド・新オプション・新 extras 等）を含む?
   │       └─ Yes → minor
   │       └─ No  ↓
   └─ バグ修正のみ → patch
```

#### 0.x 系での判定フロー（現状）

```text
変更内容を確認
   │
   ├─ 機能追加 もしくは 破壊的変更 を含む?
   │       └─ Yes → minor
   │       └─ No  ↓
   └─ バグ修正のみ → patch
```

#### `hve` における判定例

| 変更例 | 1.x なら | 0.x なら（現状）|
|---|---|---|
| `--verbose` オプション追加 | `minor` | `minor` |
| `mdq` の検索結果スコア計算式変更で順位が変わる | `major`（出力非互換）| `minor` |
| GUI セッションの作業ディレクトリ分離（[CHANGELOG 既存エントリ](../CHANGELOG.md)）| `minor`（新規ファイル `hve/gui/session_workdir.py` の追加・CLI 単独実行は不変）| `minor` |
| `--with-gui` フラグ廃止・新フラグ体系へ移行（[CHANGELOG 既存エントリ](../CHANGELOG.md)）| `major`（CLI 互換性破壊）| `minor` |
| `pip show hve` のバージョン表記不一致を解消する内部修正 | `patch` | `patch` |

### 3.4 PEP 440 と SemVer の差分（必要時のみ参照）

通常のリリースでは意識不要だが、プレリリースやポストリリースを行う場合は PEP 440 形式を使う必要がある。現リポジトリの `[tool.bumpversion]` 設定は SemVer 形式 (`MAJOR.MINOR.PATCH`) のみを対象とするため、以下の形式が必要になった時点で `[tool.bumpversion]` に追加設定が必要となる（本書スコープ外）。

| 用途 | PEP 440 形式 | SemVer 形式 |
|---|---|---|
| アルファ版 | `1.0.0a1` | `1.0.0-alpha.1` |
| ベータ版 | `1.0.0b1` | `1.0.0-beta.1` |
| RC 版 | `1.0.0rc1` | `1.0.0-rc.1` |
| 開発版 | `1.0.0.dev1` | （規定なし）|
| ポストリリース | `1.0.0.post1` | （規定なし）|

`pip` は PEP 440 規約に従ってバージョン比較を行う。SemVer 形式のハイフン区切りプレリリース表記は `pip` に正しく解釈されないため、Python パッケージ運用では **PEP 440 形式を採用する**。

### 3.5 Git タグ命名

`bump-my-version` は `tag_name = "v{new_version}"` 設定により `v0.1.1` / `v0.2.0` 形式のタグを自動生成する。手動でタグを追加する場合も同形式に揃える。

---

## 4. `CHANGELOG.md` の書き方

リポジトリ直下の [CHANGELOG.md](../CHANGELOG.md) は **利用者向け** の変更履歴である。Git ログとは別物で、コミットメッセージの貼り付けではなく、利用者が「アップグレードすると何が変わるか」を判断できる粒度で書く。

### 4.1 採用書式

[Keep a Changelog 1.1.0](https://keepachangelog.com/ja/1.1.0/) をベースとし、現リポジトリで定着している以下の独自規約を加える。

- **見出し階層**: `## [Unreleased]` / `## [x.y.z] - YYYY-MM-DD`（リリース済み）の 2 レベル
- **カテゴリ見出し**: `### {Category} — {1 行件名}`（em dash `—` で接続）
- **エントリ本文**: 件名直下に 1〜複数段落の散文で「根本原因」「修正内容」「影響範囲」を記述
- **新しいバージョンが上に来る**（逆時系列）
- **日付は ISO 8601** (`YYYY-MM-DD`)

### 4.2 カテゴリ一覧

Keep a Changelog の標準 6 カテゴリ (Added / Changed / Deprecated / Removed / Fixed / Security) に加え、現 CHANGELOG.md で定着している修飾・派生カテゴリも許容する。

| カテゴリ | 用途 |
|---|---|
| `Added` | 新機能の追加 |
| `Changed` | 既存機能の変更（互換性は維持）|
| `Changed (Breaking)` | 既存機能の **後方互換性を壊す** 変更（[§3.3](#33-patch--minor--major-の判定) の `major` 該当）|
| `Deprecated` | 近く削除予定の機能 |
| `Removed` | 削除済みの機能 |
| `Fixed` | バグ修正 |
| `Security` | 脆弱性対応 |
| `Notes` | 上記いずれでもないリリース備考（参考情報・方針メモ等）|
| `Deferred` / `Skipped` | 当該フェーズで実施を見送った項目（後続に申し送り）|

> カテゴリの選択は変更内容の **性質** で決める。bump 種別との対応は [§3.3](#33-patch--minor--major-の判定) を参照。`Changed (Breaking)` を含む場合、1.x 系では `major`、0.x 系では `minor` まで上げる。

### 4.3 `bump-my-version` による自動昇格

`bump-my-version bump {patch|minor|major}` を実行すると、`CHANGELOG.md` 内の置換が以下の規則で行われる（[pyproject.toml](../pyproject.toml) `[tool.bumpversion.files]` 設定）。

```toml
[[tool.bumpversion.files]]
filename = "CHANGELOG.md"
search   = "## [Unreleased]"
replace  = "## [Unreleased]\n\n## [{new_version}] - {now:%Y-%m-%d}"
```

> **Copilot ジョブでは通常使用しない**: この置換は見出し直後へ版見出しを挿入するため、既に存在する `[Unreleased]` エントリーを新しい版へ取り込む。一括リリースとして全エントリーを同じ版に含めると確認できる場合だけ使用し、それ以外は既存内容の後ろに対象ジョブの版見出しを手動で追加する。

#### 昇格前

```markdown
# CHANGELOG

## [Unreleased]

### Added — 新機能 X
...
```

#### 昇格後（例: `bump minor` で `0.1.0` → `0.2.0`、実行日 `2026-05-26`）

```markdown
# CHANGELOG

## [Unreleased]

## [0.2.0] - 2026-05-26

### Added — 新機能 X
...
```

このため **`## [Unreleased]` 見出しは常に CHANGELOG.md 冒頭付近に維持** する必要がある。手動編集で見出しを変更・削除すると bump 時にスキップされ、エントリが過去バージョン側に取り残される（[§8](#8-トラブルシューティング) の「`## [Unreleased]` が見つからずスキップ」行を参照）。

### 4.4 エントリの書き方

新規エントリは `## [Unreleased]` 直下に追記する。テンプレート:

```markdown
### {Category} — {何をしたか 1 行件名}

{1〜2 段落の概要。利用者視点での変化を最初に書く。}

**根本原因**（バグ修正の場合）: {問題の発生メカニズム}

**修正内容**: {何を変更したか。複数項目があれば箇条書き}
- ...

**主な変更ファイル**: {重要なファイルパスを列挙}
```

#### 良い例（既存 CHANGELOG より引用）

```markdown
### Fixed — GUI セッション毎の作業ディレクトリ分離 (Issue-gui-session-workdir-isolation)

GUI から ARD 等の Workflow を実行中に、過去タスク（例: `Issue-gui-unified-workbench/`）の
`subissues.md` が誤って探索結果として採用され、テーブル形式パース失敗で Step が止まる問題を修正。

**根本原因**: `discover_subissues_md_verbose` (`hve/split_fork.py`) は `run_id`/`step_id` での
スコープフィルタを実装していたが、`runner.py` 側からの呼び出しで `None` のまま渡されており、
`work/Issue-*/subissues.md` が glob で全件採用されていた。

**修正内容（二段防御）**:
- **L1 物理分離**: ...
- **L2 論理スコープ**: ...
```

利用者視点での影響（壊れていた挙動→直った挙動）を最初に書き、内部実装の説明は **根本原因** 以降に分離している点に倣う。

### 4.5 やってはいけないこと

| 禁止事項 | 理由 |
|---|---|
| `## [Unreleased]` 見出しの削除・改名 | bump-my-version の昇格対象が見つからずスキップされる |
| 過去のリリース見出し（`## [0.1.0] - ...`）の変更 | リリース履歴の整合性が壊れる。修正は新規エントリで行う |
| `git log` の出力をそのまま貼り付け | 利用者にとって意味不明（CHANGELOG は人間向け）|
| プライベート API の変更を `Changed (Breaking)` と書く | 公開 API の互換性破壊と紛らわしい。`Changed` または `Fixed` で扱う |
| エントリの追記漏れ | リリース後にどのバージョンに何が入ったか分からなくなる。変更時に同 PR / 同コミットで追記する |

### 4.6 リリース時のチェック

リリース担当者は `bump-my-version` 実行前に `## [Unreleased]` 配下を読み、以下を確認する。

1. すべての変更項目に対応する `### {Category} — {件名}` エントリがあるか
2. カテゴリの選択が適切か（互換性破壊が `Changed` に紛れていないか）
3. 最大インパクトのカテゴリから bump 種別が決まっているか（[§3.3](#33-patch--minor--major-の判定)）

---

## 5. バージョンアップ手順（`bump-my-version`）

本章はリリース担当者向けの操作手順である。背景と規約（何をどう判定するか）は [§3 バージョンニング規約](#3-バージョンニング規約semver--pep-440) と [§4 CHANGELOG.md の書き方](#4-changelogmd-の書き方) を先に参照すること。

`hve` のバージョン番号は [§2.2](#22-バージョン番号の保持箱所) に示す 3 箱所にハードコードされている。加えてリリース時には [CHANGELOG.md](../CHANGELOG.md) の `## [Unreleased]` 見出しを新バージョン見出しに昭格する必要がある（[§4.3](#43-bump-my-version-による自動昭格)）。

これらを **1 コマンドで同時更新 + commit + Git タグ作成** するため、`bump-my-version` を採用している。設定は [pyproject.toml](../pyproject.toml) の `[tool.bumpversion]` セクションに記述済み。

### 5.1 前提条件

- リポジトリ直下にいる（`C:\GitHub\RoyalytyService2ndGen` 等）
- `.venv` 構築済み（未構築なら `hve\setup-hve.cmd` または `./hve/setup-hve.sh`）
- `git status` がクリーンであること（未コミットの変更があると失敗する）
- Windows PowerShell の場合、Rich の Unicode 出力でエラーが出ないよう `PYTHONIOENCODING=utf-8` を推奨

### 5.2 インストール

`bump-my-version` はリリース担当者のみが必要なため、`pyproject.toml` の依存には含めず個別インストールする。

```powershell
# Windows (PowerShell)
.venv\Scripts\python.exe -m pip install bump-my-version
```

```bash
# Linux / macOS
.venv/bin/python -m pip install bump-my-version
```

導入確認:

```powershell
.venv\Scripts\bump-my-version.exe --version
```

### 5.3 バージョンアップの実行

[§3.3](#33-patch--minor--major-の判定) の判定フローに従い、変更内容で `patch` / `minor` / `major` を選ぶ。

このコマンドは一括リリース向けである。Copilot ジョブで既存の `[Unreleased]` エントリーがある場合は、`CHANGELOG.md` の自動昇格を避けるために実行せず、版番号と対象ジョブの変更履歴を手動で同じ変更セットへ同期する。Copilot ジョブの `minor` / `major` はユーザーの明示判断がある場合だけ選択する。

| 変更内容 | コマンド | 例 |
|---|---|---|
| バグ修正のみ | `bump patch` | `0.1.0` → `0.1.1` |
| 後方互換ありの機能追加 | `bump minor` | `0.1.0` → `0.2.0` |
| 破壊的変更 | `bump major` | `0.1.0` → `1.0.0` |

実行例:

```powershell
# Windows (PowerShell)
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\bump-my-version.exe bump patch
```

```bash
# Linux / macOS
.venv/bin/bump-my-version bump patch
```

これだけで以下がすべて自動実行される:

1. `pyproject.toml` の `version`、`[tool.bumpversion].current_version` を更新
2. `hve/__init__.py` の `__version__` を更新
3. `CHANGELOG.md` の `## [Unreleased]` の下に `## [新バージョン] - YYYY-MM-DD` 見出しを挿入
4. 3 ファイルを `git add` + `git commit`（メッセージ: `chore(release): bump version to <new_version>`）
5. `v<new_version>` 形式の Git タグを作成（メッセージ: `chore(release): v<new_version>`）

### 5.4 事前確認（dry-run）

実際には変更せず、何が起きるかだけ表示:

```powershell
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\bump-my-version.exe bump patch --dry-run --verbose
```

> dry-run でも `allow_dirty = false` が効くため、作業中の変更があると失敗する。設定だけ検証したい場合は `--allow-dirty` を付与すること（実際の bump 実行時には付けない）。

### 5.5 リモートへの反映

```powershell
git push
git push --tags
```

GitHub 側でタグが PR / Release と連動する場合は、`git push --follow-tags` を 1 行で済ませても良い。

---

## 6. リリース後の確認とロールバック

[§5.5](#55-リモートへの反映) で `git push --follow-tags` を実行した直後、もしくは push 前に間違いに気付いた場合の対応手順をまとめる。**動作確認 → 問題があればロールバック** の順で進める。

### 6.1 動作確認

バージョン更新後、以下で反映を確認:

```powershell
.venv\Scripts\python.exe -c "import hve; print(hve.__version__)"
.venv\Scripts\python.exe -m pip show hve | Select-String Version
```

`pip show` の値が更新されない場合は editable install を再同期:

```powershell
.venv\Scripts\python.exe -m pip install -e . --no-deps
```

### 6.2 ロールバック

実行直後に間違いに気付いた場合（push 前）:

```powershell
git tag -d v<new_version>            # タグを削除
git reset --hard HEAD~1              # コミットを取り消し
```

すでに push してしまった場合:

```powershell
git push origin :refs/tags/v<new_version>   # リモートタグ削除
git revert <commit-sha>                     # コミットを打ち消す（履歴は残る）
git push
```

---

## 7. 対象外パッケージ（`mdq` 等）の運用

### 7.1 設定の場所

[pyproject.toml](../pyproject.toml) の末尾 `[tool.bumpversion]` セクション。変更対象ファイルを追加したい場合は `[[tool.bumpversion.files]]` を追記する。

> `pyproject.toml` 自身は bump-my-version 1.x が設定ファイルとして暗黙で対象に含めるため、`[[tool.bumpversion.files]]` への明示登録は不要（重複登録になる）。

### 7.2 連動しないバージョン

以下は **`hve` 本体と独立して管理** されているため、`bump-my-version` の対象外。各ファイルが保持するバージョン文字列を実体ベースで列挙する（執筆時点）。

| # | ファイル | 現在の値 | 用途 |
|---|---|---|---|
| 1 | [cq/\_\_init\_\_.py](../cq/__init__.py) | `__version__ = "0.4.0"` | Code Query engine |
| 2 | [.github/skills/code-query/SKILL.md](../.github/skills/code-query/SKILL.md) | `version: 0.4.0` | Code Query Skill |
| 3 | [tools/skills/code_query/pyproject.toml](../tools/skills/code_query/pyproject.toml) | `version = "0.3.0"` | `code-query-gui` distribution |
| 4 | [tools/for-other-repo/code-query/package.toml](../tools/for-other-repo/code-query/package.toml) | `version = "1.3.0"` | Code Query 移植用キット |
| 5 | [mdq/\_\_init\_\_.py](../mdq/__init__.py) | `__version__ = "0.8.0"` | Markdown Query engine |
| 6 | [.github/skills/markdown-query/SKILL.md](../.github/skills/markdown-query/SKILL.md) | `version: 0.8.0` | Markdown Query Skill |
| 7 | [tools/skills/markdown_query/pyproject.toml](../tools/skills/markdown_query/pyproject.toml) | `version = "0.3.0"` | `markdown-query-gui` distribution |
| 8 | [tools/for-other-repo/markdown-query/package.toml](../tools/for-other-repo/markdown-query/package.toml) | `version = "1.3.0"` | Markdown Query 移植用キット |
| 9 | [tools/for-other-repo/tool-search/package.toml](../tools/for-other-repo/tool-search/package.toml) | `version = "1.3.0"` | Tool Search 移植用キット |

> **注**: `tools/skills/*/vendor/` と `tools/skills/*/skill/` は正本から生成する。版数変更時も直接編集せず、各キットの `sync-vendor` を実行して同期する。

### 7.3 手動更新の判断基準と手順

#### 7.3.1 いつ更新するか

上記 7.2 のファイル群は `hve` 本体とは独立に管理されるため、以下のいずれかに該当する場合のみ更新する。

| 対象 | 更新するタイミング |
|---|---|
| `cq` / `mdq` engine と対応 Skill | 公開仕様に変更があった時。判定基準は [§3.3](#33-patch--minor--major-の判定) を各 engine / Skill 単位に適用 |
| `code-query-gui` / `markdown-query-gui` | 独立 GUI の公開仕様に変更があった時。GUI entrypoint の `__version__` も同時更新 |
| 各 `tools/for-other-repo/*/package.toml` | 移植用キットとして新しい版を配布する時。engine 版とは別に管理 |
| `tools/skills/*/vendor/` / `skill/` | 正本更新後に `sync-vendor` で再生成する。直接編集しない |

#### 7.3.2 更新手順

`bump-my-version` の対象外であるため、正本と配布宣言を明示的に更新し、生成物は同期スクリプトで再生成する。Git タグやリリースノートは `hve` 本体と分離する。

1. engine / canonical Skill / GUI `pyproject.toml` / `package.toml` の対象版を更新
2. Code Query / Markdown Query の各 `sync-vendor` を実行して vendor・Skill・共通 kit コピーを再生成
3. vendor byte 一致、Skill bundle、kit bundle、他リポジトリ配布契約のテストを実行
4. `git add` して、対象パッケージを示すスコープ付きメッセージで commit
5. Git タグを付ける場合は **`hve` 本体の `vx.y.z` タグと衝突しないよう**、パッケージ名を接頭辞に含めた命名（例: `markdown-query-v0.6.0`）を推奨する

> これらの手順は本書の `bump-my-version` フロー（[§5](#5-バージョンアップ手順bump-my-version)）と独立して実施できる。

---

## 8. トラブルシューティング

| 症状 | 原因 | 対処 | 関連 |
|---|---|---|---|
| `Git working directory is not clean` | 未コミットの変更がある | `git status` 確認 → 必要に応じて `git stash` または `git commit` | [§5.1](#51-前提条件) |
| `UnicodeEncodeError: 'cp932' codec ...` (Windows) | コンソールが cp932 で Rich の Unicode 出力に失敗 | `$env:PYTHONIOENCODING="utf-8"` を実行前に設定 | [§5.1](#51-前提条件) |
| `## [Unreleased]` が見つからずスキップ | CHANGELOG.md を手動編集して見出しを変えた | `## [Unreleased]` 見出しを CHANGELOG.md 冒頭に復活させる | [§4.3](#43-bump-my-version-による自動昇格) / [§4.5](#45-やってはいけないこと) |
| コマンドが見つからない | `pip install bump-my-version` を `.venv` 外で実行した | `.venv\Scripts\python.exe -m pip install bump-my-version` で再導入 | [§5.2](#52-インストール) |
| `pip show hve` のバージョンが古いまま | editable install のメタデータが未同期 | `.venv\Scripts\python.exe -m pip install -e . --no-deps` で再同期 | [§6.1](#61-動作確認) |
| bump 種別の判定に迷う | 変更の互換性影響を評価していない | [§3.3](#33-patch--minor--major-の判定) の判定フローを参照 | [§3](#3-バージョニング規約semver--pep-440) |
| カテゴリ選択に迷う | `Changed` と `Changed (Breaking)` の境界が曖昧 | パブリック API 互換性破壊の有無で判定。[§4.2](#42-カテゴリ一覧) を参照 | [§4](#4-changelogmd-の書き方) |

---
