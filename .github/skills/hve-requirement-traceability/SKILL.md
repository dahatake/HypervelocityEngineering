---
name: hve-requirement-traceability
description: >
  HVE application maintenance requirement traceability. USE FOR: HVE application maintenance, bugfix, requirement traceability. DO NOT USE FOR: generated app or non-HVE application changes. WHEN: HVE, mdq, cq, or hve-dev paths change.
metadata:
  origin: user
  version: 1.0.0
---
# hve-requirement-traceability

## 目的

HVE アプリケーション自体の保守で、関連する active 要件と実在テストだけを選択的に確認する。

## 適用範囲

- HVE アプリケーション自体の保守にだけ適用する。
- HVE が生成・支援する他アプリケーションには適用しない。

## Non-goals（このスキルの範囲外）

- HVE が生成・支援する他アプリケーションの要件検索は扱わない。
- HVE が生成・支援する他アプリケーションの成果物間の重複は扱わない。`app-scope-resolution` Skill と生成物側のカタログが担う。
- 要求定義書全文を常時読み込まない。
- 要件 ID、変更種別、テスト結果を推測しない。

## 編集前確認

1. `hve-dev/hve-feature-inventory.csv` で候補 ID を絞り込む。
2. `hve-dev/requirement-definition.md` で定義と source を確認する。
3. `hve-dev/requirement-test-mapping.md` で対応テストを確認する。
- `source=hve-dev/requirement-definition.md` かつ `active-or-described` だけを適用可能とする。
- 未知・競合・`deprecated-or-removed`・`partial-or-not-supported` の ID は現行要件として適用してはならない。
- 索引と要求定義の不整合を解消するまで実装へ進まない。
- 適用してよいのは規範要件（`FR-*` / `NFR-*` / `G-*` の定義行と、当該要件が明示的に参照する従属表・箇条書き・スキーマ）だけとする。逆抽出の表・構成・確認時点の記述は説明的基線、改訂履歴・解消済み TBD・`deprecated-or-removed` は履歴情報であり、現行要件として適用しない。
- 現行コードと規範要件が矛盾する場合、コードを正解として要件を上書きせず、バグ修正か仕様変更かを明示して解消する。仕様変更なら実装前に規範要件を改訂する。

## 面横断の再利用確認

HVE 対象パスへ新規の判定・生成・検証ロジックを追加する場合にだけ適用する（FR-MAINT-07）。

1. `hve-dev/hve-surface-inventory.csv` の `rule_tokens` 列を対象の規範リテラルで検索する。
2. 不足する場合に限り `behavior_summary` 列を検索する。
3. なお不足する場合に限り `symbol` 列を検索する。
- この順序は、名前や構文の類似だけでは識別子の異なる同一手続きへ到達できないために定める。
- シンボル名の不一致だけを根拠に既存実装が無いと判断してはならない。
- 2 面以上に同一ルールの判定実装がある場合は新規実装を追加せず、単一実装へ寄せる。
- ヒット 0 件の場合に限り新規実装を許可し、どの実行面を単一実装とするかをタスク完了報告へ記録する。
- 索引が生成元と一致しない場合は stale として扱い、再生成するまで判断根拠に使わない。

## 新規要件 ID の bootstrap

1. 要求定義へ active 要件を追加または改訂する。
2. 要求テストマッピングへ受入テストを追加し、未実装なら `要追加` と記録する。
3. 同じ対象テストを作成して RED を確認する。
4. `hve-dev/hve-feature-inventory.csv` と `hve-dev/hve-test-inventory.csv` を再生成し、新規 ID・source・status・テストパスを照合する。
5. 実装する。
6. 同じ対象テストで GREEN を確認する。
7. 要求テストマッピングへ実結果を反映する。
- 索引照合では `source=hve-dev/requirement-definition.md`、`active-or-described`、テストパスを確認する。
- 新規 ID は要求定義書の定義行を一次情報とする。
- 新規 ID は同一変更セット内だけで暫定規範として扱う。
- 索引照合が完了するまで新規 ID を他の変更から利用しない。
- bootstrap 中の新規 ID を既存要件へ偽装しない。
- `hve-dev/hve-tdd-change-policy.md` または生成元 `hve-dev/generate_tdd_inventory.py` が §3.7 と矛盾する場合は §3.7 を正とし、同一変更で同期する。

## feature の TDD 順序

1. 要求定義へ active 要件を追加または改訂する。
2. 要求テストマッピングへ受入テストを追加し、未実装なら `要追加` と記録する。
3. 同じ対象テストを作成して RED を確認する。
4. `hve-dev/hve-feature-inventory.csv` と `hve-dev/hve-test-inventory.csv` を再生成し、新規 ID・source・status・テストパスを照合する。
5. 実装する。
6. 同じ対象テストで GREEN を確認する。
7. 要求テストマッピングへ実結果を反映する。
- feature では要件 ID・実在テストパス・RED / GREEN 証跡の N/A を認めない。
- bugfix / maintenance で N/A を使う場合は具体的理由と人間レビューを必須とする。
- `hve-dev/hve-tdd-change-policy.md` と生成元 `hve-dev/generate_tdd_inventory.py` は §3.7 と同一変更で同期する。
- 変更種別は `feature` / `bugfix` / `maintenance` の 3 値とする。観測できる能力・動作・公開インタフェース・設定・Workflow / Prompt / I/O 契約を追加または変更するなら `feature`、既存の規範要件または明示済み受入条件へ戻すだけなら `bugfix`、実行時の観測可能な挙動を変えないなら `maintenance` とする。分類を確定できない場合は `feature` とする。

## 関連要件の選択取得

- 検索キーは Issue 本文、対象パス、対象 symbol、失敗テスト、Workflow / Step ID から構成する。
- 要件 ID が既知の場合は検索せず、`hve-dev/hve-feature-inventory.csv` の当該行の `line` 列が指す定義行だけを読む。ID が未知の場合に限り以下の検索へ進む。
1. `python -m mdq search --q "<検索語>" --paths "hve-dev/requirement-definition.md" --top-k 5 --max-tokens 800` で初回取得する。
2. 初回結果が不足する場合に限り、親見出しを 1 段取得する。
3. 親見出しでも不足する場合に限り、隣接チャンクを 1 段取得する。
4. 隣接チャンクでも不足する場合に限り、関連章を取得する。
5. 0 件または矛盾時は検索語を変えて最大 2 回再試行し、解消しなければ理由を記録して確認を求める。
- 索引欠損・stale・検索 CLI 障害時は、特定済みの要件 ID または見出しだけを read / grep する。
- 本規則を汎用 Markdown 検索 fallback より優先する。
- 要求書全文へ自動 fallback しない。

## 全文取得の例外

- ユーザーの明示要求がある場合。
- 要求定義書自体を横断改訂する場合。
- 章単位でも解消できない複数章の矛盾がある場合。
- 上記以外では要求定義書全文を取得しない。
