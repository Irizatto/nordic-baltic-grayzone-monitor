"""Configuration with safe, mock-first defaults."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
DOCS_DATA = ROOT / "docs" / "data"
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
