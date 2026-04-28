# DAG 作成・見積・分割判定 詳細ルール

> 本ファイルは `task-dag-planning/SKILL.md` の §2.1〜§2.3 詳細を収容する参照資料です。

---

## 用語定義

| フィールド | 値 | 定義 |
|-----------|---|------|
| `task_scope` | `single` | 独立して検証可能な成果物が 1 つ |
| `task_scope` | `multi` | 独立して検証可能な成果物が 2 つ以上（分離可能） |
| `context_size` | `small` | タスク実行に必要な参照ファイル数が 1〜3 件 |
| `context_size` | `medium` | タスク実行に必要な参照ファイル数が 4〜8 件 |
| `context_size` | `large` | タスク実行に必要な参照ファイル数が 9 件以上、または単一ファイルが 500 行超 |

---

## §2.1 DAG+見積の作成ルール（AGENTS.md §2 完全版）

> **フェーズ遷移の前提条件**: §1.1 または §1.2 のコンテキスト収集プロトコルが適用される場合、そのコンテキスト収集が完了していること。コンテキスト収集が未完了の状態で計画作成に進むことは禁止する。

次のいずれかに当てはまる場合、実装開始前に `work/Issue-<識別子>/plan.md` を作る：
- 大規模/大量/生成/複数モジュール/複数サービス/仕様→実装
- 影響範囲や検証方法が不明
- task_scope=multi または context_size=large に該当する

見積は R(調査)+P(計画)+I(実装)+V(検証)+F(仕上げ) の合計（各ノードに分単位で付与）。見積は参考情報として記載可能だが、**CI 判定の根拠には使用しない**。

## §2.1.1 粒度の最低基準

以下に該当する場合は `task_scope` または `context_size` を見直すこと：
- 1 タスクで新規ファイルを 3 件以上生成する場合 → `task_scope=multi` 候補
- タスク実行に必要な参照ファイルが 9 件以上の場合 → `context_size=large`
- タスク実行に参照する単一ファイルが 500 行を超える場合 → `context_size=large`
- 独立して検証・レビュー可能な成果物が 2 つ以上ある場合 → `task_scope=multi`

## §2.2 分割判定（機械的に実行 — エージェントの裁量なし）

以下の判定を **必ず** 実行し、結果を `plan.md` の `## 分割判定` セクションに記録する：

```
if task_scope == "multi":
    判定 = "SPLIT_REQUIRED"
    # ※ context_size が small/medium であっても SPLIT_REQUIRED。例外なし。
    # ※ 「一括実行が合理的」「分割による品質低下リスク」等の理由で覆すことは禁止。
    → §2.3 分割モード（Plan-Only）に入る
    → 実装ファイルの作成・変更は禁止
    → subissues.md を必ず作成する
    → PR タイトルに [WIP] を付与する
    → ここで作業を終了する（Execute には進まない）

elif context_size == "large":
    判定 = "SPLIT_REQUIRED"
    → 上記と同じ

else:  # task_scope == "single" かつ context_size IN ("small", "medium")
    判定 = "PROCEED"
    → 実装に進んでよい
```

**禁止事項**:
- `task_scope=multi` または `context_size=large` の場合に「分割不要」「1バッチで実行可能」「まとめて実施」と判断すること
- Custom Agent の記述を根拠に分割判定を覆すこと（AGENTS.md §8 により AGENTS.md が常に優先）
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

> メタデータ（冒頭5行）と `## 分割判定` セクションのフォーマットは **SKILL.md §2.1.2** を参照すること。

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
| PROCEED | true/false | 0 | ✅ 許可（task_scope=single かつ context_size=small または medium の場合のみ） |

### `subissues.md` のフォーマット（必須 — 自動 Issue 作成に必要）

#### ファイルレベルメタデータ（最初の `<!-- subissue -->` より前に記載）

```
<!-- parent_issue: NNN -->
```

- `<!-- parent_issue: NNN -->` は **運用上必須**。作業対象Issueの番号（数値のみ、`#` なし）を記載する。
  - 取得元: PR の起点となった Issue 番号（`Fixes #N` で指定した Issue と同一）
  - **推論・捏造禁止**: 不明な場合は `TBD` と記載し作業を停止すること
  - ワークフロー互換: `<!-- parent-issue: #NNN -->`（ハイフン形式・`#` 付き）も受け付けるが、`<!-- parent_issue: NNN -->` を推奨
  - **現状の自動検証範囲**: `validate-subissues.yml` が自動検証するのは title のみであり、`parent_issue` の有無や値整合はこのワークフローでは未検証
  - **後続ワークフローでの利用**: `create-subissues-from-pr.yml` は **subissues.md のメタデータを最優先** で使用する。PR body の `Fixes #N` はフォールバック。両者は同じ Issue 番号を指すこと。

#### ブロックレベルメタデータ（各 Sub Issue の定義）

各 Sub Issue を以下の HTML コメント形式のメタデータヘッダーで開始する。
`<!-- subissue -->` が各ブロックの開始マーカー（**必須区切り**）。`---`（水平線）は可読性向上のための**オプション**であり、ワークフローは `<!-- subissue -->` のみで分割する。

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
- `<!-- title: ... -->` が Issue タイトル（**必須**。空値禁止。`REPLACE_ME` 等のプレースホルダーも空値扱い）
- `<!-- labels: ... -->` がラベル（カンマ区切り。省略可）
- `<!-- custom_agent: ... -->` が Copilot アサイン時の Custom Agent 名。**省略すると Copilot がアサインされない（split-mode では事実上の致命的欠落）。** 親Issueの `## Custom Agent` セクションに記載されている Agent 名を記載すること。
- `<!-- depends_on: ... -->` が依存先 Sub のブロック番号（カンマ区切り）。**ブロック番号 = subissues.md 内の `<!-- subissue -->` マーカーの出現順（1始まり）。** `## [Sub-N]` の N ではなくマーカー順である点に注意。
  - **省略 = 依存なし = ルートノード = Copilot 即時アサイン。** 省略は「意図的な並行実行」を意味する。plan.md の DAG で依存がある場合は**必ず記載すること**。省略すると前提未完了で作業が開始される。
  - **plan.md DAG との対応**: plan.md で `S1→S2` の依存がある場合、subissues.md のブロック2（2番目の `<!-- subissue -->`）に `<!-- depends_on: 1 -->` を記載する。
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
2. `<!-- title: ... -->` の値が空でないこと（`REPLACE_ME` などのプレースホルダーも実質的に空値扱いとして運用上禁止）
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
