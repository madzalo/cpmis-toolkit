#!/usr/bin/env python3
"""
Command-line interface for CPMIS Sync Rescue.
"""

import argparse
import sys
import os

from __init__ import __version__
from config import Config
from extractor import DataExtractor
from validator import DataValidator
from importer import DataImporter
from verifier import DataVerifier
from batch_processor import BatchProcessor
from utils import Logger


def cmd_extract(args):
    """Extract data from database."""
    config = Config()
    config.db_path = args.db
    if args.date:
        config.reference_date = args.date
    
    extractor = DataExtractor(config)
    result = extractor.extract(args.db, args.date)
    return 0 if result.success else 1


def cmd_validate(args):
    """Run dry-run validation."""
    config = Config()
    validator = DataValidator(config)
    result = validator.validate(args.username, args.password)
    return 0 if result.success else 1


def cmd_import(args):
    """Import data to DHIS2."""
    config = Config()
    importer = DataImporter(config)
    result = importer.import_data(args.username, args.password)
    return 0 if result.success else 1


def cmd_verify(args):
    """Verify imported data."""
    config = Config()
    verifier = DataVerifier(config)
    result = verifier.verify(args.username, args.password)
    return 0 if result.success else 1


def cmd_batch(args):
    """Process batch imports."""
    config = Config()
    if args.imports_folder:
        config.imports_folder = args.imports_folder
    if args.completed_folder:
        config.completed_folder = args.completed_folder
    if args.work_dir:
        config.work_dir = args.work_dir
    
    processor = BatchProcessor(config)
    result = processor.process_all()
    return 0 if result.failed == 0 else 1


def cmd_version(args):
    """Show version."""
    print(f"CPMIS Sync Rescue v{__version__}")
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="cpmis-sync",
        description="CPMIS Sync Rescue - DHIS2 Data Import Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cpmis-sync extract --db export-database.db
  cpmis-sync validate --username USER --password PASS
  cpmis-sync import --username USER --password PASS
  cpmis-sync verify --username USER --password PASS
  cpmis-sync batch --imports-folder imports --completed-folder done
        """
    )
    parser.add_argument("-v", "--version", action="store_true", help="Show version")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract data from database")
    extract_parser.add_argument("--db", required=True, help="Path to SQLite database")
    extract_parser.add_argument("--date", help="Reference date (YYYY-MM-DD)")
    extract_parser.set_defaults(func=cmd_extract)
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Run dry-run validation")
    validate_parser.add_argument("--username", required=True, help="DHIS2 username")
    validate_parser.add_argument("--password", required=True, help="DHIS2 password")
    validate_parser.set_defaults(func=cmd_validate)
    
    # Import command
    import_parser = subparsers.add_parser("import", help="Import data to DHIS2")
    import_parser.add_argument("--username", required=True, help="DHIS2 username")
    import_parser.add_argument("--password", required=True, help="DHIS2 password")
    import_parser.set_defaults(func=cmd_import)
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify imported data")
    verify_parser.add_argument("--username", required=True, help="DHIS2 username")
    verify_parser.add_argument("--password", required=True, help="DHIS2 password")
    verify_parser.set_defaults(func=cmd_verify)
    
    # Batch command
    batch_parser = subparsers.add_parser("batch", help="Process batch imports")
    batch_parser.add_argument("--imports-folder", default="imports", help="Folder with zip files")
    batch_parser.add_argument("--completed-folder", default="completed_imports", help="Folder for completed zips")
    batch_parser.add_argument("--work-dir", default="batch_processing", help="Working directory")
    batch_parser.set_defaults(func=cmd_batch)
    
    args = parser.parse_args()
    
    if args.version:
        return cmd_version(args)
    
    if not args.command:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
