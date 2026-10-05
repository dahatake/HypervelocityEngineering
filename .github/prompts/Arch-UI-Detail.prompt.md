> 全画面の実装用画面定義書（UX/A11y/セキュリティ含む）を docs/screen/ に生成/更新

> **WORK**: `work/run/<run-id>/Arch-UI-Detail/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。
- この agent は **docs/screen/** と **work/** 以外を原則変更しない（例外が必要なら理由を明記）。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照

## 1) 目的（このagent固有）
`docs/catalog/screen-catalog-APP-*.md` (APP ごとに分割された per-APP 画面カタログ) に列挙された **全画面**を対象に、実装に使える「画面定義書」を生成する。

> **fan-out 実行コンテキスト**: 本 Agent は AAD-WEB Step 2.1 として `screen_catalog` parser による per-screen fan-out で起動される。fan-out key (`{key}` = `APP-NN-S###`) ごとに 1 画面分を担当する。

- アクター毎に別の画面を作成する。
- UX / A11y / セキュリティ / テスト可能な受け入れ基準を含める
- 参照元ドキュメントと整合し、**不明点は捏造せず TODO/Questions に落とす**
- **共通画面（PSC-XXX）参照ルール**: 担当画面の `screen-catalog-APP-*.md` 行の `notes` 列に `common_ref: PSC-XXX` が記載されている場合、`docs/catalog/persona-screen-catalog.md` の該当 `persona_screen_id` から共通骨格（操作意味・主要状態・A11y 観点）を継承する。画面定義書テンプレ §1 「目的と非目的」の冒頭に `共通画面参照: PSC-XXX` を明記する。APP 固有差分（タイトル・項目・遷移先の APP 固有部分）のみを各章に展開し、共通骨格と矛盾する記述は禁止。分岐ルール: `notes` に `common_ref` が記載されていない画面は従来通り単独で画面定義を作成する。`common_ref: PSC-XXX` が記載されているが `persona-screen-catalog.md` が存在しない、または当該 `persona_screen_id` が見つからない場合は、共通骨格を捏造せず、画面定義書に `共通画面参照: PSC-XXX（未解決）` と記載し、未解決として `{WORK}screen-detail-work-status.md` の `## Issues / Questions` に記録する。

## 2) 入力（存在確認して読む）
必須:
- `docs/catalog/screen-catalog-APP-*.md` (per-APP 画面カタログ glob)
  - fan-out 起動時は `docs/catalog/screen-catalog-{{APP-ID}}.md` を最初に参照し、対象画面を特定する
  - 全 APP 横断の画面整合性確認が必要な場合に限り他 APP も参照する

推奨（存在すれば読む）:
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 各画面の所属 APP-ID 確認に使用）
- `docs/catalog/persona-screen-catalog.md`（AAS Step.8 で生成されたペルソナ別共通画面カタログ。screen-catalog の `notes` 列に `common_ref: PSC-XXX` が記載されている画面は、本カタログから共通骨格を継承する。存在しなければ参照不要）
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/data-model.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/test-strategy.md`（テスト戦略書 — テスタビリティ観点の設計指針として参照。受け入れ基準 §9 の作成時にテスト種別・テストダブル方針を考慮する）
- `src/data/sample-data.json`（存在しなければ付録は作らず Questions へ）

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D05-ユースケース-シナリオカタログ.md` — ユースケース・シナリオ
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D11-画面-UX-操作意味仕様書.md` — 画面UX・操作仕様
- `knowledge/D12-権限-認可-職務分掌設計書.md` — 権限・認可・職務分掌

## 3) 作業ディレクトリ（このagent固有）
- task-slug: `screen-detail`
- `{WORK}`
  - `plan.md`（計画を書く場合に使用）
  - `screen-detail-work-status.md`（進捗：フォーマット固定）
  - `subissues.md`（分割時に使用。Sub Issue 用本文）

## 4) 実行フロー（必ずこの順）

### 4.1 Planner（最初に必ず / 大量生成はしない）
- 計画を書く場合は Skill `task-dag-planning` に従う。
1) `screen-list.md` から画面IDと画面名を抽出して画面数を確定  
2) 画面ごとに概算（X–Y分）と合計を見積（厳密不要）  
3) 1 セッションで終わらない量だと判断した場合は、独立して検証できる単位で `subissues.md` に分割してよい（形式は `.github/skills/_hve-plan-artifacts/hve-binding.md` §3）。
4) `{WORK}screen-detail-work-status.md` の `## Planner` にも記録

