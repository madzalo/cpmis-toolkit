"""
Configuration management for CPMIS Sync Rescue.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Set, Optional
from dotenv import load_dotenv

# Load .env from project root (three levels up from src/sync/config.py)
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / '.env')


@dataclass
class Config:
    """Centralized configuration for DHIS2 data import workflow."""
    
    # DHIS2 Server
    server: str = os.getenv("DHIS2_SERVER", os.getenv("DHIS2_URL", "https://cpmis.gender.gov.mw"))
    
    # Database
    db_path: str = "export-database.db"
    
    # Date Configuration
    reference_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    # Batch Processing
    batch_size: int = int(os.getenv("BATCH_SIZE", "200"))
    poll_wait: int = 2
    poll_max: int = 60
    
    # Directories (relative to project root)
    imports_folder: str = str(_project_root / "imports")
    completed_folder: str = str(_project_root / "completed_imports")
    work_dir: str = str(_project_root / "outputs" / "sync")
    
    # DHIS2 Entity Type UIDs
    child_tei_type: str = "dbHBSY6hTo8"
    household_tei_type: str = "PuKSqf3nWoo"
    
    # Attribute UIDs
    name_source_attr: str = "UADoN3P2lNa"
    name_required_attr: str = "AJBnw1hCqte"
    child_first_name_attr: str = "UADoN3P2lNa"
    child_surname_attr: str = "AJBnw1hCqte"
    household_firstname_attr: str = "BEW0LacDZlt"
    household_surname_attr: str = "J6IRtvVe7qL"
    
    # Excluded Attributes
    excluded_attributes: Set[str] = field(default_factory=lambda: {"LndrKtN5rMH"})
    
    # File Names
    payload_file: str = "dhis2_import_payload.json"
    dry_run_result_file: str = "dry_run_result.json"
    import_result_file: str = "import_result.json"
    access_denied_file: str = "access_denied_teis.json"
    import_report_json: str = "import_report.json"
    import_report_csv: str = "import_report.csv"
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        return cls(
            server=os.getenv("DHIS2_SERVER", os.getenv("DHIS2_URL", "https://cpmis.gender.gov.mw")),
            batch_size=int(os.getenv("BATCH_SIZE", "200")),
            imports_folder=os.getenv("IMPORTS_FOLDER", str(_project_root / "imports")),
            completed_folder=os.getenv("COMPLETED_FOLDER", str(_project_root / "completed_imports")),
            work_dir=os.getenv("WORK_DIR", str(_project_root / "outputs" / "sync")),
        )
    
    def ensure_directories(self):
        """Create required directories if they don't exist."""
        for folder in [self.imports_folder, self.completed_folder, self.work_dir]:
            os.makedirs(folder, exist_ok=True)


# Default singleton instance for backward compatibility
_default_config: Optional[Config] = None


def get_config() -> Config:
    """Get the default configuration instance."""
    global _default_config
    if _default_config is None:
        _default_config = Config.from_env()
    return _default_config
