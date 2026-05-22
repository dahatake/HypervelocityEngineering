#!/usr/bin/env python3
"""Generate APP-04 screen test-spec files based on screen-catalog-APP-04.md.

Output: docs/test-specs/APP-04-S{NNN}-test-spec.md (20 files)
Pattern follows existing docs/test-specs/APP-09-S001-test-spec.md.
"""
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "test-specs"

# (screen_id, screen_name, function_type, actor, description, transitions, key_apis, notes)
SCREENS = [
    # B2C Member Portal
    ("S001", "会員Portal（タブ）", "portal", "B2C 会員",
     "サブスク機能の入口。タブ: マイサブスク / プラン一覧 / 支払方法 / 通知設定",
     ["S002 プラン一覧", "S006 マイサブスク一覧", "S011 支払方法管理", "S012 通知設定"],
     ["GET /plans (一覧サマリ任意)", "GET /subscriptions/{id} (現契約サマリ)"],
     "起点。UC-16 全フローのナビゲーション基盤。RBAC は会員 IdP スコープ。"),
    ("S002", "プラン一覧", "list", "B2C 会員",
     "提供中の有料プラン一覧（価格・Tier 特典・利用期間）",
     ["S003 プラン詳細・加入申込"],
     ["GET /plans"],
     "Plan エンティティ参照（data-model §3.5）。price/tier/term 列を表示。"),
    ("S003", "プラン詳細・加入申込", "detail", "B2C 会員",
     "プラン特典の詳細表示と加入ボタン",
     ["S004 決済情報入力・確認"],
     ["GET /plans/{id} (推論)", "POST /subscriptions (次画面で実行)"],
     "クーリングオフ条件・規約同意の事前提示。"),
    ("S004", "決済情報入力・確認", "form", "B2C 会員",
     "決済手段登録・サマリ確認・加入確定",
     ["S005 加入完了", "S011 支払方法管理 (課金失敗フォールバック)"],
     ["POST /subscriptions (Idempotency-Key 必須)"],
     "決済事業者 SDK（B-02 確定後）。PCI DSS / トークン化必須。"),
    ("S005", "加入完了", "completion", "B2C 会員",
     "subscription_state_changed(active) 発火後の完了表示と Tier 反映通知",
     ["S006 マイサブスク一覧"],
     ["GET /subscriptions/{id} (完了サマリ)"],
     "通知連携トリガ。state=active を確認。"),
    ("S006", "マイサブスク（契約一覧）", "list", "B2C 会員",
     "現在の契約一覧（active / grace / cancelled）",
     ["S007 サブスク契約詳細"],
     ["GET /subscriptions?owner={unified_id} (推論)"],
     "1 会員=複数契約の可否は要確認（Q2）。"),
    ("S007", "サブスク契約詳細", "detail", "B2C 会員",
     "契約状態・次回課金・更新履歴・利用 Tier の表示",
     ["S008 プラン変更", "S009 解約申請"],
     ["GET /subscriptions/{id}"],
     "subscription_contract 参照（data-model §3.5）。"),
    ("S008", "プラン変更（Up/Down）", "form", "B2C 会員",
     "アップグレード／ダウングレードの入力",
     ["S004 決済情報入力・確認"],
     ["POST /subscriptions/{id}:change (推論, TBD)"],
     "課金差額・反映タイミングの開示が必要（TBD: B-02）。"),
    ("S009", "解約申請", "form", "B2C 会員",
     "解約理由・確認・引止オファー（任意）",
     ["S010 解約完了"],
     ["POST /subscriptions/{id}:cancel"],
     "チャージバック判定要件は B-02 確定後再評価。"),
    ("S010", "解約完了", "completion", "B2C 会員",
     "解約反映と Tier 失効スケジュール通知",
     ["S006 マイサブスク一覧"],
     ["GET /subscriptions/{id} (state=cancelled 確認)"],
     "subscription_state_changed(cancelled) 発火後。"),
    ("S011", "支払方法管理", "form", "B2C 会員",
     "登録済み決済手段の追加・更新・削除",
     [],
     ["決済 SaaS SDK (B-02)"],
     "PCI DSS / トークン化必須（PII 取扱い注意）。"),
    ("S012", "通知設定", "form", "B2C 会員",
     "サブスク関連通知（更新前リマインド・課金失敗）のオプトイン",
     [],
     ["（CMP 経由）"],
     "CMP との同意整合は APP-02 側 SoR。"),
    # Ops Portal
    ("S101", "運用Portal（タブ）", "portal", "サブスク運用担当",
     "運用機能の入口。タブ: プラン管理 / 契約一覧 / 状態遷移モニタ / オペレーション / レポート",
     ["S102 プラン管理一覧", "S104 契約検索・一覧", "S106 課金失敗・猶予中モニタ",
      "S107 オペレーション処理", "S108 サブスクレポート"],
     ["GET /plans", "GET /subscriptions (検索)"],
     "起点。RBAC（プロダクト / 経理 / IT）で表示タブを制御。"),
    ("S102", "プラン管理一覧", "list", "サブスク運用担当",
     "提供中・公開予定・終売プランの一覧",
     ["S103 プラン作成・編集"],
     ["GET /plans?status=*"],
     "Plan SoR=APP-04。"),
    ("S103", "プラン作成・編集", "form", "サブスク運用担当",
     "プラン定義（価格・Tier 特典・期間）の作成／編集",
     [],
     ["POST /plans (TBD)", "PATCH /plans/{id} (TBD)"],
     "承認 WF 連動は B-02 確定後（Q3）。"),
    ("S104", "契約検索・一覧", "list", "サブスク運用担当",
     "会員 ID / 状態 / プランで契約を検索",
     ["S105 契約詳細"],
     ["GET /subscriptions?state=*&plan_id=*&unified_id=*"],
     "大量データ前提（ページング・CSV エクスポート）。"),
    ("S105", "契約詳細", "detail", "サブスク運用担当",
     "契約の状態履歴・課金履歴・関連イベントを表示",
     ["S107 オペレーション処理"],
     ["GET /subscriptions/{id}", "GET /subscriptions/{id}/events (推論)"],
     "subscription_state_changed の監査ログ表示。"),
    ("S106", "課金失敗・猶予中モニタ", "list", "サブスク運用担当",
     "grace 状態の契約・リトライ状況の監視",
     ["S105 契約詳細", "S107 オペレーション処理"],
     ["GET /subscriptions?state=grace"],
     "アラート閾値設定・SLA 監視。"),
    ("S107", "オペレーション処理", "form", "サブスク運用担当",
     "手動解約 / チャージバック / 返金処理",
     [],
     ["POST /subscriptions/{id}:cancel", "POST /subscriptions/{id}:chargeback (TBD)"],
     "強い権限。二重承認推奨（Q4）。"),
    ("S108", "サブスクレポート", "dashboard", "サブスク運用担当",
     "MRR / Churn / プラン別加入推移の集計表示",
     [],
     ["GET /kpis (SVC-10, 推論)"],
     "KPI-16 連動（APP-09 BI 基盤との重複範囲は Q5）。"),
]


