# Source Code からの Documentation（ソースコードからの段階的ドキュメント生成）

← [README](../README.md)

---

## 概要（4層構造）

`adoc` ワークフローは、Context Window を小さく保つために、前段の要約のみを後段へ渡す 4 層構造で実行します。`src/` 相当の既存コードを入力に技術文書（`docs-generated/`）を生成し、`knowledge/` との整合確認を進める際の補助資料として活用できます。

![3つの情報源をもとに3つのワークフローが連携し、レイヤー1のファイルインベントリとファイル単位サマリーから、レイヤー2のコンポーネント分析、レイヤー2.5のインデックス、レイヤー3から4の横断分析と目的特化ドキュメント生成へ段階的に進む adoc の4層構造図](./images/knowledge-interface-flow.svg)

- レイヤー1（Step.1〜2.x）: ファイルインベントリ + ファイル単位サマリー
- レイヤー2（Step.3.x）: コンポーネント/モジュール分析
- レイヤー2.5（Step.4）: レイヤー2成果物のインデックス
- レイヤー3〜4（Step.5.x〜6.x）: 横断分析 + 目的特化ドキュメント

---

## Agent チェーン図（ADOC）

以下の図は、このワークフローで使用される Custom Agent がファイルの入出力を介してどのように連鎖するかを示します。

