"""Tkinter screens and event handlers for Brick Buster."""
from dataclasses import astuple
from pathlib import Path
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from database import DatabaseManager, DataError, ValidationError
from importer import DataImporter, FILES, load_image_urls
from views import ImageLoader, ResultView
from services import SetService, CollectionService, InventoryResolver, BuildService


class Screens:
    """Main-screen navigation; caller criteria are retained in context dictionaries."""
    def __init__(self, app):
        self.app = app
        self.current_screen = 'home'
        self.context = {}
        self.history = []
        self.widgets = {}
        self.frame = ttk.Frame(app.root, padding=20)
        self.frame.pack(fill='both', expand=True)

    def show(self, screen_id, context=None, remember=True):
        if self.app.busy:
            return
        if remember:
            self.history.append((self.current_screen, self.context))
        self.current_screen = screen_id
        self.context = context if context is not None else {}
        self.widgets.clear()
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.app.feedback.set('')
        nav = ttk.Frame(self.frame)
        nav.pack(fill='x', pady=(0, 14))
        ttk.Button(nav, text='Home', command=lambda: self.app.show_screen('home')).pack(side='left')
        ttk.Button(nav, text='Back', command=self.back,
                   state='normal' if self.history else 'disabled').pack(side='left', padx=8)
        ttk.Label(nav, text='BRICK BUSTER', style='Title.TLabel').pack(side='right')
        getattr(self.app, 'screen_' + screen_id)(self.frame, self.context)

    def back(self):
        if self.history and not self.app.busy:
            screen_id, context = self.history.pop()
            self.show(screen_id, context, remember=False)

    def submit(self, action, *fields):
        return self.app.run_action(action, *fields)

    def render_state(self, state):
        self.app.show_feedback('info', state)


