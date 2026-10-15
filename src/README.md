# Task 4 - Brick Buster 
A Python application using Tkinter and SQLite to manage owned LEGO sets, query piece quantities, and check whether a target set can be built.

## Files 
| File | Purpose | 
|---|---|
| database.py | SQLite tables, connections and transactions |
| importer.py | Validates and imports CSV or CSV ZIP files |
| services.py | Collection management and build calculations |
| app.py | Tkinter graphical interface |
| main.py | Starts the application |
| views.py | List/image-grid results and cached thumbnails |

## Running the application 
Requires Python 3.10 or later with Tkinter.
From the repository folder, run:

    python -m pip install -r requirements.txt
    python src/main.py

On first launch, open Import Rebrickable data and select the folder containing the supplied CSV or CSV ZIP files.
The SQLite database is created automatically in data. 

## Result views
Use List or Grid on collection, set search, piece search and missing-items screens.
Click a card to select it, then use the existing action buttons. Grid pages contain
up to 12 items. Part images use the selected colour; unavailable images show a
placeholder without preventing actions. Parent theme filters include subthemes.

Image links are imported automatically when the CSVs contain `img_url`. If older
CSVs omitted that column, open **Import Rebrickable data → Load image links from
Rebrickable ZIP…** and select the original `all_downloads.zip`. This only enriches
existing catalogue rows; it does not add sets or change owned quantities.

Images require internet on first use. Thumbnails are cached in `image_cache`
beside the SQLite database. Collection management and calculations work offline.
