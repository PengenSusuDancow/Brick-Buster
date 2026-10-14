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

## Running the application 
Requires Python 3.10 or later with Tkinter.
From the repository folder, run:

    python src/main.py

On first launch, open Import Rebrickable data and select the folder containing the supplied CSV or CSV ZIP files.
The SQLite database is created automatically in data/.
