"""Offline tests using temporary databases and synthetic catalogue data."""
import csv
from io import BytesIO, StringIO
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from database import DatabaseManager, DataError
from importer import DataImporter, load_image_urls
from services import CollectionService, InventoryResolver, SetService
from views import ImageLoader

CDN = "https://cdn.rebrickable.com/media/"
DATA = {
    "themes": "id,name,parent_id\n1,Root,\n2,Child,1\n3,Other,\n",
    "colors": "id,name\n0,Black\n4,Red\n",
    "parts": "part_num,name\np1,Brick\np2,Tile\n",
    "sets": "set_num,name,year,theme_id,num_parts\nA-1,Alpha,2020,2,3\nB-1,Beta,2021,3,1\n",
    "minifigs": "fig_num,name,num_parts\nfig-1,Figure,1\n",
    "inventories": "id,version,set_num\n1,1,A-1\n2,1,B-1\n",
    "inventory_parts": "inventory_id,part_num,color_id,quantity,is_spare\n1,p1,0,2,False\n1,p1,4,1,False\n2,p2,0,1,False\n",
    "inventory_minifigs": "inventory_id,fig_num,quantity\n1,fig-1,1\n",
    "inventory_sets": "inventory_id,set_num,quantity\n",
}
IMAGE_TABLES = ("sets", "minifigs", "inventory_parts")


class ImageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.db = DatabaseManager(self.folder / "test.db")
        self.addCleanup(self.db.close)
        self.write_csvs()
        DataImporter(self.db).publish_atomically(self.folder)

    def write_csvs(self, images=False):
        for table, text in DATA.items():
            rows = list(csv.reader(StringIO(text)))
            if images and table in IMAGE_TABLES:
                rows[0].append("img_url")
                for row in rows[1:]:
                    key = (
                        f"{row[1]}-{row[2]}"
                        if table == "inventory_parts" else row[0]
                    )
                    row.append(f"{CDN}{table}/{key}.png")
            with (self.folder / f"{table}.csv").open(
                "w", newline="", encoding="utf-8"
            ) as file:
                csv.writer(file).writerows(rows)

    def archive(self, overrides=None):
        self.write_csvs(images=True)
        path = self.folder / "images.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for table in IMAGE_TABLES:
                text = (overrides or {}).get(
                    table, (self.folder / f"{table}.csv").read_text()
                )
                archive.writestr(f"{table}.csv", text)
        return path

    def snapshot(self, images=True):
        result = {}
        for table in (*DATA, "owned_sets", "import_state"):
            columns = [
                row["name"]
                for row in self.db.read(f"PRAGMA table_info({table})")
                if images or row["name"] != "img_url"
            ]
            result[table] = [
                tuple(row) for row in self.db.read(
                    f'SELECT {",".join(columns)} FROM {table} ORDER BY rowid'
                )
            ]
        return result

    def test_optional_image_columns(self):
        self.assertEqual(self.db.image_url("set", "A-1"), "")
        self.write_csvs(images=True)
        DataImporter(self.db).publish_atomically(self.folder)
        self.assertEqual(
            self.db.image_url("set", "A-1"), CDN + "sets/A-1.png"
        )
        self.assertEqual(
            self.db.image_url("minifigure", "fig-1"),
            CDN + "minifigs/fig-1.png",
        )
        self.assertEqual(
            self.db.image_url("part", "p1", 0),
            CDN + "inventory_parts/p1-0.png",
        )

    def test_enrichment_preserves_catalogue_and_owned_copies(self):
        collection = CollectionService(self.db, InventoryResolver(self.db))
        collection.add_set("A-1", 2)
        collection.add_set("B-1", 3)
        before = self.snapshot(images=False)
        updates = {
            "sets": f"set_num,img_url\nA-1,{CDN}a.png\nOUTSIDE,{CDN}outside.png\n",
            "minifigs": f"fig_num,img_url\nfig-1,{CDN}figure.png\nfig-out,{CDN}outside.png\n",
            "inventory_parts": f"inventory_id,part_num,color_id,is_spare,img_url\n1,p1,0,False,{CDN}part.png\n999,p1,0,False,{CDN}outside.png\n",
        }
        load_image_urls(self.db, self.archive(updates))
        self.assertEqual(self.snapshot(images=False), before)
        self.assertEqual(self.db.image_url("set", "A-1"), CDN + "a.png")

    def test_image_import_rolls_back(self):
        before = self.snapshot()
        bad = {
            "inventory_parts":
                "inventory_id,part_num,color_id,is_spare,img_url\n"
                "1,p1,0,invalid,x\n"
        }
        with self.assertRaises(DataError):
            load_image_urls(self.db, self.archive(bad))
        self.assertEqual(self.snapshot(), before)

    def test_exact_colour_and_blank_image(self):
        load_image_urls(self.db, self.archive())
        for colour in (0, 4):
            self.assertEqual(
                self.db.image_url("part", "p1", colour),
                CDN + f"inventory_parts/p1-{colour}.png",
            )
        self.assertEqual(self.db.image_url("part", "p1", 99), "")
        original = self.db.image_url("set", "A-1")
        load_image_urls(
            self.db, self.archive({"sets": "set_num,img_url\nA-1,\n"})
        )
        self.assertEqual(self.db.image_url("set", "A-1"), original)

    def test_parent_theme_filters_include_children(self):
        service = SetService(self.db)
        self.assertEqual(
            [row["set_num"] for row in service.search_sets(theme=1)],
            ["A-1"],
        )
        self.assertEqual(
            [row["set_num"] for row in service.search_sets("Alpha", 1, 2020)],
            ["A-1"],
        )
        self.assertEqual(service.search_sets("Alpha", 3), [])
        self.assertEqual(service.search_sets("Alpha", year=2021), [])

    def test_migration_preserves_existing_data(self):
        path = self.folder / "legacy.db"
        old = {
            "sets": (
                "set_num TEXT PRIMARY KEY,name TEXT,year INT,theme_id INT,num_parts INT",
                ("A-1", "Saved", 2020, 2, 3),
            ),
            "minifigs": (
                "fig_num TEXT PRIMARY KEY,name TEXT,num_parts INT",
                ("fig-1", "Figure", 1),
            ),
            "inventory_parts": (
                "inventory_id INT,part_num TEXT,color_id INT,is_spare INT,quantity INT",
                (1, "p1", 0, 0, 2),
            ),
            "owned_sets": (
                "set_num TEXT PRIMARY KEY,quantity INT", ("A-1", 2)
            ),
            "import_state": (
                "id INT PRIMARY KEY,ready INT,generation INT,completed_at TEXT",
                (1, 1, 7, "previous import"),
            ),
        }
        with sqlite3.connect(path) as connection:
            for table, (schema, row) in old.items():
                connection.execute(f"CREATE TABLE {table} ({schema})")
                placeholders = ",".join("?" for _ in row)
                connection.execute(
                    f"INSERT INTO {table} VALUES ({placeholders})", row
                )
        connection.close()

        for _ in range(2):
            db = DatabaseManager(path)
            try:
                for table, (_, row) in old.items():
                    actual = tuple(db.read(f"SELECT * FROM {table}")[0])
                    expected = row + ("",) if table in IMAGE_TABLES else row
                    self.assertEqual(actual, expected)
                self.assertTrue(db.catalogue_ready())
                self.assertEqual(db.generation, 7)
            finally:
                db.close()

    def test_thumbnail_cache_and_image_failures(self):
        loader = ImageLoader(Mock(), self.folder / "cache")
        self.addCleanup(loader.close)
        url = CDN + "sets/A-1.png"
        png = BytesIO()
        Image.new("RGB", (400, 200), "red").save(png, format="PNG")

        with patch("views.urlopen", return_value=BytesIO(png.getvalue())):
            thumbnail = loader._fetch(url)
        self.assertEqual(thumbnail.size, (180, 90))

        with patch("views.urlopen", side_effect=OSError("offline")) as request:
            cached = loader._fetch(url)
            request.assert_not_called()
            self.assertEqual(cached.tobytes(), thumbnail.tobytes())
            self.assertIsNone(loader._fetch(CDN + "missing.png"))

        with patch("views.urlopen", return_value=BytesIO(b"invalid image")):
            self.assertIsNone(loader._fetch(CDN + "invalid.png"))

        callback = Mock()
        loader.load("", callback)
        callback.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
