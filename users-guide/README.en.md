[日本語](README.md) | **English**

# EABK User Guide

EABK (Enterprise App Build Kit) and **EABK Studio** are a single application. This folder, `users-guide/`, is its one and only user guide. For the overview, installation, Quickstart, and terminology, read the top-level [README.en.md](../README.en.md) first.

| Part | Audience | Chapter labels | Location |
|---|---|---|---|
| Part 1 | **EABK core**: submit requests, advance runs, and operate the managed data and quality gates | 1–10 | Directly in this folder |
| Part 2 | **EABK Studio**: a local-only viewer for browsing the managed data (the data layer) through diagrams, tables, and search | S1–S8 | [studio/](studio/README.en.md) |

The two parts are connected by the same data layer (the requirements definition, the catalog, the System Test ledger, the ID ledger, and the run history). EABK writes it, and Studio reads it. To change requirements or the implementation, make the request with `/build`, not in Studio.

## Part 1: EABK core

| # | Document | When to read it |
|---|---|---|
| 1 | [How to write requests (/build and run_options)](01-writing-requests.en.md) | You want to know how to write good requests and answers, and about approval policies |
| 2 | [During and after a run](02-during-and-after-run.en.md) | You want to know how to check progress, resume, read the report, and merge |
| 3 | [Managed data formats](03-requirements-format.en.md) | You want to know the formats of the requirements definition, the catalog, the ID ledger, and the System Test ledger |
| 4 | [Settings and customization](04-customization.en.md) | You want to adjust build and test commands and gates, or use MCP servers and plugins (Work IQ, Azure, and so on) |
| 5 | [Scripts reference](05-scripts-reference.en.md) | You want to know how to use each command in `scripts/` |
| 6 | [Quality gates and checks](06-quality-gates.en.md) | You want to know the meaning of the hooks (G-1 to G-6) and verify checks (CHK-01 to 27) and how to fix them |
| 7 | [Troubleshooting](07-troubleshooting.en.md) | A run stopped, was rejected, or failed |
| 8 | [Adoption roadmap and KPIs](08-roadmap.en.md) | You want to know the steps from diagnosis to production operation and how to measure the effect |
| 9 | [Version upgrade procedure](09-versioning.en.md) | Bump the version (distribution source), or update an already-installed repository (users) |
| 10 | [Adopting an existing app](10-adopting-existing-apps.en.md) | Prepare the data layer from existing code and design documents through inventory → reverse-generated requirements (pending approval) → pinning current behavior. Research on the approach and verification of its fit |
| 11 | [Integration catalog](11-integration-catalog.en.md) | You want to record integrations with external systems (API, file, DB, event) in `docs/integrations.md` and learn how to add, change, retire, and check them (`verify.py --docs-only`) |

## Part 2: EABK Studio

For the index and the prerequisites for starting it, see [studio/README.en.md](studio/README.en.md).

| # | Document | When to read it |
|---|---|---|
| S1 | [Getting started](studio/01-first-steps.en.md) | You want to check the prerequisites, launch Studio, and spend your first 10 minutes |
| S2 | [Reading the screens](studio/02-screens.en.md) | You want to know what each screen (with real screenshots) tells you |
| S3 | [What to look at, and how](studio/03-tasks.en.md) | You want task-oriented procedures such as reporting, impact analysis, and checking items pending approval |
| S4 | [When things don't work / glossary](studio/04-troubleshooting.en.md) | Studio won't start or doesn't show up on screen. You want to look up a term |
| S5 | [For Product Managers](studio/05-product-manager.en.md) | You want to decide which goal to invest in next from progress, approvals, and unanswered questions |
| S6 | [For Architects](studio/06-architect.en.md) | You want to check dependencies, boundaries, placement, and missing layers |
| S7 | [For Software Engineers](studio/07-software-engineer.en.md) | You want to trace from a requirement to implementation files and tests |
| S8 | [Data reference](studio/08-data-reference.en.md) | You want to know which screen reads what from which file, and how it is computed |

## Reading order by role (for first-time users)

In every case, first read "Introduction", "Installation", and "Quickstart" in [README.en.md](../README.en.md).

| You are | Reading order |
|---|---|
| **Product Manager** | 1 (How to write requests) → 2 (During and after a run: reading the report, answering the question sheet, merging) → 8 (Adoption roadmap and KPIs) → [S5](studio/05-product-manager.en.md) (view progress in Studio) |
| **Architect** | 3 (Managed data formats) → 6 (Quality gates and checks) → 4 (Settings and customization) → 8 (Adoption roadmap) → [S6](studio/06-architect.en.md) (view design consistency in Studio) |
| **Software Engineer** | 4 (Settings: registering verification commands) → 5 (Scripts reference) → 7 (Troubleshooting) → 9 (Version upgrade) → 10 (Adopting an existing app) → [S7](studio/07-software-engineer.en.md) (trace implementation and tests in Studio) |

## Find by goal

| What you want to do | Where to read |
|---|---|
| Submit your first run | [Quickstart in README.en.md](../README.en.md#quickstart) → [1](01-writing-requests.en.md) |
| Check a run's result and decide whether to merge | [2](02-during-and-after-run.en.md). To see the state of requirements, catalog, and tests in diagrams, see [S3](studio/03-tasks.en.md) |
| Learn how to write the requirements definition and catalog | [3](03-requirements-format.en.md). For the formats Studio reads, see [S8](studio/08-data-reference.en.md) |
| Configure verification commands, models, and gates | [4](04-customization.en.md), [6](06-quality-gates.en.md) |
| A run stopped, was rejected, or failed | [7](07-troubleshooting.en.md). If Studio doesn't work, see [S4](studio/04-troubleshooting.en.md) |
| Adopt it in an existing app | [10](10-adopting-existing-apps.en.md); for phased adoption, see [8](08-roadmap.en.md) |
| Update the toolkit | [9](09-versioning.en.md) |
| View the data layer in diagrams and tables | [S1](studio/01-first-steps.en.md), [S2](studio/02-screens.en.md) |

## Links to README sections

| What you want to know | README section |
|---|---|
| The problem it solves and the overall architecture | [Overview](../README.en.md#overview) |
| Agent responsibilities and write permissions | [Agents and permissions](../README.en.md#agents-and-permissions) |
| The steps of a run (steps 0–6) | [The flow of a single run](../README.en.md#the-flow-of-one-run) |
| Installing, updating, and uninstalling | [Installation](../README.en.md#installation) |
| How to submit the first run and what to check | [Quickstart](../README.en.md#quickstart) |
| Overview and launch of EABK Studio | [EABK Studio](../README.en.md#eabk-studio-data-layer-viewer) |
| Terminology | [Glossary](../README.en.md#glossary) |

## Conventions used in this guide

- Chapter numbers are `1`–`10` in Part 1 and `S1`–`S8` in Part 2. Sections follow the chapter number, as in `4.4` and `S8.5.2`. Use these labels when referring to them from other guides.
- In the distribution source repository the folder is `users-guide/`. In a repository where you installed with `tools/install.py`, it is placed in `EABK-docs/` (the `users-guide/` of the target repository is not touched). Links within the guide are relative paths based on the distribution source's layout.
- Real screenshots are in `studio/images/`, their capture conditions are in [studio/screen-images.json](studio/screen-images.json), and recapturing is done with `studio/capture-screens.py`. Diagrams for EABK core are in `images/`.
- When you add or rename a file, update `MANAGED` in `tools/install.py` (and `OBSOLETE` for files to be removed) accordingly ([9](09-versioning.en.md)).
