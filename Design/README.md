This working document explains the implemented design, the reasons for its structure, and the calculations behind collection quantities and buildability. Editable diagrams and the full wireframe set accompany this report in Design.

## What changed in this revision

| Earlier design | Implemented behaviour now documented |
|---|---|
| Image metadata omitted | `img_url` is stored in sets, minifigs and inventory_parts; legacy databases receive those columns. |
| Plain results tables | Collection, set search, part search and missing report all support List and Grid. |
| Generic GUI responsibility | Screens manages navigation history; ResultView manages shared rows/selection; ImageLoader fetches and caches thumbnails. |
| Import described as staging tables | Catalogue replacement occurs inside one SQLite transaction, with deferred foreign keys and rollback. There are no separate staging tables. |
| CSV folder only | Import accepts exactly one plain CSV or per-table `.csv.zip` for each required table. Image links can also be loaded from one original ZIP. |
| Caller mode hides search actions | Both Add selected set and Use as target are always displayed, regardless of caller mode. |
| Unspecified theme hierarchy | Parent theme searches include descendants; set results are limited to 500, part results to 300. |
| Flexible nested overlap handling | The current resolver rejects any common direct/nested part-colour key or figure ID as ambiguous. |
| BuildResult described as shortages only | BuildResult.rows contains every required item, including zero shortages; missing_items filters positive shortages. |

## Database Working
The core schema remains eleven tables: themes, sets, minifigs, parts, colors, inventories, inventory_parts, inventory_minifigs, inventory_sets, owned_sets and import_state. The application imports only fields needed by its functions and image support; it does not import elements, categories, material or part-substitution relationships.

owned_sets.set_num is the primary key and a foreign key to sets. One row records the copy quantity for one set type. Add increments an existing quantity, Update replaces it, and Remove deletes the row after a GUI confirmation. The database explicitly checks typeof(quantity)='integer' AND quantity>0 for owned copies.

The source inventories.set_num field can identify either a set or a minifigure. Importer membership checks separate it into nullable set_num and fig_num foreign keys. A database XOR check requires exactly one owner; separate unique constraints enforce (set_num, version) and (fig_num, version) uniqueness. Versions must be positive.

inventory_parts retains the composite key (inventory_id, part_num, color_id, is_spare). The other child keys are (inventory_id, fig_num) and (inventory_id, set_num). Quantity checks in those inventory tables require positivity; integer parsing and nonblank validation are performed by the importer. Unlike the earlier design's blanket non-null assumption, some foreign-key/composite-key columns in the actual DDL do not declare NOT NULL. The importer supplies and validates their values. See src/database.py for exact column nullability and constraints.

img_url TEXT NOT NULL DEFAULT '' exists on sets, minifigs and inventory_parts. It is metadata, not a matching key. DatabaseManager.image_url() retrieves set or figure URLs by identifier and part URLs by part number plus colour when supplied. An absent URL returns an empty string. Omitting a part colour permits a preview lookup across colours, but the current part-query screen passes the selected colour. The missing report maps a colour name back to an ID only if it has exactly one match; otherwise its part image is unavailable.

Indexes cover inventory set ownership/version, figure ownership/version, and part image lookup by part/colour. Theme parent references are deferred. Every connection enables foreign keys. The local database defaults to data/brick_buster.sqlite3; main.py --db can select another path. Thumbnails live in image_cache beside that database, not in SQL image blobs.

##Import and Image Enrichment
For each of nine tables, DataImporter requires exactly one <table>.csv or <table>.csv.zip in the chosen folder. A table ZIP must contain exactly one corresponding CSV. The nine tables are themes, colors, parts, sets, minifigs, inventories, inventory_parts, inventory_minifigs and inventory_sets. This is distinct from the image-enrichment action that accepts one original all_downloads.zip containing the three image-bearing CSV files.

Full import validates headers, parses integers and source booleans, resolves owner membership and replaces the catalogue inside BEGIN IMMEDIATE. It temporarily saves and removes owned rows, reloads the catalogue, restores ownership, checks foreign keys and detects theme/latest-inventory nested-set cycles. Only then does it mark ready and increment generation. Failure rolls back to the previous catalogue and collection. A failed first import leaves readiness false. Removing an owned set from a replacement catalogue fails the reference check rather than silently losing ownership.
stage_and_validate_graph() is a method name, not evidence of staging tables. Import-time readiness also does not guarantee every set is resolvable: absent inventories, direct/nested overlap, excessive nesting and empty usable contents are rejected later by InventoryResolver when those contents are requested.

load_image_urls(db, archive_path) is a module-level function in importer.py. It updates nonblank URLs only for existing set, figure and inventory-part keys in one transaction. It does not add catalogue items, change quantities, alter readiness or increment generation. A failure rolls back image updates. Consequently, successful image enrichment does not invalidate the current build result; successful full catalogue import does.

Both import actions run in a background worker with a separate DatabaseManager connection. A queue transfers progress/results back to Tkinter. While busy, the import inputs are disabled and navigation/closing is blocked. After completion, feedback is shown on the same Import screen.

##Classes and Image Architecture
BrickBusterApp constructs DatabaseManager, InventoryResolver, SetService, CollectionService, BuildService, Screens and one shared ImageLoader. It owns a shared tk.StringVar view mode, initially List, and the current session result. Screen methods remain methods of BrickBusterApp rather than separate screen classes. Screens stores the current screen, context dictionary, navigation history and widget references.