### 4.2 分割時の扱い

> subissues.md は `validate-subissues` が形式を検査し、違反があると Cloud の Sub-Issue 作成が止まる。以下の順序に従う。

#### 4.2.1 必須手順（順序固定・省略禁止）

1. **template を read してコピー元とする**（再発明禁止）:
   - `.github/skills/_hve-plan-artifacts/subissues-template.md` を read
   - 各サブブロックは template の構造（`<!-- subissue -->` → `<!-- title: -->` → `<!-- custom_agent: -->` → `<!-- depends_on: -->` → `## Sub-N: ...`）を踏襲
2. **各 `<!-- subissue -->` 直下に HTML コメントメタを必ず記載**:
   - `<!-- title: <Markdown 見出しと一致するタイトル> -->`（必須・空値/`REPLACE_ME` 禁止）
   - `<!-- custom_agent: Arch-UI-Detail -->`（必須）
   - `<!-- depends_on: <1-indexed カンマ区切り、なければ空> -->`（任意。前方参照禁止）
3. **ファイル保存後、validate-subissues を必ず execute で実行し PASS を確認**（PASS まで完了報告禁止）:
   - Windows: `pwsh -NoProfile -File .github/scripts/powershell/validate-subissues.ps1 -Path {WORK}subissues.md`
   - bash:    `bash .github/scripts/bash/validate-subissues.sh --path {WORK}subissues.md`
4. PASS が出ない場合は **その場で修正して再実行**し、完了報告に validator 実行結果（`✅ PASS` ログ）を添付する。

> Markdown 見出し（`## Sub-N: ...`）のみで `<!-- title: -->` を省略すると `validate-subissues` が失敗する。Markdown 見出しと `<!-- title: -->` の両方が必要である。

#### 4.2.2 サブタスク分割方針

- 1サブあたりの目安: 3〜5画面。
- 各Subの本文（`## Sub-N:` 以降）には以下を必ず含める:
  - 対象画面ID一覧
  - 成果物（生成するファイル）
  - 手順（参照する入力 / 生成順 / 更新ルール）
  - 検証（最小）
  - Questions（あれば記載、無ければ None）
- その後終了（この run では docs を生成しない）

### 4.3 Execution
0) 入力を読み切り、画面一覧を確定  
   - 不足/矛盾が致命的なら、既定値を選び、理由・影響・後で確認すべき事項を1か所にまとめる。
   - 致命的でない不明点は各成果物に TODO として明記。

1) 付録を作成/更新（存在する場合のみ）
- `docs/screen/sample-data-appendix.md`
  - 先頭に `<!-- SAMPLE_DATA: REMOVE_WHEN_API_READY -->`
  - `src/data/sample-data.json` の全文を `json` コードブロックで掲載
  - 長大な場合は `Skill large-output-chunking` のルールに従い、**小チャンクで追記**して完成させる

2) 各画面の画面定義書を作成/更新
- 出力先:
  - `docs/screen/{screenId}-{screenNameSlug}-description.md`
- 命名:
  - `{screenId}` は screen-list のID
  - `{screenNameSlug}` は screen-list の名称をスラッグ化（小文字/空白は `-` / 英数と `-` のみ。ファイル名に不適な文字は `-` へ置換）
- 各ファイルは idempotent に更新（生成ブロックのみ更新）:
  - ブロック外の手書き内容は保持する

3) 進捗更新（追記のみ）
- `{WORK}screen-detail-work-status.md` に Done/Pending を更新（フォーマット固定）

