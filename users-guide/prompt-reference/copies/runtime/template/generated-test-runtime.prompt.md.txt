## 生成テストの実行環境

- Unit / 実装コード向け TDD RED / TDD GREEN はローカル端末 / CI で実行可能にする。
- 外部サービスを使う Integration / Post-deploy / E2E は、構成済みサービスを前提にしてよいが、接続先・認証・base URL は環境変数またはテスト設定ファイルで注入する。
- 必須設定が未設定の場合は環境ブロッカーとして扱い、未実行のまま PASS / GREEN 扱いしない。
- 接続文字列・アカウントキー・SAS・Function Key・Bearer token 等の秘密情報をコード、README、ログにハードコードしない。