```mermaid
flowchart TD
  subgraph L1["レイヤー 1"]
    s1{"Doc-FileInventory [1]"}
  end
  subgraph L2["レイヤー 2"]
    s2_1{"Doc-FileSummary [2.1]"}
    s2_2{"Doc-TestSummary [2.2]"}
    s2_3{"Doc-ConfigSummary [2.3]"}
    s2_4{"Doc-CICDSummary [2.4]"}
    s2_5{"Doc-LargeFileSummary [2.5]"}
  end
  subgraph L3["レイヤー 3"]
    s3_1{"Doc-ComponentDesign [3.1]"}
    s3_2{"Doc-APISpec [3.2]"}
    s3_3{"Doc-DataModel [3.3]"}
    s3_4{"Doc-TestSpecSummary [3.4]"}
    s3_5{"Doc-TechDebt [3.5]"}
  end
  subgraph L4["レイヤー 4"]
    s4{"Doc-ComponentIndex [4]"}
  end
  subgraph L5["レイヤー 5"]
    s5_1{"Doc-ArchOverview [5.1]"}
    s5_2{"Doc-DependencyMap [5.2]"}
    s5_3{"Doc-InfraDeps [5.3]"}
    s5_4{"Doc-NFRAnalysis [5.4]"}
  end
  subgraph L6["レイヤー 6"]
    s6_1{"Doc-Onboarding [6.1]"}
    s6_2{"Doc-Refactoring [6.2]"}
    s6_3{"Doc-Migration [6.3]"}
  end
  s1 -->|"docs-generated/inventory.md"| s2_1
  s1 -->|"docs-generated/inventory.md"| s2_2
  s1 -->|"docs-generated/inventory.md"| s2_3
  s1 -->|"docs-generated/inventory.md"| s2_4
  s1 -->|"docs-generated/inventory.md"| s2_5
  s2_1 -->|"docs-generated/files/{relative-path}.md"| s3_1
  s2_2 -->|"docs-generated/files/{relative-path}.md"| s3_1
  s2_3 -->|"docs-generated/files/{relative-path}.md"| s3_1
  s2_4 -->|"docs-generated/files/{relative-path}.md"| s3_1
  s2_5 -->|"docs-generated/files/{relative-path}.md"| s3_1
  s2_1 -. "docs-generated/files/{relative-path}.md（代替依存）" .-> s3_1
  s2_1 -->|"docs-generated/files/{relative-path}.md"| s3_2
  s2_2 -->|"docs-generated/files/{relative-path}.md"| s3_2
  s2_3 -->|"docs-generated/files/{relative-path}.md"| s3_2
  s2_4 -->|"docs-generated/files/{relative-path}.md"| s3_2
  s2_5 -->|"docs-generated/files/{relative-path}.md"| s3_2
  s2_1 -. "docs-generated/files/{relative-path}.md（代替依存）" .-> s3_2
  s2_1 -->|"docs-generated/files/{relative-path}.md"| s3_3
  s2_2 -->|"docs-generated/files/{relative-path}.md"| s3_3
  s2_3 -->|"docs-generated/files/{relative-path}.md"| s3_3
  s2_4 -->|"docs-generated/files/{relative-path}.md"| s3_3
  s2_5 -->|"docs-generated/files/{relative-path}.md"| s3_3
  s2_1 -. "docs-generated/files/{relative-path}.md（代替依存）" .-> s3_3
  s2_2 -->|"docs-generated/files/{relative-path}.md"| s3_4
  s2_1 -->|"docs-generated/files/{relative-path}.md"| s3_5
  s2_2 -->|"docs-generated/files/{relative-path}.md"| s3_5
  s2_3 -->|"docs-generated/files/{relative-path}.md"| s3_5
  s2_4 -->|"docs-generated/files/{relative-path}.md"| s3_5
  s2_5 -->|"docs-generated/files/{relative-path}.md"| s3_5
  s2_1 -. "docs-generated/files/{relative-path}.md（代替依存）" .-> s3_5
  s3_1 -->|"docs-generated/components/{component}.md"| s4
  s3_2 -->|"docs-generated/components/api-spec.md"| s4
  s3_3 -->|"docs-generated/components/data-model.md"| s4
  s3_4 -->|"docs-generated/components/test-spec-summary.md"| s4
  s3_5 -->|"docs-generated/components/tech-debt.md"| s4
  s4 -->|"docs-generated/component-index.md"| s5_1
  s4 -->|"docs-generated/component-index.md"| s5_2
  s4 -->|"docs-generated/component-index.md"| s5_3
  s4 -->|"docs-generated/component-index.md"| s5_4
  s3_4 -->|"docs-generated/components/test-spec-summary.md"| s5_4
  s3_5 -->|"docs-generated/components/tech-debt.md"| s5_4
  s5_1 -->|"docs-generated/architecture/overview.md"| s6_1
  s5_2 -->|"docs-generated/architecture/dependency-map.md"| s6_1
  s5_2 -->|"docs-generated/architecture/dependency-map.md"| s6_2
  s5_4 -->|"docs-generated/architecture/nfr-analysis.md"| s6_2
  s3_5 -->|"docs-generated/components/tech-debt.md"| s6_2
  s5_1 -->|"docs-generated/architecture/overview.md"| s6_3
  s5_3 -->|"docs-generated/architecture/infra-deps.md"| s6_3
  s5_4 -->|"docs-generated/architecture/nfr-analysis.md"| s6_3
  s1 -. "knowledge/ 参照" .-> kn
  s2_1 -. "knowledge/ 参照" .-> kn
  s2_2 -. "knowledge/ 参照" .-> kn
  s2_3 -. "knowledge/ 参照" .-> kn
  s2_4 -. "knowledge/ 参照" .-> kn
  s2_5 -. "knowledge/ 参照" .-> kn
  s3_1 -. "knowledge/ 参照" .-> kn
  s3_2 -. "knowledge/ 参照" .-> kn
  s3_3 -. "knowledge/ 参照" .-> kn
  s3_4 -. "knowledge/ 参照" .-> kn
  s3_5 -. "knowledge/ 参照" .-> kn
  s4 -. "knowledge/ 参照" .-> kn
  s5_1 -. "knowledge/ 参照" .-> kn
  s5_2 -. "knowledge/ 参照" .-> kn
  s5_3 -. "knowledge/ 参照" .-> kn
  s5_4 -. "knowledge/ 参照" .-> kn
  s6_1 -. "knowledge/ 参照" .-> kn
  s6_2 -. "knowledge/ 参照" .-> kn
  s6_3 -. "knowledge/ 参照" .-> kn
  kn[/"knowledge/"/]
  classDef arch fill:#4A90D9,stroke:#1f3a5a,color:#fff;
  classDef dev fill:#50C878,stroke:#1b5e20,color:#111;
  classDef doc fill:#9B59B6,stroke:#4a235a,color:#fff;
  classDef qa fill:#E67E22,stroke:#7e3d00,color:#111;
  classDef km fill:#F39C12,stroke:#7a4f00,color:#111,stroke-width:3px;
  classDef file fill:#95A5A6,stroke:#5d6d73,color:#111;
  class s1 doc;
  class s2_1 doc;
  class s2_2 doc;
  class s2_3 doc;
  class s2_4 doc;
  class s2_5 doc;
  class s3_1 doc;
  class s3_2 doc;
  class s3_3 doc;
  class s3_4 doc;
  class s3_5 doc;
  class s4 doc;
  class s5_1 doc;
  class s5_2 doc;
  class s5_3 doc;
  class s5_4 doc;
  class s6_1 doc;
  class s6_2 doc;
  class s6_3 doc;
  class kn file;
  subgraph LEG["凡例"]
    la(["Arch-*（青）: 設計"]):::arch
    ld["Dev-*（緑）: 実装"]:::dev
    lc{"Doc-*（紫）: 文書生成"}:::doc
    lq{{"QA-*（橙）: 品質確認"}}:::qa
    lk[["KnowledgeManager（金）"]]:::km
    lf[/"ファイル/ディレクトリ（灰）"/]:::file
  end
```

