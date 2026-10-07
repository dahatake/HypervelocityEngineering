import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]

SAMPLE_RD = """# 要求定義書

## 1. 概要

### 1.2 目的

| ID | 目的 | 成功指標 | 測定方法 |
|---|---|---|---|
| G-001 | 申請の離脱を減らす | 離脱率 | アクセス解析 |

## 3. 前提・制約

### 3.1 既定制約（要求定義プロンプトの常設方針）

- ui_policy-1 利用者がレイアウトを変更できる UI

### 3.2 パラメータ（PARAM）

| ID | 名前 | 値 | 単位 | 根拠 | 決定状態 |
|---|---|---|---|---|---|
| PARAM-001 | 下書きの保持期間 | 30 | 日 | 依頼原文 | 承認済み |

### 3.3 用語

| 用語 | 定義 | 禁止同義語 |
|---|---|---|
| 申請 | 利用者が提出する書類 | 申込、エントリー |

## 4. ペルソナ

| ペルソナ | 業務 | 主要な判断 | 使うデータ | 判断の頻度と緊急度 | 役割 | 出典 |
|---|---|---|---|---|---|---|
| 申請者 | 申請の入力 | 提出してよいか | 申請 | 毎日・中 | 利用者 | SRC-001 |

## 6. 要求

### 6.1 機能要求

#### FR-001 入力の中断と再開
- 要求: 申請を入力している利用者は、入力を中断して後で再開したときに、入力済みの内容を確認できる。
- 決定状態: 承認済み（依頼 2026-10-08）　出自: 依頼原文　優先度: MUST（再入力が離脱の原因のため）
- 上位: G-001　出典: 依頼原文
- 対象エンティティ: 申請　関係する状態: 下書き　参照パラメータ: PARAM-001
- 受入基準 AC-001: 入力途中で画面を閉じた利用者が再び開いたとき、入力済みの値が失われない。保持期間は {PARAM-001} とする。
  - 検証レベル: system
- 受入基準 AC-002: 保持期間を過ぎた下書きは表示されない。
  - 検証レベル: integration
  - BLOCKED: Q-001

## 10. 仮定・未解決事項

### 10.1 質問票

| ID | 重要度 | 質問 | 選択肢 | 推奨 | 状態 | 回答 |
|---|---|---|---|---|---|---|
| Q-001 | 高 | 保持期間の起点はいつか | A: 作成時 / B: 最終更新時 | B | 未回答 | |

## 11. 出典台帳

| ID | 資料 | 版・日付 | 確認した位置 | 確認日 | 区分 |
|---|---|---|---|---|---|
| SRC-001 | 利用者調査 | 2026-09 | 全体 | 2026-10-08 | 本文 |
"""

SAMPLE_CATALOG = """# カタログ

## 機能

| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |
|---|---|---|---|---|---|
| FR-001 | 入力の中断と再開 | 承認済み | 未実装 | 未実装 | なし |
"""


def run(cmd, cwd, input_text=None, check=False):
    env = dict(os.environ, PYTHONUTF8="1")
    proc = subprocess.run(cmd, cwd=str(cwd), input=input_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if check and proc.returncode != 0:
        raise AssertionError(f"{cmd} failed ({proc.returncode})\n{proc.stdout}\n{proc.stderr}")
    return proc


def git(repo, *args):
    return run(["git", *args], repo, check=True).stdout.strip()


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def py(self, script, *args, input_text=None, check=False):
        return run([sys.executable, str(self.path / "scripts" / script), *args], self.path, input_text, check)

    def write(self, rel, text):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def read(self, rel):
        return (self.path / rel).read_text(encoding="utf-8")

    def commit(self, msg="update"):
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", msg, "--allow-empty")

    def gate(self, event, payload):
        payload.setdefault("cwd", str(self.path))
        proc = run([sys.executable, str(self.path / "scripts" / "hooks" / "gate.py"), event], self.path, json.dumps(payload))
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout) if proc.stdout.strip() else {}


def init_git(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q", "-b", "main"], path, check=True)
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "test")
    git(path, "config", "commit.gpgsign", "false")


@pytest.fixture
def empty_repo(tmp_path):
    path = tmp_path / "app"
    init_git(path)
    (path / "README.md").write_text("# app\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture
def repo(empty_repo):
    run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(empty_repo), "--skip-verify"], empty_repo, check=True)
    r = Repo(empty_repo)
    r.commit("install toolkit")
    return r


@pytest.fixture
def sample(repo):
    repo.write("docs/requirements-definition.md", SAMPLE_RD)
    repo.write("docs/catalog.md", SAMPLE_CATALOG)
    repo.py("next-id.py", "--sync", "--adopt", check=True)
    repo.commit("sample requirements")
    return repo
