[日本語](03-tasks.md) | **English**

# S3 "In This Situation, How Do I Look at It?"

## I want to report progress
1. Look at "Approved," "Implementation registered," and "Tests passed" on the Dashboard.
2. In "Implementation progress by goal," check which goals are behind.
3. On the 2D map, set the color to "Implementation status." Red dots are requirements whose implementation has not yet been registered.

> "Implementation registered" only means whether implementation files are written in the catalog. It does not guarantee that things work. Confirm behavior with "Tests passed" and the "Test cases" table.

## I want to know a feature's requirements and where it was built
1. Enter the feature name or a requirement ID (e.g., `FR-011`) in the search box and pick a result.
2. In the details on the right, look at the text, acceptance criteria, implementation files, and tests.
3. On the 2D or 3D map, follow the lines extending from it to see which component it is in.

## I want to confirm that a goal is truly being met
In the goal tree (Diagrams), look at the colors of each goal's requirements. Click a goal and its success metrics and measurement methods appear in the details. The verification levels of a requirement's acceptance criteria can be seen in "Verification levels of acceptance criteria" on the Dashboard.

## I want to find everything that's "stalled"
- Click "BLOCKED requirements" on the Dashboard → they are highlighted on the map.
- In the "Questionnaire" table, filter for questions whose status is "Unanswered." Once the answers are decided, the stalled requirements can move forward (ask EABK's agent to record the answers).
- In the "Audit findings" table, check the unresolved findings.

## I want to see what's awaiting approval (AI proposals)
In the "Requirements" table, filter "Decision state" to "AI proposal." This becomes the list of targets when you request decisions.

## I want to know where a change will have an impact
Select the requirement you want to change and switch the map to 3D to see the relationships. Requirements that handle the same data (entity) and requirements that use the same shared component are highlighted. In the implementation placement diagram under "Diagrams" (formerly "Placement"), "Data × Component" shows which component holds the implementations that handle that data.

## I want to know where the data, APIs, and components I use are
Look in order at the 3 tabs of the implementation placement diagram under "Diagrams" (the former "Placement" screen; `#/diagrams?kind=layers&view=matrix`). APIs and tables appear only if registered in the catalog (if not registered, "None").

## I want to explain to outside stakeholders
Explaining while showing the context diagram under "Diagrams" (who uses it and what it integrates with) and the state transition diagram (the states of the business flow) makes it easier to get across. The 3D map's "Tour" suits situations where you want to show the big picture.

## I want material to paste into a specification
In the table screens, "CSV" exports a list. Save diagrams with your browser's screenshot feature or similar.

## I want to share the same screen with someone
Send the URL from the address bar (only to people who have the same repository open). Examples: `#/map2d?select=FR-001`, `#/tables?tab=questions`, `#/diagrams?kind=states`.
