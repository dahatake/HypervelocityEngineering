# ディレクトリ構造詳細・qa/ 規則・ソースコードパス標準

> 本ファイルは `work-artifacts-layout/SKILL.md` の §4.1〜§4.4 詳細を収容する参照資料です。

---

## §4.1 既存ファイルの削除と新規作成（絶対ルール）

`work/` および `qa/` 配下のファイル作成・更新時は以下の疑似コードに**必ず**従うこと：

```
対象ファイル = work/ または qa/ 配下の書き込み対象パス

if 対象ファイルが既に存在する:
    → 既存ファイルを削除する（Git 上の delete 操作）
    → 削除されたことを確認する
    → 新規ファイルを作成する（Git 上の create 操作）
else:
    → 新規ファイルを作成する（Git 上の create 操作）

→ 作成後、ファイルが空でないことを copilot-instructions.md §0 の書き込み失敗対策に従って確認する
```

※ 1コミット内での delete + create 同時実行は許可。edit/update は不可。

**禁止**: 上書き更新(edit/update/patch) / 追記(append) / 削除省略

**適用範囲**: `work/` 全ファイル・サブディレクトリ / `qa/` 全ファイル / `knowledge/` 全ファイル / §2.3 分割モードのファイル / 全 Custom Agent（AGENTS.md §8 により例外なし）

> **理由**：上書き更新は残留データの原因。delete→create でクリーン状態を保証。

---

## §4.5 並列安全性ルール（複数ジョブ同時実行時のファイル衝突防止）

複数のジョブが同時実行された際に `work/` 配下の同じディレクトリにファイルが書き込まれる衝突を防ぐため、`run_id`（タイムスタンプ + UUID短縮）と `step_id` の2層構造による識別子を使用する。

### 識別子の構成

| 要素 | 値の例 | 役割 |
|------|-------|------|
| **run_id** | `20260413T143022-a1b2c3` | いつの実行か（再実行衝突を防止） |
| **step_id** | `1.1`, `2.3` | どのステップか（並列ステップ衝突を防止） |

### 方式別の分離戦略

- **Web UI 方式**: Issue 番号（`Issue-<N>`）で自動分離（変更不要）
- **CLI SDK 方式**:
  - `work` ディレクトリ: `work/self-improve/run-{run_id}/step-{step_id}/`
  - `qa` ファイル: `qa/{run_id}-{step_id}-qa-merged.md`
  - ロックファイル: `work/self-improve/run-{run_id}/.self-improve-lock`

### ディレクトリ構造（CLI SDK 方式）

```
work/
├── <Agent名>/Issue-<番号>/           ← Web UI方式（変更なし）
│   ├── README.md
│   ├── plan.md
│   ├── contracts/
│   └── artifacts/
└── self-improve/                     ← CLI SDK方式
    └── run-20260413T143022-a1b2c3/   ← run_id で分離
        ├── .self-improve-lock        ← ロックファイル
        ├── step-1.1/                 ← step_id で分離
        │   └── artifacts/
        │       └── learning-001.md
        └── step-2.3/
            └── artifacts/
                └── learning-001.md
```

### `run_id` のライフサイクル

- `run_id` はワークフロー実行開始時（`orchestrator.py` の `run_workflow()` 内）に1回生成する
- `SDKConfig.run_id` フィールドで保持し、`StepRunner` に伝播する
- `run_id` が未設定（空文字列）の場合は `generate_run_id()` で自動生成する（後方互換性）

### `run_id` 生成関数

```python
import time, uuid

def generate_run_id() -> str:
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    short_uuid = uuid.uuid4().hex[:6]
    return f"{ts}-{short_uuid}"
```

タイムスタンプ（ソート可能・人間可読）+ UUID短縮（秒単位の同時実行でも衝突防止）の組み合わせ。

> **注意**: `permission_handler.py` の `_ALLOWED_WRITE_PATHS`（`work/`, `qa/`）はプレフィックスマッチのため変更不要。

---

質問票（QA）のファイル出力先は `qa/` 配下とする（`work/` には質問票を保存しない）。

**構造**: `qa/` 直下にフラットにファイルを配置する（サブディレクトリは作成しない）。

**ファイル命名規則**:
- `<適切なタイトル>.md` 形式とし、質問票のコンテキストから識別可能な名前を付ける
- 命名の優先順位:
  1. Custom Agent 経由かつ Issue 番号がある場合: `<Agent名>-Issue-<番号>.md`（例: `Arch-DataModeling-Issue-58.md`）
  2. Issue 番号がある場合（非 Custom Agent）: `Issue-<番号>-<簡潔な説明>.md`（例: `Issue-42-context-review.md`）
  3. Issue 番号が不明な場合: `<タスク内容の簡潔な要約>.md`（例: `batch-design-qa.md`）
- ファイル名にはパスセーフな文字のみ使用する（英数字・ハイフン・アンダースコア。日本語は避ける）

**適用対象**:
- copilot-instructions.md §0.2 ステップ3 で作成する質問票（非PR連携時のコンテキスト収集）
- `copilot-auto-qa.yml` や類似のトリガーによる質問票作成依頼の応答として出力するファイル
- PR コメントやチャットでの回答はファイル出力ではないため対象外

**書き込みルール**: §4.1 の適用範囲に `qa/` 配下が含まれるため、削除→新規作成ルールが同等に適用される。

> **注意**: `qa/` 配下には質問票ファイルのみを配置する。`plan.md`、`subissues.md` 等の計画ファイルは従来通り `work/` 配下に保存する。

---

## §4.4 ソースコードパスの標準定義

リポジトリ内のソースコードパスは以下を標準とする。各 Custom Agent は独自パスを定義せず、この標準に従うこと。

| 用途 | 標準パス | 説明 |
|------|---------|------|
| UI 実装 | `src/app/` | Web フロントエンド |
| API 実装 | `src/api/{サービスID}-{サービス名}/` | バックエンド（Azure Functions 等） |
| IaC | `infra/azure/` | Azure リソース作成スクリプト |
| テスト(API) | `test/api/` | バックエンド テストコード |
| テスト(UI) | `test/ui/` | フロントエンド テストコード |
| データ | `src/data/` | データ登録スクリプト等 |

※ Custom Agent が `app/` や `api/` と記載している場合でも、本標準に従い `src/app/`、`src/api/` と解釈すること。
