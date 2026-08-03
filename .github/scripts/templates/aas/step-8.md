{root_ref}
## 目的
ユースケース文書とペルソナカタログを根拠に、ペルソナ別の共通画面骨格を抽出し、`docs/catalog/persona-screen-catalog.md` を作成する。
本ステップは APP-ID 横断の単一の真実源（SoT）として、複数 APP-ID で同一ペルソナが共通利用する画面（ダッシュボード・通知一覧・プロフィール等）の重複定義を防ぐ。APP-ID 単位の画面詳細は AAD-WEB（`docs/catalog/screen-catalog-APP-*.md`）に残す。

## 抽出観点
- ペルソナ毎に、複数 APP-ID で共通して利用される画面骨格を抽出する（1 ペルソナ × 複数 APP-ID で同一目的の画面が現れるパターン）
- 1 APP-ID 専用の画面は本カタログには含めない（AAD-WEB の per-APP 画面カタログに委譲）
- 各共通画面に対して、利用ペルソナ（複数可）と関連 APP-ID（N:N）を記載する
- **判定基準**: 同一ペルソナ・同一目的の画面候補が、入力上で 2 つ以上の APP-ID に明示的に紐づく場合のみ共通画面として採用する。根拠が不明な場合は共通画面に含めず、`候補/TBD` として別表に記録する（推測で共通化しない）
- **共通画面ID 採番ルール**: 各共通画面に `persona_screen_id` を `PSC-001` 形式で安定採番する（PSC = Persona Screen Catalog）。下流 AAD-WEB（Arch-UI-List / Arch-UI-Detail）からこの ID で参照される
- 不明な項目は推測せず `TBD` または `不明（要確認）` と明記する

## 入力
- `docs/catalog/persona-catalog.md`（Step.9 で生成、必須）
- `docs/catalog/app-catalog.md`（アプリケーション一覧、必須）
- `docs/catalog/domain-analytics.md`（補助）
- `docs/catalog/service-catalog.md`（補助）

## 出力
- `docs/catalog/persona-screen-catalog.md`

{existing_artifact_policy}

## Custom Agent
`Arch-UI-PersonaScreenList` を使用

## 依存
- Step.9（ペルソナカタログ）が `aas:done` であること

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` のアプリケーション一覧（APP-ID）を参照し、各共通画面に「関連APP」（N:N）を記載すること。APP-ID 単位の画面詳細は記載しない（AAD-WEB へ委譲）。

## 完了条件
- `docs/catalog/persona-screen-catalog.md` が作成されている
- 各共通画面に `persona_screen_id`（PSC-XXX 形式）・`persona_id`（PRS-XXX）・`shared_by_apps`（関連 APP-ID、N:N）が記載されている
- 1 APP-ID 専用画面が本カタログに含まれていない、または `候補/TBD` 表に除外理由付きで記録されている
{completion_instruction}{additional_section}
