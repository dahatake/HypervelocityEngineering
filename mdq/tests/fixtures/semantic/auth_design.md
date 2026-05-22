# Mixed-content Japanese design doc (fixture for semantic_paragraph eval)

## 認証フロー

OAuth 2.0 Authorization Code Flow を採用する。クライアントは認可サーバの
`/authorize` エンドポイントへリダイレクトし、ユーザー認証完了後に
`code` を受け取る。続いて `/token` エンドポイントへ `code` を送信し、
`access_token` と `refresh_token` を取得する。

`refresh_token` は HttpOnly Cookie に保存し、XSS から保護する。
`access_token` は JavaScript からアクセス可能なメモリ内変数で保持し、
画面遷移時に再取得する。

## エラーハンドリング

API レイヤで発生するエラーは Problem Details for HTTP APIs (RFC 7807) に
従う。`type` / `title` / `status` / `detail` / `instance` を JSON で返す。

クライアント側はステータスコード 401 を受信した場合、refresh_token を
用いて access_token を再取得する。再取得に失敗した場合はログイン画面へ
遷移させる。

## ロギング

構造化ロギングを採用し、JSON 1 行 1 レコードで出力する。
必須フィールドは `timestamp` / `level` / `trace_id` / `service` / `message`。

PII（個人識別情報）はログに含めない。`email` `phone` `address` 等は
ハッシュ化して保存する。