![ADOC: Doc-FileInventory → Doc-Migration の19ステップチェーン（並列4箇所含む）](./images/chain-adoc.svg)


## 前提条件

- `hve` CLI が実行可能であること
- GitHub Copilot cloud agent が利用可能であること
- 出力先は `docs-generated/`（既存 `docs/` と分離）

---

## 方式1: Copilot cloud agent 手動実行

1. Issue/Sub-issue を作成する
2. Step ごとに対応する `Doc-*` Custom Agent を選択して実行する
3. 各 Step 完了後に `adoc:done` ラベルが付与されることを確認する

---

## 方式2: ワークフローオーケストレーション（Web）

1. Issues → New issue で **Source Codeからのドキュメント作成** を選択
2. `branch` / `target_dirs` / `doc_purpose` などを入力
3. Submit 後、`auto-app-documentation` ラベルでオーケストレーションを開始

### Issue Template フィールド詳細

| フィールド | 目的 | 入力例 |
|---|---|---|
| `branch` | ドキュメント生成を実行する対象ブランチ | `main` / `feature/adoc` |
| `target_dirs` | 対象ディレクトリを限定（未指定時は全体） | `src/,hve/` |
| `exclude_patterns` | 解析対象から除外するパターン | `node_modules/,dist/,*.lock` |
| `doc_purpose` | 生成物の主目的 | `all` / `onboarding` / `refactoring` / `migration` |
| `max_file_lines` | 大規模ファイル分割の閾値 | `300` / `500` / `1000` |
| `steps` | 実行する Step の限定（未選択時は全 Step） | Step.1〜Step.6 から選択 |
| `enable_review` | PR 完了時のセルフレビュー自動化 | チェックで `auto-context-review` 付与 |
| `enable_qa` | QA 質問票自動化 | チェックで `auto-qa` 付与 |
| `additional_comment` | ステップへ引き継ぐ追加条件 | `docs-generated/ のみ更新したい` |

---

## 方式3: ワークフローオーケストレーション（ローカル hve）

### CLI 実行例

```bash
python -m hve orchestrate \
  --workflow adoc \
  --branch main \
  --target-dirs src/,hve/ \
  --exclude-patterns "node_modules/,vendor/,dist/,*.lock,__pycache__/" \
  --doc-purpose all \
  --max-file-lines 500
```

目的別実行例:

```bash
python -m hve orchestrate --workflow adoc --doc-purpose onboarding
python -m hve orchestrate --workflow adoc --doc-purpose refactoring
python -m hve orchestrate --workflow adoc --doc-purpose migration
```

---

## 成果物出力先

- `docs-generated/inventory.md`
- `docs-generated/files/`
- `docs-generated/components/`
- `docs-generated/component-index.md`
- `docs-generated/architecture/`
- `docs-generated/guides/`

---

## DAG 実行の Wave 計画

```text
Wave 1: Step.1
Wave 2: Step.2.1 ‖ Step.2.2 ‖ Step.2.3 ‖ Step.2.4 ‖ Step.2.5
Wave 3: Step.3.1 ‖ Step.3.2 ‖ Step.3.3 ‖ Step.3.4 ‖ Step.3.5
Wave 4: Step.4
Wave 5: Step.5.1 ‖ Step.5.2 ‖ Step.5.3 ‖ Step.5.4
Wave 6: Step.6.1 ‖ Step.6.2 ‖ Step.6.3
```
