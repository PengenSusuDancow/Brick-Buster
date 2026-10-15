# Regression tests

From the repository folder, install the application dependency and run:

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s Testing -p 'test_*.py' -v
```

The tests use Python's standard `unittest` runner, tiny synthetic catalogues and
temporary databases. No real collection, downloaded CSVs, internet connection or
graphical desktop is required. Image tests use the application's Pillow dependency.

Coverage includes migration of existing databases, CSVs with or without image
columns, image import rollback, preservation of catalogue scope and owned copies,
exact-colour images, parent-theme filters, thumbnail caching and image failures.
List/grid interaction and scrolling should also be checked in the running app.
