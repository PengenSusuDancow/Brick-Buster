"""Collection rules and read-only build checks, independent of the GUI."""
from collections import Counter
from dataclasses import dataclass, field
from database import DataError, ValidationError


def positive_quantity(value):
    if isinstance(value, bool):
        raise ValidationError('Enter a positive whole number.')
    text = str(value).strip()
    if not text.isascii() or not text.isdecimal():
        raise ValidationError('Enter a positive whole number. Use Remove to delete a set.')
    if len(text) > 19 or int(text) > 9223372036854775807:
        raise ValidationError('Copy quantity is too large for the database.')
    if int(text) <= 0:
        raise ValidationError('Enter a positive whole number. Use Remove to delete a set.')
    return int(text)


@dataclass
class ItemPool:
    parts: Counter = field(default_factory=Counter)
    minifigs: Counter = field(default_factory=Counter)

    def scaled(self, copies):
        return ItemPool(Counter({k: v * copies for k, v in self.parts.items()}),
                        Counter({k: v * copies for k, v in self.minifigs.items()}))

    def add(self, other):
        self.parts.update(other.parts)
        self.minifigs.update(other.minifigs)


@dataclass
class Shortage:
    item_type: str
    identifier: str
    name: str
    color: str
    required: int
    available: int
    missing: int


@dataclass
class BuildResult:
    target: str
    status: str
    generation: int
    rows: list


class SetService:
    def __init__(self, db):
        self.db = db

    def search_sets(self, text='', theme=None, year=None, limit=500):
        self.db.require_ready()
        # Treat wildcard characters as literal search input.
        text = text.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        clauses = ["(s.set_num LIKE ? ESCAPE '\\' OR s.name LIKE ? ESCAPE '\\')"]
        params = ['%' + text + '%'] * 2
        if theme is not None:
            clauses.append('s.theme_id=?')
            params.append(theme)
        if year is not None:
            clauses.append('s.year=?')
            params.append(year)
        params.append(limit)
        return self.db.read('''SELECT s.set_num,s.name,t.name AS theme,s.year
            FROM sets s JOIN themes t ON s.theme_id=t.id WHERE ''' +
            ' AND '.join(clauses) + ' ORDER BY s.set_num LIMIT ?', params)

    def get_set(self, set_num):
        self.db.require_ready()
        rows = self.db.read('SELECT * FROM sets WHERE set_num=?', (set_num,))
        if not rows:
            raise ValidationError('Select a set from the catalogue.')
        return rows[0]

    def list_themes(self):
        return self.db.read('SELECT id,name FROM themes ORDER BY name,id')

    def list_years(self):
        return [r[0] for r in self.db.read('SELECT DISTINCT year FROM sets ORDER BY year DESC')]


class InventoryResolver:
    def __init__(self, db):
        self.db = db
        self._generation = -1
        self._cache = {}

    def _refresh(self):
        self.db.require_ready()
        if self._generation != self.db.generation:
            self._cache.clear()
            self._generation = self.db.generation

    def select_inventory(self, owner):
        rows = self.db.read('SELECT * FROM inventories WHERE set_num=? OR fig_num=? '
                            'ORDER BY version DESC LIMIT 1', (owner, owner))
        if not rows:
            raise DataError(f'No inventory is available for {owner}.')
        return rows[0]

    @staticmethod
    def validate_disjoint_contents(direct, nested, set_num):
        # CSV rows do not describe whether overlapping direct/nested entries are
        # additional items or duplicated summaries. Fail explicitly in that case.
        if direct.parts.keys() & nested.parts.keys() or direct.minifigs.keys() & nested.minifigs.keys():
            raise DataError(f'{set_num}: direct and nested contents overlap. '
                            'Their provenance must be reviewed before calculating a total.')

    def resolve_set(self, set_num, path=()):
        self._refresh()
        if set_num in path:
            raise DataError(f'Nested-set cycle involving {set_num}.')
        if len(path) >= 200:
            raise DataError('Nested-set structure is too deep to resolve safely.')
        if set_num in self._cache:
            return self._cache[set_num].scaled(1)
        if not self.db.read('SELECT 1 FROM sets WHERE set_num=?', (set_num,)):
            raise DataError(f'Unknown nested set {set_num}.')
        inv = self.select_inventory(set_num)['id']
        direct = ItemPool()
        for row in self.db.read('SELECT part_num,color_id,quantity FROM inventory_parts '
                                'WHERE inventory_id=? AND is_spare=0', (inv,)):
            direct.parts[(row['part_num'], row['color_id'])] += row['quantity']
        for row in self.db.read('SELECT fig_num,quantity FROM inventory_minifigs WHERE inventory_id=?', (inv,)):
            direct.minifigs[row['fig_num']] += row['quantity']
        nested = ItemPool()
        for row in self.db.read('SELECT set_num,quantity FROM inventory_sets WHERE inventory_id=?', (inv,)):
            nested.add(self.resolve_set(row['set_num'], path + (set_num,)).scaled(row['quantity']))
        self.validate_disjoint_contents(direct, nested, set_num)
        direct.add(nested)
        if not direct.parts and not direct.minifigs:
            raise DataError(f'{set_num}: inventory contains no usable parts or minifigures.')
        self._cache[set_num] = direct.scaled(1)
        return direct

    def aggregate_owned(self, entries):
        result = ItemPool()
        for entry in entries:
            result.add(self.resolve_set(entry['set_num']).scaled(entry['quantity']))
        return result