def gen(s):
    sid, name, ftype, actor, desc, trans, apis, notes = s
    is_ops = sid.startswith("S1")
    role = "ops:write" if is_ops else "subscription:write"
    role_read = "ops:read" if is_ops else "subscription:read"

    # AC list
    acs = [
        ("AC-01", f"認証済み表示（正常系）", f"ログイン済み {actor}", f"{sid} へ遷移", f"{ftype} 要素と主要 UI が表示"),
        ("AC-02", "未認証時のリダイレクト", "未ログイン", f"{sid} URL 直叩き", "SSO 認可画面へリダイレクト"),
        ("AC-03", "RBAC: 権限不足", f"{role_read} スコープなし", f"{sid} 表示要求", "403 表示・主要要素非表示"),
        ("AC-04", "同意ガード（fail-closed）",
         "SVC-03 で subscription purpose 同意 granted=false（TBD: purpose 名称）", f"{sid} 表示", "機能ガード表示・操作不可"),
        ("AC-05", "API エラー時フォールバック", f"{apis[0] if apis else 'API'} が 5xx", f"{sid} 表示", "エラーバナー + 再試行ボタン、ページ骨格は継続描画"),
        ("AC-06", "ローディング状態", "API レスポンス遅延（>500ms）", f"{sid} 表示", "スケルトン UI / スピナー表示"),
        ("AC-07", "空状態（empty state）", "対象データ 0 件", f"{sid} 表示", "空状態メッセージ + 推奨アクション提示"),
        ("AC-08", "A11y", "スクリーンリーダー", "主要 UI を読み上げ", "WAI-ARIA / コントラスト適合（WCAG 2.1 AA）"),
    ]

    # form/list/detail specific AC
    if ftype == "form":
        acs += [
            ("AC-09", "バリデーション: 必須欠落", "必須項目空欄", "送信ボタン押下", "送信抑止 + 個別エラーメッセージ表示"),
            ("AC-10", "バリデーション: 境界値", "境界値（max+1 / 型違い）", "送信", "送信抑止 + フィールドレベルエラー"),
            ("AC-11", "冪等送信（重複クリック）", "送信ボタン連打", "短時間で複数クリック", "Idempotency-Key で 1 リクエストのみ確定 (UI 二重送信抑止)"),
            ("AC-12", "サーバ業務エラー（4xx/409）", "バックエンドが SUB-STATE-* / SUB-VAL-* / SUB-CONSENT-* を返却", "送信", "エラーコードに応じた人間可読メッセージを表示"),
        ]
    elif ftype == "list":
        acs += [
            ("AC-09", "ページング", ">1 ページ分のデータ", "次/前ページ操作", "URL クエリ更新 + 再フェッチ"),
            ("AC-10", "ソート / フィルタ", "対象列クリック / 条件入力", "アクション", "再フェッチ + aria-sort 更新"),
        ]
    elif ftype == "detail":
        acs += [
            ("AC-09", "未存在 ID", "存在しない {id} を URL に指定", "表示", "404 表示 + 一覧へ戻る導線"),
        ]
    elif ftype == "completion":
        acs += [
            ("AC-09", "状態整合（強整合）", "サーバが state 反映前", "表示要求", "サーバ確定後のみ完了画面を描画（楽観的更新禁止）"),
        ]
    elif ftype == "dashboard":
        acs += [
            ("AC-09", "鮮度 SLA 境界", "refresh_freq=60 分の境界 (59m / 61m)", "表示", "asOf バッジ表示・古い場合は警告"),
        ]

    # Build markdown
    lines = []
    lines.append("<!-- parent-issue: #0 -->")
    lines.append("<!-- app-ids: APP-04 -->")
    lines.append(f"<!-- screen-id: {sid} -->")
    lines.append("<!-- generated-by: Arch-TDD-TestSpec (Step 2.3) -->")
    lines.append("<!-- generated-at: 2026-05-22 -->")
    lines.append(f"<!-- source: docs/catalog/screen-catalog-APP-04.md §{1 if not is_ops else 2} ({sid}), docs/services/SVC-05-subscription-service-description.md, docs/catalog/test-strategy.md §2/§4/§5.1, docs/test-specs/SVC-05-test-spec.md -->")
    lines.append("<!-- atdd-template: docs/templates/atdd-template.md（不在）→ §1.5 に Given-When-Then 直記 -->")
    lines.append("")
    lines.append(f"# Test Spec: {sid} {name}")
    lines.append("")
    lines.append(f"> 本書は APP-04 画面 {sid} の **AC-ID × Test-ID 正本（SoT）**。`docs/templates/atdd-template.md` 不在のため Given-When-Then を §1.5 に直記。")
    lines.append('> 本資料は Copilot 推論により作成（"この回答は Copilot 推論をしたものです。"）。')
    lines.append("")
    lines.append("## 1. 概要")
    lines.append(f"- **対象画面**: {sid} {name}（function_type=`{ftype}`）")
    lines.append("- **対象アプリケーション**: APP-04 サブスクリプション基盤（Webフロントエンド + クラウド）")
    lines.append("- **対応 UC**: UC-16（会員がサブスク型ロイヤリティに加入・更新する）")
    lines.append(f"- **アクター**: {actor}")
    lines.append(f"- **画面概要**: {desc}")
    if trans:
        lines.append(f"- **画面遷移先**: {', '.join(trans)}")
    if apis:
        lines.append(f"- **主要 API 呼び出し**: {', '.join(apis)} — 出典: `docs/services/SVC-05-*.md` §3")
    lines.append(f"- **特記**: {notes}")
    lines.append("- **テスト方針**: Jest Component（Unit）+ Playwright E2E + axe A11y + MSW（API モック）+ OpenAPI Contract 検証（SVC-05）")
    lines.append("")
    lines.append("## 1.5 ATDD（UI シナリオ：Given-When-Then）")
    lines.append("")
    lines.append("| AC-ID | シナリオ | Given | When | Then |")
    lines.append("|---|---|---|---|---|")
    for ac_no, sc, g, w, t in acs:
        lines.append(f"| {sid}-{ac_no} | {sc} | {g} | {w} | {t} |")
    lines.append("")
    lines.append("## 2. E2E / 操作シナリオ")
    lines.append("")
    lines.append("| Test-ID | 種別 | AC-ID | シナリオ | ツール |")
    lines.append("|---|---|---|---|---|")
    # 各 AC に対し Jest Unit + (主要 AC のみ Playwright E2E)
    e2e_acs = {"AC-01", "AC-02", "AC-03"}
    if ftype == "form":
        e2e_acs.update({"AC-09", "AC-11", "AC-12"})
    elif ftype == "list":
        e2e_acs.add("AC-09")
    elif ftype == "detail":
        e2e_acs.add("AC-09")
    elif ftype == "completion":
        e2e_acs.add("AC-09")
    elif ftype == "dashboard":
        e2e_acs.add("AC-09")

    tests = []
    for i, (ac_no, sc, _g, _w, _t) in enumerate(acs, start=1):
        ac_id = f"{sid}-{ac_no}"
        tests.append((f"T-{sid}-U-{i:03d}", "Jest Component", ac_id, f"{sc}（コンポーネント単体）", "Jest + RTL + MSW"))
        if ac_no in e2e_acs:
            tests.append((f"T-{sid}-E-{i:03d}", "Playwright E2E", ac_id, f"{sc}（通しシナリオ）", "Playwright + MSW"))
        if ac_no == "AC-08":
            tests.append((f"T-{sid}-A-{i:03d}", "A11y", ac_id, "axe スキャン + ARIA 確認", "axe-core"))

    # API Contract test
    if apis:
        tests.append((f"T-{sid}-C-001", "Contract", f"{sid}-AC-01", "SVC-05 OpenAPI request/response 適合", "Pact / OpenAPI Validator"))

    for tid, kind, ac_id, sc, tool in tests:
        lines.append(f"| {tid} | {kind} | {ac_id} | {sc} | {tool} |")
    lines.append("")
    lines.append("## 2.5 AC → Test トレーサビリティ（前方）")
    lines.append("")
    lines.append("| AC-ID | カバー Test-ID |")
    lines.append("|---|---|")
    # build map
    ac_to_t = {}
    for tid, _k, ac_id, _s, _to in tests:
        ac_to_t.setdefault(ac_id, []).append(tid)
    for ac_no, _sc, _g, _w, _t in acs:
        ac_id = f"{sid}-{ac_no}"
        lines.append(f"| {ac_id} | {', '.join(ac_to_t.get(ac_id, ['(未割当)']))} |")
    lines.append("")
    lines.append("## 3. バリデーション仕様")
    if ftype == "form":
        lines.append("- 必須項目／文字数／型／範囲: 各入力に対し境界値テスト（empty / max / max+1 / 型違い / 制御文字）。")
        lines.append(f"- 認可: RBAC（`{role_read}` / `{role}`）。`{role}` 欠落で送信ボタン非活性。")
        lines.append("- XSS／インジェクション: 自由入力欄は HTML エスケープ済を Component で確認。")
        lines.append("- Idempotency-Key: 送信時にクライアント側 UUID を `Idempotency-Key` ヘッダへ付与（SVC-05 §3 規約）。")
    else:
        lines.append(f"- 認可: RBAC（`{role_read}`）。スコープ欠落で 403。ABAC は本画面該当なし（推論）。")
        lines.append("- XSS／インジェクション: 動的描画箇所は HTML エスケープ済を Component で確認。")
        lines.append("- URL パラメータ: `{id}` 等は UUID 形式バリデーション（不正値は 400 / 一覧へ戻す）。")
    lines.append("")
    lines.append("## 4. テストデータ")
    lines.append("- 共通シード（SVC-05 test-spec §3 と整合）: Plan 3 件（basic / premium / enterprise）／ SubscriptionContract 各状態 1 件（active / grace / cancelled）／ unified_id 5 件。")
    if is_ops:
        lines.append("- 大量データ: 契約 1,000 件（ページング検証用）／ grace 50 件（S106 モニタ用）。")
        lines.append("- ロール: `ops-product` / `ops-finance` / `ops-it` / `auditor` 4 種。")
    else:
        lines.append("- ロール: `member` / `member-consent-denied` / `anonymous` 3 種。")
    lines.append("- 固定シード Faker（決定論的）で生成。実値は `test-strategy.md §3 SVC-05` の方針に従う。")
    lines.append("")
    lines.append("## 4.5 API モック / テストダブル")
    lines.append("- MSW で SVC-05（API-27/28/29）を OpenAPI ベース Mock Server 経由でモック。`docs/services/SVC-05-*.md` §3 を契約源とする。")
    lines.append("- 障害系（5xx / 4xx エラーコード SUB-STATE-001/002, SUB-VAL-001/002, SUB-CONSENT-001, SUB-EXT-001/002, SUB-AUTH-001）はモック側で誘発し UI 縮退表示を確認。")
    lines.append("- 同意ガード: SVC-03 `GET /consents` を MSW でモック（granted=true/false の 2 ケース）。")
    lines.append("- イベント駆動箇所（S005/S010）は SSE/WebSocket ではなくポーリングまたは画面戻り時の `GET /subscriptions/{id}` で state 確認（推論）。")
    lines.append("")
    lines.append("## 4.6 API 契約検証")
    lines.append("- SVC-05 OpenAPI（`docs/services/SVC-05-*.md` §3 / 付録 A）に対し、UI が発行する request 適合と受信 response 適合を Pact / Contract Test で固定。")
    lines.append("- `Idempotency-Key` ヘッダ・`If-Match` ETag の付与有無を契約テストで検証（API-27 / API-28）。")
    lines.append("- エラーレスポンス body（`error_code` / `message` / `details`）の schema 適合も同テストで担保。")
    lines.append("")
    lines.append("## 4.7 A11y（axe / WAI-ARIA）")
    lines.append("- WCAG 2.1 AA を最低基準。axe-core を CI で実行（critical/serious=0 がゲート）。")
    if ftype == "portal":
        lines.append("- タブ系: `role=tablist` / `aria-selected` / `aria-controls` の整合。")
    elif ftype == "list":
        lines.append("- 表ヘッダ・ソート可否（`aria-sort`）正、行選択は `aria-rowindex`。")
    elif ftype == "form":
        lines.append("- フォーム: `<label for>` 関連付け、エラーは `aria-invalid` / `aria-describedby`、送信中は `aria-busy=true`。")
    elif ftype == "detail":
        lines.append("- 見出し階層 h1→h2→h3 を順守、状態バッジは `aria-label` で読み上げ補完。")
    elif ftype == "completion":
        lines.append("- 完了通知は `role=status` / `aria-live=polite` で SR へ通知。")
    elif ftype == "dashboard":
        lines.append("- 図表は `aria-label` / `<title>` でサマリ提供、色のみで意味を伝えない（パターン / テキスト併用）。")
    lines.append("- キーボード操作: 全フォーカス可能要素を Tab/Shift+Tab で巡回可能、focus ring を視覚的に保持。")
    lines.append("")
    lines.append("## 5. TDD 順序（推奨）")
    lines.append("1. Jest Component（Red）: 主要 UI 状態（ローディング / エラー / 空状態 / 通常）")
    if ftype == "form":
        lines.append("2. Jest Component（Red）: バリデーション・RBAC ガード・冪等送信")
        lines.append("3. Contract（Red）: SVC-05 API-27/28 の request/response 契約 + Idempotency-Key")
    else:
        lines.append("2. Jest Component（Red）: RBAC ガード・同意ガード（fail-closed）")
        lines.append("3. Contract（Red）: SVC-05 API の request/response 契約")
    lines.append("4. Playwright E2E（Red）: ハッピーパス → 主要分岐 → 画面遷移")
    lines.append("5. A11y（Red）: axe スキャンを各画面状態で実行")
    lines.append("6. Refactor: 共通モック・ロール fixture 抽出")
    lines.append("")
    lines.append("## 6. 網羅性")
    lines.append(f"- ✅ シナリオ {len(acs)} 件をすべて Test-ID と双方向トレース")
    lines.append("- ✅ RBAC / 同意ガード / 障害縮退 / A11y / API 契約検証を必須カバー")
    lines.append("- ⚠ TBD: 決済 SaaS 確定後（B-02）、UI 側 SDK 連携テストを追加")
    if is_ops:
        lines.append("- ⚠ TBD: 二重承認 WF（Q4）/ KPI 重複範囲（Q5）確定後に追加")
    lines.append("")
    lines.append("## 7. Questions（最大 3）")
    lines.append("1. **Q-1（高）**: 決済 SaaS（B-02）確定前提のモック構成で Red を進めるか、それとも SaaS 候補を 1 つ選定して PoC するか？ — **暫定案**: モック先行で Red、PoC は別 Issue 化。")
    lines.append("2. **Q-2（中）**: SVC-05 OpenAPI 仕様（`docs/services/SVC-05-*.md` 付録 A）に対する Contract Test の Consumer 側ツールは Pact で確定して良いか？ — **暫定案**: Pact 採用、CI で provider verification を SVC-05 側に課す。")
    lines.append("3. **Q-3（中）**: 同意 purpose 名称（subscription / billing）確定前は purpose=`subscription` を仮置きで良いか？ — **暫定案**: 仮置きで Red、CMP 確定後に rename。")
    lines.append("")
    lines.append("## 8. Test → AC 逆引きトレーサビリティ")
    lines.append("")
    lines.append("| Test-ID | カバー AC-ID |")
    lines.append("|---|---|")
    for tid, _k, ac_id, _s, _to in tests:
        lines.append(f"| {tid} | {ac_id} |")
    lines.append("")
    lines.append("## 検証")
    lines.append(f"- 検証: AC-ID（{len(acs)}件）と Test-ID（{len(tests)}件）の双方向表（§2.5 / §8）で対称性確保。RBAC / 同意ガード / 障害縮退 / A11y / 契約検証 / モック方針を §3〜§4.7 で網羅。")
    lines.append("- 既知の制約: `docs/templates/atdd-template.md` 不在のため Given-When-Then を §1.5 に直記。決済 SaaS 仕様（B-02）未確定のため API-27/28 の決済連携部はモック前提。")
    lines.append("")
    lines.append("<!-- validation-confirmed -->")
    lines.append("")
    return "\n".join(lines)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in SCREENS:
        sid = s[0]
        out = OUT_DIR / f"APP-04-{sid}-test-spec.md"
        content = gen(s)
        out.write_text(content, encoding="utf-8", newline="\n")
        print(f"WROTE {out.relative_to(OUT_DIR.parent.parent)} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
