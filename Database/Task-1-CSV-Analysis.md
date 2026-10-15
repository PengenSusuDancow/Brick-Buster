## Task 1 CSV Analysis

**Lead:** Suhamri, Taccad 
**Status:** Reviewed

This document analyses the supplied Rebrickable CSV files
and records the differences from Figure 4 in the assignment.

### What the files actually contain: 
| CSV table | Data rows | Selected logical primary key |
| --- | --- | --- |
| themes | 496 | id |
| colors | 275 | id |
| part_categories | 76 | id |
| parts | 64,898 | part_num |
| elements | 114,656 | element_id |
| inventories | 47,781 | id |
| sets | 28,537 | set_num |
| minifigs | 17,293 | fig_num |
| inventory_parts | 1,567,028 | inventory_id, part_num, color_id, is_spare |
| inventory_sets | 5,214 | inventory_id, set_num |
| inventory_minifigs | 25,902 | inventory_id, fig_num |
| part_relationships | 37,536 | rel_type, child_part_num, parent_part_num |
| part_mappings | 183,055 | part_num, ext_system, ext_id |
| set_mappings | 71,586 | set_num, ext_system |
| color_mappings | 846 | id, ext_system, ext_id |

### Additional columns absent from Figure 4

| CSV table | Columns absent from Figure 4 |
| --- | --- |
| parts | part_material |
| sets | img_url |
| minifigs | img_url |
| inventory_parts | img_url |
| elements | design_id |
| colors | num_parts, num_sets, y1, y2 |

None of the twelve Figure 4 tables or their displayed columns is missing from the archive. The headers of themes, part_categories, part_relationships, inventories, inventory_sets and inventory_minifigs match the figure. Three further tables are present:

| Additional table | Actual CSV columns |
| --- | --- |
| part_mappings | part_num, ext_system, ext_id, is_export_id, is_import_id |
| set_mappings | set_num, ext_system, ext_id |
| color_mappings | id, ext_system, ext_id, ext_descr, is_export_id, is_import_id |

## Source database ER diagram 
```mermaid
erDiagram
    themes |o..o{ themes : "R01 parent theme"
    themes ||..o{ sets : "R02 theme"
    sets |o..o{ inventories : "R03 set owner (XOR R04)"
    minifigs |o..o{ inventories : "R04 minifig owner (XOR R03)"
    inventories ||--o{ inventory_parts : "R05 containing inventory"
    parts ||--o{ inventory_parts : "R06 part"
    colors ||--o{ inventory_parts : "R07 colour"
    inventories ||--o{ inventory_sets : "R08 containing inventory"
    sets ||--o{ inventory_sets : "R09 contained set"
    inventories ||--o{ inventory_minifigs : "R10 containing inventory"
    minifigs ||--o{ inventory_minifigs : "R11 contained minifig"
    part_categories ||..o{ parts : "R12 category"
    parts ||..o{ elements : "R13 part"
    colors ||..o{ elements : "R14 colour"
    parts ||--o{ part_relationships : "R15 child part"
    parts ||--o{ part_relationships : "R16 parent part"
    parts ||--o{ part_mappings : "R17 external part mapping"
    colors ||--o{ color_mappings : "R18 external colour mapping"
    sets |o--o{ set_mappings : "R19 set mapping owner (XOR R20)"
    minifigs |o--o{ set_mappings : "R20 minifig mapping owner (XOR R19)"
    themes {
        integer id PK
        text name
        integer parent_id FK "blank cells observed"
    }
    colors {
        integer id PK
        text name
        text rgb
        boolean is_trans
        integer num_parts
        integer num_sets
        integer y1 "blank cells observed"
        integer y2 "blank cells observed"
    }
    part_categories {
        integer id PK
        text name
    }
    parts {
        text part_num PK
        text name
        integer part_cat_id FK
        text part_material
    }
    elements {
        text element_id PK
        text part_num FK
        integer color_id FK
        text design_id "blank cells observed"
    }
    inventories {
        integer id PK
        integer version
        text set_num "set OR minifig - XOR rule"
    }
    sets {
        text set_num PK
        text name
        integer year
        integer theme_id FK
        integer num_parts
        text img_url
    }
    minifigs {
        text fig_num PK
        text name
        integer num_parts
        text img_url
    }
    inventory_parts {
        integer inventory_id PK,FK
        text part_num PK,FK
        integer color_id PK,FK
        integer quantity
        boolean is_spare PK
        text img_url "blank cells observed"
    }
    inventory_sets {
        integer inventory_id PK,FK
        text set_num PK,FK
        integer quantity
    }
    inventory_minifigs {
        integer inventory_id PK,FK
        text fig_num PK,FK
        integer quantity
    }
    part_relationships {
        text rel_type PK
        text child_part_num PK,FK
        text parent_part_num PK,FK
    }
    part_mappings {
        text part_num PK,FK
        text ext_system PK
        text ext_id PK
        boolean is_export_id
        boolean is_import_id
    }
    set_mappings {
        text set_num PK "set OR minifig - XOR rule"
        text ext_system PK
        text ext_id
    }
    color_mappings {
        integer id PK,FK
        text ext_system PK
        text ext_id PK
        text ext_descr
        boolean is_export_id
        boolean is_import_id
    }
```

