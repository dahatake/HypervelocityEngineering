[日本語](11-integration-catalog.md) | **English**

# 11. Integration catalog (`docs/integrations.md`)

This is a data-layer file that records, one item per integration, the app's integrations with external apps and data through APIs, files, DBs, events, and so on (FR-1035 to FR-1037). It is **optional**. Only apps with external integrations create it. If the file does not exist, checks, Studio, and cleanup work as before, and no error or warning is raised.

## 11.1 What you receive at installation

- `python tools/install.py` creates the template `docs/integrations.md` (an explanation of the format and an empty index table) **only if it does not exist yet**. An existing catalog in the target is not overwritten, and its content does not change on update (rerun or `--force`).
- The checks are built into the toolkit's `scripts/rdcheck.py` (CHK-28) and `scripts/next-id.py` (numbering of `INT`), and are updated by the same procedure as existing distributions (rerun). This chapter is also distributed to `EABK-docs/`. The behavior of `--no-ci` (do not install the workflow) is unchanged.
- The file name can be changed with `management_files.integrations` in `scripts/ebak.config.json` (default `docs/integrations.md`).

## 11.2 Format

Place an index table (ID, name, counterpart, direction, status, related requirements) at the top, followed by one entry per integration in the following form.

```text
#### INT-001 Order API
- Counterpart: Partner A's order system
- Direction: Inbound
- Method: REST (HTTPS)
- Data classification: Transaction data (confidential)
- Personal information: Yes
- Authentication and authorization: OAuth 2.0 client credentials
- Secret storage location: Key Vault (write only the name)
- Responsibility boundary: Partner A is responsible up to sending; we are responsible for storage and processing after receipt
- Status: In operation
- Related requirements: FR-012
- Frequency and volume: TBD (Q-010)
- Availability / SLA: None
(Below that, also fill in rate limits, errors, retries, idempotency, contract, version, change notification, monitoring, data retention, fallback on failure, legal, and license, each with a value, "None", or TBD (Q-xxx))
```

(In the actual file, the field names and values are written in Japanese, as in the Japanese edition of this chapter.)

- **Fields that must have a value** (AC-208): counterpart, direction (inbound / outbound / bidirectional), method, data classification, personal information, authentication and authorization, responsibility boundary, status (under consideration / in operation / retired), and related requirements (FR-xxx, NFR-xxx-xxx).
- **Fields for the other aspects** must always be filled with one of: a value, `なし` (none), or `TBD（Q-xxx）` (an ID from the question sheet). The check reports missing fields.
- **Do not write credential values** (AC-209). There are no fields for tokens, passwords, keys, or connection strings. In "Authentication and authorization" write the name of the method, and in "Secret storage location" write only the name of the storage location. The check reports value-like strings as violations.

## 11.3 Procedure for adding, changing, and retiring

Adding, changing, and retiring are done **only by rd-author**, and changes are recorded in the change history of the requirements definition (do not rewrite them by hand).

1. **Add**: Assign `INT-xxx` with `python scripts/next-id.py INT` (with `--peek`, it is not recorded). Write the heading `#### INT-xxx <name>` and the fields, add one row to the index table, and write requirement IDs in "Related requirements". From the requirement's side, associate it by referencing `INT-xxx` in the body or acceptance criteria. For aspects whose value is undecided, use `TBD（Q-xxx）` and raise a Q in the question sheet.
2. **Change**: Fix the field values. Advance the status in the order under consideration → in operation → retired. It can be made "in operation" only when all related requirements are approved (otherwise a warning).
3. **Retire**: Set the status to "retired". IDs are not reused (using an ID that is deleted or skipped in the ID ledger is an error).

## 11.4 Checks (`python scripts/verify.py --docs-only`)

Violations are reported with ID and location, and it ends with exit 1. If there are no violations, it exits 0.

| Violation | Severity |
|---|---|
| Duplicate ID, malformed ID (not of the `INT-001` form) | error |
| Missing required field, missing field for any of the 16 aspects, empty field | error |
| Value not in the "value / none / TBD (Q-xxx)" form, TBD whose Q-ID is not in the question sheet | error |
| Direction or status value outside the definition | error |
| Related requirement ID not in the requirements definition, credential-like string or field | error |
| `INT-xxx` referenced by the requirements definition is not in the catalog (undefined reference) | error |
| Status is "in operation" but not all related requirements are approved; mismatch between the index table and the entries | warn |

`python scripts/rdcheck.py trace INT-xxx` lists the requirements and acceptance criteria that reference that integration.

## 11.5 When writing requirements for external integrations (16-aspect checklist)

For requests that include external integrations, rd-author and rd-auditor scan the 16 aspects in `.github/skills/requirement-definition/integration-requirements.md` (the questions to confirm, what to write in the requirement, examples of acceptance criteria, and design matters not to write in the requirement). Aspects whose value is undecided are routed to the question sheet (TBD Q-ID), and aspects touching personal information, authentication and authorization, or external exposure are excluded from blanket approval. Requirement templates (the basic form and examples of acceptance criteria with structured fields and verification levels) are in the same document.
