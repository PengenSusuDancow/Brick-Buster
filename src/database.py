"""SQLite storage. Only standard-library dependencies are needed."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class DataError(ValueError):
    """The catalogue cannot safely support the requested calculation."""


class ValidationError(ValueError):
    """An input value does not satisfy the application rules."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS themes (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL,
 parent_id INTEGER REFERENCES themes(id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE IF NOT EXISTS sets (
 set_num TEXT PRIMARY KEY, name TEXT NOT NULL, year INTEGER NOT NULL,
 theme_id INTEGER NOT NULL REFERENCES themes(id), num_parts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS minifigs (
 fig_num TEXT PRIMARY KEY, name TEXT NOT NULL, num_parts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS parts (part_num TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS colors (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventories (
 id INTEGER PRIMARY KEY, version INTEGER NOT NULL CHECK(version > 0),
 set_num TEXT REFERENCES sets(set_num), fig_num TEXT REFERENCES minifigs(fig_num),
 CHECK ((set_num IS NOT NULL) != (fig_num IS NOT NULL)),
 UNIQUE(set_num, version), UNIQUE(fig_num, version));
CREATE TABLE IF NOT EXISTS inventory_parts (
 inventory_id INTEGER REFERENCES inventories(id), part_num TEXT REFERENCES parts(part_num),
 color_id INTEGER REFERENCES colors(id), is_spare INTEGER NOT NULL CHECK(is_spare IN (0,1)),
 quantity INTEGER NOT NULL CHECK(quantity > 0),
 PRIMARY KEY(inventory_id, part_num, color_id, is_spare));
CREATE TABLE IF NOT EXISTS inventory_minifigs (
 inventory_id INTEGER REFERENCES inventories(id), fig_num TEXT REFERENCES minifigs(fig_num),
 quantity INTEGER NOT NULL CHECK(quantity > 0), PRIMARY KEY(inventory_id, fig_num));
CREATE TABLE IF NOT EXISTS inventory_sets (
 inventory_id INTEGER REFERENCES inventories(id), set_num TEXT REFERENCES sets(set_num),
 quantity INTEGER NOT NULL CHECK(quantity > 0), PRIMARY KEY(inventory_id, set_num));
CREATE TABLE IF NOT EXISTS owned_sets (
 set_num TEXT PRIMARY KEY REFERENCES sets(set_num),
 quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0));
CREATE TABLE IF NOT EXISTS import_state (
 id INTEGER PRIMARY KEY CHECK(id=1), ready INTEGER NOT NULL CHECK(ready IN (0,1)),
 generation INTEGER NOT NULL CHECK(generation>=0), completed_at TEXT);
INSERT OR IGNORE INTO import_state VALUES (1,0,0,NULL);
CREATE INDEX IF NOT EXISTS inventory_owner ON inventories(set_num, version);
CREATE INDEX IF NOT EXISTS figure_owner ON inventories(fig_num, version);
"""


class DatabaseManager:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.executescript(SCHEMA)

    @property
    def generation(self):
        return self.read('SELECT generation FROM import_state WHERE id=1')[0][0]

    def catalogue_ready(self):
        return bool(self.read('SELECT ready FROM import_state WHERE id=1')[0][0])

    def require_ready(self):
        if not self.catalogue_ready():
            raise DataError('Import the Rebrickable data before using this feature.')

    def read(self, query, params=()):
        return self.connection.execute(query, params).fetchall()

    @contextmanager
    def transaction(self):
        try:
            self.connection.execute('BEGIN IMMEDIATE')
            yield self.connection
            self.commit()
        except Exception:
            self.rollback()
            raise

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()
