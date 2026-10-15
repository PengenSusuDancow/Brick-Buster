"""Offline image tests. All catalogue rows and image responses are synthetic."""
import csv
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from PIL import Image
from database import DatabaseManager, DataError
from importer import DataImporter, load_image_urls
from services import BuildService, CollectionService, InventoryResolver, SetService
from views import ImageLoader


CDN = 'https://cdn.rebrickable.com/media/'


def csv_text(header, rows):
    stream = StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(header.split(','))
    writer.writerows(rows)
    return stream.getvalue()


def catalogue_csvs(images=False):
    """Synthetic fixtures only; these are not real LEGO catalogue records."""
    tables = {
        'themes': ('id,name,parent_id', [(1, 'Ninjago', ''), (2, 'Legacy', 1),
                                        (3, 'Classic', ''), (4, 'Technic', '')]),
        'sets': ('set_num,name,year,theme_id,num_parts', [
            ('A-1', 'Dragon Tower', 2020, 2, 3),
            ('B-1', 'Creative Box', 2017, 3, 1),
            ('C-1', 'Loader', 2016, 4, 1)]),
        'minifigs': ('fig_num,name,num_parts', [('fig-1', 'Figure', 1)]),
        'parts': ('part_num,name', [('p1', 'Brick'), ('p2', 'Plate')]),
        'colors': ('id,name', [(0, 'Black'), (4, 'Red'), (1, 'Blue')]),
        'inventories': ('id,version,set_num', [(101, 1, 'A-1'),
            (102, 1, 'B-1'), (103, 1, 'C-1'), (201, 1, 'fig-1')]),
        'inventory_parts': ('inventory_id,part_num,color_id,quantity,is_spare', [
            (101, 'p1', 0, 2, 'False'), (101, 'p1', 4, 1, 'False'),
            (102, 'p2', 0, 1, 'False'), (103, 'p1', 1, 1, 'False'),
            (201, 'p1', 1, 1, 'False')]),
        'inventory_minifigs': ('inventory_id,fig_num,quantity', [(101, 'fig-1', 1)]),
        'inventory_sets': ('inventory_id,set_num,quantity', []),
    }
    if images:
        for table in ('sets', 'minifigs', 'inventory_parts'):
            header, rows = tables[table]
            if table == 'inventory_parts':
                rows = [(*row, CDN + f'parts/{row[1]}-{row[2]}.jpg') for row in rows]
            else:
                rows = [(*row, CDN + f'{table}/{row[0]}.jpg') for row in rows]
            tables[table] = (header + ',img_url', rows)
    return {table: csv_text(*data) for table, data in tables.items()}


class CatalogueImageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.db = DatabaseManager(self.folder / 'catalogue.sqlite3')
        self.addCleanup(self.db.close)

    def import_catalogue(self, images=False):
        source = self.folder / 'csvs'
        source.mkdir(exist_ok=True)
        for table, content in catalogue_csvs(images).items():
            (source / (table + '.csv')).write_text(content, encoding='utf-8')
        DataImporter(self.db).publish_atomically(source)

    def image_archive(self, overrides=None):
        files = catalogue_csvs(images=True)
        files.update(overrides or {})
        archive_path = self.folder / 'images.zip'
        with zipfile.ZipFile(archive_path, 'w') as archive:
            for table in ('sets', 'minifigs', 'inventory_parts'):
                archive.writestr(table + '.csv', files[table])
        return archive_path

    def test_csv_image_columns_are_optional(self):
        self.import_catalogue()
        self.assertEqual(self.db.image_url('set', 'A-1'), '')
        self.assertEqual(self.db.image_url('part', 'p1', 0), '')
        self.import_catalogue(images=True)
        self.assertEqual(self.db.image_url('set', 'A-1'), CDN + 'sets/A-1.jpg')
        self.assertEqual(self.db.image_url('minifigure', 'fig-1'), CDN + 'minifigs/fig-1.jpg')

    def test_enrichment_only_updates_existing_items_and_preserves_collection(self):
        self.import_catalogue()
        resolver = InventoryResolver(self.db)
        collection = CollectionService(self.db, resolver)
        collection.add_set('A-1', 2)
        collection.add_set('B-1', 3)
        build = BuildService(collection, resolver)
        before_result = build.check_target('C-1')
        before_state = tuple(self.db.read('SELECT * FROM import_state')[0])
        files = catalogue_csvs(images=True)
        files['sets'] += 'OUTSIDE-1,Outside catalogue,2026,1,1,' + CDN + 'outside.jpg\n'
        files['minifigs'] += 'fig-outside,Outside figure,1,' + CDN + 'outside-figure.jpg\n'
        files['inventory_parts'] += '999,p1,0,20,False,' + CDN + 'outside-part.jpg\n'
        counts = load_image_urls(self.db, self.image_archive(files))
        self.assertEqual(counts, {'sets': 3, 'minifigs': 1, 'inventory_parts': 5})
        self.assertEqual([tuple(row) for row in self.db.read('SELECT * FROM owned_sets ORDER BY set_num')],
                         [('A-1', 2), ('B-1', 3)])
        self.assertEqual(tuple(self.db.read('SELECT * FROM import_state')[0]), before_state)
        self.assertEqual(self.db.read('SELECT count(*) FROM sets')[0][0], 3)
        self.assertEqual(self.db.read('SELECT count(*) FROM minifigs')[0][0], 1)
        self.assertEqual(self.db.read('SELECT count(*) FROM inventory_parts')[0][0], 5)
        self.assertEqual(build.check_target('C-1'), before_result)
        self.assertEqual(self.db.image_url('set', 'A-1'), CDN + 'sets/A-1.jpg')
        self.assertEqual(self.db.image_url('set', 'B-1'), CDN + 'sets/B-1.jpg')
        self.assertEqual(self.db.image_url('part', 'p1', 0), CDN + 'parts/p1-0.jpg')
        self.assertEqual(self.db.image_url('part', 'p1', 4), CDN + 'parts/p1-4.jpg')

    def test_blank_enrichment_url_keeps_existing_image(self):
        self.import_catalogue(images=True)
        original = self.db.image_url('set', 'A-1')
        archive = self.image_archive({'sets': 'set_num,img_url\nA-1,\n'})
        self.assertEqual(load_image_urls(self.db, archive)['sets'], 0)
        self.assertEqual(self.db.image_url('set', 'A-1'), original)

    def test_invalid_later_table_rolls_back_earlier_image_updates(self):
        self.import_catalogue(images=True)
        original = self.db.image_url('set', 'A-1')
        archive = self.image_archive({
            'sets': 'set_num,img_url\nA-1,' + CDN + 'replacement.jpg\n',
            'inventory_parts': 'inventory_id,part_num,color_id,is_spare,img_url\n'
                               '101,p1,0,invalid,' + CDN + 'part.jpg\n',
        })
        with self.assertRaises(DataError):
            load_image_urls(self.db, archive)
        self.assertEqual(self.db.image_url('set', 'A-1'), original)

    def test_part_image_lookup_never_substitutes_another_colour(self):
        self.import_catalogue(images=True)
        self.assertEqual(self.db.image_url('part', 'p1', 0), CDN + 'parts/p1-0.jpg')
        self.assertEqual(self.db.image_url('part', 'p1', 4), CDN + 'parts/p1-4.jpg')
        self.assertEqual(self.db.image_url('part', 'p1', 15), '')
        self.assertEqual(self.db.image_url('part', 'unknown', 0), '')

    def test_parent_theme_and_combined_filters(self):
        self.import_catalogue()
        service = SetService(self.db)
        self.assertEqual([r['set_num'] for r in service.search_sets(theme=1)], ['A-1'])
        self.assertEqual([r['set_num'] for r in service.search_sets('Dragon', theme=1, year=2020)], ['A-1'])
        self.assertEqual(service.search_sets('Dragon', theme=1, year=2017), [])
        self.assertEqual(service.search_sets(theme=999), [])