### 4.3.1 業務 UI の視覚デザイン基準と除外するスタイル
業務 UI は、一貫性のある配置・文言・操作、読み取りやすい可読性、重要度が分かる情報の階層、十分なコントラストとアクセシビリティを優先して定義する。

除外するスタイル:
- 過度なグラデーション背景
- ネオン/グロー効果
- 装飾目的だけのアニメーション
- グラスモーフィズムの多用
- 意味のない絵文字アイコン
- 紫系グラデーションの既定テンプレート風配色

### 4.4 受入観点（完了条件の補足）

#### 4.4.1 位置付け

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

#### 4.4.2 ドメイン固有観点
- **機能完全性・要件達成度**：画面定義書（UX/A11y/セキュリティ/AC）が screen-list および参照ドキュメントと整合し、対応する実装に使用可能か
- **ユーザー視点・使いやすさ**：A11y/i18n/エラーメッセージが妥当で、ユーザーが操作・理解できるか
- **保守性・拡張性・堅牢性**：テンプレ構造が統一され、サンプルデータ/API接続/状態管理が明確で、将来の画面追加に対応可能か

#### 4.4.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。

## 5) 書き込み失敗（空ファイル化等）対策（このagent固有・必須）
- 1回の edit の目安: **最大200行 or 6–8KB**
- 各ファイル更新後に read して **空でない**ことを確認
- 空なら、より小さなチャンクで再試行（最大3回）
- `sample-data-appendix.md` は特に分割して追記する（巨大出力ルールを優先）

## 6) 進捗ファイルのフォーマット（固定 / 改変禁止）
以下をそのままの見出し順で保持する（追記・更新のみ、構造を変えない）:

## Planner
* Screen count: <n>
* Estimate total: <X–Y min>
* Split: <Yes/No>
* Split groups: <group summary>

## Done
* <画面-ID> <画面名>
* ...

## Pending
* <画面-ID> <画面名>
* ...

## Issues / Questions
* <最大3項目、無ければ None>

## 7) 画面定義書テンプレ（各画面ファイルに必須）
以下のテンプレートを各画面の定義書に使用する（内容は例示）。不明点は捏造せず、TODO/Questions に落とすこと。

```md
## 1) 目的と非目的
* 所属アプリケーション: APP-xx（`docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」を参照）
* 共通画面参照: PSC-XXX（`screen-catalog-APP-*.md` の `notes` 列に `common_ref: PSC-XXX` が記載されている場合のみ記載。未解決時は `PSC-XXX（未解決）`）
* 目的 / 想定ユーザー / 前提

## 2. 画面構成
* レイアウト概要
* コンポーネント一覧（入力/表示/操作）

## 3. ユーザーフロー / 状態
* 主要フロー
* 状態（初期/読込中/空/エラー/完了）

## 4. 入出力・データ
* 表示データ（出典: data-model / service-catalog）
* 入力項目（型/必須/制約）
* API連携予定（未確定は TODO として明示。捏造しない）

## 5. バリデーション & エラーメッセージ
* ルール
* 文言（日本語）

## 6. A11y / i18n
* キーボード操作
* フォーカス順
* aria / 読み上げ
* 色以外の表現

## 7. セキュリティ / プライバシー
* 取り扱うデータ分類（個人情報等）
* サニタイズ/制限
* 保存範囲（ローカル/送信有無）
* 注意: 参照元にない仕様は TODO/Questions に落とす

## 8. 非機能要件
* パフォーマンス/レスポンス目安（根拠が無ければ TODO）
* 監視やログ（必要時のみ、前提を明示）

## 9. 受け入れ基準（テスト可能）
* Given/When/Then 形式で 3〜7個

## 10. サンプルデータ（開発用・削除容易）
* 付録参照: `sample-data-appendix.md`
* この画面で使う抜粋（キーのみ）:
```json
{ "TODO": "この画面で利用するキーのみ抜粋（削除容易）" }
```
```