SetService performs search and filter operations. A recursive theme query includes descendant themes. CollectionService handles ownership changes and available piece totals. InventoryResolver provides one consistent interpretation of selected inventories. BuildService compares target and owned pools. ItemPool uses Counter objects; BuildResult and Shortage are dataclasses. Shortage.color is a string, with '-' used for complete minifigures. positive_quantity(value) is a module function that rejects nonpositive, noninteger, non-ASCII decimal and out-of-range input before writes.

ResultView wraps a Treeview and an alternative image grid. The Treeview rows and selection remain the source for both modes. Switching modes retains selection and, when entering Grid, goes to the page containing the selected item. Grid uses three columns and a maximum of twelve cards per page with Previous/Next controls and scrolling. A single shared mode means the choice carries across result screens. Clicking a card, or using Space/Enter on a focused card, selects its row; it does not automatically add a set or open another window.

ImageLoader uses three worker threads and a queue to deliver thumbnail callbacks on the Tk thread. It checks the URL-hashed PNG cache before downloading. Initial requests accept HTTPS URLs with hostname cdn.rebrickable.com, use a six-second timeout and reject responses larger than 8 MB. Thumbnails are bounded to 180 by 120 pixels. Empty, failed or unsupported images produce Image unavailable, while successful cached images remain usable offline. Image failure does not disable collection or calculation actions. ResultView revision checks prevent stale callbacks from updating rebuilt cards.

Core calculations use local SQLite after successful import. Uncached images need internet. Pillow is used by views.py in addition to Python's Tkinter and standard-library components; this is not a standard-library-only application.

## Screen and navigation working

| Screen or dialog | Implemented controls and transitions |
|---|---|
| S01 Home | Five entry buttons and database path. Without readiness, only Collection and Import are enabled. |
| S02 Import | Folder entry, Browse, Validate and import, Load image links from Rebrickable ZIP, progress and feedback. |
| S03 Collection | Add, Update and Remove above List/Grid results. Update/Remove enable when an entry is selected. |
| S04 Search | Number/name, theme and year; Search/Clear; List/Grid; both Add selected set and Use as target. Results load on entry. |
| D01 Quantity | Modal with current ownership and additional/replacement entry. Save commits and opens Collection. Cancel closes the modal and reveals its caller. |
| D02 Removal | Native Yes/No prompt. Yes removes all owned copies of that set; No changes nothing. |
| S05 Piece query | Search parts by number/name; Find part; List/Grid; colour picker; Check quantity. The action validates a selection when clicked. |
| S06 and S07 Build | Target identifier, Choose target, result text, Check buildability and conditional View missing items. S07 is an area within S06. |
| S08 Missing report | Target and one-copy label; List/Grid with all FR09 fields; Back to build result. A missing/stale session result displays a message instead. |

Home and Back are created on main screens. Back depends on history, not the screen name: returning to Home can still leave Back available. Context dictionaries retain search text/filter values, but the current code does not restore every selected result row when reconstructing a screen. Both search selection actions remain present even when entered with mode='add' or mode='target'; those mode values currently do not change the controls.

Collection mutation and successful full import clear session_result. A new build check clears the old result before calculation. Choosing a different target does not immediately erase the stored object, but the build screen only displays it when the target matches. The missing report checks catalogue generation. Its UI entry button appears only for NOT_BUILDABLE. This documents actual state handling rather than the earlier proposal of unconditional invalidation on target selection.

##Worked calculations matching the code

The following examples use the small synthetic catalogue in `Testing/test_brick_buster.py`, not the full Rebrickable dataset. A-1 has version 1 with 99 red p1 parts and version 2 with 3 non-spare red p1 parts, 10 spare red p1 parts and one complete fig-1. Version 2 is selected; version 1 and spares do not contribute. Although fig-1 has a component inventory containing p2, those components are not added to the loose-part pool.

For two owned copies of A-1, red p1 available is `2 x 3 = 6`; blue p1 available is zero; fig-1 available is two. N-1 contains two nested copies of A-1 and no direct contents. Two owned copies of N-1 therefore yield `2 x 2 x 3 = 12` red p1 and `2 x 2 x 1 = 4` complete fig-1.

For one owned A-1, target B-1 requires five red p1 and one fig-2:

| Item | Required | Available | Missing |
|---|---|---|---|
| p1 red | 5 | 3 | 2 |
| fig-2 | 1 | 0 | 1 |

`missing = max(required - available, 0)`, so B-1 is NOT_BUILDABLE. Owning two A-1 copies removes the part shortage but does not provide fig-2. BuildResult.rows contains all requirements; missing_items returns only rows with positive shortages. An empty collection gives zero available quantities and all target shortages. Checks consume nothing.

The resolver caches one-copy pools per catalogue generation, multiplies each nested edge and each owned quantity, detects recursion-path cycles, and rejects a path of length 200 or more. Missing inventories and pools with no usable parts or figures are errors. It rejects any overlap between direct and aggregated nested item keys even when a real-world overlap might be legitimate. It sums matching contributions from separate child branches. This is a conservative current limitation, not a general provenance-normalisation algorithm. The earlier worked example that added the same red part directly and through a child has therefore been removed.