class MigrationTests(unittest.TestCase):
    def test_existing_database_keeps_data_and_ownership(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.sqlite3'
            # The three pre-image table shapes and saved user state.
            with sqlite3.connect(path) as connection:
                connection.executescript('''
                    CREATE TABLE sets (set_num TEXT PRIMARY KEY, name TEXT NOT NULL,
                        year INTEGER NOT NULL, theme_id INTEGER NOT NULL, num_parts INTEGER NOT NULL);
                    CREATE TABLE minifigs (fig_num TEXT PRIMARY KEY, name TEXT NOT NULL, num_parts INTEGER NOT NULL);
                    CREATE TABLE inventory_parts (inventory_id INTEGER, part_num TEXT, color_id INTEGER,
                        is_spare INTEGER NOT NULL, quantity INTEGER NOT NULL,
                        PRIMARY KEY(inventory_id, part_num, color_id, is_spare));
                    CREATE TABLE owned_sets (set_num TEXT PRIMARY KEY, quantity INTEGER NOT NULL);
                    CREATE TABLE import_state (id INTEGER PRIMARY KEY, ready INTEGER,
                        generation INTEGER, completed_at TEXT);
                    INSERT INTO sets VALUES ('A-1','Saved set',2020,1,2);
                    INSERT INTO minifigs VALUES ('fig-1','Saved figure',1);
                    INSERT INTO inventory_parts VALUES (101,'p1',0,0,2);
                    INSERT INTO owned_sets VALUES ('A-1',2);
                    INSERT INTO import_state VALUES (1,1,7,'previous import');
                ''')
            db = DatabaseManager(path)
            try:
                for table in ('sets', 'minifigs', 'inventory_parts'):
                    self.assertIn('img_url', [r['name'] for r in db.read(f'PRAGMA table_info({table})')])
                    self.assertEqual(db.read(f'SELECT count(*) FROM {table}')[0][0], 1)
                self.assertEqual(tuple(db.read('SELECT * FROM owned_sets')[0]), ('A-1', 2))
                self.assertEqual(tuple(db.read('SELECT * FROM import_state')[0]), (1, 1, 7, 'previous import'))
                self.assertEqual(db.image_url('set', 'A-1'), '')
            finally:
                db.close()
            # Opening the migrated database again must also be harmless.
            db = DatabaseManager(path)
            try:
                self.assertEqual(db.read('SELECT quantity FROM owned_sets')[0][0], 2)
                self.assertEqual(db.generation, 7)
            finally:
                db.close()


class ImageLoaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        self.loader = ImageLoader(Mock(), self.cache)
        self.addCleanup(self.loader.close)
        self.url = CDN + 'sets/A-1.jpg'

    def test_download_creates_bounded_thumbnail_then_works_offline(self):
        data = BytesIO()
        Image.new('RGB', (600, 600), 'red').save(data, format='PNG')
        with patch('views.urlopen', return_value=BytesIO(data.getvalue())) as request:
            thumbnail = self.loader._fetch(self.url)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(thumbnail.size, (120, 120))
        path = self.cache / (sha256(self.url.encode()).hexdigest() + '.png')
        self.assertTrue(path.is_file())
        with patch('views.urlopen', side_effect=OSError('offline')) as request:
            cached = self.loader._fetch(self.url)
        request.assert_not_called()
        self.assertEqual(cached.size, thumbnail.size)
        self.assertEqual(cached.getpixel((0, 0)), thumbnail.getpixel((0, 0)))

    def test_missing_invalid_and_failed_images_are_optional(self):
        callback = Mock()
        self.loader.load('', callback)
        callback.assert_called_once_with(None)
        with patch('views.urlopen', side_effect=OSError('offline')) as request:
            self.assertIsNone(self.loader._fetch(self.url))
            self.assertEqual(request.call_count, 1)
        with patch('views.urlopen') as request:
            self.assertIsNone(self.loader._fetch('https://example.com/image.png'))
            self.assertIsNone(self.loader._fetch('http://cdn.rebrickable.com/image.png'))
            request.assert_not_called()
        with patch('views.urlopen', return_value=BytesIO(b'not an image')):
            self.assertIsNone(self.loader._fetch(self.url))


if __name__ == '__main__':
    unittest.main()
