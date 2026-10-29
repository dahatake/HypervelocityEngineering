[日本語](04-troubleshooting.md) | **English**

# S4 When Things Don't Work and Glossary

## When things don't work

| Symptom | What to do |
|---|---|
| The browser doesn't open | Paste the URL shown in the terminal (`http://127.0.0.1:…`) into the browser by hand. |
| `python` is not found | Install Python 3.9 or later, or try `py EABK-Studio/studio.py`. |
| "EABK data layer not found" | If Studio showed guidance at launch and exited, the target folder has none of `docs/requirements-definition.md`, `docs/catalog.md`, or `tests/system/ledger.json`. Specify the correct folder with `--repo`. If you have only installed EABK and have not yet created requirements, first create them with `/build`. |
| I can't tell which files are being read | Run `python EABK-Studio/studio.py --repo <repository> --check`. It shows which management data files were found / not found, the counts of requirements, acceptance criteria, catalog rows, ledger cases, and run history entries that could be parsed, and warnings, then exits (it does not launch). The exit code is 0 if the data layer exists and 1 if not. If you have moved file locations, check `management_files` in `scripts/ebak.config.json`. |
| Nothing shows on screen (count is 0) | If the `--check` count is 0, the column names in a table's header do not match the format in [08-data-reference.en.md](08-data-reference.en.md) (e.g., the feature table lacks the `要求ID` and `実装ファイル` columns). Align with EABK's [management data format](../03-requirements-format.en.md). |
| `preview-conflict` in Consistency maintenance | The catalog was updated by another means after Studio launched. Restart Studio and preview again. |
| The menu doesn't appear for a `?select=` link | Links with `select` are a display for capturing screenshots. Normally use `q`, as in `#/map2d?q=<requirement ID>`. |
| The screen is stale | It auto-updates within a few seconds. If that doesn't fix it, reload the browser. |
| 3D doesn't display / is slow | Enable hardware acceleration in your browser. If it is slow, reduce what is shown with "Layers." |
| APIs / tables are empty | The "APIs / events" and "Tables" tables in the catalog have no entries (this is not an error). |
| "Implementation" differs from reality | "Implementation" is what the catalog states. Ask EABK's agent to update the catalog. |
| Only some requirements appear | Requirements are read when written in the heading format `#### FR-001 Title`. For the format, see "Management data format" in the EABK core users-guide. |
| The port is in use | The next number is chosen automatically. You can also specify one, like `--port 9000`. |

## Glossary

| Term | Meaning |
|---|---|
| Data layer | The records EABK manages (requirements definition, catalog, System Test ledger, ID ledger, run history) |
| Goal (G-001) | What the business wants to do. Every requirement belongs to some goal |
| Requirement (FR / NFR) | FR is a functional requirement; NFR is a non-functional requirement such as performance or safety |
| Acceptance criterion (AC) | The condition under which a requirement can be said to be satisfied. Verification levels are system / integration / unit / manual |
| Decision state | Approved, AI proposal (awaiting approval), on hold, rejected, deprecated |
| Priority | MUST (required), SHOULD (desirable), MAY (optional) |
| BLOCKED | An acceptance criterion that cannot proceed, e.g., because of an unanswered question |
| Questionnaire (Q-) | Items that need to be decided, with options and recommendations |
| PARAM | Definition of a value such as a threshold or period |
| Entity | A "thing" a requirement handles (an application, an order, etc.). The unit of data |
| Shared component | A component used by multiple features |
| Component | A major structural unit of the app (the top-level folder of the source) |
| Catalog | A correspondence table of features, APIs, tables, and shared components with implementation files and tests |
| System Test ledger | The test cases corresponding to acceptance criteria, and their results |
