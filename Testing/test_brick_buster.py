"""Behavioural checks with small catalogues; no network or GUI is required."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from database import DatabaseManager, DataError, ValidationError
from importer import DataImporter, FILES
from services import SetService, CollectionService, InventoryResolver, BuildService


def write_catalogue(folder):
    rows = {
        'themes': [(1, 'Root', ''), (2, 'City', 1)],
        'colors': [(0, 'Blue'), (1, 'Red')],
        'parts': [('p1', 'Brick'), ('p2', 'Tile')],
        'sets': [('A-1', 'Owned set', 2024, 2, 4), ('B-1', 'Target set', 2025, 2, 6),
                 ('N-1', 'Nested bundle', 2024, 1, 8), ('E-1', 'No inventory', 2024, 1, 1)],
        'minifigs': [('fig-1', 'Person', 1), ('fig-2', 'Other person', 1)],
        'inventories': [(1, 1, 'A-1'), (2, 2, 'A-1'), (3, 1, 'B-1'),
                        (4, 1, 'N-1'), (5, 1, 'fig-1')],
        'inventory_parts': [(1, 'p1', 1, 99, 'False'), (2, 'p1', 1, 3, 'False'),
                            (2, 'p1', 1, 10, 'True'), (3, 'p1', 1, 5, 'False'),
                            (5, 'p2', 0, 1, 'False')],
        'inventory_minifigs': [(2, 'fig-1', 1), (3, 'fig-2', 1)],
        'inventory_sets': [(4, 'A-1', 2)],
    }
    for table, fields in FILES.items():
        with (folder / (table + '.csv')).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            writer.writerows(rows[table])


class BrickBusterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'test.sqlite3'
        write_catalogue(self.folder)
        self.db = DatabaseManager(self.path)
        self.importer = DataImporter(self.db)
        self.importer.publish_atomically(self.folder)
        self.resolver = InventoryResolver(self.db)
        self.collection = CollectionService(self.db, self.resolver)
        self.build = BuildService(self.collection, self.resolver)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def append(self, table, row):
        with (self.folder / (table+'.csv')).open('a', newline='', encoding='utf-8') as stream:
            csv.writer(stream).writerow(row)

    def test_duplicate_copies_latest_version_and_spares(self):
        self.collection.add_set('A-1', 1)
        self.collection.add_set('A-1', '1')
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 6)
        self.assertEqual(self.collection.get_piece_quantity('p1', 0), 0)

    def test_shortages_include_figures(self):
        self.collection.add_set('A-1', 1)
        result = self.build.check_target('B-1')
        shortages = self.build.missing_items(result)
        self.assertEqual(result.status, 'NOT_BUILDABLE')
        self.assertEqual([(r.item_type, r.required, r.available, r.missing) for r in shortages],
                         [('Part', 5, 3, 2), ('Minifigure', 1, 0, 1)])

    def test_enough_parts_does_not_replace_missing_figure(self):
        self.collection.add_set('A-1', 2)
        result = self.build.check_target('B-1')
        self.assertEqual([r.item_type for r in self.build.missing_items(result)], ['Minifigure'])

    def test_owned_target_is_buildable_without_consumption(self):
        self.collection.add_set('B-1', 1)
        self.assertEqual(self.build.check_target('B-1').status, 'BUILDABLE')
        self.assertEqual(self.build.check_target('B-1').status, 'BUILDABLE')
        self.assertEqual(self.collection.list_owned_sets()[0]['quantity'], 1)

    def test_empty_collection(self):
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 0)
        rows = self.build.missing_items(self.build.check_target('B-1'))
        self.assertEqual([r.missing for r in rows], [5, 1])

    def test_complete_figures_are_not_expanded(self):
        self.collection.add_set('A-1', 1)
        self.assertEqual(self.collection.get_piece_quantity('p2', 0), 0)

    def test_nested_set_quantities(self):
        self.collection.add_set('N-1', 2)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 12)
        self.assertEqual(self.resolver.aggregate_owned(self.collection.list_owned_sets()).minifigs['fig-1'], 4)

    def test_invalid_quantities_do_not_change_collection(self):
        self.collection.add_set('A-1', 2)
        for quantity in (0, -1, '1.5', 'abc', True, '', 1.0, '999999999999999999999999', '9'*5000):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    self.collection.update_quantity('A-1', quantity)
        self.assertEqual(self.collection.list_owned_sets()[0]['quantity'], 2)

    def test_update_remove_and_restart(self):
        self.collection.add_set('A-1', 1)
        self.collection.update_quantity('A-1', 4)
        self.db.close()
        self.db = DatabaseManager(self.path)
        service = CollectionService(self.db, InventoryResolver(self.db))
        self.assertEqual(service.get_piece_quantity('p1', 1), 12)
        service.remove_set('A-1')
        self.db.close()
        self.db = DatabaseManager(self.path)
        self.assertEqual(self.db.read('SELECT * FROM owned_sets'), [])

    def test_search_name_number_theme_and_year(self):
        service = SetService(self.db)
        self.assertEqual([r['set_num'] for r in service.search_sets('Target', 2, 2025)], ['B-1'])
        self.assertEqual(len(service.search_sets('A-1')), 1)
        self.assertEqual(service.search_sets('Target', 1), [])
        self.assertEqual(service.search_sets('%'), [])

    def test_failed_reimport_rolls_back_catalogue_and_collection(self):
        self.collection.add_set('A-1', 2)
        generation = self.db.generation
        self.append('inventory_parts', (2, 'unknown', 1, 3, 'False'))
        with self.assertRaises(DataError):
            self.importer.publish_atomically(self.folder)
        self.assertTrue(self.db.catalogue_ready())
        self.assertEqual(self.db.generation, generation)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 6)

    def test_failed_first_import_not_ready(self):
        other = DatabaseManager(self.folder / 'empty.sqlite3')
        try:
            (self.folder / 'parts.csv').unlink()
            with self.assertRaises(DataError):
                DataImporter(other).publish_atomically(self.folder)
            self.assertFalse(other.catalogue_ready())
        finally:
            other.close()

    def test_cycle_import_rejected(self):
        self.append('inventory_sets', (2, 'N-1', 1))
        with self.assertRaisesRegex(DataError, 'Cycle'):
            self.importer.publish_atomically(self.folder)
        self.assertEqual(self.db.generation, 1)

    def test_overlapping_nested_contents_are_explicit_error(self):
        self.append('inventory_parts', (4, 'p1', 1, 1, 'False'))
        self.importer.publish_atomically(self.folder)
        with self.assertRaisesRegex(DataError, 'overlap'):
            self.resolver.resolve_set('N-1')

    def test_missing_inventory_is_error_not_buildable(self):
        with self.assertRaisesRegex(DataError, 'No inventory'):
            self.build.check_target('E-1')

    def test_reimport_preserves_collection_and_invalidates_result(self):
        self.collection.add_set('A-1', 2)
        result = self.build.check_target('A-1')
        self.importer.publish_atomically(self.folder)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 6)
        with self.assertRaisesRegex(DataError, 'changed'):
            self.build.missing_items(result)

    def test_zip_import(self):
        for table in FILES:
            plain = self.folder / (table+'.csv')
            with zipfile.ZipFile(str(plain)+'.zip', 'w') as archive:
                archive.write(plain, arcname=plain.name)
            plain.unlink()
        self.assertEqual(self.importer.publish_atomically(self.folder)['sets'], 4)

    def test_inventory_figure_owner_normalized(self):
        row = self.db.read('SELECT set_num,fig_num FROM inventories WHERE id=5')[0]
        self.assertEqual(tuple(row), (None, 'fig-1'))


if __name__ == '__main__':
    unittest.main()
