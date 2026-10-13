"""Stream plain CSV or CSV ZIP files into an atomic catalogue transaction."""
import csv
import io
from pathlib import Path
import sqlite3
import zipfile
from contextlib import contextmanager
from database import DataError


# The application deliberately imports fewer fields than the Task 1 source model.
FILES = {
    'themes': ('id', 'name', 'parent_id'),
    'colors': ('id', 'name'),
    'parts': ('part_num', 'name'),
    'sets': ('set_num', 'name', 'year', 'theme_id', 'num_parts'),
    'minifigs': ('fig_num', 'name', 'num_parts'),
    'inventories': ('id', 'version', 'set_num'),
    'inventory_parts': ('inventory_id', 'part_num', 'color_id', 'quantity', 'is_spare'),
    'inventory_minifigs': ('inventory_id', 'fig_num', 'quantity'),
    'inventory_sets': ('inventory_id', 'set_num', 'quantity'),
}
INTS = {'id', 'parent_id', 'year', 'theme_id', 'num_parts', 'version',
        'inventory_id', 'color_id', 'quantity'}


@contextmanager
def csv_stream(path, table):
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist()
                       if Path(n).name == table + '.csv' and not n.endswith('/')]
            if len(members) != 1:
                raise DataError(f'{path.name}: expected exactly one {table}.csv.')
            with archive.open(members[0]) as raw:
                with io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as stream:
                    yield stream
    else:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            yield stream


class DataImporter:
    def __init__(self, db):
        self.db = db

    def validate_files(self, folder):
        folder = Path(folder)
        paths = {}
        for table, fields in FILES.items():
            candidates = [folder / (table + suffix) for suffix in ('.csv', '.csv.zip')]
            found = [p for p in candidates if p.is_file()]
            if len(found) != 1:
                raise DataError(f'Provide exactly one {table}.csv or {table}.csv.zip in the folder.')
            with csv_stream(found[0], table) as stream:
                header = next(csv.reader(stream), [])
                if len(header) != len(set(header)) or not set(fields).issubset(header):
                    raise DataError(f'{found[0].name}: missing or duplicate column names.')
            paths[table] = found[0]
        return paths

    def normalize_inventory_ownership(self, owner, sets, figures):
        is_set, is_figure = owner in sets, owner in figures
        if is_set == is_figure:
            raise DataError(f'Inventory owner {owner!r} must match exactly one set or minifigure.')
        return (owner, None) if is_set else (None, owner)

    def _values(self, row, fields):
        values = []
        for field in fields:
            text = row[field]
            if text == '' and field == 'parent_id':
                values.append(None)
            elif text == '':
                raise DataError(f'{field} must not be blank.')
            elif field == 'is_spare':
                if text not in ('True', 'False'):
                    raise DataError('is_spare must be True or False.')
                values.append(int(text == 'True'))
            elif field in INTS:
                try:
                    if text.strip() != text or any(c not in '-0123456789' for c in text):
                        raise ValueError()
                    value = int(text)
                except ValueError:
                    raise DataError(f'{field} must be an integer, got {text!r}.') from None
                if field in ('quantity', 'version') and value <= 0:
                    raise DataError(f'{field} must be positive.')
                if field == 'num_parts' and value < 0:
                    raise DataError('num_parts must not be negative.')
                values.append(value)
            else:
                values.append(text)
        return values

    def stage_and_validate_graph(self):
        """Reject catalogue cycles while still inside the import transaction."""
        parents = {r['id']: r['parent_id'] for r in self.db.read('SELECT id,parent_id FROM themes')}
        self._acyclic({k: [v] if v is not None else [] for k, v in parents.items()}, 'theme')
        latest = self.db.read('''SELECT i.id,i.set_num FROM inventories i
          WHERE i.set_num IS NOT NULL AND i.version=(
            SELECT MAX(j.version) FROM inventories j WHERE j.set_num=i.set_num)''')
        owners = {r['id']: r['set_num'] for r in latest}
        edges = {owner: [] for owner in owners.values()}
        for row in self.db.read('SELECT inventory_id,set_num FROM inventory_sets'):
            if row['inventory_id'] in owners:
                edges[owners[row['inventory_id']]].append(row['set_num'])
        self._acyclic(edges, 'nested set')

    @staticmethod
    def _acyclic(graph, kind):
        done = set()
        for start in graph:
            if start in done:
                continue
            visiting = set()
            stack = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    visiting.discard(node)
                    done.add(node)
                elif node not in done:
                    if node in visiting:
                        raise DataError(f'Cycle detected in {kind} data at {node}.')
                    visiting.add(node)
                    stack.append((node, True))
                    stack.extend((child, False) for child in graph.get(node, []))

    def publish_atomically(self, folder, progress=lambda message: None):
        paths = self.validate_files(folder)
        counts = {}
        try:
            with self.db.transaction() as conn:
                # No partially loaded catalogue is ever published. A rollback retains
                # both the old catalogue and the user's collection on any failure.
                conn.execute('PRAGMA defer_foreign_keys=ON')
                saved = list(conn.execute('SELECT set_num,quantity FROM owned_sets'))
                conn.execute('DELETE FROM owned_sets')
                for table in reversed(FILES):
                    conn.execute('DELETE FROM ' + table)
                known_sets, known_figures = set(), set()
                for table, fields in FILES.items():
                    progress('Importing ' + table + '...')
                    columns = list(fields)
                    if table == 'inventories':
                        columns.append('fig_num')
                    sql = f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})'
                    batch, count = [], 0
                    with csv_stream(paths[table], table) as stream:
                        reader = csv.DictReader(stream)
                        for line, row in enumerate(reader, 2):
                            try:
                                if None in row or any(v is None for v in row.values()):
                                    raise DataError('Row width does not match the header.')
                                values = self._values(row, fields)
                                if table == 'sets':
                                    known_sets.add(row['set_num'])
                                elif table == 'minifigs':
                                    known_figures.add(row['fig_num'])
                                elif table == 'inventories':
                                    values[-1:] = self.normalize_inventory_ownership(row['set_num'], known_sets, known_figures)
                                batch.append(values)
                                count += 1
                                if len(batch) == 2000:
                                    conn.executemany(sql, batch)
                                    batch.clear()
                            except (ValueError, sqlite3.Error) as exc:
                                raise DataError(f'{paths[table].name}, near row {line}: {exc}') from exc
                        if batch:
                            conn.executemany(sql, batch)
                    if count == 0 and table in ('sets', 'inventories', 'parts', 'colors', 'themes'):
                        raise DataError(f'{table}.csv contains no data.')
                    counts[table] = count
                conn.executemany('INSERT INTO owned_sets VALUES (?,?)', saved)
                violation = conn.execute('PRAGMA foreign_key_check').fetchone()
                if violation:
                    raise DataError(f'Invalid reference in {violation[0]} (row {violation[1]}). '
                                    'A saved owned set may also be absent from the replacement catalogue.')
                self.stage_and_validate_graph()
                conn.execute("UPDATE import_state SET ready=1,generation=generation+1,completed_at=datetime('now') WHERE id=1")
            progress('Import complete. Catalogue ready; collection retained.')
            return counts
        except (sqlite3.Error, OSError, zipfile.BadZipFile, UnicodeError, csv.Error) as exc:
            raise DataError(f'Import failed: {exc}') from exc
