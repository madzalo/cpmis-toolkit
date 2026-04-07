"""
Utility functions and classes for CPMIS Sync Rescue.
"""

import os
import sys
import zipfile
from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Logger:
    """Formatted logging for console output."""
    
    @staticmethod
    def header(text: str):
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}  {text}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")
    
    @staticmethod
    def info(text: str):
        print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")
    
    @staticmethod
    def success(text: str):
        print(f"{Colors.GREEN}✅ {text}{Colors.END}")
    
    @staticmethod
    def warning(text: str):
        print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")
    
    @staticmethod
    def error(text: str):
        print(f"{Colors.RED}❌ {text}{Colors.END}")
    
    @staticmethod
    def step(step_num: int, total: int, text: str):
        print(f"{Colors.CYAN}[{step_num}/{total}] {text}{Colors.END}")
    
    @staticmethod
    def progress(text: str):
        print(f"  {Colors.CYAN}→ {text}{Colors.END}")


def extract_zip(zip_path: str, extract_dir: str) -> bool:
    """Extract a zip file to a directory."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        return True
    except Exception as e:
        Logger.error(f"Failed to extract {zip_path}: {e}")
        return False


def extract_nested_zips(extract_dir: str, password: Optional[str] = None):
    """Extract any nested zip files found in the directory."""
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith('.zip'):
                nested_zip = os.path.join(root, file)
                Logger.info(f"Found nested zip: {file}, extracting...")
                try:
                    with zipfile.ZipFile(nested_zip, 'r') as zf:
                        if password:
                            try:
                                zf.extractall(root, pwd=password.encode())
                            except RuntimeError:
                                zf.extractall(root)
                        else:
                            zf.extractall(root)
                    Logger.success(f"Extracted nested zip: {file}")
                    os.remove(nested_zip)
                except Exception as e:
                    Logger.warning(f"Could not extract nested zip {file}: {e}")


def find_database(extract_dir: str, password: Optional[str] = None) -> Optional[str]:
    """Find the export-database.db file in extracted directory."""
    extract_nested_zips(extract_dir, password)
    
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file == 'export-database.db':
                return os.path.join(root, file)
    return None


def get_username_from_zip(zip_name: str) -> str:
    """Extract username from zip filename."""
    base = os.path.basename(zip_name)
    if '-' in base:
        return base.split('-')[0].lower()
    return base.replace('.zip', '').lower()


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} minutes"
    hours = minutes / 60
    return f"{hours:.1f} hours"


import random
import json
import glob

PROCESSING_MESSAGES = [
    "🔄 Syncing data with server...",
    "📡 Establishing secure connection...",
    "🔐 Validating credentials...",
    "📦 Preparing data packages...",
    "🚀 Uploading to DHIS2...",
    "⚡ Processing tracked entities...",
    "🔍 Validating enrollments...",
    "📊 Checking event data...",
    "🌐 Communicating with server...",
    "💾 Saving progress...",
    "🔧 Applying data transformations...",
    "📋 Verifying data integrity...",
    "🎯 Targeting org units...",
    "🔗 Linking enrollments...",
    "⏳ Almost there...",
]

DRY_RUN_MESSAGES = [
    "🧪 Testing data structure...",
    "🔬 Analyzing payload...",
    "📝 Checking field mappings...",
    "🔎 Validating UIDs...",
    "📐 Verifying data types...",
    "🧩 Checking relationships...",
    "🔒 Testing access permissions...",
    "📏 Measuring data size...",
]


def get_random_message(is_dry_run: bool = False) -> str:
    """Get a random processing message."""
    messages = DRY_RUN_MESSAGES if is_dry_run else PROCESSING_MESSAGES
    return random.choice(messages)


def show_ignored_report():
    """Show a detailed report of ignored items from the last import."""
    Logger.header("IGNORED ITEMS REPORT")
    
    # Find the most recent import_result.json
    result_files = glob.glob("../batch_processing/**/import_result.json", recursive=True)
    result_files += glob.glob("import_result.json")
    
    if not result_files:
        Logger.warning("No import results found. Run an import first.")
        return
    
    # Get the most recent file
    latest_file = max(result_files, key=os.path.getmtime)
    Logger.info(f"Reading: {latest_file}")
    
    try:
        with open(latest_file) as f:
            data = json.load(f)
    except Exception as e:
        Logger.error(f"Failed to read file: {e}")
        return
    
    summary = data.get("summary", {})
    total_ignored = summary.get("total_ignored", 0)
    
    if total_ignored == 0:
        Logger.success("No items were ignored in the last import!")
        return
    
    print(f"\n{Colors.BOLD}SUMMARY{Colors.END}")
    print(f"  Total ignored: {Colors.YELLOW}{total_ignored}{Colors.END}")
    print(f"  Total created: {Colors.GREEN}{summary.get('total_created', 0)}{Colors.END}")
    print(f"  Total updated: {Colors.CYAN}{summary.get('total_updated', 0)}{Colors.END}")
    
    # Show batch details
    batches = data.get("batches", [])
    if batches:
        print(f"\n{Colors.BOLD}PER-BATCH BREAKDOWN{Colors.END}")
        for batch in batches:
            if batch.get("ignored", 0) > 0:
                print(f"  Batch {batch.get('batch')}: "
                      f"{Colors.YELLOW}{batch.get('ignored')} ignored{Colors.END} | "
                      f"Status: {batch.get('status')}")
    
    # Check for failed batches with errors
    failed = data.get("failed_batches", [])
    if failed:
        print(f"\n{Colors.BOLD}{Colors.RED}FAILED BATCHES WITH ERRORS{Colors.END}")
        for fb in failed:
            print(f"  Batch {fb.get('batch')}:")
            if fb.get("access_errors"):
                print(f"    🔒 Access errors: {len(fb['access_errors'])}")
                for err in fb["access_errors"][:3]:
                    print(f"       → {err[:80]}")
            if fb.get("other_errors"):
                print(f"    ⚠️  Other errors: {len(fb['other_errors'])}")
                for err in fb["other_errors"][:3]:
                    print(f"       → {err[:80]}")
    
    print(f"\n{Colors.CYAN}💡 Tip: Ignored items usually already exist on the server{Colors.END}")


class ProgressTracker:
    """Track and display real-time progress."""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = None
        import time
        self.start_time = time.time()
    
    def update(self, current: int, extra: str = ""):
        """Update progress display."""
        import time
        self.current = current
        elapsed = time.time() - self.start_time
        
        if self.total > 0:
            pct = (current / self.total) * 100
            eta = (elapsed / current * (self.total - current)) if current > 0 else 0
            
            bar_len = 30
            filled = int(bar_len * current / self.total)
            bar = "█" * filled + "░" * (bar_len - filled)
            
            status = f"\r  [{bar}] {pct:5.1f}% | {current}/{self.total} | ⏱ {elapsed:.0f}s"
            if eta > 0:
                status += f" | ETA: {eta:.0f}s"
            if extra:
                status += f" | {extra}"
            
            print(status, end="", flush=True)
    
    def finish(self):
        """Mark progress as complete."""
        import time
        elapsed = time.time() - self.start_time
        print(f"\n  {Colors.GREEN}✅ Completed in {format_duration(elapsed)}{Colors.END}")
