[日本語](task.md) | **English**

# Saving and resuming draft applications

## Purpose

Even if a user stops partway through a long application form, they should be able to pick up where they left off later.
A retention period is set so that old drafts do not remain forever.

## Requirements

- In-progress input can be saved per user and per form.
- The saved content can be retrieved later to resume.
- A draft past its retention period cannot be resumed.
- A list of a user's drafts can be retrieved.
- Submitting removes the draft.
- Expired drafts can be deleted in bulk.
- The content is stored in a JSON file.

## Undecided points, and the defaults if not asked

The following points are not stated in the request. You may confirm them with the requester during the work.
If you do not confirm, apply the default on the right.

| Issue | Default |
|---|---|
| Retention period | 30 days, counted from the time of saving. It expires exactly when 30 days have elapsed. |
| Expiry on each save | Overwriting resets the expiry, counted from the save time. Resuming does not extend it. |
| Drafts for the same user and the same form | Only one. It is overwritten. |
| Content size | Reject the content if its JSON form exceeds 65536 bytes. |
| Handling of expired drafts | When resuming is attempted, treat it the same as nonexistent (`DraftNotFoundError`). |

## Public interface (fixed)

Python 3.11, pytest. No third-party runtime dependencies. The package name is `drafts`. Place it at the repository root.

### Exceptions (importable from `drafts`)

- `DraftError(Exception)`: base class.
- `DraftNotFoundError(DraftError)`: the draft does not exist or has expired.
- `DraftTooLargeError(DraftError)`: the content is too large.

### Class `drafts.DraftStore`

| Call | Behavior |
|---|---|
| `DraftStore(path, retention_days=30, clock=None)` | `path` is a JSON file (created if absent). `clock` is a function that takes no arguments and returns a `datetime.datetime` (without timezone). If `None`, the current time. |
| `save(user, form_id, data)` | Save `data` (a JSON-serializable `dict`) and reset the expiry. |
| `resume(user, form_id) -> dict` | Return the saved content. If absent or expired, raise `DraftNotFoundError`. |
| `list_drafts(user) -> list[str]` | Return the non-expired `form_id`s in ascending order. |
| `submit(user, form_id) -> dict` | Return the content and delete the draft. If absent or expired, raise `DraftNotFoundError`. |
| `purge_expired() -> int` | Delete expired drafts and return the number deleted. |

Each call writes to `path`. If you recreate a `DraftStore` with the same `path`, the content remains.
