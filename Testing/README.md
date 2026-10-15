# Brick Buster testing

The assignment requires working CSV import, adding owned sets, piece quantities
and target buildability. This suite also covers the selected FR01-FR09 and
NFR01-NFR05 requirements, plus the implemented image and list/grid features.
The PDF does not prescribe a test framework or a coverage percentage.

## Install and run

Use Python 3.10 or later with Tkinter installed. Run these commands from the project root, with `src`
and `Testing` beside each other. On systems that use `python3`, substitute that
name for `python`.

```sh
python -m pip install Pillow
python -m unittest discover -s Testing -p "test_*.py" -v
python Testing/gui_smoke.py
```

The first test command runs 38 automated tests. The second runs five GUI tests
and requires Tkinter and a graphical desktop. It briefly opens test windows.
The GUI command is separate so terminal-only environments can run the backend
and image tests. A failed or unavailable GUI run is not a GUI pass.

The tests use temporary databases and clearly labelled synthetic catalogues.
Synthetic identifiers, names, quantities and image responses are test fixtures,
not claims about real LEGO sets or your owned collection. The image downloader
is tested with simulated responses; the suite needs no live image server.

## Files

| File | Purpose |
|---|---|
| `test_brick_buster.py` | 29 import, collection, calculation, search and failure/rollback tests; also provides the shared tiny CSV fixture. |
| `test_image_support.py` | Nine image metadata, migration, exact-colour lookup, cache and image-failure tests. |
| `gui_smoke.py` | Five desktop tests for screens, dialogs, cancellation/confirmation, build reports, list/grid selection, paging, thumbnails and placeholders. |
| `README.md` | Commands, requirements coverage, observed results and remaining manual checks. |

Keep all three Python files together in `Testing`. The GUI tests import the
fixture from `test_brick_buster.py`. The runner is Python's built-in `unittest`.

## Requirements coverage

| Requirement | Automated evidence |
|---|---|
| FR01: CSV import | Counts/readiness/FKs; plain and individually zipped CSVs; missing/duplicate headers and files; corrupt ZIPs; bad widths, values, keys, owners and cycles. |
| NFR05: invalid data | Failed first import stays unready; failed reimports restore the entire catalogue, ownership and generation; owned sets cannot disappear silently. |
| FR02: set search/filters | Number/name, case/whitespace, combined theme/year, parent themes including children, unrelated themes, no matches, literal wildcard input and result limit. |
| FR03-FR06: collection | Add, accumulate copies, list, replace quantity, remove, invalid values/unknown sets, dialog cancellation and removal confirmation. |
| NFR01-NFR02: persistence/input | Add, update and remove checked across database restart; invalid changes leave stored data unchanged. |
| FR07: piece quantity | Multiple copies and sets, exact colour/part, latest inventory only, excluded spares, complete minifigures, nested quantities and zero/invalid queries. |
| FR08: buildability | Buildable/not buildable, wrong colour, missing minifigure, empty collection, missing/empty inventory, nested targets, surplus and repeated non-consuming checks. |
| FR09: missing report | Exact item type, identifier, name, colour, required/available/missing values; surplus omitted; stale catalogue results rejected. |
| NFR03: GUI feedback/navigation | Real Tk widgets, callbacks, Back context, disabled pre-import actions, valid/invalid quantity dialogs and build report flow. Visual clarity also needs the manual checks below. |
| NFR04: offline operation | Backend calls with TCP connection creation blocked; cached images tested with simulated network failure; GUI fallback tested with a failed image response. Real desktop offline operation is checked below. |
| Image/list/grid additions | Optional image columns, enrichment rollback/preservation, exact-colour images, legacy migration, thumbnail caching/failure, card selection, view switching, 12-item page boundary and empty results. |

Parent-theme filters intentionally include subthemes. The earlier test expected
the opposite and failed on the reviewed GitHub version. The replacement checks
inclusion of child themes and exclusion of unrelated themes.

For corrupt ZIPs, validation can raise Python's `BadZipFile` before the importer
wraps an error as `DataError`. The negative test accepts those two data-error
types, requires a nonempty error message and verifies that no data changed.
The GUI's background import error display still needs the manual check below.

## Observed results

| Run | Observed result |
|---|---|
| Original GitHub tests | 27 run: 26 passed, one stale parent-theme expectation failed. |
| Revised automated suite | 38 run, all passed. |
| Revised GUI suite | Five run, all passed on a graphical desktop. |

Recorded during this review on 15 October 2026 using Python 3.13.2,
Tk 8.6 and Pillow 11.2.1 on macOS. The GUI harness uses one Tk main window
per process, with separate temporary databases for each test, to avoid macOS
Tk crashes when repeatedly destroying/recreating main windows.

These runs verify the synthetic scenarios listed above. They do not establish
that the actual collection CSVs, every screen size or every platform have passed.

## Manual acceptance checks still to record

Use a separate manual-test database:

```sh
python src/main.py --db data/manual_test.sqlite3
```

Record the actual result, tester, date and screenshot reference for each row.
All rows below are **Not run** in this review; do not label them passed until
someone performs them. Tests use confirmed set IDs and ownership quantities.

| ID | Check | Expected result | Result |
|---|---|---|---|
| M01 | Extract the actual supplied CSV ZIP, then use Browse and Validate and import to select its CSV folder. | Background import finishes, reports success and enables catalogue actions. | Not run |
| M02 | Select an incomplete/invalid CSV folder through the GUI, then correct it and retry. | Clear error, usable controls and unchanged existing collection/catalogue; retry succeeds. | Not run |
| M03 | Add confirmed owned sets; change quantities; restart the application; remove one entry and restart again. | Displayed collection and saved quantities match each action. | Not run |
| M04 | Select one real part/colour; independently total its non-spare rows from the latest inventories, multiplied by owned copies. | GUI quantity matches the independent total. | Not run |
| M05 | Check an owned target, then use a smaller test collection and a target with independently verified shortages. | Buildable for the complete owned target; correct parts/minifigure shortages for the other target. | Not run |
| M06 | Search real IDs/names; combine/clear theme and year filters; navigate Back. | Correct matches, no-result messages, cleared filters and retained Back context. | Not run |
| M07 | On collection, set search, piece search and missing report, switch List/Grid, click a card and use its action buttons. | Same rows and selection; correct action on the selected item. | Not run |
| M08 | Check images with an uncached actual catalogue item, then cached/unavailable images and exact part colours. | Correct set/part images or a usable unavailable-image placeholder. | Not run |
| M09 | Resize the window, scroll long lists/grids and move between grid pages. | Labels remain readable; controls and results remain reachable. | Not run |
| M10 | Disconnect the network after import; query pieces, manage the collection and check a target. | Core operations still work; image failures do not block them. | Not run |

Run the automated commands again after changing `src`. Keep actual test results
and screenshots with your project evidence. The assignment's live demonstration
and team review remain separate from this test-suite run.
