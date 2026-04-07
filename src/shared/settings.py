import os
from pathlib import Path
from dotenv import load_dotenv

# Find .env at the project root (two levels up from src/shared/)
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / '.env')

# DHIS2 API credentials
DHIS2_URL = os.getenv('DHIS2_URL')
DHIS2_USERNAME = os.getenv('DHIS2_USERNAME')
DHIS2_PASSWORD = os.getenv('DHIS2_PASSWORD')

# PostgreSQL database credentials (optional - for direct DB updates)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'dhis2')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Sync settings (optional - for cpmis-sync-rescue)
DHIS2_SERVER = os.getenv('DHIS2_SERVER', os.getenv('DHIS2_URL', 'https://cpmis.gender.gov.mw'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '200'))
