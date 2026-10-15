"""Construct and exercise all Tk screens. Run separately from headless tests."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app import BrickBusterApp
from importer import DataImporter
from test_brick_buster import write_catalogue


with tempfile.TemporaryDirectory() as folder:
    root = tk.Tk()
    root.withdraw()
    app = BrickBusterApp(root, Path(folder) / 'gui.sqlite3')
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    for screen in ('home', 'collection', 'import'):
        app.show_screen(screen)
        root.update()
    write_catalogue(Path(folder))
    DataImporter(app.db).publish_atomically(folder)
    for screen in ('home', 'collection', 'search', 'piece', 'import'):
        app.show_screen(screen)
        root.update()
    app.show_screen('build', {'target': 'B-1'})
    app.screens.widgets['check_build']()
    root.update()
    assert app.session_result.status == 'NOT_BUILDABLE'
    app.show_screen('missing')
    root.update()
    app.collection.add_set('B-1', 1)
    app.on_collection_or_import_change()
    assert app.session_result is None
    app.show_screen('build', {'target': 'B-1'})
    app.screens.widgets['check_build']()
    root.update()
    assert app.session_result.status == 'BUILDABLE'
    app.quantity_dialog('B-1', 'update')
    root.update()
    dialogs = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert len(dialogs) == 1
    dialogs[0].destroy()
    assert not errors, errors
    app.close()
print('GUI smoke check passed: all screens, quantity dialog and both build outcomes.')
