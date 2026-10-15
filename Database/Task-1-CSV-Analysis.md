## Task 1 CSV Analysis

**Lead:** Suhamri, Taccad 
**Status:** Reviewed

This document analyses the supplied Rebrickable CSV files
and records the differences from Figure 4 in the assignment.

### What the files actually contain: 
| File/table | Data rows | Proposed primary key |
|---|---:|---|
| colors | 275 | id |
| elements | 114,315 | element_id |
| inventories | 47,597 | id |
| inventory_minifigs | 25,831 | inventory_id + fig_num |
| inventory_parts | 1,558,562 | inventory_id + part_num + color_id + is_spare |
| inventory_sets | 5,212 | inventory_id + set_num |
| minifigs | 17,229 | fig_num |
| parts | 64,680 | part_num |
| part_categories | 76 | id |
| part_relationships | 37,438 | rel_type + child_part_num + parent_part_num |
| sets | 28,417 | set_num |
| themes | 496 | id |

### Additional columns absent from Figure 4

| CSV file | Additional columns |
|---|---|
| parts.csv | part_material |
| sets.csv | img_url |
| minifigs.csv | img_url |
| inventory_parts.csv | img_url |
| elements.csv | design_id |
| colors.csv | num_parts, num_sets, y1, y2 |

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

### Key and relationship explanations 
- `inventory_parts` uses the composite key
  `(inventory_id, part_num, color_id, is_spare)`.
  Including `is_spare` distinguishes normal and spare entries
  for the same part and colour in an inventory.
- `inventories.set_num` can identify either a set or a minifigure.
  This differs from Figure 4, which shows only the set relationship.
- `inventory_sets.set_num` identifies a set contained in an
  inventory, rather than the inventory's owner.
- `themes.parent_id` is optional because root themes have no parent.
- Set, part and minifigure identifiers are stored as text to
  preserve letters, hyphens and leading zeroes.

### Diagram notation

- PK means primary key; FK means foreign key.
- Multiple PK fields together form one composite key.
- `||` means exactly one; `o|` means zero or one;
  `o{` means zero or many.
- The two inventory-owner relationships are exclusive alternatives:
  each inventory belongs to exactly one set OR one minifigure.

### Scope

This diagram models the supplied Rebrickable CSV data.
The application's collection tables belong to Task 3.
  
