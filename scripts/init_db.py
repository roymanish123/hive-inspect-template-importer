"""Initialize the configured database. Safe to run again."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app
print("Schema initialized:", "PostgreSQL" if app.extensions["database"].url else "SQLite")
