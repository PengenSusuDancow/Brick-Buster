"""Offline behavioural tests. All catalogue rows below are synthetic test data."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from database import DatabaseManager, DataError, ValidationError
from importer import DataImporter
from services import SetService, CollectionService, InventoryResolver, BuildService


def write_catalogue(folder):
    """A has 3 red bricks + fig-1; B needs 5 red bricks + fig-2.

    C has 5 BLUE bricks + fig-2, N contains two copies of A, and E has no
    inventory. A's old inventory and spare pieces must not be counted.
    These identifiers and names are not real LEGO catalogue information.
    """
    tables = {
        'themes': ('id,name,parent_id', [(1, 'Root', ''), (2, 'City', 1),
                                        (3, 'Classic', '')]),
        'colors': ('id,name', [(0, 'Blue'), (1, 'Red')]),
        'parts': ('part_num,name', [('p1', 'Brick'), ('p2', 'Tile')]),
        'sets': ('set_num,name,year,theme_id,num_parts', [
            ('A-1', 'Owned set', 2024, 2, 4),
            ('B-1', 'Target set', 2025, 2, 6),
            ('C-1', 'Blue set', 2025, 3, 6),
            ('N-1', 'Nested bundle', 2024, 1, 8),
            ('E-1', 'No inventory', 2024, 1, 1)]),
        'minifigs': ('fig_num,name,num_parts', [('fig-1', 'Person', 1),
                                               ('fig-2', 'Other person', 1)]),
        'inventories': ('id,version,set_num', [
            (1, 1, 'A-1'), (2, 2, 'A-1'), (3, 1, 'B-1'),
            (4, 1, 'N-1'), (5, 1, 'fig-1'), (6, 1, 'C-1')]),
        'inventory_parts': ('inventory_id,part_num,color_id,quantity,is_spare', [
            (1, 'p1', 1, 99, 'False'), (2, 'p1', 1, 3, 'False'),
            (2, 'p1', 1, 10, 'True'), (3, 'p1', 1, 5, 'False'),
            (5, 'p2', 0, 1, 'False'), (6, 'p1', 0, 5, 'False')]),
        'inventory_minifigs': ('inventory_id,fig_num,quantity', [
            (2, 'fig-1', 1), (3, 'fig-2', 1), (6, 'fig-2', 1)]),
        'inventory_sets': ('inventory_id,set_num,quantity', [(4, 'A-1', 2)]),
    }
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, (header, rows) in tables.items():
        with (folder / (name + '.csv')).open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header.split(','))
            writer.writerows(rows)
    return {name: len(rows) for name, (_, rows) in tables.items()}


class BrickBusterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'test.sqlite3'
        self.expected_counts = write_catalogue(self.folder)
        self.open_database()
        self.addCleanup(lambda: self.db.close())
        self.importer.publish_atomically(self.folder)

    def open_database(self):
        self.db = DatabaseManager(self.path)
        self.importer = DataImporter(self.db)
        self.resolver = InventoryResolver(self.db)
        self.collection = CollectionService(self.db, self.resolver)
        self.build = BuildService(self.collection, self.resolver)
        self.sets = SetService(self.db)

    def restart(self):
        self.db.close()
        self.open_database()

    def append(self, table, row):
        with (self.folder / (table + '.csv')).open('a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(row)

    def change(self, table, field, value, row=0):
        path = self.folder / (table + '.csv')
        with path.open(newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        rows[row + 1][rows[0].index(field)] = str(value)
        with path.open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(rows)

    def snapshot(self):
        tables = (*self.expected_counts, 'owned_sets', 'import_state')
        return {t: [tuple(r) for r in self.db.read('SELECT * FROM ' + t + ' ORDER BY rowid')]
                for t in tables}

    def reject_import(self, exceptions=DataError):
        before = self.snapshot()
        with self.assertRaises(exceptions) as error:
            self.importer.publish_atomically(self.folder)
        self.assertTrue(str(error.exception))
        self.assertEqual(self.snapshot(), before)

    def test_import_counts_readiness_and_foreign_keys(self):
        self.assertTrue(self.db.catalogue_ready())
        self.assertEqual(self.db.generation, 1)
        for table, count in self.expected_counts.items():
            self.assertEqual(self.db.read('SELECT COUNT(*) FROM ' + table)[0][0], count)
        self.assertEqual(self.db.read('PRAGMA foreign_key_check'), [])
        owner = self.db.read('SELECT set_num,fig_num FROM inventories WHERE id=5')[0]
        self.assertEqual(tuple(owner), (None, 'fig-1'))

    def test_each_csv_can_be_supplied_in_its_own_zip(self):
        for table in self.expected_counts:
            plain = self.folder / (table + '.csv')
            with zipfile.ZipFile(str(plain) + '.zip', 'w') as z:
                z.write(plain, 'nested/' + plain.name)
            plain.unlink()
        self.assertEqual(self.importer.publish_atomically(self.folder), self.expected_counts)

    def test_missing_duplicate_and_invalid_headers_are_rejected(self):
        path = self.folder / 'parts.csv'
        for case in ('missing', 'both formats', 'missing header', 'duplicate header'):
            with self.subTest(case=case):
                write_catalogue(self.folder)
                extra = self.folder / 'parts.csv.zip'
                if case == 'missing':
                    path.unlink()
                elif case == 'both formats':
                    with zipfile.ZipFile(extra, 'w') as z:
                        z.write(path, path.name)
                else:
                    path.write_text('wrong\nx\n' if case == 'missing header'
                                    else 'part_num,name,name\np1,Brick,Brick\n', encoding='utf-8')
                self.reject_import()
                extra.unlink(missing_ok=True)

    def test_invalid_csv_values_roll_back_the_whole_import(self):
        self.collection.add_set('A-1', 2)
        cases = [('inventory_parts', 'quantity', v) for v in ('0', '-1', '1.5', 'abc', '')]
        cases += [('inventories', 'version', '0'), ('sets', 'num_parts', '-1'),
                  ('sets', 'year', 'bad'), ('inventory_parts', 'is_spare', 'yes'),
                  ('inventory_parts', 'part_num', 'unknown'),
                  ('inventory_parts', 'color_id', '999'),
                  ('inventories', 'set_num', 'unknown')]
        for table, field, value in cases:
            with self.subTest(table=table, field=field, value=value):
                write_catalogue(self.folder)
                self.change(table, field, value)
                self.reject_import()

    def test_bad_row_width_duplicate_key_and_empty_required_table(self):
        for case in ('short row', 'long row', 'duplicate key', 'empty table', 'ambiguous owner'):
            with self.subTest(case=case):
                write_catalogue(self.folder)
                if case == 'short row': self.append('inventory_parts', (2, 'p2', 0))
                elif case == 'long row': self.append('inventory_parts', (2, 'p2', 0, 1, 'False', 'extra'))
                elif case == 'duplicate key': self.append('parts', ('p1', 'Duplicate'))
                elif case == 'ambiguous owner': self.append('minifigs', ('A-1', 'Collision', 1))
                else: (self.folder / 'parts.csv').write_text('part_num,name\n', encoding='utf-8')
                self.reject_import()

    def test_corrupt_zip_is_reported_and_changes_nothing(self):
        (self.folder / 'parts.csv').unlink()
        (self.folder / 'parts.csv.zip').write_bytes(b'not a zip file')
        self.reject_import((DataError, zipfile.BadZipFile))

    def test_failed_first_import_stays_not_ready(self):
        other = DatabaseManager(self.folder / 'empty.sqlite3')
        try:
            (self.folder / 'parts.csv').unlink()
            with self.assertRaises(DataError): DataImporter(other).publish_atomically(self.folder)
            self.assertFalse(other.catalogue_ready())
            self.assertEqual(other.generation, 0)
            with self.assertRaises(DataError): SetService(other).search_sets()
        finally:
            other.close()

    def test_theme_and_nested_set_cycles_are_rejected(self):
        self.change('themes', 'parent_id', 2)
        self.reject_import()
        write_catalogue(self.folder)
        self.append('inventory_sets', (2, 'N-1', 1))
        self.reject_import()

    def test_valid_reimport_preserves_ownership_and_refreshes_results(self):
        self.collection.add_set('A-1', 2)
        old = self.build.check_target('A-1')
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 6)
        self.change('inventory_parts', 'quantity', 4, row=1)
        self.importer.publish_atomically(self.folder)
        self.assertEqual(self.collection.list_owned_sets()[0]['quantity'], 2)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 8)
        with self.assertRaises(DataError): self.build.missing_items(old)

    def test_reimport_cannot_discard_an_owned_set(self):
        self.collection.add_set('A-1', 2)
        removals = [('sets', 'set_num', {'A-1'}),
                    ('inventories', 'set_num', {'A-1'}),
                    ('inventory_parts', 'inventory_id', {'1', '2'}),
                    ('inventory_minifigs', 'inventory_id', {'1', '2'}),
                    ('inventory_sets', 'set_num', {'A-1'})]
        for table, field, excluded in removals:
            path = self.folder / (table + '.csv')
            with path.open(newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames
                rows = [r for r in reader if r[field] not in excluded]
            with path.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                writer.writerows(rows)
        self.reject_import()

    def test_add_existing_set_accumulates_copies(self):
        self.assertEqual(self.collection.list_owned_sets(), [])
        self.collection.add_set('A-1', 1)
        self.collection.add_set('A-1', ' 2 ')
        self.assertEqual(len(self.collection.list_owned_sets()), 1)
        self.assertEqual(self.collection.list_owned_sets()[0]['quantity'], 3)

    def test_invalid_add_and_update_quantities_do_not_change_data(self):
        self.collection.add_set('A-1', 2)
        invalid = (0, -1, 1.0, '1.5', 'abc', True, '', None, '١', '+1',
                   9223372036854775808, '9' * 5000)
        for action in (self.collection.add_set, self.collection.update_quantity):
            for value in invalid:
                with self.subTest(action=action.__name__, value=str(value)[:25]):
                    before = self.snapshot()
                    with self.assertRaises(ValidationError): action('A-1', value)
                    self.assertEqual(self.snapshot(), before)

    def test_unknown_and_unowned_sets_are_rejected(self):
        for action, args in ((self.collection.add_set, ('unknown', 1)),
                             (self.collection.update_quantity, ('A-1', 1)),
                             (self.collection.remove_set, ('A-1',))):
            with self.subTest(action=action.__name__):
                with self.assertRaises(ValidationError): action(*args)
        self.assertEqual(self.collection.list_owned_sets(), [])

    def test_add_update_and_remove_survive_restart(self):
        self.collection.add_set('A-1', 2)
        self.restart()
        self.assertEqual(self.collection.list_owned_sets()[0]['quantity'], 2)
        self.collection.update_quantity('A-1', 4)
        self.restart()
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 12)
        self.collection.remove_set('A-1')
        self.restart()
        self.assertEqual(self.collection.list_owned_sets(), [])
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 0)

    def test_piece_totals_use_latest_inventory_and_exclude_spares(self):
        self.collection.add_set('A-1', 2)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 6)
        self.assertEqual(self.collection.get_piece_quantity('p1', 0), 0)
        self.collection.add_set('B-1', 1)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 11)

    def test_minifigure_component_parts_are_not_double_counted(self):
        self.collection.add_set('A-1', 1)
        self.assertEqual(self.collection.get_piece_quantity('p2', 0), 0)
        self.assertEqual(self.resolver.aggregate_owned(self.collection.list_owned_sets()).minifigs['fig-1'], 1)

    def test_invalid_piece_and_colour_are_rejected(self):
        for part, color in (('unknown', 1), ('p1', 999)):
            with self.subTest(part=part, color=color):
                with self.assertRaises(ValidationError): self.collection.get_piece_quantity(part, color)

    def test_empty_collection_reports_every_required_item_missing(self):
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 0)
        result = self.build.check_target('B-1')
        self.assertEqual(result.status, 'NOT_BUILDABLE')
        self.assertEqual([r.missing for r in self.build.missing_items(result)], [5, 1])

    def test_missing_report_has_correct_identifiers_names_and_quantities(self):
        self.collection.add_set('A-1', 1)
        result = self.build.check_target('B-1')
        self.assertEqual(result.status, 'NOT_BUILDABLE')
        rows = self.build.missing_items(result)
        actual = [(r.item_type, r.identifier, r.name, r.color, r.required, r.available, r.missing) for r in rows]
        self.assertEqual(actual, [('Part', 'p1', 'Brick', 'Red', 5, 3, 2),
                                  ('Minifigure', 'fig-2', 'Other person', '-', 1, 0, 1)])

    def test_enough_parts_still_requires_the_correct_minifigure(self):
        self.collection.add_set('A-1', 2)
        result = self.build.check_target('B-1')
        self.assertEqual(result.status, 'NOT_BUILDABLE')
        self.assertEqual([r.identifier for r in self.build.missing_items(result)], ['fig-2'])

    def test_blue_parts_cannot_satisfy_a_red_part_requirement(self):
        self.collection.add_set('C-1', 1)
        result = self.build.check_target('B-1')
        self.assertEqual(result.status, 'NOT_BUILDABLE')
        self.assertEqual([(r.identifier, r.color, r.missing) for r in self.build.missing_items(result)], [('p1', 'Red', 5)])

    def test_buildable_surplus_and_repeated_checks_do_not_consume_items(self):
        self.collection.add_set('B-1', 1)
        self.collection.add_set('A-1', 2)
        before = self.snapshot()
        for _ in range(2):
            result = self.build.check_target('B-1')
            self.assertEqual(result.status, 'BUILDABLE')
            self.assertEqual(self.build.missing_items(result), [])
            self.assertTrue(all(r.missing == 0 for r in result.rows))
        self.assertEqual(self.snapshot(), before)

    def test_nested_owned_and_target_sets_use_contained_quantities(self):
        self.collection.add_set('N-1', 2)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 12)
        self.assertEqual(self.resolver.aggregate_owned(self.collection.list_owned_sets()).minifigs['fig-1'], 4)
        self.collection.remove_set('N-1')
        self.collection.add_set('A-1', 2)
        self.assertEqual(self.build.check_target('N-1').status, 'BUILDABLE')

    def test_overlapping_nested_contents_are_an_error(self):
        self.append('inventory_parts', (4, 'p1', 1, 1, 'False'))
        self.importer.publish_atomically(self.folder)
        with self.assertRaisesRegex(DataError, 'overlap'): self.build.check_target('N-1')

    def test_disjoint_direct_and_nested_contents_are_both_counted(self):
        self.append('inventory_parts', (4, 'p2', 0, 1, 'False'))
        self.importer.publish_atomically(self.folder)
        self.collection.add_set('N-1', 1)
        self.assertEqual(self.collection.get_piece_quantity('p1', 1), 6)
        self.assertEqual(self.collection.get_piece_quantity('p2', 0), 1)

    def test_missing_empty_and_unknown_inventories_are_errors(self):
        for target in ('E-1', 'unknown'):
            with self.subTest(target=target):
                with self.assertRaises(DataError): self.build.check_target(target)
        self.append('inventories', (7, 1, 'E-1'))
        self.importer.publish_atomically(self.folder)
        with self.assertRaises(DataError): self.build.check_target('E-1')
        self.collection.add_set('E-1', 1)
        with self.assertRaises(DataError): self.collection.get_piece_quantity('p1', 1)

    def test_search_name_number_parent_theme_and_combined_filters(self):
        ids = lambda rows: [r['set_num'] for r in rows]
        self.assertEqual(ids(self.sets.search_sets('A-1')), ['A-1'])
        self.assertEqual(ids(self.sets.search_sets(' target ', 1, 2025)), ['B-1'])
        self.assertEqual(ids(self.sets.search_sets(theme=2)), ['A-1', 'B-1'])
        self.assertEqual(ids(self.sets.search_sets(theme=1)), ['A-1', 'B-1', 'E-1', 'N-1'])
        self.assertEqual(self.sets.search_sets('Target', 3), [])
        self.assertEqual(self.sets.search_sets('Target', year=2024), [])
        self.assertEqual(self.sets.search_sets(theme=999), [])
        self.assertEqual(len(self.sets.search_sets(limit=2)), 2)

    def test_search_input_is_literal_and_does_not_change_data(self):
        before = self.snapshot()
        for text in ('%', '_', '\\', "' OR 1=1 --", 'not found'):
            with self.subTest(text=text): self.assertEqual(self.sets.search_sets(text), [])
        self.assertEqual(self.snapshot(), before)

    def test_collection_queries_and_build_checks_need_no_network(self):
        self.collection.add_set('B-1', 1)
        with patch('socket.create_connection', side_effect=AssertionError('Network used')):
            self.assertEqual(self.collection.get_piece_quantity('p1', 1), 5)
            self.assertEqual(self.build.check_target('B-1').status, 'BUILDABLE')
            self.assertEqual(len(self.sets.search_sets('B-1')), 1)


if __name__ == '__main__':
    unittest.main()
