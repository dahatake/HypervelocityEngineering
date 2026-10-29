[日本語](README.md) | **English**

# EABK Studio User Guide (Part 2)

This folder is Part 2 of the [EABK User Guide](../README.en.md) (EABK itself is chapters 1–10 in Part 1; the chapters in this part are S1–S8). EABK Studio is an app that runs only on your own computer and lets you browse the "record of requirements, catalog, and tests" managed by EABK (the data layer) through **diagrams, tables, and search**. Even if you can't read code, you can see "what we decided to build," "how far it has been built," and "where each component, piece of data, and API lives."

![EABK Studio header](images/header.png)

## Read by your role

| You are | Read first | Launch | First screen |
|---|---|---|---|
| Product Manager (decides what to invest in) | [05-product-manager.en.md](05-product-manager.en.md) | `python EABK-Studio/studio.py --role pm` | Dashboard |
| Architect (checks design consistency and boundaries) | [06-architect.en.md](06-architect.en.md) | `python EABK-Studio/studio.py --role architect` | 2D map |
| Software Engineer (looks for where implementation and tests are) | [07-software-engineer.en.md](07-software-engineer.en.md) | `python EABK-Studio/studio.py --role swe` | Tables |

You can also switch roles at any time with the `Product Manager`, `Architect`, and `Software Engineer` buttons at the top right of the screen.

## Reading order (S1 → S2 → by role → S3 → S8 → S4)

| Chapter | File | Contents |
|---|---|---|
| S1 | [01-first-steps.en.md](01-first-steps.en.md) | How to launch, your first 10 minutes |
| S2 | [02-screens.en.md](02-screens.en.md) | What each screen tells you (with real screenshots) |
| S5–S7 | Role-specific guides (table above) | 15-minute tutorial, recommended links, what you can decide |
| S3 | [03-tasks.en.md](03-tasks.en.md) | A how-to collection: "In this situation, how do I look at it?" |
| S8 | [08-data-reference.en.md](08-data-reference.en.md) | Which screen reads what from which file, and how it calculates |
| S4 | [04-troubleshooting.en.md](04-troubleshooting.en.md) | When things don't work (`--check`) and glossary |

This guide lives in `users-guide/studio/` in the distribution source, and in `EABK-docs/studio/` in a repository where EABK was installed with `tools/install.py`. Technical specifications are in [EABK-Studio/README.md](../../EABK-Studio/README.md). The images are examples made by reading the data of the repository that built the tool itself (capture conditions are in [screen-images.json](screen-images.json); re-capture with `capture-screens.py`).

## Things to know first

- **Normal browsing is read-only**. As the one exception, only when a user reviews the diff and runs "Consistency maintenance" does Studio align the catalog's titles and decision states with the requirements source of truth. If it fails, the original content is restored.
- **Nothing is sent outside**. Communication stays inside your own computer (127.0.0.1). Source code is not opened.
- **It stays up to date automatically**. When a data-layer file is updated, the screen reloads within a few seconds.
- With `JA | EN` at the top right of the screen, you can switch the screen's language between Japanese and English (requirement text and the like remain as written).
