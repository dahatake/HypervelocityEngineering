# HVE TDD ベースライン突合サマリー

- 生成日時 (UTC): `2026-08-06T21:41:36Z`
- 対象: `hve` アプリケーションのみ（HVE CLI / GUI / Cloud Agent Orchestrator 関連）。他アプリ開発には適用しない。
- 捏造防止: テスト仕様欄は docstring / 関数名 / assert・raises・Pester `Should` / shell `pass` ラベル等、実在コードから機械抽出した。

## 生成物

- `hve-dev/hve-test-inventory.csv` — 既存テストコードの全関数/ケース棚卸し。
- `hve-dev/hve-feature-inventory.csv` — 要求定義 ID と実コード Workflow/Step の機能一覧。
- `hve-dev/hve-tdd-change-policy.md` — 今後の hve 限定 TDD 運用ルール。

## 対象範囲

- 含める: `hve/tests/`, `hve/gui/tests/`, `.github/scripts/*/tests/`, `.github/scripts/tests/test_validate_skill_routing.py`, `mdq/tests/`, `cq/tests/`, `mdq/gui/tests/`。
- 含めない: テスト fixture (`.github/scripts/tests/fixtures/` 等) と、HVE/MDQ 支援ツールに該当しない生成物・仮想環境・キャッシュ。

## テスト棚卸し件数

- 抽出行数: **10500**
- 対象ファイル数: **521**

| 分類 | ファイル数 | 行数 |
|---|---:|---:|
| core-python | 300 | 7676 |
| cq-support-python | 32 | 603 |
| github-script-powershell | 5 | 76 |
| github-script-python | 3 | 58 |
| github-script-shell | 7 | 94 |
| gui-python | 138 | 1629 |
| markdown-query-gui-support-python | 6 | 40 |
| mdq-support-python | 30 | 324 |

| 種別 | 行数 |
|---|---:|
| fixture | 188 |
| helper | 1973 |
| pester-it | 85 |
| python-file | 8 |
| script | 1 |
| setup-teardown | 114 |
| shell-case | 36 |
| shell-helper | 5 |
| test | 8090 |

## 機能一覧件数

- 抽出行数: **323**

| 種別 | 行数 |
|---|---:|
| C | 4 |
| FR | 158 |
| GATE | 5 |
| NFR | 30 |
| UC | 6 |
| WORKFLOW | 12 |
| WORKFLOW_STEP | 108 |

## 要求定義 ↔ 既存マッピング文書の突合

- `hve-dev/requirement-definition.md` 側 ID 数（FR/NFR/GATE/C/UC）: **203**
- `hve-dev/requirement-test-mapping.md` 側 ID 数: **223**
- 要求定義にあるがマッピング見出しが未確認の ID: **2**
- マッピングにあるが要求定義の抽出対象に無い ID: **2**
- 要求定義上で廃止/削除表記を含む ID: **7**

### 要求定義にあるがマッピング見出しが未確認

- `FR-WF-ADFDV-01`
- `FR-WF-ADFDV-02`

### マッピングにあるが要求定義の抽出対象に無い ID

- `FR-RTO`
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