## Relationship register

Read each row as a child field referencing a parent key. Multiplicities describe the logical model, not exact current counts per parent. The R03/R04 pair and R19/R20 pair each require exactly one branch.

| ID | Child reference -> parent key | Parent per child | Children per parent |
| --- | --- | --- | --- |
| R01 | themes.parent_id -> themes.id | 0..1 | 0..* |
| R02 | sets.theme_id -> themes.id | 1 | 0..* |
| R03 | inventories.set_num -> sets.set_num | 0..1 | 0..* |
| R04 | inventories.set_num -> minifigs.fig_num | 0..1 | 0..* |
| R05 | inventory_parts.inventory_id -> inventories.id | 1 | 0..* |
| R06 | inventory_parts.part_num -> parts.part_num | 1 | 0..* |
| R07 | inventory_parts.color_id -> colors.id | 1 | 0..* |
| R08 | inventory_sets.inventory_id -> inventories.id | 1 | 0..* |
| R09 | inventory_sets.set_num -> sets.set_num | 1 | 0..* |
| R10 | inventory_minifigs.inventory_id -> inventories.id | 1 | 0..* |
| R11 | inventory_minifigs.fig_num -> minifigs.fig_num | 1 | 0..* |
| R12 | parts.part_cat_id -> part_categories.id | 1 | 0..* |
| R13 | elements.part_num -> parts.part_num | 1 | 0..* |
| R14 | elements.color_id -> colors.id | 1 | 0..* |
| R15 | part_relationships.child_part_num -> parts.part_num | 1 | 0..* |
| R16 | part_relationships.parent_part_num -> parts.part_num | 1 | 0..* |
| R17 | part_mappings.part_num -> parts.part_num | 1 | 0..* |
| R18 | color_mappings.id -> colors.id | 1 | 0..* |
| R19 | set_mappings.set_num -> sets.set_num | 0..1 | 0..* |
| R20 | set_mappings.set_num -> minifigs.fig_num | 0..1 | 0..* |


### Notation

PK marks the selected logical primary key; multiple PK markers form one composite key. FK marks an ordinary validated reference; REF marks the conditional set/minifigure reference. UML end labels mean 1 exactly one, 0..1 optional one, and 0..* zero or many. Solid lines indicate that the parent key contributes to the selected child key; dashed lines are non-identifying. Crossings are not joins. In the editable Mermaid version, |o on the left and o| on the right both mean zero or one. The same cardinalities, key fields, identifying lines and XOR labels are used.

### Scope

This diagram models the supplied Rebrickable CSV data.
The application's collection tables belong to Task 3.
  