class BrickBusterApp:
    def __init__(self, root, db_path):
        self.root = root
        root.title('Brick Buster — LEGO collection manager')
        root.geometry('1120x760')
        root.minsize(880, 600)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('Heading.TLabel', font=('Segoe UI', 15, 'bold'))
        style.configure('Treeview', rowheight=29)
        self.db = DatabaseManager(db_path)
        self.view_mode = tk.StringVar(root, value='List')
        self.images = ImageLoader(root, self.db.path.parent / 'image_cache')
        self.resolver = InventoryResolver(self.db)
        self.sets = SetService(self.db)
        self.collection = CollectionService(self.db, self.resolver)
        self.build = BuildService(self.collection, self.resolver)
        self.services = (self.sets, self.collection, self.build)
        self.session_result = None
        self.busy = False
        self.events = queue.Queue()
        self.feedback = tk.StringVar()
        ttk.Label(root, textvariable=self.feedback, padding=12, wraplength=1050).pack(side='bottom', fill='x')
        self.screens = Screens(self)
        self.show_screen('home', remember=False)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def show_screen(self, screen, context=None, remember=True):
        self.screens.show(screen, context, remember)

    def show_feedback(self, kind, message):
        self.feedback.set(('Error: ' if kind == 'error' else '') + message)

    def run_action(self, action, *args):
        try:
            return action(*args)
        except (DataError, ValidationError, sqlite3.Error, OSError) as exc:
            self.show_feedback('error', str(exc))
            return None

    def on_collection_or_import_change(self):
        self.session_result = None

    def close(self):
        if self.busy:
            messagebox.showinfo('Import running', 'Please wait for the import to finish.', parent=self.root)
            return
        self.images.close()
        self.db.close()
        self.root.destroy()

    @staticmethod
    def heading(frame, title, detail=''):
        ttk.Label(frame, text=title, style='Heading.TLabel').pack(anchor='w', pady=(0, 8))
        if detail:
            ttk.Label(frame, text=detail, wraplength=1000).pack(anchor='w', pady=(0, 12))

    def table(self, frame, columns, headings, widths=None, image_for=None):
        return ResultView(frame, columns, headings, widths, self.images, self.view_mode,
                          image_for or (lambda values: self.db.image_url('set', values[0])))

    def screen_home(self, frame, context):
        ready = self.db.catalogue_ready()
        self.heading(frame, 'Your LEGO collection',
                     'Collection and calculations work offline. Images need internet until cached.' if ready else
                     'Catalogue not ready. Import the CSV files to begin.')
        for label, screen in [('My collection', 'collection'), ('Search and filter sets', 'search'),
                              ('Query owned piece', 'piece'), ('Check target set', 'build'),
                              ('Import Rebrickable data', 'import')]:
            ttk.Button(frame, text=label, width=34,
                       state='normal' if ready or screen in ('collection', 'import') else 'disabled',
                       command=lambda s=screen: self.show_screen(s)).pack(anchor='w', pady=8)
        ttk.Label(frame, text='Database: ' + str(self.db.path), wraplength=950).pack(anchor='w', pady=20)

    def screen_import(self, frame, context):
        self.heading(frame, 'Import Rebrickable data',
                     'Choose a folder containing the nine required CSV files or CSV ZIP files. '
                     'A failed import retains the previous catalogue and collection.')
        folder = tk.StringVar(value=context.get('folder', ''))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        entry = ttk.Entry(row, textvariable=folder)
        entry.pack(side='left', fill='x', expand=True)
        def browse():
            chosen = filedialog.askdirectory(parent=self.root)
            if chosen:
                folder.set(chosen)
        browse_button = ttk.Button(row, text='Browse…', command=browse)
        browse_button.pack(side='left', padx=8)
        ttk.Label(frame, text='Required: ' + ', '.join(t + '.csv' for t in FILES),
                  wraplength=950).pack(anchor='w', pady=14)
        def start(image_archive=None):
            context['folder'] = folder.get()
            if image_archive is None and not folder.get().strip():
                self.show_feedback('error', 'Choose a CSV folder first.')
                return
            self.busy = True
            for widget in (entry, browse_button, start_button, images_button):
                widget.configure(state='disabled')
            progress.start(15)
            self.show_feedback('info', 'Validating files…')
            def worker():
                worker_db = None
                try:
                    worker_db = DatabaseManager(self.db.path)
                    if image_archive is not None:
                        counts = load_image_urls(worker_db, image_archive)
                        self.events.put(('images', counts))
                    else:
                        counts = DataImporter(worker_db).publish_atomically(
                            context['folder'], lambda msg: self.events.put(('progress', msg)))
                        self.events.put(('success', counts))
                except Exception as exc:
                    self.events.put(('failure', str(exc)))
                finally:
                    if worker_db:
                        worker_db.close()
            threading.Thread(target=worker, daemon=True).start()
            self.root.after(100, poll)
        def poll():
            try:
                while True:
                    kind, payload = self.events.get_nowait()
                    if kind == 'progress':
                        self.show_feedback('info', payload)
                    else:
                        self.busy = False
                        progress.stop()
                        for widget in (entry, browse_button, start_button, images_button):
                            widget.configure(state='normal')
                        images_button.configure(state='normal' if self.db.catalogue_ready() else 'disabled')
                        if kind == 'images':
                            self.show_feedback('info', f'Image links loaded: {sum(payload.values()):,} rows. '
                                               'Open a results screen and choose Grid.')
                        elif kind == 'success':
                            self.on_collection_or_import_change()
                            self.show_feedback('info', f'Import complete: {sum(payload.values()):,} rows. '
                                               'Catalogue ready; saved collection retained.')
                        else:
                            self.show_feedback('error', payload)
                        return
            except queue.Empty:
                self.root.after(100, poll)
        start_button = ttk.Button(frame, text='Validate and import', command=start)
        start_button.pack(anchor='w', pady=10)
        def choose_images():
            archive = filedialog.askopenfilename(parent=self.root, title='Choose Rebrickable all_downloads.zip',
                                                filetypes=[('ZIP archive', '*.zip')])
            if archive:
                start(archive)
        images_button = ttk.Button(frame, text='Load image links from Rebrickable ZIP…', command=choose_images,
                                   state='normal' if self.db.catalogue_ready() else 'disabled')
        images_button.pack(anchor='w', pady=10)
        ttk.Label(frame, text='For older CSVs without image links, select all_downloads.zip. '
                  'Only existing catalogue items are updated; your collection is retained.',
                  wraplength=950).pack(anchor='w')
        progress = ttk.Progressbar(frame, mode='indeterminate')
        progress.pack(fill='x', pady=12)

    def screen_collection(self, frame, context):
        self.heading(frame, 'My collection', 'Record complete sets and the number of copies you own.')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Add set', state='normal' if self.db.catalogue_ready() else 'disabled',
                   command=lambda: self.show_screen('search', {'mode': 'add'})).pack(side='left', padx=(0, 8))
        update = ttk.Button(buttons, text='Update quantity', state='disabled')
        update.pack(side='left', padx=8)
        remove = ttk.Button(buttons, text='Remove set', state='disabled')
        remove.pack(side='left', padx=8)
        tree = self.table(frame, ('set', 'name', 'quantity'), ('Set number', 'Name', 'Owned copies'), (140, 620, 120))
        entries = self.collection.list_owned_sets()
        for r in entries:
            tree.insert('', 'end', iid=r['set_num'], values=tuple(r))
        if not entries:
            self.show_feedback('info', 'No owned sets yet. Use Add set after importing the catalogue.')
        def selected(event=None):
            state = 'normal' if tree.selection() else 'disabled'
            update.configure(state=state)
            remove.configure(state=state)
        tree.bind('<<TreeviewSelect>>', selected)
        def edit():
            if tree.selection():
                self.quantity_dialog(tree.selection()[0], mode='update')
        def delete():
            if not tree.selection():
                return
            key = tree.selection()[0]
            vals = tree.item(key, 'values')
            if messagebox.askyesno('Remove owned set', f'Remove all {vals[2]} owned copies of {key} — {vals[1]}?', parent=self.root):
                def action():
                    self.collection.remove_set(key)
                    self.on_collection_or_import_change()
                    self.show_screen('collection', remember=False)
                    self.show_feedback('info', 'Set removed from your collection.')
                self.run_action(action)
        update.configure(command=edit)
        remove.configure(command=delete)

    def quantity_dialog(self, set_num, mode='add'):
        selected = self.sets.get_set(set_num)
        owned = self.db.read('SELECT quantity FROM owned_sets WHERE set_num=?', (set_num,))
        count = owned[0][0] if owned else 0
        dialog = tk.Toplevel(self.root)
        dialog.title('Add copies' if mode == 'add' else 'Update quantity')
        dialog.transient(self.root)
        dialog.grab_set()
        box = ttk.Frame(dialog, padding=20)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text=f'{set_num} — {selected["name"]}', wraplength=450).pack(anchor='w')
        ttk.Label(box, text=f'Currently owned: {count}').pack(anchor='w', pady=8)
        ttk.Label(box, text='Additional copies:' if mode == 'add' else 'Replacement quantity:').pack(anchor='w')
        value = tk.StringVar(value='1' if mode == 'add' else str(count))
        entry = ttk.Entry(box, textvariable=value)
        entry.pack(fill='x', pady=8)
        entry.focus_set()
        error = tk.StringVar()
        ttk.Label(box, textvariable=error, wraplength=450, foreground='#b91c1c').pack(anchor='w')
        def save():
            try:
                action = self.collection.add_set if mode == 'add' else self.collection.update_quantity
                action(set_num, value.get())
            except (ValidationError, DataError, sqlite3.Error) as exc:
                error.set(str(exc))
                return
            self.on_collection_or_import_change()
            dialog.destroy()
            self.show_screen('collection')
            self.show_feedback('info', 'Collection saved.')
        ttk.Button(box, text='Save', command=save).pack(side='left', pady=12)
        ttk.Button(box, text='Cancel', command=dialog.destroy).pack(side='left', padx=8)

    def screen_search(self, frame, context):
        self.heading(frame, 'Search and filter sets', 'Results are limited to 500 sets. Narrow the search if needed.')
        filters = ttk.Frame(frame)
        filters.pack(fill='x')
        text = tk.StringVar(value=context.get('text', ''))
        theme = tk.StringVar(value=context.get('theme', 'All themes'))
        year = tk.StringVar(value=context.get('year', 'All years'))
        themes = {'All themes': None}
        themes.update({f'{r["name"]} [{r["id"]}]': r['id'] for r in self.sets.list_themes()})
        for label, widget in [('Set number or name', ttk.Entry(filters, textvariable=text, width=36)),
                              ('Theme', ttk.Combobox(filters, textvariable=theme, values=list(themes), state='readonly', width=28)),
                              ('Year', ttk.Combobox(filters, textvariable=year, values=['All years'] + self.sets.list_years(), state='readonly', width=12))]:
            ttk.Label(filters, text=label).pack(side='left', padx=4)
            widget.pack(side='left', padx=4)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=8)
        tree = self.table(frame, ('set', 'name', 'theme', 'year'), ('Set number', 'Name', 'Theme', 'Year'), (130, 480, 230, 85))
        def search():
            context.update(text=text.get(), theme=theme.get(), year=year.get())
            def action():
                results = self.sets.search_sets(text.get(), themes[theme.get()],
                                               None if year.get() == 'All years' else int(year.get()))
                tree.delete(*tree.get_children())
                for row in results:
                    tree.insert('', 'end', iid=row['set_num'], values=tuple(row))
                self.show_feedback('info', f'{len(results)} matching sets shown.' if results else
                                   'No sets match these criteria. Change the search or filters.')
            self.run_action(action)
        def clear():
            text.set('')
            theme.set('All themes')
            year.set('All years')
            search()
        ttk.Button(actions, text='Search', command=search).pack(side='left')
        ttk.Button(actions, text='Clear filters', command=clear).pack(side='left', padx=8)
        bottom = ttk.Frame(frame)
        bottom.pack(fill='x')
        add = ttk.Button(bottom, text='Add selected set…', state='disabled',
                         command=lambda: self.run_action(self.quantity_dialog, tree.selection()[0]))
        add.pack(side='left')
        target = ttk.Button(bottom, text='Use as target', state='disabled',
                            command=lambda: self.show_screen('build', {'target': tree.selection()[0]}))
        target.pack(side='left', padx=8)
        def selection(event=None):
            state = 'normal' if tree.selection() else 'disabled'
            add.configure(state=state)
            target.configure(state=state)
        tree.bind('<<TreeviewSelect>>', selection)
        self.screens.widgets.update(search=search, search_tree=tree)
        search()

    def screen_piece(self, frame, context):
        self.heading(frame, 'Query owned piece quantity',
                     'Match the exact part number and colour. Spares and minifigure component parts are excluded.')
        search = tk.StringVar(value=context.get('search', ''))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        ttk.Label(row, text='Find part by number or name').pack(side='left')
        ttk.Entry(row, textvariable=search, width=48).pack(side='left', padx=8)
        tree = self.table(frame, ('part', 'name'), ('Part number', 'Name'), (160, 700),
                          image_for=lambda values: self.db.image_url('part', values[0], colors.get(color.get(), -1)))
        def find():
            context['search'] = search.get()
            text = search.get().strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            rows = self.db.read("SELECT part_num,name FROM parts WHERE part_num LIKE ? ESCAPE '\\' "
                                "OR name LIKE ? ESCAPE '\\' ORDER BY part_num LIMIT 300", ['%'+text+'%']*2)
            tree.delete(*tree.get_children())
            for r in rows:
                tree.insert('', 'end', iid=r['part_num'], values=tuple(r))
            self.show_feedback('info', f'{len(rows)} parts shown; refine search if needed.' if rows else 'No matching parts.')
        ttk.Button(row, text='Find part', command=lambda: self.run_action(find)).pack(side='left')
        colors = {f'{r["name"]} [{r["id"]}]': r['id'] for r in self.db.read('SELECT id,name FROM colors ORDER BY name,id')}
        color = tk.StringVar(value=context.get('color', next(iter(colors), '')))
        bottom = ttk.Frame(frame)
        bottom.pack(fill='x')
        ttk.Label(bottom, text='Colour').pack(side='left')
        color_picker = ttk.Combobox(bottom, textvariable=color, values=list(colors), state='readonly', width=40)
        color_picker.pack(side='left', padx=8)
        def change_color(event=None):
            context['color'] = color.get()
            tree.refresh()
        color_picker.bind('<<ComboboxSelected>>', change_color)
        def check():
            def action():
                if not tree.selection() or color.get() not in colors:
                    raise ValidationError('Select a part and colour first.')
                context['color'] = color.get()
                part = tree.selection()[0]
                total = self.collection.get_piece_quantity(part, colors[color.get()])
                self.show_feedback('info', f'{part} — {color.get()}: Available quantity = {total:,}.')
            self.run_action(action)
        ttk.Button(bottom, text='Check quantity', command=check).pack(side='left')
        find()

    def screen_build(self, frame, context):
        self.heading(frame, 'Check target set', 'Check one target copy. This does not reserve or consume pieces '
                     'and may require dismantling owned sets.')
        target = context.get('target', '')
        ttk.Label(frame, text='Target: ' + (target or 'Choose a target set first.')).pack(anchor='w', pady=12)
        ttk.Button(frame, text='Choose target…', command=lambda: self.show_screen('search', {'mode': 'target'})).pack(anchor='w', pady=8)
        result_text = tk.StringVar()
        result = self.session_result
        if result and result.target == target:
            result_text.set(result.status.replace('_', ' '))
        ttk.Label(frame, textvariable=result_text, style='Heading.TLabel').pack(anchor='w', pady=20)
        missing = ttk.Button(frame, text='View missing items', command=lambda: self.show_screen('missing'))
        def refresh_missing():
            current = self.session_result
            if current and current.target == target and current.status == 'NOT_BUILDABLE':
                missing.pack(anchor='w', pady=8)
            else:
                missing.pack_forget()
        def check():
            self.session_result = None
            result_text.set('')
            refresh_missing()
            def action():
                if not target:
                    raise ValidationError('Choose a target set first.')
                self.session_result = self.build.check_target(target)
                result_text.set(self.session_result.status.replace('_', ' '))
                self.show_feedback('info', 'All required parts and minifigures are available.' if
                                   self.session_result.status == 'BUILDABLE' else 'Required items are missing. Open the report for quantities.')
                refresh_missing()
            self.run_action(action)
        ttk.Button(frame, text='Check buildability', command=check, state='normal' if target else 'disabled').pack(anchor='w', pady=8)
        refresh_missing()
        self.screens.widgets['check_build'] = check

    def screen_missing(self, frame, context):
        self.heading(frame, 'Missing items report')
        result = self.session_result
        if result is None or result.generation != self.db.generation:
            ttk.Label(frame, text='This result is out of date. Run the build check again.').pack(anchor='w')
            return
        ttk.Label(frame, text=f'Target: {result.target} | Copies checked: 1').pack(anchor='w')
        def missing_image(values):
            if values[0] == 'Minifigure':
                return self.db.image_url('minifigure', values[1])
            colors = self.db.read('SELECT id FROM colors WHERE name=?', (values[3],))
            return self.db.image_url('part', values[1], colors[0][0]) if len(colors) == 1 else ''
        tree = self.table(frame, ('type', 'id', 'name', 'color', 'required', 'available', 'missing'),
                          ('Type', 'Identifier', 'Name', 'Colour', 'Required', 'Available', 'Missing'),
                          (100, 120, 330, 150, 90, 90, 90), image_for=missing_image)
        for row in self.build.missing_items(result):
            tree.insert('', 'end', values=astuple(row))
        ttk.Button(frame, text='Back to build result',
                   command=lambda: self.show_screen('build', {'target': result.target})).pack(anchor='w')
