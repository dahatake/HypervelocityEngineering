[日本語](02-screens.md) | **English**

# S2 Reading the Screens

Switch screens with the navigation at the top (9 items). Point at any item and a one-line description of "what data you can browse" appears as a tooltip, and the same sentence appears at the top of the screen. On every screen, **the selected item and its related items are highlighted** (common to search, diagrams, and tables). The data and calculations each screen reads are in [08-data-reference.en.md](08-data-reference.en.md).

![Header (tabs, search, target repository, role switch, language)](images/header.png)

## Navigation overview (what data you see)

| Item | Data you can browse |
|---|---|
| ① Dashboard | Per-goal progress, metrics, history, and counts of unresolved items |
| ② Implementation status | For each approved requirement: not started, implementation registered, tests passed |
| ③ Map | A relationship graph for tracing the links goal → requirement → component / API / table → file → test (2D / 3D) |
| ④ Diagrams | Context, goal tree, state transition, data relationship, component, and implementation placement diagrams (2D / 3D) |
| ⑤ Entities | The kinds of business data, and the mapping of create / read / update / delete per use case |
| ⑥ External integrations | A list and details of integrations with external apps and data (list and detail views were added in FR-1042) |
| ⑦ Source mapping | The catalog's file paths, and their mapping to requirements, components, and tests |
| ⑧ Tables | The original rows of all records (sorting, CSV) |
| ⑨ Consistency maintenance | The operation that aligns the catalog's titles and decision states with the requirements source of truth (the only place where writing happens) |

### Kinds of management data and their primary place to browse

The "primary place to browse" is the item where you see that kind's meaning, relationships, and details; there is exactly 1 item per kind. ⑧ Tables is a secondary place to browse that cuts across all kinds as raw data rows for viewing, sorting, and CSV export, and is not counted as a primary place.

| Kind | Primary place | Secondary |
|---|---|---|
| Goal | Dashboard | Tables |
| Requirement | Implementation status | Tables |
| Acceptance criterion | Implementation status | Tables |
| Test case | Implementation status | Tables |
| Shared component | Diagrams (component diagram) | Tables |
| API | Diagrams (implementation placement diagram) | Tables |
| Table | Diagrams (data relationship diagram) | Tables |
| File | Source mapping | Tables |
| PARAM | Map | Tables |
| Question | Dashboard | Tables |
| Term | Entities | Tables |
| Persona | Diagrams (context diagram) | Tables |
| Entity | Entities | Tables |
| External integration | External integrations | Tables |
| Decision record | Dashboard | Tables |
| Audit finding | Dashboard | Tables |
| Source | Map | Tables |
| Run history | Dashboard | Tables |

The old URLs `#/map2d`, `#/map3d`, and `#/placement` remain as aliases and redirect to the Map (2D / 3D) and Diagrams (implementation placement diagram).

## Switching between 2D / 3D
The Map and the 6 kinds of diagram (context diagram, goal tree, state transition diagram, data relationship diagram, component diagram, implementation placement diagram) have a 2D / 3D switch icon at the top right (bottom right for the Map). The icons are anime-style "flat" and "solid" figures with the words "2D" and "3D" attached. Either way, the same content comes from the same management data. When you switch, your selection, filters, diagram kind, and search text are kept. You can also switch with the keyboard (Tab → Enter) and with `> 2D` in the search box, and the icon animation stops when the OS reduced-motion setting is on. In environments where 3D can't be rendered, 2D is shown along with the reason and a table with the same content.

## Real screen examples

The following are real screens captured through Playwright verification, reading the management data of the same commit.
Capture conditions and SHA-256 are recorded in [screen-images.json](screen-images.json). The screen IDs (`map2d`, `map3d`, `placement`) remain valid as aliases of the old URLs.

| Screen | Real screen |
|---|---|
| Dashboard | ![Dashboard](images/dashboard.png) |
| Map (2D) | ![Map (2D)](images/map2d.png) |
| Map (3D) | ![Map (3D)](images/map3d.png) |
| Diagrams | ![Diagrams](images/diagrams.png) |
| Diagrams' implementation placement diagram (formerly "Placement") | ![Diagrams' implementation placement diagram](images/placement.png) |
| Source mapping | ![Source mapping](images/source.png) |
| Tables | ![Tables](images/tables.png) |

