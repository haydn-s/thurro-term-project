"""Test package.

The `__init__.py` is load-bearing: it makes pytest walk up to
final-deliverable/ when it inserts the rootdir on sys.path, which is what lets
these modules `import app`. Without it pytest inserts tests/ instead and the
imports fail.
"""
