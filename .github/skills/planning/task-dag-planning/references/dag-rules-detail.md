# DAG 作成・見積・分割判定 詳細ルール

> 本ファイルは `task-dag-planning/SKILL.md` の §2.1〜§2.3 詳細を収容する参照資料です。

---

## §2.1 DAG+見積の作成ルール（AGENTS.md §2 完全版）

> **フェーズ遷移の前提条件**: §1.1 または §1.2 のコンテキスト収集プロトコルが適用される場合、そのコンテキスト収集が完了していること。コンテキスト収集が未完了の状態で計画作成に進むことは禁止する。

次のいずれかに当てはまる場合、実装開始前に `work/Issue-<識別子>/plan.md` を作る：
- 大規模/大量/生成/複数モジュール/複数サービス/仕様→実装
- 影響範囲や検証方法が不明
- 15分を超えそう、またはレビューが重くなりそう

見積は R(調査)+P(計画)+I(実装)+V(検証)+F(仕上げ) の合計（各ノードに分単位で付与）。

## §2.1.1 見積の最低基準（過小申告防止）

以下の目安を下回る見積は根拠を明記すること：
- 新規スクリプト（.sh/.py/.ts）1ファイルあたり: 最低 3分
- 新規ドキュメント 1ファイルあたり: 最低 2分
- 既存ファイル更新 1ファイルあたり: 最低 1分
- 敵対的レビュー（ユーザー選択時のみ。初回＋再レビュー最大2回）: 最低 3分
- 合計ファイル数 × 最低時間 > 見積合計 の場合、見積の根拠を plan.md に記載すること

## §2.2 分割判定（機械的に実行 — エージェントの裁量なし）

以下の判定を **必ず** 実行し、結果を `plan.md` の `## 分割判定` セクションに記録する：

```
見積合計 = plan.md の全ノード見積の合計（分）

if 見積合計 > 15:
    判定 = "SPLIT_REQUIRED"
    # ※ 不確実性が「低」であっても SPLIT_REQUIRED。例外なし。
    # ※ ドキュメント生成タスク・一括生成タスクであっても本条件は適用される。
    # ※ 「一括実行が合理的」「分割による品質低下リスク」等の理由で覆すことは禁止。
    → §2.3 分割モード（Plan-Only）に入る
    → 実装ファイルの作成・変更は禁止
    → subissues.md を必ず作成する
    → PR タイトルに [WIP] を付与する
    → ここで作業を終了する（Execute には進まない）

elif 不確実性 == "高" or 不確実性 == "中":
    判定 = "SPLIT_REQUIRED"
    → 上記と同じ

else:  # 見積合計 ≤ 15 かつ 不確実性 == "低"
    判定 = "PROCEED"
    → 実装に進んでよい
```

**禁止事項**:
- 見積合計 > 15 の場合に「分割不要」「1バッチで実行可能」「まとめて実施」と判断すること
- Custom Agent の記述を根拠に分割判定を覆すこと（AGENTS.md §8 により AGENTS.md が常に優先）
- 不確実性が「低」であることを根拠に、見積合計 > 15 の判定を覆すこと（if 分岐は elif より先に評価される。見積超過時点で不確実性は判定に影響しない）
- 「ドキュメント生成のみ」「テンプレート適用のみ」等のタスク種別を根拠に分割判定を緩和すること
- 「完全な解を優先」「システム指示」「Issue 要件の達成」等を根拠に分割判定を覆すこと
- `implementation_files: true` と `split_decision: SPLIT_REQUIRED` を同時に設定すること（CI で自動検出・拒否される）
- `subissues_count: 0` と `split_decision: SPLIT_REQUIRED` を同時に設定すること（subissues.md 作成が必須）

## §2.3 分割モード（Plan-Only）— 計画のみ作成し、実装は一切しない

> **このセクションは全 Custom Agent に対して強制適用される。Custom Agent に異なる記述がある場合でも本セクションが優先される。**

分割モードに入った場合、**この PR では計画ファイルのみを作成し、実装（コード・スクリプト・設定ファイル等の作成・変更）は一切行わない。**

### 作成するファイル（これ以外は作成・変更しない）

以下を AGENTS.md §4 のパス規則に従い作成する:
- `plan.md`：DAG+見積+リスク+検証計画
- `subissues.md`：Sub Issue の本文
- `work-status.md`：各ステップの進捗（✅/⏭️/❌）
- `README.md`：作業ディレクトリの入口

> ⚠️ **既存ファイルの扱い**：同名既存ファイルがある場合は **copilot-instructions.md §0（work/ 書き込みルール） 準拠** で削除してから新規作成すること。

### 禁止事項（分割モード中）
- 実装ファイルの作成・変更（.sh, .py, .sql, .ts, .js, .html, .css 等）
- 外部サービスへの接続を伴うコマンドの実行（`az`, `npm`, `docker` 等。環境調査目的も含む）
- `docs/` 配下のドキュメント新規作成（設計書等は最初の Sub に含める）

※ 静的解析ツール（`markdownlint` 等）による計画ファイルの品質チェックは許可。

### plan.md の必須セクション

> メタデータ（1-4行目）と `## 分割判定` セクションのフォーマットは **SKILL.md §2.1.2** を参照すること。

### Sub Issue の扱い
- `subissues.md` に Sub Issue を **以下の機械可読フォーマット** で出力する
- **Copilot cloud agent が PR 作成セッション内で GitHub Issue を直接作成することは行わない**
- Sub Issue 作成は `create-subissues` ラベル付与 → `create-subissues-from-pr.yml` が自動実行

