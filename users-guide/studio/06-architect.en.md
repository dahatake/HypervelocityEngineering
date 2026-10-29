[日本語](06-architect.md) | **English**

# S6 Guide for Architects

This guide shows you how to verify the **connections, boundaries, and placement** between requirements and implementation from a design perspective. It takes about 15 minutes.

Click `🏗️ Architect` at the top right of the screen to open the 2D map. Launching with `--role architect` also opens this screen first.

## S6.1 Screens to view and the data they read

| Screen | What the Architect looks at | Data read (details in [08](08-data-reference.en.md)) |
|---|---|---|
| 2D / 3D map | Dependencies of goal → requirement → data, components, APIs, tables → files → tests. Isolation and concentration | Requirements definition, catalog, ledger |
| Diagrams | Boundary (context), state transitions, data relationships, components | Tables in the requirements definition, catalog paths |
| Placement | Which requirements and data are implemented in which components | Requirements, catalog paths |
| Placement (runtime) | What Studio reads, what it writes, and what it sends outside | Files read, external integrations |
| Source mapping | How densely files map to requirements | Catalog paths (code is not read) |
| Structure | The gap between current and ideal for the 7 data layers | All data layers |
| Consistency | Gaps in requirement → AC → test → catalog → implementation | Requirements, ledger, catalog |

## S6.2 15-minute tutorial

1. **Launch** (1 minute).
   ```powershell
   python EABK-Studio/studio.py --role architect
   ```
2. **Get an overview** (2 minutes). The 2D map runs from left to right: "goal → requirement → data, shared components, APIs, tables → source files → test cases." Zoom with the wheel and pan by dragging. Double-click or use `Bird's-eye view` to return to the whole view.

   ![2D map](images/map2d.png)

   With `Layers` you can add acceptance criteria, parameters, and questions. Setting the color switch to `Implementation status` immediately shows requirements with no implementation files (red).
3. **See the impact range of one requirement** (2 minutes). Click a requirement's dot. Relations up to two hops away (data, components, files, tests) are highlighted, and details appear on the right. This gives you a sense of "where a change would ripple." Press `Esc` to clear.
4. **View in 3D** (1 minute). In `3D map`, the same relationships appear as layers. Use `Side` to check how the layers stack, and `Top` to check how the placement spreads.
5. **Check the boundaries** (2 minutes). In `Diagrams` → `Context diagram`, check the users (personas) and external integrations (method, source of truth). Next, in `State transition diagram`, check the states and transitions of each entity.

   ![State transition diagram](images/states.png)
6. **Check where things are placed** (2 minutes). Open `Placement`. The number at the intersection of a row (goal, boundary, kind) and a column (component) is how many of that row's requirements have an implementation in that component. Look for concentration in particular columns, and for a single requirement scattered across many components.

   ![Placement](images/placement.png)

   Selecting a cell shows a list of requirements and files. With `Data × Component`, you can also check where each entity is placed.
7. **Check how Studio itself behaves** (1 minute). Open `#/placement?kind=runtime`. It lists the files read, the direction of reading, where it writes (none), and external transmission (the definition, if the requirements definition has an external integration). You can use this for a security check before adoption.

   ![Placement (runtime)](images/runtime.png)
8. **Check for missing layers** (3 minutes). Open `#/consistency` and see, for each requirement, whether all five of requirement, AC, test, catalog, and implementation files are present. Then, in `#/structure`, read the "current state, ideal, difference, applied rule, judgment reason, and basis" of the 7 data layers. The kinds of difference are: valid, missing, orphaned, reference mismatch, duplicate, and surplus.

   ![Structure](images/structure.png)
9. **Jump to the basis location** (1 minute). Use the `Basis` (file:line) on a judgment row, or `↗ VS Code` in the detail panel, to open the relevant line in the requirements definition or catalog. Request design fixes from rd-author via `/build`.

## S6.3 Recommended links

| Purpose | Link |
|---|---|
| Overall dependencies | `#/map2d` |
| Around a specific requirement | `#/map2d?q=<requirement ID>` |
| 3D overview | `#/map3d` |
| Boundary (context diagram) | `#/diagrams?kind=ctx` |
| State transitions | `#/diagrams?kind=states` |
| Data relationships | `#/diagrams?kind=entities`; ER diagram with basis: `#/diagrams?kind=er` |
| Component structure | `#/diagrams?kind=components` |
| Requirement × Component | `#/placement?tab=biz` |
| Entity × Component | `#/placement?tab=data` |
| Placement of components, APIs, and tables | `#/placement?tab=items` |
| Where Studio reads and writes | `#/placement?kind=runtime` |
| Missing layers | `#/consistency`, `#/structure` |
| Tables of components, APIs, and tables | `#/tables?tab=parts`, `#/tables?tab=apis` |

## S6.4 What an Architect can decide

| Decision | Screen to base it on | Next action |
|---|---|---|
| Impact range of a change | Two-hop highlighting in 2D / 3D, implementation files and components in the detail panel | Include the affected requirements and tests in the `scope` of the request |
| Where responsibilities belong | Placement heatmap, component diagram | If one responsibility is scattered, request extraction into a shared component |
| Boundaries and the source of truth for data | Context diagram, table of external integrations (method, direction, source of truth) | Request that integrations with an empty source of truth be filled in the requirements definition |
| Validity of the state model | State transition diagram (states with no terminal state, isolated states) | Request a fix to the state table |
| Design gaps | Consistency (one layer missing), structure (missing, orphaned, reference mismatch) | Split requests between rd-author (requirements, catalog) and implementer (implementation) |
| Safety of adoption | Placement (runtime), [S8.9 and S8.10 in Studio 8](08-data-reference.en.md) | Explain the scope of reading, writing, and sending to the security team |

## S6.5 Notes when reading

- The position (coordinates) of a dot on the map has no meaning. What matters is whether it is connected by a line, and which column or layer it is in.
- A component is determined by the first one or two levels of the path written in the catalog ([S8.5.2](08-data-reference.en.md)). It is not necessarily an actual build unit.
- The basis for a relationship is only what is **written** in the requirements and catalog. For relationships in the ER diagram, when there is no `関係` (relationship) description, it does not guess and shows "relationship information is insufficient."
- Source code is not read. Actual code dependencies (such as imports) cannot be determined with this tool.

Next, proceed to [07-software-engineer.en.md](07-software-engineer.en.md) or [08-data-reference.en.md](08-data-reference.en.md).
