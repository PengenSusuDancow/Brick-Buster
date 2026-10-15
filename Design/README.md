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
