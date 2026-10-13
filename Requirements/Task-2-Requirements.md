## Task 2 — Requirements Gathering

Project:Brick Buster — ZEIT2105 Assignment 2  
Status:Final — approved by the team  
Prepared:13 October 2026   
Author:Sazmi

## Purpose and actor

Brick Buster helps a LEGO collector manage complete owned sets, query available pieces, and check whether the collection can build a selected target set. The application will use Python, a graphical interface, and a local SQLite database populated from Rebrickable CSV files. The primary actor is the LEGO collector, who also performs local data setup.

## Prioritised functional requirements

## Must requirements are compulsory functionality. Should requirements are the selected additions and remain within implementation scope. Could and Won’t requirements are excluded.

| ID | Requirement | Priority | Scope | Use case |
|---|---|---|---|---|
| FR01 | Import the necessary Rebrickable CSV data into SQLite. | Must | Implement | UC01 |
| FR02 | Search sets by set number or name and optionally filter by theme and year. | Should | Implement | UC02 |
| FR03 | Add a complete owned set and record a positive whole-number copy quantity. | Must | Implement | UC03 |
| FR04 | View owned sets and their copy quantities. | Should | Implement | UC04 |
| FR05 | Update a set’s owned copy quantity. | Should | Implement | UC05 |
| FR06 | Remove a set entry from the collection. | Should | Implement | UC06 |
| FR07 | Query the total available quantity of a selected part and colour across all owned copies. | Must | Implement | UC07 |
| FR08 | Check whether sufficient matching parts, colours and complete minifigures are available to build one selected target set. | Must | Implement | UC08 |
| FR09 | Show missing parts and minifigures with identifiers, names, colours where applicable, and required, available and missing quantities. | Should | Implement | UC09 |
| FR10 | Find all sets buildable from the collection. | Could | Exclude | — |
| FR11 | Export missing items to CSV. | Could | Exclude | — |
| FR12 | Purchase missing items or integrate with shopping services. | Won’t | Exclude | — |

## Quality requirements

| ID | Requirement | Verification |
|---|---|---|
| NFR01 | Collection changes persist after restarting the application. | Add, update and remove entries as well as restart and verify the saved collection. |
| NFR02 | Invalid copy quantities are rejected without changing stored collection data. | Enter zero, negative, fractional and nonnumeric quantities. |
| NFR03 | The GUI uses consistent navigation and gives clear success, empty-result and error messages. | Walk through each use case and inspect its feedback. |
| NFR04 | Collection queries and build checks work offline after successful data import. | Disconnect the network and perform those operations. |
| NFR05 | Missing or invalid source data produces a clear error rather than a misleading build result. | Attempt import/checks with missing or invalid required data. |

## Business rules and scope

- All sets in the supplied collection are complete. Repeated booklets represent additional owned copies.
- A set’s contribution is multiplied by its owned copy quantity. Multiple booklets belonging to one copy must not be counted again during collection entry.
- Parts match exactly by part number and colour. Substitutions are excluded.
- Minifigures match exactly by `fig_num` and are counted as complete figures. Their component parts are not also added to the loose-part pool.
- Spare parts are excluded. Pieces from assembled sets are available for reuse, which may require dismantling those sets.
- One target copy is checked at a time. Checks do not reserve or consume collection pieces.
- Missing quantity for each item is `max(required - available, 0)`. Buildability requires zero shortage for every required part and minifigure.
- Exactly one inventory version is used per set or minifigure; inventory versions must not be summed together.
- Sets represented through `inventory_sets` must have their required contents resolved without omission or double counting.
- User accounts, loose-piece editing, damaged/incomplete sets and simultaneous build planning are outside this version’s scope.

## Use case specifications

| ID | Use case | Preconditions | Main interaction and outcome | Alternative/error |
|---|---|---|---|---|
| UC01 | Import Rebrickable Data | Required CSV files are accessible. | Collector starts import, system validates and loads necessary data then reports completion. | Missing/invalid files: report failure, do not mark incomplete data ready for use. |
| UC02 | Search and Filter Sets | Catalogue imported. | Collector enters a number/name and optional theme/year filters, system displays matching sets for selection. | No matches: show an empty-result message and allow criteria changes. |
| UC03 | Add Owned Set | Catalogue imported and a set selected. | Collector enters copy quantity then system saves the owned set and confirms the result. For an existing entry, add the entered copies to its quantity. | Invalid quantity: reject and retain the previous collection. |
| UC04 | View Collection | Application is open. | Collector opens the collection; system lists owned sets and quantities. | Empty collection: show a message and an Add Set action. |
| UC05 | Update Owned Quantity | An owned entry exists. | Collector selects an entry and enters its replacement quantity and the system saves the change. | Invalid quantity: reject, use Remove Owned Set to delete the entry. |
| UC06 | Remove Owned Set | An owned entry exists. | Collector selects an entry and confirms removal, system deletes it and refreshes the collection. | Cancellation leaves the entry unchanged. |
| UC07 | Query Owned Piece Quantity | Catalogue and inventories imported. | Collector selects a part and color then the system totals matching non-spare parts across owned copies and displays the quantity. | None owned: display zero. Missing inventory data: display an error. |
| UC08 | Check Target Set Buildability | Target selected required inventory data available. | Collector starts the check and the system compares required parts and minifigures with available quantities and displays buildable/not buildable. | Shortages: UC09 extends this use case. Missing data: report that the check cannot be completed. |
| UC09 | View Missing Pieces Report | UC08 identifies at least one shortage. | System displays all missing parts and complete minifigures, including required, available, and missing quantities. | If no shortage exists, this extension is not triggered. |

## Acceptance criteria

1. Adding two copies of a set contributes twice its inventory quantities.
2. A requirement for five red copies of a part is not satisfied by five blue copies.
3. With five required and three available, the report shows a shortage of two.
4. Sufficient parts but a missing required minifigure produces “not buildable” and a minifigure shortage.
5. An empty collection returns zero owned pieces and reports all required target items as missing.
6. Updating/removing a collection entry changes subsequent totals and remains saved after restart.
7. A search by set number finds the intended set; name searches and theme/year filters narrow the results.

Use case diagram

![Brick Buster use case diagram](Task-2-Use-Cases.svg)
