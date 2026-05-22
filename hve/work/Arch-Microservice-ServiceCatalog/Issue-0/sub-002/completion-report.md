<!-- validation-confirmed -->
<!-- parent-task: Arch-Microservice-ServiceCatalog/Issue-0/sub-002 -->

# Sub-002 完了報告: use-case前半とAPP-IDからサービススライスを抽出

## 目的

親 Step 6 (Arch-Microservice-ServiceCatalog) の SPLIT_REQUIRED 分割サブタスクとして、`use-case-catalog.md` の前半範囲（1〜430 行目目安、UC-01〜UC-11）から対応 UC と、`app-catalog.md` から関連 APP-ID 候補を抽出し、後続のサービススライス確定（Sub-003 以降）の入力を作成する。

## 変更点

- 新規作成: `work/Arch-Microservice-ServiceIdentify/Issue-0/sub-002/uc-app-slices-part1.md`
  - UC × APP-ID マッピング表（11 UC × 9 APP-ID、N:N、R/S 区別）
  - APP-ID 出現サマリー
  - 候補サービススライス 5 件の申し送り
  - TBD 集約（前半範囲では APP-ID マッピング側に該当なし）
- 新規作成: 本 completion-report.md

> 既存 `docs/` 配下のファイルは一切変更していない（読み取りのみ）。

## 影響範囲

- 後続 Sub-003（後半 UC-12〜UC-25 抽出）と Sub-004 以降（マッピング統合・サービスカタログ確定）への入力提供のみ。
- 既存ドキュメント・コード・CI への影響なし。

## 検証

- **入力範囲確認**: `use-case-catalog.md` 行 61〜421 が UC-01〜UC-11 を完全に内包することを `grep -n "^### UC-"` で確認（UC-11 の最終行 = 420、UC-12 開始 = 422）。受け入れ条件「1〜430 行目目安」を満たす。
- **抽出件数**: UC = 11 件、APP-ID = 9 種（APP-01/02/03/04/05/06/08/09/12）。期待件数（前半 UC = 11）と一致。
- **APP-ID 出典確認**: 全 11 件の R/S 判定を `app-catalog.md` §5 カバレッジ行列（行 99〜125）と突合。各 UC につき Primary（R）が必ず 1 個、Secondary（S）が 0〜3 個に揃っており、`N` を関連 APP として誤計上していないことを確認。
- **TBD 整合性**: 前半範囲で APP-ID 判定不能な UC は 0 件。`app-catalog.md` §5 に該当 UC 行が全て存在し、TBD 計上の必要なし。受け入れ条件 3 つ目は「該当なし」を §4 で明記する形で充足。
- **N:N 表記**: 表構成上、Primary 列と Secondary 列を分離しつつ、1 UC が複数 APP（最大 3 個: UC-01/05/10）、1 APP が複数 UC（例: APP-04 が 5 UC）に紐づく N:N 関係を表現していることを確認。
- **SPLIT_REQUIRED 再発防止**: 出力サイズは uc-app-slices-part1.md = 約 5.5KB、completion-report.md = 約 3KB。context_size=medium 想定範囲内に収まり、再分割は不要。

## 既知の制約

- 本スライスは前半 UC（UC-01〜UC-11）のみを対象とする。後半（UC-12〜UC-25）に登場する APP-07 / APP-10 / APP-11、および Secondary としての APP-04 拡張等は Sub-003 で別途抽出する必要がある。
- UC 内の未確定事項（CDP 方針、不正検知選定等）は `use-case-catalog.md` 側に残存。サービス境界の最終確定時に再参照が必要。
- app-catalog の R/S 判定をそのまま採用しているため、もし後段で R/S 自体に疑義が出た場合は app-catalog 側の更新が前提となる。

## 次にやるサブタスク

- Sub-003: `use-case-catalog.md` 後半（行 422〜857 目安、UC-12〜UC-25）から同形式のスライス（part2）を抽出。
- Sub-004 以降（想定）: part1 + part2 を統合し、サービスカタログ（service-catalog-matrix.md）の N:N マッピング・SoT・優先度行を完成させる。
- レビュー観点: UC-01⇄UC-25（同意・会員）、UC-05⇄UC-24（取引・不正検知）の APP-01 / APP-12 統合可否を後段で再評価。

## artifacts

- `work/Arch-Microservice-ServiceIdentify/Issue-0/sub-002/uc-app-slices-part1.md`
- `work/Arch-Microservice-ServiceCatalog/Issue-0/sub-002/completion-report.md`

## status / summary / next_actions

- **status**: done
- **summary**: UC-01〜UC-11 の N:N サービススライスを抽出し、APP-01/02/03/04/05/06/08/09/12 の関連 9 APP を Primary/Secondary 区別付きで整理。TBD は app-catalog §5 の網羅により 0 件。
- **next_actions**: Sub-003（後半 UC スライス抽出）の起動。
- **artifacts**: 上記 §artifacts 参照。
