"""Central configuration for safe, environment-driven data collection."""
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DOCS_DATA = ROOT / "docs" / "data"
PROCESSED_DATA = ROOT / "data" / "processed"
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "true").lower() == "true"

DIGITRAFFIC_BASE_URL = "https://meri.digitraffic.fi/api/ais/v1"
DIGITRAFFIC_USER_AGENT = "NBGM-research/1.0"
DIGITRAFFIC_BBOX = {"lat_min": 58.5, "lat_max": 61.5, "lon_min": 17.0, "lon_max": 31.0}

BARENTSWATCH_TOKEN_URL = "https://id.barentswatch.no/connect/token"
BARENTSWATCH_AIS_URL = "https://live.ais.barentswatch.no"
BARENTSWATCH_CLIENT_ID = os.getenv("BARENTSWATCH_CLIENT_ID")
BARENTSWATCH_CLIENT_SECRET = os.getenv("BARENTSWATCH_CLIENT_SECRET")
BARENTSWATCH_BBOX = {"lat_min": 64.0, "lat_max": 82.0, "lon_min": 0.0, "lon_max": 45.0}
