## Task 1 CSV Analysis

**Lead:** Suhamri, Taccad 
**Status:** In progress 

This document analyses the supplied Rebrickable CSV files
and records the differences from Figure 4 in the assignment.

## What the files actually contain: 
  File/table          | Data rows | Proposed primary key |
| colors              | 275       | id                   |
| elements            | 114,315   | element_id           |
| inventories         | 47,597    | id                   |
| inventory_minifigs  | 25,831    | inventory_id + fig_num |
| inventory_parts     | 1,558,562 | inventory_id + part_num + color_id + is_spare |
| inventory_sets      | 5,212     | inventory_id + set_num |
| minifigs            | 17,229    | fig_num                |
| parts               | 64,680    | part_num               |
| part_categories     | 76        | id                     |
| part_relationships  | 37,438    | rel_type + child_part_num + parent_part_num |
| sets                | 28,417    | set_num                |
| themes              | 496       | id

CSV file  |  Additional columns absent from Figure 4
parts.csv  |  part_material
sets.csv  |  img_url
minifigs.csv  |  img_url
inventory_parts.csv  |  img_url
elements.csv  |  design_id
colors.csv  |  num_parts, num_sets, y1, y2

## Source database ER diagram 
```mermaid 
erDiagram 
themes { 
    integer id PK
    text name
    integer parent_id FK "blank for root themes"
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

inventories {
    integer id PK
    integer version
    text set_num "references set OR minifig"
}

inventory_parts {
    integer inventory_id PK,FK
    text part_num PK,FK
    integer color_id PK,FK
    integer quantity
    boolean is_spare PK
    text img_url "blank values observed"
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

parts {
    text part_num PK
    text name
    integer part_cat_id FK
    text part_material
}

part_categories {
    integer id PK
    text name
}

part_relationships {
    text rel_type PK
    text child_part_num PK,FK
    text parent_part_num PK,FK
}

elements {
    text element_id PK
    text part_num FK
    integer color_id FK
    text design_id "blank values observed"
}

colors {
    integer id PK
    text name
    text rgb
    boolean is_trans
    integer num_parts
    integer num_sets
    integer y1 "blank values observed"
    integer y2 "blank values observed"
}
themes |o--o{ themes : parent_id
    themes ||--o{ sets : theme_id
    sets |o..o{ inventories : "set owner (XOR)"
    minifigs |o..o{ inventories : "minifigure owner (XOR)"
    inventories ||--o{ inventory_parts : inventory_id
    parts ||--o{ inventory_parts : part_num
    colors ||--o{ inventory_parts : color_id
    inventories ||--o{ inventory_sets : inventory_id
    sets ||--o{ inventory_sets : set_num
    inventories ||--o{ inventory_minifigs : inventory_id
    minifigs ||--o{ inventory_minifigs : fig_num
    part_categories ||--o{ parts : part_cat_id
    parts ||--o{ elements : part_num
    colors ||--o{ elements : color_id
    parts ||--o{ part_relationships : child_part_num
    parts ||--o{ part_relationships : parent_part_num
```
Each inventory belongs to exactly one set OR one minifigure.
The two owner relationships are exclusive alternatives (XOR),
not two simultaneously enforced SQL foreign keys.

Fields marked PK together form one composite primary key.
Keys and relationships are proposed from analysis of the CSV data.
