# リポジトリオンボーディング 入出力例

> 本ファイルは `repo-onboarding-fast/SKILL.md` の入出力例セクションを収容する参照資料です。

---

## 入出力例

> ※ 以下は説明用の架空例です（本リポジトリ RoyaltyService2ndGen を対象とした例）

### 例1: 本リポジトリ（RoyaltyService2ndGen）を対象とした onboarding.md

**入力（トリガー条件）:**
- 新しい Custom Agent（例: Dev-Microservice-Azure-ServiceCoding-AzureFunctions）が本リポジトリに初めてアサインされた
- 作業ディレクトリ: Issue #101

**出力（`work/Dev-Microservice-Azure-ServiceCoding-AzureFunctions/Issue-101/onboarding.md`）:**

```markdown
# onboarding: RoyaltyService2ndGen リポジトリ

## 入口（主要パス）

| パス | 説明 |
|------|------|
| `docs/catalog/service-catalog.md` | 全サービス（SVC-01〜SVC-16）の概要・API 仕様・リソース一覧 |
| `docs/catalog/domain-analytics.md` | DDD ドメイン分析（BC・集約・ドメインイベント） |
| `AGENTS.md` | 全 Agent に適用される強制ルール（§1〜§10） |
| `.github/agents/` | Custom Agent 定義（30+個） |
| `.github/skills/` | Skill 定義（36+個） |
| `src/api/` | Azure Functions 実装（SVC 単位のサブディレクトリ） |
| `infra/azure/` | Azure リソース作成スクリプト（bash） |
| `test/api/` | API テストコード（pytest / .NET） |

## 境界（API/データ/責務）

| 境界 | 内容 |
|------|------|
| 公開 API | `src/api/{SVC-ID}-{service-name}/function_app.py` |
| データ SoT | Cosmos DB（各 SVC 固有コンテナ）+ Azure SQL（SVC-12 専用） |
| 認証・認可 | SVC-15 アクセス制御サービス（RBAC, Managed Identity） |

## 踏襲元（類似実装パス）

src/api/SVC-10-ai-cs-support-service/ ← エンドポイント定義の参考
infra/azure/create-azure-api-resources.sh ← リソース作成スクリプトの参考
.github/workflows/deploy-api-svc10.yml ← CI/CD workflow の参考

## 標準コマンド

```bash
# Python テスト実行
pytest test/api/ -x --tb=short

# .NET テスト実行（SVC 例）
dotnet test test/api/AICSSupportService.Tests/

# デプロイ → .github/workflows/deploy-api-svc{NN}.yml を参照
```

## 不明点と Spike 案

- [ ] 外部ロイヤルティ API の最新仕様 → docs/catalog/service-catalog.md#SVC-03 を確認
```

---

### 例2: エッジケース（既存 onboarding.md がある場合の更新）

**入力（トリガー条件）:**
- 同じ Issue の別 Sub が再度アサインされ、既存の `onboarding.md` が存在する

**出力（更新ルール）:**

1. `work/<AgentName>/Issue-<N>/onboarding.md` が既に存在することを確認
2. copilot-instructions.md §0（work/ 書き込みルール）に従い **既存ファイルを削除**
3. 最新の調査結果を含む内容で **新規作成**
4. 削除→作成後にファイルが空でないことを `read` で確認