## Dashboard
The counts of requirements, approvals, implementation registered, acceptance criteria, tests passed, unanswered questions, and BLOCKED. Decision states, priorities, progress per goal, implementation per requirement boundary (the files the requirements were split into), verification levels of acceptance criteria, System Test results, and run history. **Click a chart or number and the matching requirements are highlighted on the map.**

## Map (2D)
An overall diagram arranged from left to right in the order "goal → requirement → data / shared component / API / table → source file → test case."

| Operation | Result |
|---|---|
| Wheel / drag | Zoom / move |
| Point at a dot | Highlight directly connected items |
| Click a dot | Highlight up to 2 steps out, with details on the right |
| Double-click / "Bird's-eye view" | Survey the whole |
| "Tour" | The camera automatically circles goal by goal |
| "Layers" | Add display of acceptance criteria, parameters, questions, etc. |
| Color switch | Color requirements by kind / decision state / implementation status (red = not implemented) |

Click the minimap at the bottom left to jump to that location.

## Map (3D)
See the same relationships as 2D in layers, in three dimensions. Choose 3D with the switch icon, or open `#/map3d`. Drag to rotate, right-drag or Shift+drag to pan, and the wheel to zoom. When you select something, the camera moves in and light flows along related lines. "Side view" switches to the stacking of the layers, "Top view" to the spread of the layout, and "Auto-rotate" to a slow rotation when you do nothing.

## Diagrams
Diagrams commonly used in requirements definition, built solely from the content of the data layer. Every diagram can be shown in 2D or 3D (3D is a solid diagram of points and lines; rotate with drag or arrow keys, zoom with the wheel or + −).

| Diagram | What you can learn |
|---|---|
| Context diagram | The boundary between the system and its users (personas) and external integrations |
| Goal tree | The number of requirements per goal, and whether they are implemented (color) |
| State transition diagram | The states that targets such as applications and executions take, and their transitions |
| Data relationship diagram | How data (entities) handled together in requirements connect |
| Component diagram | The app's parts (components), the modules inside them, and the shared components, APIs, and tables placed there |
| Implementation placement diagram | In which layer's implementation assets (screen, API, data) a requirement is placed. Includes layer × component, data × component, where shared components, APIs, and tables are placed, and a view of the runtime environment (formerly "Placement") |