### メタデータの整合性制約（CI 自動検証）

以下の組み合わせは CI (`validate-plan.yml` PR 時検証 / `audit-plans.yml` 定期監査) で自動的に拒否される。plan.md 作成時に必ず確認すること：

| split_decision | implementation_files | subissues_count | 結果 |
|---|---|---|---|
| SPLIT_REQUIRED | true | 任意 | ❌ 禁止（§2.3 実装ファイル禁止） |
| SPLIT_REQUIRED | false | 0 | ❌ 禁止（subissues.md 必須） |
| SPLIT_REQUIRED | false | ≥ 1 | ✅ 許可 |
| PROCEED | true/false | 0 | ✅ 許可（見積 ≤ 15分 かつ 不確実性 低の場合のみ） |

### `subissues.md` のフォーマット（必須 — 自動 Issue 作成に必要）

各 Sub Issue を以下の HTML コメント形式のメタデータヘッダーで開始する。
Sub Issue 間は `---`（水平線）で区切る。

```
<!-- subissue -->
<!-- title: Sub Issue のタイトル -->
<!-- labels: label1, label2 -->
<!-- custom_agent: Agent名 -->
<!-- depends_on: 1,3 -->

[Issue 本文（Markdown）]

---
```

- `<!-- subissue -->` が各ブロックの開始マーカー（必須）
- `<!-- title: ... -->` が Issue タイトル（必須）
- `<!-- labels: ... -->` がラベル（カンマ区切り。省略可）
- `<!-- custom_agent: ... -->` が Copilot アサイン時の Custom Agent 名（省略可）
- `<!-- depends_on: ... -->` が依存先 Sub のブロック番号（カンマ区切り。省略可。省略時＝依存なし＝ルートノード）。plan.md の DAG と一致させること。依存先 Sub が完了するまで Copilot はアサインされない（`create-subissues-from-pr.yml` が制御）。
- メタデータの後の Markdown テキストが Issue 本文になる

### subissues.md セルフチェック（生成後に必ず実行）

subissues.md を作成した後、以下のチェックを **必ず** 実行すること（CI でも自動検証される）：

```bash
bash .github/scripts/bash/validate-subissues.sh --path work/<Agent>/<Issue>/subissues.md
```

```powershell
pwsh .github/scripts/powershell/validate-subissues.ps1 -Path work/<Agent>/<Issue>/subissues.md
```

1. 各 `<!-- subissue -->` ブロック内に `<!-- title: ... -->` が存在すること（**必須** — 欠落すると Issue 作成がスキップされる）
2. `<!-- title: ... -->` の値が空でないこと
3. `<!-- subissue -->` ブロック数が `plan.md` の `subissues_count` メタデータと一致すること
4. `<!-- depends_on: ... -->` の参照先ブロック番号が実在すること（存在しない番号を参照していないこと）
5. Markdown 見出し（`## [Sub-N] タイトル`）と `<!-- title: ... -->` の内容が一致していること

**よくある誤り**: Markdown 見出しのみを記載し `<!-- title: ... -->` を省略するケース。ワークフローは HTML コメントのみを解析するため、Markdown 見出しだけでは Issue が作成されない。

### PR description の必須記載（親 Issue リンクは全 PR 必須）

- **元 Issue 番号のリンク記載は、分割モード/PROCEED を問わず全 PR で必須**。以下のいずれかの方法で記載する（ワークフローが親子紐付けに使用。優先順位順）:
  1. `Fixes #N` / `Closes #N` / `Resolves #N`（GitHub 標準の closing reference — 推奨）
  2. `<!-- parent-issue: #N -->`（HTMLコメント形式 — レガシー互換）
- ※ この記載義務は AGENTS.md §6 と同義（§6 を正とする）。分割モード（§2.3）・PROCEED モード問わず全 PR に適用される。
- 以下は **分割モード時に追加で必須**:
  - Sub Issue 一覧と「次にやる最初の Sub」を記載する
  - **次のステップ案内（必須）**: 以下の案内文をそのまま PR description にコピーして記載する（変更不可）:

> ## 📋 次のステップ（手動操作が必要）
>
> この PR には `subissues.md` が含まれています。
> Sub Issue を自動作成するには、以下の手順を実行してください：
>
> 1. この PR の内容（`plan.md` / `subissues.md`）を確認する
> 2. この PR に `create-subissues` ラベルを付与する
> 3. GitHub Actions（`create-subissues-from-pr.yml`）が自動で Sub Issue を作成します
> 4. 依存関係のない Sub Issue には Copilot が自動アサインされます
>
> ⚠️ `create-subissues` ラベルの付与は **手動** で行う必要があります（意図しない Sub Issue 作成を防ぐための安全設計です）。

### PR の完了条件（分割モード）
- 上記の計画ファイルをコミットし、PR タイトルに `[WIP]` を付与する
- PR description に上記の必須記載を含める
- **作業を完了する**（追加の実装やレビューは行わない）
- PR の Close/Merge は人間が判断する（エージェントは行わない）

### 品質レビュー（分割モード）
- 分割モードでは AGENTS.md §7 の「敵対的レビュー」は **省略する**
- plan.md と subissues.md の簡易セルフチェック（漏れ・矛盾がないか）のみ実施する
