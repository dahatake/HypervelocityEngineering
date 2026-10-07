# 文書ストアにロール別の権限を追加する

## 目的

リポジトリには、文書を保存する小さなライブラリ `docstore` がすでにある。
複数の利用者が使うようになったので、利用者のロールに応じて操作を制限したい。

## 要求

- 利用者にロールを割り当てられる。ロールは `viewer`、`editor`、`admin` の 3 種類。
- `viewer` は、文書の読み取りと一覧だけができる。
- `editor` は、`viewer` の操作に加えて、作成と更新ができる。
- `admin` は、すべての操作ができる。削除とロールの割り当ては `admin` だけができる。
- 権限のない操作は、文書を変更せずに拒否する。
- **利用者を指定しない従来の呼び出しは、これまでと同じように動く。** 既存のテストは変更せず、通り続けること。

## 公開インターフェース（固定）

既存の `docstore` パッケージ（`DocumentStore`、各例外）を拡張する。既存の名前と動作は変えない。

### 追加する例外（`docstore` から import できる）

- `PermissionDeniedError(DocstoreError)`：権限がない、またはロールが割り当てられていない利用者。

### `DocumentStore` に追加・拡張する呼び出し

| 呼び出し | 動作 |
|---|---|
| `set_role(user, role, actor=None)` | `user` にロールを割り当てる（上書き可）。`actor` が `None` なら制限なし。`actor` を指定したら、その利用者が `admin` でなければ `PermissionDeniedError`。`role` が 3 種類以外なら `ValueError`。 |
| `get_role(user) -> str \| None` | 割り当て済みのロール。なければ `None`。 |
| `create(doc_id, content, user=None)` | `user=None` は従来どおり。指定時は `editor` 以上が必要。 |
| `read(doc_id, user=None)` | 指定時は `viewer` 以上が必要。 |
| `update(doc_id, content, user=None)` | 指定時は `editor` 以上が必要。 |
| `delete(doc_id, user=None)` | 指定時は `admin` が必要。 |
| `list_ids(user=None)` | 指定時は `viewer` 以上が必要。 |

ロールが未割り当ての利用者は、すべての操作で `PermissionDeniedError`。
権限の確認は、文書の存在の確認より先に行う（権限のない利用者に、文書があるかどうかを教えない）。