## Entities
`#/entities`. Rows are entities, and columns form a correspondence table of requirements and usage scenarios. In each cell, symbols (C, R, U, D) and words show whether that use case uses the entity to **create, read, update, or delete** (it doesn't rely on color alone). An association whose usage is not described is "Used (usage not described)," and an unrelated pair is blank. An entity not used by any use case is "Unused," and a requirement with no entity is "No entity." You can filter rows and columns, sort rows, save as CSV, and show as text, all operable with the keyboard. Selecting an entity's heading goes to its details (description, states and transition conditions, requirements that use it, usage scenarios, managing tables, components / APIs / shared components that use it, source locations), and from there you can go to the ER diagram or implementation placement diagram, and return to these details from an entity's detail panel in a diagram. The display switches with JA / EN.

### Semantic zoom (relationships and columns)
At the bottom of `#/entities`, and in the 2D map and 3D map (which open to it first when the model has relationships or columns, and can be switched to the conventional diagram with "Relationship graph (conventional)"), you can view entity relationships and columns at 3 levels of granularity depending on magnification. Magnification is 1 when the whole just fits.

| Magnification (default) | Granularity | Contents |
|---|---|---|
| 1 or more, less than 2 (PARAM-017) | Whole | Clusters (groups of entities connected by relationships) and counts. An entity with no relationships is a single-entity cluster. Selecting a cluster zooms into it |
| 2 or more, less than 8 (PARAM-018) | Medium | Entities and relationship lines. Kinds are distinguished by line style, mark, and word: foreign key (◆, solid line) / reference (◇, dashed line) / usage (▫, dotted line). Selecting an entity highlights what it relates to |
| 8 or more | Large | A list of columns (key, name, type, referenced target). Referenced columns can be followed with a line and "→". An entity without columns shows "Columns not described" |

Operation: wheel, pinch, buttons (+ − ⤢ and Whole / Medium / Large), keyboard (+ − to zoom, arrows to move, 0 for whole, 1 / 2 / 3 for granularity, n / p for next / previous entity, . / , for columns, Enter to go to the referenced target, Esc to clear). In 3D, rotate and tilt with ⟲ ⟳ ⤒ ⤓ (Q, E, R, F). Switching between 2D and 3D keeps your selection, magnification, and filters. "View as table (alternative representation)" shows clusters, relationships, and columns in a table. What doesn't fit on screen is omitted from rendering (this is indicated), and no data is lost.

## Reading the implementation placement diagram (formerly "Placement")
The "Implementation placement diagram" under Diagrams (`#/diagrams?kind=layers`) includes a table (heatmap) of "where in the app the business requirements were built" (`view=matrix`; formerly `#/placement`).

- **Business layer × component**: Choose rows from goal, boundary, or kind. The number is how many of that row's requirements have an implementation in that component.
- **Data × component**: Where a requirement's "target entity" (the data it handles) is implemented.
- **Where shared components, APIs, and tables are placed**: The component that holds each one's definition file.

Selecting a cell shows a list of requirements and files, and highlights them on the map too.

At `#/diagrams?kind=layers&view=runtime` (formerly `#/placement?kind=runtime`), you can check the positions of the PC, browser, Studio server, target repository,
management data, implementation files, and explicitly stated cloud / external boundaries, and the read, write, and external-send directions.

## Structure, consistency, and maintenance

These are pages opened by URL (`#/structure` and `#/consistency` do not appear in the top tabs).

- `#/structure`: Compares the entire data layer by current state, ideal, difference, applicable rules, judgment reasons, and evidence.

  ![Structure](images/structure.png)
- `#/consistency`: Traces requirement → AC → System Test → catalog → implementation file for each requirement ID.

  ![Consistency](images/consistency.png)
- `整合性保守 / Maintenance`: Previews catalog rows that differ from the requirements source of truth, and after confirmation updates only the title and decision state.

  ![Consistency maintenance](images/maintenance.png)

### Other real screens

| Screen | Real screen |
|---|---|
| Placement (runtime environment; `#/placement?kind=runtime`) | ![Placement (runtime environment)](images/runtime.png) |
| Tables' test cases (`#/tables?tab=cases`) | ![Test cases](images/cases.png) |
| State transition diagram (`#/diagrams?kind=states`) | ![State transition diagram](images/states.png) |

The data and calculations each screen reads are in [08-data-reference.en.md](08-data-reference.en.md), and role-specific usage is in [05](05-product-manager.en.md), [06](06-architect.en.md), and [07](07-software-engineer.en.md).

## Source mapping
A diagram (treemap) that shows the names of files written in the catalog by area. Area is the number of linked requirements; blue is implementation and green is tests. Select a file to see the requirements it satisfies, the components it uses, and its tests. **It does not read the contents of source code.**

## Tables
"Tables" is a screen that lists the original rows of management data by kind. Choose a kind from under 4 group headings: "Requirements" (goals, requirements, acceptance criteria, PARAM, questionnaire), "Design" (entities, shared components, APIs, tables, external integrations, terms, personas), "Evidence" (test cases, files, sources), and "Operations" (decision records, audit findings, run history). An ID written in a cell is a link to its details, and an ID not in the management data is shown as "Unresolved." You can sort by header, filter in the box above, show only rows related to what you selected on the map with "Only rows related to the selection," and export as CSV.

## Detail panel on the right
It appears when you select an item. For a requirement, you can see the text, acceptance criteria, decision state, priority, parent goal, data handled, parameters, implementation files, tests, and BLOCKED questions. The "VS Code" link opens the definition's location or the file in the editor. "View on the 2D / 3D map" moves you to that screen.
