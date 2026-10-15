"""One results table with an optional, paginated image grid."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from queue import Empty, Queue
import ssl
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from PIL import Image, ImageOps, ImageTk


class ImageLoader:
    """Download/cache thumbnails off the UI thread; deliver them on the UI thread."""
    def __init__(self, root, cache_folder):
        self.root = root
        self.cache_folder = Path(cache_folder)
        self.ssl_context = ssl.create_default_context()
        # Some macOS Python installs omit a CA file; retain certificate checking
        # by using the system's trusted certificates when available.
        if not ssl.get_default_verify_paths().cafile and Path('/etc/ssl/cert.pem').is_file():
            self.ssl_context.load_verify_locations('/etc/ssl/cert.pem')
        self.pool = ThreadPoolExecutor(max_workers=3)
        self.results = Queue()
        self.pending = {}
        self.closed = False
        self.timer = root.after(100, self._poll)

    def load(self, url, callback):
        if self.closed:
            return
        if not url:
            callback(None)
            return
        if url in self.pending:
            self.pending[url].append(callback)
            return
        self.pending[url] = [callback]
        future = self.pool.submit(self._fetch, url)
        future.add_done_callback(lambda f: None if f.cancelled() else self.results.put((url, f.result())))

    def _fetch(self, url):
        try:
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname != 'cdn.rebrickable.com':
                return None
            path = self.cache_folder / (sha256(url.encode()).hexdigest() + '.png')
            if path.exists():
                try:
                    with Image.open(path) as cached:
                        return cached.copy()
                except OSError:
                    path.unlink(missing_ok=True)
            request = Request(url, headers={'User-Agent': 'BrickBuster/1.0'})
            with urlopen(request, timeout=6, context=self.ssl_context) as response:
                data = response.read(8_000_001)
            if len(data) > 8_000_000:
                return None
            with Image.open(BytesIO(data)) as original:
                thumbnail = ImageOps.exif_transpose(original).convert('RGBA')
                thumbnail.thumbnail((180, 120))
            try:
                self.cache_folder.mkdir(parents=True, exist_ok=True)
                thumbnail.save(path, format='PNG')
            except OSError:
                pass  # An unwritable cache must not prevent viewing an image.
            return thumbnail
        except Exception:
            return None  # Images are optional; collection actions remain available.

    def _poll(self):
        try:
            while True:
                url, thumbnail = self.results.get_nowait()
                for callback in self.pending.pop(url, []):
                    callback(thumbnail)
        except Empty:
            pass
        if not self.closed:
            self.timer = self.root.after(100, self._poll)

    def close(self):
        self.closed = True
        self.root.after_cancel(self.timer)
        self.pending.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)


class ResultView:
    """Retain Treeview rows and selection as the single source for both views."""
    PAGE_SIZE = 12

    def __init__(self, parent, columns, headings, widths, loader, mode, image_for):
        self.loader, self.mode, self.image_for = loader, mode, image_for
        self.columns, self.headings = columns, headings
        self.page, self.revision = 0, 0
        self.cards = {}
        self.refresh_job = None
        self.alive = True
        self.wrap = ttk.Frame(parent)
        self.wrap.pack(fill='both', expand=True, pady=10)
        controls = ttk.Frame(self.wrap)
        controls.pack(fill='x', pady=(0, 6))
        ttk.Label(controls, text='View:').pack(side='left')
        for value in ('List', 'Grid'):
            ttk.Radiobutton(controls, text=value, value=value, variable=mode).pack(side='left', padx=6)
        self.list_frame = ttk.Frame(self.wrap)
        self.tree = ttk.Treeview(self.list_frame, columns=columns, show='headings', selectmode='browse')
        for i, (column, heading) in enumerate(zip(columns, headings)):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=widths[i] if widths else 140, minwidth=65)
        ybar = ttk.Scrollbar(self.list_frame, orient='vertical', command=self.tree.yview)
        xbar = ttk.Scrollbar(self.list_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        ybar.grid(row=0, column=1, sticky='ns')
        xbar.grid(row=1, column=0, sticky='ew')
        self.list_frame.rowconfigure(0, weight=1)
        self.list_frame.columnconfigure(0, weight=1)
        self.grid_frame = ttk.Frame(self.wrap)
        pager = ttk.Frame(self.grid_frame)
        pager.pack(fill='x')
        self.previous = ttk.Button(pager, text='Previous', command=lambda: self._move(-1))
        self.previous.pack(side='left')
        self.page_label = ttk.Label(pager)
        self.page_label.pack(side='left', padx=12)
        self.next = ttk.Button(pager, text='Next', command=lambda: self._move(1))
        self.next.pack(side='left')
        self.canvas = tk.Canvas(self.grid_frame, highlightthickness=0,
                                background=ttk.Style(parent).lookup('TFrame', 'background') or '#d9d9d9')
        scrollbar = ttk.Scrollbar(self.grid_frame, orient='vertical', command=self.canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.grid = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.grid, anchor='nw')
        self.grid.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self._bind_scroll(self.canvas)
        self._bind_scroll(self.grid)
        for column in range(3):
            self.grid.columnconfigure(column, weight=1, uniform='card')
        self.tree.bind('<<TreeviewSelect>>', self._highlight)
        self.trace = mode.trace_add('write', self._switch)
        self.wrap.bind('<Destroy>', self._destroy)
        self._switch()

    def bind(self, sequence, callback):
        return self.tree.bind(sequence, callback, add='+')

    def selection(self):
        return self.tree.selection()

    def item(self, *args, **kwargs):
        return self.tree.item(*args, **kwargs)

    def get_children(self):
        return self.tree.get_children()

    def insert(self, *args, **kwargs):
        item = self.tree.insert(*args, **kwargs)
        self.refresh()
        return item

    def delete(self, *items):
        self.tree.delete(*items)
        self.page = 0
        self.refresh()

    def refresh(self, *unused):
        if self.alive and self.refresh_job is None:
            self.refresh_job = self.wrap.after_idle(self._render)

    def _switch(self, *unused):
        self.list_frame.pack_forget()
        self.grid_frame.pack_forget()
        if self.mode.get() == 'Grid':
            self.grid_frame.pack(fill='both', expand=True)
            selected = self.selection()
            if selected:
                self.page = self.get_children().index(selected[0]) // self.PAGE_SIZE
            self.refresh()
        else:
            self.list_frame.pack(fill='both', expand=True)
            if self.selection():
                self.tree.see(self.selection()[0])

    def _move(self, step):
        self.page += step
        self.refresh()

    def _select(self, item):
        self.tree.selection_set(item)
        self.tree.focus(item)
        if item in self.cards:
            self.cards[item].focus_set()

    def _bind_scroll(self, widget):
        for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            widget.bind(event, self._scroll)

    def _scroll(self, event):
        if getattr(event, 'num', None) in (4, 5):
            steps = -1 if event.num == 4 else 1
        elif self.wrap.tk.call('tk', 'windowingsystem') == 'aqua':
            steps = -event.delta
        else:
            steps = -int(event.delta / 120)
        self.canvas.yview_scroll(steps, 'units')
        return 'break'

    def _highlight(self, event=None):
        selected = self.selection()
        for item, card in self.cards.items():
            card.configure(highlightbackground='#2362aa' if item in selected else '#d1d5db')

    def _render(self):
        self.refresh_job = None
        if not self.alive or self.mode.get() != 'Grid':
            return
        self.revision += 1
        revision = self.revision
        for widget in self.grid.winfo_children():
            widget.destroy()
        self.cards.clear()
        items = self.get_children()
        pages = max(1, (len(items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page = min(max(0, self.page), pages - 1)
        self.page_label.configure(text=f'Page {self.page + 1} of {pages} · {len(items)} items')
        self.previous.configure(state='normal' if self.page else 'disabled')
        self.next.configure(state='normal' if self.page < pages - 1 else 'disabled')
        self.canvas.yview_moveto(0)
        if not items:
            ttk.Label(self.grid, text='No items to display.').grid(padx=15, pady=20)
        for index, item in enumerate(items[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]):
            values = self.item(item, 'values')
            card = tk.Frame(self.grid, background='white', highlightthickness=2, cursor='hand2', takefocus=True)
            card.grid(row=index // 3, column=index % 3, padx=5, pady=5, sticky='nsew')
            self.cards[item] = card
            photo = tk.Label(card, text='Loading image…', background='white', foreground='#6b7280', width=24, height=7)
            photo.pack(padx=8, pady=8)
            name_index = self.columns.index('name')
            tk.Label(card, text=values[name_index], background='white', foreground='#111827', wraplength=230,
                     font=('TkDefaultFont', 11, 'bold')).pack(padx=8, pady=(0, 6))
            detail = '\n'.join(f'{heading}: {value}' for i, (heading, value) in
                               enumerate(zip(self.headings, values)) if i != name_index)
            tk.Label(card, text=detail, background='white', foreground='#111827', wraplength=230, justify='left').pack(padx=8, pady=(0, 10))
            for widget in (card, *card.winfo_children()):
                widget.bind('<Button-1>', lambda e, key=item: self._select(key))
                self._bind_scroll(widget)
            for key in ('<space>', '<Return>'):
                card.bind(key, lambda e, item=item: self._select(item))
            def display(thumbnail, label=photo, token=revision):
                if not self.alive or token != self.revision:
                    return
                if thumbnail is None:
                    label.configure(text='Image unavailable')
                else:
                    label.image = ImageTk.PhotoImage(thumbnail, master=self.wrap)
                    label.configure(image=label.image, text='', width=180, height=120)
            self.loader.load(self.image_for(values), display)
        self._highlight()

    def _destroy(self, event):
        if event.widget is self.wrap:
            self.alive = False
            self.mode.trace_remove('write', self.trace)
            if self.refresh_job is not None:
                self.wrap.after_cancel(self.refresh_job)
