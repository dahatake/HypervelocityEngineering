# 生成テストの実行環境契約

## 1.6) 生成テストの実行環境契約

HVE が生成するテストコードは、次の契約に従う。

- **単体テスト / 実装コード向け TDD RED / TDD GREEN はローカル実行可能を既定**とする。外部 I/O は Mock / Stub / Emulator / Testcontainers 等に置き換え、`dotnet test` / `pytest` / `npm test` / `jest` / `playwright` などの標準コマンドで実行できる構造にする。
- **外部サービスを検証対象にする integration / post-deploy / E2E テスト**は、対象サービスが正しく作成・構成済みであることを前提にしてよい。ただし接続先・認証・base URL は環境変数またはテスト設定ファイルから取得し、ローカル端末・CI・デプロイ先のいずれでも同じ設定キーで実行できるようにする。
- **未構成の外部サービスを成功扱いしない**。必須の URL / Endpoint / Resource 名 / 認証経路が未設定の場合は、fake GREEN にせず `Expected Outcome` / `Failure Analysis` に環境ブロッカーとして記録する。
- **秘密情報をテストコード・README・ログへハードコードしない**。接続文字列、アカウントキー、SAS、Function Key、Bearer token は環境変数または実行環境の secret store から渡す。
- ローカル専用の mock テストと、構成済み外部サービスを使う integration テストを混同しない。どちらのカテゴリかを README / `tdd-test-report.md` に明記する。

### 実行環境の分類

| 分類 | 既定の実行場所 | 外部サービス | 設定の渡し方 |
|---|---|---|---|
| Unit / Component | ローカル / CI | Mock / Stub / Emulator / Testcontainers に置換 | テストプロジェクト内の fixture / test settings |
| 実装コード向け TDD RED / GREEN | ローカル / CI | 原則テストダブル化。実装コード側は本番設定を外部化 | `dotnet test` / `pytest` / `npm test` 等で決定的に実行 |
| Integration | ローカル / CI / デプロイ先 | 構成済み外部サービスを利用可 | Endpoint / Resource 名 / 認証情報を環境変数またはテスト設定ファイルで注入 |
| Post-deploy / E2E | ローカル / CI / デプロイ先 | デプロイ済み URL / 実サービスを利用 | `*_BASE_URL` / `E2E_BASE_URL` 等の環境変数を優先 |

- 外部サービス未設定を PASS 扱いしない。必須設定が不足する場合は環境ブロッカーとして明示する。
- Secret / token / connection string / Function key はコード・README・ログへハードコードしない。