class CollectionService:
    def __init__(self, db, resolver):
        self.db, self.resolver = db, resolver

    def list_owned_sets(self):
        return self.db.read('SELECT o.set_num,s.name,o.quantity FROM owned_sets o '
                            'JOIN sets s USING(set_num) ORDER BY o.set_num')

    def _validate_set(self, set_num):
        SetService(self.db).get_set(set_num)

    def add_set(self, set_num, quantity):
        quantity = positive_quantity(quantity)
        self._validate_set(set_num)
        with self.db.transaction() as conn:
            conn.execute('INSERT INTO owned_sets VALUES (?,?) ON CONFLICT(set_num) '
                         'DO UPDATE SET quantity=quantity+excluded.quantity', (set_num, quantity))

    def update_quantity(self, set_num, quantity):
        quantity = positive_quantity(quantity)
        self._validate_set(set_num)
        with self.db.transaction() as conn:
            if conn.execute('UPDATE owned_sets SET quantity=? WHERE set_num=?', (quantity, set_num)).rowcount != 1:
                raise ValidationError('That set is not in your collection.')

    def remove_set(self, set_num):
        with self.db.transaction() as conn:
            if conn.execute('DELETE FROM owned_sets WHERE set_num=?', (set_num,)).rowcount != 1:
                raise ValidationError('Select an owned set to remove.')

    def get_piece_quantity(self, part_num, color_id):
        self.db.require_ready()
        if not self.db.read('SELECT 1 FROM parts WHERE part_num=?', (part_num,)):
            raise ValidationError('Select a valid part number.')
        if not self.db.read('SELECT 1 FROM colors WHERE id=?', (color_id,)):
            raise ValidationError('Select a valid colour.')
        return self.resolver.aggregate_owned(self.list_owned_sets()).parts[(part_num, color_id)]


class BuildService:
    def __init__(self, collection, resolver):
        self.collection, self.resolver = collection, resolver

    def check_target(self, set_num):
        required = self.resolver.resolve_set(set_num)
        available = self.resolver.aggregate_owned(self.collection.list_owned_sets())
        db = self.resolver.db
        rows = []
        for (part, color), count in sorted(required.parts.items()):
            names = db.read('SELECT p.name,c.name FROM parts p CROSS JOIN colors c '
                            'WHERE p.part_num=? AND c.id=?', (part, color))
            if not names:
                raise DataError(f'Missing part/colour metadata for {part}/{color}.')
            owned = available.parts[(part, color)]
            rows.append(Shortage('Part', part, names[0][0], names[0][1], count, owned, max(count-owned, 0)))
        for fig, count in sorted(required.minifigs.items()):
            names = db.read('SELECT name FROM minifigs WHERE fig_num=?', (fig,))
            if not names:
                raise DataError(f'Missing minifigure metadata for {fig}.')
            owned = available.minifigs[fig]
            rows.append(Shortage('Minifigure', fig, names[0][0], '-', count, owned, max(count-owned, 0)))
        status = 'NOT_BUILDABLE' if any(r.missing for r in rows) else 'BUILDABLE'
        return BuildResult(set_num, status, db.generation, rows)

    def missing_items(self, result):
        if result.generation != self.resolver.db.generation:
            raise DataError('Catalogue changed. Run the build check again.')
        return [row for row in result.rows if row.missing > 0]
