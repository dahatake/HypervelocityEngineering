# hve-dev

`hve-dev` は、**`hve` アプリケーションを開発・保守するエンジニア向け**の資料置き場です。

ここに置く資料は、HVE CLI / GUI / Cloud Agent Orchestrator、および同梱の MDQ / markdown-query 支援ツールの開発判断に使います。HVE が生成・支援する **他アプリケーションの開発には適用しません**。

## 基本方針

- **対象は `hve` アプリケーションのみ**です。
- バグ修正を除く機能変更は、必ず実装前に要件とテスト仕様を更新します。
- 捏造は禁止です。未確認事項は `TBD` / `未確認` / `該当なし（理由: ...）` と明記します。
- テスト名、関数名、ファイルパス、要求 ID、検証結果は、実在するコード・文書・実行結果を根拠にします。
- オーバーエンジニアリングは禁止です。必要のない抽象化、未使用オプション、将来予測による拡張点の先回りは行いません。

## hve 機能変更時の必須順序

バグ修正を除く `hve` の機能変更では、次の順序を守ります。

1. **機能要件に追加**
   - `requirement-definition.md` または後続の正規要件文書へ追加します。
2. **テスト仕様に追加**
   - `requirement-test-mapping.md` または後続の正規テスト仕様・突合表へ追加します。
   - 既存テストで満たす場合は、該当テストを明記します。
   - 既存テストが無い場合は、要追加として明記します。
3. **RED を確認する**
   - 同じ対象テストを作成し、実装前に失敗することを確認します。
4. **索引を再生成して照合する**
   - `hve-feature-inventory.csv` と `hve-test-inventory.csv` を再生成し、新規 ID の source / status とテストパスを照合します。
5. **実装して GREEN を確認する**
   - 実装後、同じ対象テストが成功することを確認します。
6. **マッピングへ実結果を反映する**
   - `requirement-test-mapping.md` に GREEN 結果を反映します。

## 主なファイル

| ファイル | 位置付け |
|---|---|
| `requirement-definition.md` | HVE Cloud Agent Orchestrator / HVE CLI Orchestrator の要求定義・機能要件書。 |
| `requirement-test-mapping.md` | 要求定義と既存テストコードの対応表。 |
| `hve-tdd-change-policy.md` | 今後の `hve` 限定 TDD 運用ルール。 |
| `hve-test-inventory.csv` | 既存テストコードの棚卸し。分類、ファイル、行番号、関数/ケース名、仕様根拠、証跡を含みます。 |
| `hve-feature-inventory.csv` | 要求定義 ID と `hve/workflow_registry.py` 由来の Workflow / Step 機能一覧。 |
| `hve-tdd-crosswalk-baseline.md` | テスト棚卸し・機能一覧・既存マッピング文書の突合サマリー。 |
| `generate_tdd_inventory.py` | 上記の棚卸し CSV / サマリー / ポリシー文書を再生成するスクリプト。 |
| `hve-app-tools.md` | `hve` アプリケーション開発で使う補助ツール・運用メモ。 |
| `.github/skills/hve-requirement-traceability/SKILL.md` | HVE 保守時に active 要件と実在テストを選択取得する手順。 |

## 棚卸し成果物の注意点

- `hve-test-inventory.csv` は、実行可否ではなく **ソース上のテストコード棚卸し**を目的とします。
- pytest の実 collection は optional dependency / importorskip の状態により、ソース上の test 関数一覧より少なくなる場合があります。
- `spec_source=function-name-and-code-evidence` の行は、関数名とコード上の assert / raises / call 等から機械抽出した仕様表現です。正式な自然文仕様へ清書する場合は、人手で根拠行を確認してください。
- `hve-feature-inventory.csv` の Workflow / Step 行は `hve/workflow_registry.py` を根拠にしています。

## 棚卸しの再生成

`hve` の要求定義・テスト・Workflow 定義を更新した場合は、棚卸しを再生成します。

```powershell
.\.venv\Scripts\python.exe hve-dev\generate_tdd_inventory.py
```

最低限の検証:

```powershell
.\.venv\Scripts\python.exe -m py_compile hve-dev\generate_tdd_inventory.py
```

必要に応じて pytest collection と突合します。

```powershell
.\.venv\Scripts\python.exe -m pytest hve/tests hve/gui/tests mdq/tests mdq/gui/tests cq/tests .github/scripts/python/tests .github/scripts/tests/test_validate_skill_routing.py --collect-only -q
```

## 敵対的レビューの扱い

重要な開発基盤資料を更新した場合は、作成者目線ではなく敵対的レビュアー目線で確認します。

確認軸:

1. 目的適合性
2. 内容の妥当性
3. 整合性
4. 品質・運用性
5. 根拠性・不確実性管理

重大度の扱い:

- **Critical**: 全て修正必須。
- **Major**: 修正を検討し、修正しない場合は理由を残します。
- **Minor**: 任意修正。ただし容易に直せるものは直します。

## このディレクトリに置くべきもの

- `hve` アプリケーション自体の開発・保守に必要な要求定義、テスト仕様、突合表、運用ルール。
- `hve` の開発者が参照する棚卸し・検証レポート。
- `hve` 開発用の補助スクリプトや運用メモ。

## このディレクトリに置かないもの

- HVE が開発支援する他アプリケーション固有の要求定義・設計書・テスト仕様。
- 実行時生成物、仮想環境、キャッシュ、ログ。
- 根拠のない推測や未確認事項を確定表現にした資料。