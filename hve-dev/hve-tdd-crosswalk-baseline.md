# HVE TDD ベースライン突合サマリー

- 生成日時 (UTC): `2026-08-27T16:51:58Z`
- 対象: `hve` アプリケーションのみ（HVE CLI / GUI / Cloud Agent Orchestrator 関連）。他アプリ開発には適用しない。
- 捏造防止: テスト仕様欄は docstring / 関数名 / assert・raises・Pester `Should` / shell `pass` ラベル等、実在コードから機械抽出した。

## 生成物

- `hve-dev/hve-test-inventory.csv` — 既存テストコードの全関数/ケース棚卸し。
- `hve-dev/hve-feature-inventory.csv` — 要求定義 ID と実コード Workflow/Step の機能一覧。
- `hve-dev/hve-surface-inventory.csv` — HVE 対象の実装シンボルと実行面の一覧。
- `hve-dev/hve-tdd-crosswalk-baseline.md` — 要求定義・テストマッピング・生成inventoryの突合サマリー。
- `hve-dev/hve-tdd-change-policy.md` — 今後の hve 限定 TDD 運用ルール。

## 対象範囲

- 含める: `hve/tests/`, `hve/gui/tests/`, `.github/scripts/*/tests/`, `.github/scripts/tests/test_validate_skill_routing.py`, `mdq/tests/`, `cq/tests/`, `mdq/gui/tests/`。
- 含めない: テスト fixture (`.github/scripts/tests/fixtures/` 等) と、HVE/MDQ 支援ツールに該当しない生成物・仮想環境・キャッシュ。

## テスト棚卸し件数

- 抽出行数: **14491**
- 対象ファイル数: **698**

| 分類 | ファイル数 | 行数 |
|---|---:|---:|
| core-python | 399 | 9977 |
| cq-support-python | 38 | 696 |
| github-script-powershell | 5 | 83 |
| github-script-python | 5 | 85 |
| github-script-shell | 8 | 112 |
| gui-python | 205 | 3125 |
| markdown-query-gui-support-python | 8 | 75 |
| mdq-support-python | 30 | 338 |

| 種別 | 行数 |
|---|---:|
| fixture | 291 |
| helper | 2846 |
| parse-error | 1 |
| pester-it | 92 |
| python-file | 7 |
| script | 1 |
| setup-teardown | 134 |
| shell-case | 36 |
| shell-helper | 5 |
| test | 11078 |

## 機能一覧件数

- 抽出行数: **497**

| 種別 | 行数 |
|---|---:|
| C | 4 |
| FR | 304 |
| GATE | 5 |
| NFR | 32 |
| UC | 8 |
| WORKFLOW | 13 |
| WORKFLOW_STEP | 131 |

## 要求定義 ↔ 既存マッピング文書の突合

- `hve-dev/requirement-definition.md` 側 ID 数（FR/NFR/GATE/C/UC）: **353**
- `hve-dev/requirement-test-mapping.md` 側 ID 数: **354**
- 要求定義にあるがマッピング見出しが未確認の ID: **27**
- マッピングにあるが要求定義の抽出対象に無い ID: **4**
- 要求定義上で廃止/削除表記を含む ID: **7**

### 要求定義にあるがマッピング見出しが未確認

- `FR-WF-AAS-03`
- `FR-WF-ADFDV-01`
- `FR-WF-ADFDV-02`
- `FR-WF-ADI-02`
- `FR-WF-ADI-03`
- `FR-WF-ADI-04`
- `FR-WF-ADI-05`
- `FR-WF-ADI-06`
- `FR-WF-ADI-07`
- `FR-WF-ADI-08`
- `FR-WF-ADI-09`
- `FR-WF-ADI-10`
- `FR-WF-ADI-11`
- `FR-WF-ADI-12`
- `FR-WF-ADI-13`
- `FR-WF-ADI-14`
- `FR-WF-ADI-15`
- `FR-WF-ADI-16`
- `FR-WF-ADI-17`
- `FR-WF-ADI-18`
- `FR-WF-CONF-01`
- `FR-WF-CONF-02`
- `FR-WF-CONF-03`
- `FR-WF-CONF-04`
- `FR-WF-CONF-05`
- `FR-WF-CONF-06`
- `NFR-SEC-ADI-02`

### マッピングにあるが要求定義の抽出対象に無い ID

- `FR-RTO`
- `FR-WF-CONF`
- `G-CAP`
- `NFR-RTO`

### 廃止/削除表記を含む ID

- `NFR-COMP-01`
- `NFR-CONC-01`
- `NFR-OBS-04`
- `NFR-PERF-04`
- `NFR-REL-01`
- `NFR-REL-02`
- `UC-05`

## 注意

- 本ファイルは突合作業のベースラインであり、最終判断は `hve-test-inventory.csv` と `hve-feature-inventory.csv` の行単位確認で行う。
- `spec_source=function-name-and-code-evidence` は、人手で自然文仕様へ清書する前の機械抽出表現である。
- pytest の実 collection は optional dependency / importorskip の状態により、ソース上の test 関数一覧より少なくなる場合がある。CSV は実行可否ではなくソース棚卸しを正とする。
