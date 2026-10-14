"""Run with: python src/main.py [--db path/to/brick_buster.sqlite3]."""
import argparse
from pathlib import Path
import tkinter as tk
from app import BrickBusterApp


def main():
    parser = argparse.ArgumentParser(description='Brick Buster LEGO collection manager')
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parent.parent / 'data' / 'brick_buster.sqlite3')
    args = parser.parse_args()
    root = tk.Tk()
    BrickBusterApp(root, args.db)
    root.mainloop()


if __name__ == '__main__':
    main()
