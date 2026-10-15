"""Run separately: python Testing/gui_smoke.py"""
from pathlib import Path
from io import BytesIO
import sys
import tempfile
from time import monotonic, sleep
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app import BrickBusterApp
from importer import DataImporter
from views import ResultView
from test_brick_buster import write_catalogue


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.app = BrickBusterApp(self.root, self.folder / 'gui.sqlite3')
        self.addCleanup(self.close_app)
        self.errors = []
        self.root.report_callback_exception = lambda kind, value, trace: self.errors.append(str(value))

    def close_app(self):
        self.app.images.close()
        self.app.db.close()
        for widget in self.root.winfo_children():
            widget.destroy()
        self.pump()

    def pump(self):
        self.root.update()
        self.assertEqual(self.errors, [], 'A GUI callback raised an exception')

    def button(self, text, parent=None):
        matches = [w for w in descendants(parent or self.root)
                   if isinstance(w, ttk.Button) and w.cget('text') == text]
        self.assertEqual(len(matches), 1, 'Expected one button: ' + text)
        return matches[0]

    def tree(self):
        matches = [w for w in descendants(self.app.screens.frame) if isinstance(w, ttk.Treeview)]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def import_catalogue(self):
        write_catalogue(self.folder)
        DataImporter(self.app.db).publish_atomically(self.folder)
        self.app.on_collection_or_import_change()

    def dialog(self, set_num, mode='add'):
        self.app.quantity_dialog(set_num, mode)
        self.pump()
        dialogs = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]
        self.assertEqual(len(dialogs), 1)
        return dialogs[0]

    def fill_quantity(self, dialog, value):
        entries = [w for w in descendants(dialog) if isinstance(w, ttk.Entry)]
        self.assertEqual(len(entries), 1)
        entries[0].delete(0, 'end')
        entries[0].insert(0, value)

    def save_quantity(self, set_num, value, mode='add'):
        dialog = self.dialog(set_num, mode)
        self.fill_quantity(dialog, value)
        self.button('Save', dialog).invoke()
        self.pump()

    def check_target(self):
        self.app.show_screen('build', {'target': 'B-1'})
        self.button('Check buildability').invoke()
        self.pump()
        return self.app.session_result

    def test_screens_filters_back_navigation_and_both_views(self):
        self.assertEqual(str(self.button('Search and filter sets').cget('state')), 'disabled')
        for screen in ('home', 'collection', 'import'):
            self.app.show_screen(screen)
            self.pump()
        self.import_catalogue()
        for mode in ('List', 'Grid'):
            self.app.view_mode.set(mode)
            for screen in ('home', 'collection', 'search', 'piece', 'import'):
                self.app.show_screen(screen)
                self.pump()
            self.assertEqual(self.check_target().status, 'NOT_BUILDABLE')
            self.app.show_screen('missing')
            self.pump()
            self.assertEqual(len(self.tree().get_children()), 2)
        self.app.show_screen('search', {'text': 'Target', 'theme': 'Root [1]', 'year': '2025'})
        self.pump()
        self.assertEqual(self.tree().get_children(), ('B-1',))
        self.app.show_screen('collection')
        self.app.screens.back()
        self.pump()
        self.assertEqual(self.tree().get_children(), ('B-1',))

    def test_quantity_validation_cancel_and_confirmed_removal(self):
        self.import_catalogue()
        self.save_quantity('A-1', '2')
        dialog = self.dialog('A-1')
        self.fill_quantity(dialog, '10')
        self.button('Cancel', dialog).invoke()
        self.pump()
        self.assertEqual(self.app.collection.list_owned_sets()[0]['quantity'], 2)
        dialog = self.dialog('A-1', 'update')
        self.fill_quantity(dialog, '0')
        self.button('Save', dialog).invoke()
        self.pump()
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(self.app.collection.list_owned_sets()[0]['quantity'], 2)
        self.fill_quantity(dialog, '4')
        self.button('Save', dialog).invoke()
        self.pump()
        self.assertEqual(self.app.collection.list_owned_sets()[0]['quantity'], 4)
        self.check_target()
        self.save_quantity('A-1', '3', 'update')
        self.assertIsNone(self.app.session_result)
        self.tree().selection_set('A-1')
        self.pump()
        with patch('app.messagebox.askyesno', return_value=False) as confirm:
            self.button('Remove set').invoke()
            self.pump()
            confirm.assert_called_once()
        self.assertEqual(self.app.collection.list_owned_sets()[0]['quantity'], 3)
        with patch('app.messagebox.askyesno', return_value=True) as confirm:
            self.button('Remove set').invoke()
            self.pump()
            confirm.assert_called_once()
        self.assertEqual(self.app.collection.list_owned_sets(), [])

    def test_build_report_and_buildable_result_through_gui(self):
        self.import_catalogue()
        self.save_quantity('A-1', '1')
        self.assertEqual(self.check_target().status, 'NOT_BUILDABLE')
        self.button('View missing items').invoke()
        self.pump()
        rows = [self.tree().item(i, 'values') for i in self.tree().get_children()]
        self.assertEqual([tuple(map(str, r)) for r in rows],
                         [('Part', 'p1', 'Brick', 'Red', '5', '3', '2'),
                          ('Minifigure', 'fig-2', 'Other person', '-', '1', '0', '1')])
        self.save_quantity('B-1', '1')
        self.assertIsNone(self.app.session_result)
        before = [tuple(r) for r in self.app.collection.list_owned_sets()]
        for _ in range(2): self.assertEqual(self.check_target().status, 'BUILDABLE')
        self.assertEqual([tuple(r) for r in self.app.collection.list_owned_sets()], before)

    def test_grid_paging_card_selection_and_empty_results(self):
        self.app.show_screen('collection')
        # A separate results view keeps this check independent of search limits.
        window = tk.Toplevel(self.root)
        window.geometry('950x650')
        self.addCleanup(window.destroy)
        mode = tk.StringVar(self.root, value='Grid')
        view = ResultView(window, ('set', 'name'), ('Set number', 'Name'),
                          (130, 300), self.app.images, mode, lambda values: '')
        self.pump()
        self.assertEqual(view.cards, {})
        self.assertEqual(str(view.next.cget('state')), 'disabled')
        for i in range(13):
            view.insert('', 'end', iid=f'S-{i}', values=(f'S-{i}', f'Synthetic set {i}'))
        self.pump()
        self.assertEqual(len(view.cards), 12)
        view.next.invoke()
        self.pump()
        self.assertEqual(set(view.cards), {'S-12'})
        view.cards['S-12'].event_generate('<Button-1>', x=5, y=5)
        self.pump()
        self.assertEqual(view.selection(), ('S-12',))
        mode.set('List')
        self.pump()
        self.assertEqual(view.selection(), ('S-12',))
        mode.set('Grid')
        self.pump()
        self.assertEqual(view.page, 1)
        view.delete(*view.get_children())
        self.pump()
        self.assertEqual(view.cards, {})
        self.assertEqual(view.page, 0)
        self.assertEqual(str(view.next.cget('state')), 'disabled')

    def test_grid_shows_thumbnail_or_unavailable_placeholder(self):
        data = BytesIO()
        Image.new('RGB', (300, 200), 'red').save(data, format='PNG')
        def response(request, **kwargs):
            if request.full_url.endswith('/ok.png'):
                return BytesIO(data.getvalue())
            raise OSError('Simulated offline image')
        window = tk.Toplevel(self.root)
        window.geometry('950x650')
        self.addCleanup(window.destroy)
        mode = tk.StringVar(self.root, value='Grid')
        view = ResultView(window, ('set', 'name'), ('Set', 'Name'), None,
                          self.app.images, mode,
                          lambda values: 'https://cdn.rebrickable.com/media/' + values[0] + '.png')
        with patch('views.urlopen', side_effect=response):
            view.insert('', 'end', iid='ok', values=('ok', 'Synthetic image'))
            view.insert('', 'end', iid='missing', values=('missing', 'Unavailable image'))
            self.pump()
            deadline = monotonic() + 3
            while self.app.images.pending and monotonic() < deadline:
                self.pump()
                sleep(0.01)
            self.assertEqual(self.app.images.pending, {}, 'Image callbacks did not finish')
        good = view.cards['ok'].winfo_children()[0]
        failed = view.cards['missing'].winfo_children()[0]
        self.assertTrue(good.cget('image'))
        self.assertLessEqual(good.image.width(), 180)
        self.assertLessEqual(good.image.height(), 120)
        self.assertEqual(failed.cget('text'), 'Image unavailable')


if __name__ == '__main__':
    unittest.main(verbosity=2)
