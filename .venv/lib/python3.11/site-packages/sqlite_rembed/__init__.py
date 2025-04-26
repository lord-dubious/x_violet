
import os
import sqlite3

__version__ = "0.0.1a9"
__version_info__ = tuple(__version__.split("."))

def loadable_path():
  loadable_path = os.path.join(os.path.dirname(__file__), "rembed0")
  return os.path.normpath(loadable_path)

def load(conn: sqlite3.Connection)  -> None:
  conn.load_extension(loadable_path())
