[日本語](task.md) | **English**

# Add role-based permissions to the document store

## Purpose

The repository already has a small library, `docstore`, that stores documents.
Now that multiple users use it, we want to restrict operations according to the user's role.

## Requirements

- Roles can be assigned to users. There are three roles: `viewer`, `editor`, and `admin`.
- A `viewer` can only read and list documents.
- An `editor` can create and update in addition to the `viewer` operations.
- An `admin` can perform all operations. Only an `admin` can delete and assign roles.
- An operation without permission is rejected without modifying any document.
- **Legacy calls that do not specify a user behave exactly as before.** Do not modify the existing tests; they must keep passing.

## Public interface (fixed)

Extend the existing `docstore` package (`DocumentStore` and its exceptions). Do not change existing names or behavior.

### Exception to add (importable from `docstore`)

- `PermissionDeniedError(DocstoreError)`: lacking permission, or a user with no role assigned.

### Calls to add or extend on `DocumentStore`

| Call | Behavior |
|---|---|
| `set_role(user, role, actor=None)` | Assign a role to `user` (overwriting allowed). If `actor` is `None`, no restriction. If `actor` is specified, raise `PermissionDeniedError` unless that user is an `admin`. If `role` is not one of the three, raise `ValueError`. |
| `get_role(user) -> str \| None` | The assigned role. `None` if none. |
| `create(doc_id, content, user=None)` | `user=None` is as before. When specified, `editor` or higher is required. |
| `read(doc_id, user=None)` | When specified, `viewer` or higher is required. |
| `update(doc_id, content, user=None)` | When specified, `editor` or higher is required. |
| `delete(doc_id, user=None)` | When specified, `admin` is required. |
| `list_ids(user=None)` | When specified, `viewer` or higher is required. |

A user with no assigned role gets `PermissionDeniedError` for every operation.
The permission check is performed before checking whether the document exists (do not reveal to an unauthorized user whether a document exists).
