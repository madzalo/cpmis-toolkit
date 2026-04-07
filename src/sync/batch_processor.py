"""
Batch processing of multiple zip files for DHIS2 import.
"""

import os
import shutil
import glob
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from config import Config, get_config
from extractor import DataExtractor
from validator import DataValidator
from importer import DataImporter
from verifier import DataVerifier
from utils import Logger, Colors, extract_zip, find_database, get_username_from_zip, format_duration


@dataclass
class BatchResult:
    """Result of processing a single zip file."""
    zip_file: str
    username: str
    firstname: str
    surname: str
    extract_dir: str
    success: bool
    created: int = 0
    updated: int = 0
    ignored: int = 0
    duration: float = 0
    error: Optional[str] = None


@dataclass 
class BatchProcessingResult:
    """Result of batch processing multiple files."""
    successful: int = 0
    failed: int = 0
    total_time: float = 0
    results: List[BatchResult] = field(default_factory=list)


class BatchProcessor:
    """Processes multiple zip files for DHIS2 import."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.extractor = DataExtractor(self.config)
        self.validator = DataValidator(self.config)
        self.importer = DataImporter(self.config)
        self.verifier = DataVerifier(self.config)
    
    def find_zip_files(self, folder: Optional[str] = None) -> List[str]:
        """Find all zip files in the imports folder."""
        folder = folder or self.config.imports_folder
        # Convert to absolute path for glob to work correctly
        abs_folder = os.path.abspath(folder)
        pattern = os.path.join(abs_folder, "*.zip")
        return sorted(glob.glob(pattern))
    
    def collect_user_details(self, zip_files: List[str]) -> List[Dict[str, str]]:
        """Collect user details for all zip files."""
        Logger.header("Enter User Details for All Zip Files")
        Logger.info("Username will be extracted from zip filename")
        Logger.info("Please provide surname only (will be capitalized for password)")
        print()
        
        user_details = []
        for i, zip_path in enumerate(zip_files, 1):
            zip_name = os.path.basename(zip_path)
            username = get_username_from_zip(zip_name)
            
            print(f"[{i}/{len(zip_files)}] {zip_name}")
            print(f"  Username (from file): {username}")
            
            surname = input("  Surname: ").strip()
            if not surname:
                Logger.warning("Surname required, skipping this file")
                continue
            
            password = f"{surname.capitalize()}@2025"
            print(f"  Password will be: {password}")
            print()
            
            user_details.append({
                "zip_path": zip_path,
                "zip_name": zip_name,
                "username": username,
                "firstname": username,
                "surname": surname.capitalize(),
                "password": password
            })
        
        return user_details
    
    def process_single(self, zip_path: str, username: str, password: str, 
                       firstname: str, surname: str) -> BatchResult:
        """Process a single zip file."""
        zip_name = os.path.basename(zip_path)
        start_time = datetime.now()
        
        Logger.header(f"Processing: {zip_name}")
        Logger.info(f"Username: {username}")
        Logger.info(f"Password: {password}")
        
        # Create extraction directory
        extract_dir = os.path.join(
            self.config.work_dir, 
            f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(extract_dir, exist_ok=True)
        
        # Extract zip
        Logger.info(f"Extracting to: {extract_dir}")
        if not extract_zip(zip_path, extract_dir):
            return BatchResult(
                zip_file=zip_name, username=username, firstname=firstname,
                surname=surname, extract_dir=extract_dir, success=False,
                error="Failed to extract zip"
            )
        
        # Find database
        db_path = find_database(extract_dir, password)
        if not db_path:
            return BatchResult(
                zip_file=zip_name, username=username, firstname=firstname,
                surname=surname, extract_dir=extract_dir, success=False,
                error="Database not found in zip"
            )
        
        Logger.success(f"Found database: {db_path}")
        
        # Step 1: Extract
        Logger.info("Step 1/4: Extracting data...")
        extract_result = self.extractor.extract(db_path)
        if not extract_result.success:
            return BatchResult(
                zip_file=zip_name, username=username, firstname=firstname,
                surname=surname, extract_dir=extract_dir, success=False,
                error=f"Extraction failed: {extract_result.error}"
            )
        
        # Step 2: Validate
        Logger.info("Step 2/4: Validating...")
        validate_result = self.validator.validate(username, password)
        if not validate_result.success:
            Logger.warning("Validation had errors, continuing anyway")
        
        # Step 3: Import
        Logger.info("Step 3/4: Importing...")
        import_result = self.importer.import_data(username, password)
        
        # Move import result immediately
        if os.path.exists(self.config.import_result_file):
            shutil.move(self.config.import_result_file, 
                       os.path.join(extract_dir, self.config.import_result_file))
        
        # Step 4: Verify
        Logger.info("Step 4/4: Verifying...")
        verify_result = self.verifier.verify(username, password)
        
        # Move generated files to extract dir
        files_to_move = [
            self.config.payload_file,
            self.config.dry_run_result_file,
            self.config.import_report_json,
            self.config.import_report_csv,
            self.config.access_denied_file
        ]
        for f in files_to_move:
            if os.path.exists(f):
                shutil.move(f, os.path.join(extract_dir, f))
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return BatchResult(
            zip_file=zip_name,
            username=username,
            firstname=firstname,
            surname=surname,
            extract_dir=extract_dir,
            success=import_result.success,
            created=import_result.total_created,
            updated=import_result.total_updated,
            ignored=import_result.total_ignored,
            duration=duration
        )
    
    def move_completed_zip(self, zip_path: str):
        """Move completed zip to completed folder."""
        os.makedirs(self.config.completed_folder, exist_ok=True)
        dest = os.path.join(self.config.completed_folder, os.path.basename(zip_path))
        shutil.move(zip_path, dest)
        Logger.info(f"Moved completed zip to: {dest}")
    
    def process_all(self, folder: Optional[str] = None, 
                    completed_folder: Optional[str] = None) -> BatchProcessingResult:
        """Process all zip files in the folder."""
        if completed_folder:
            self.config.completed_folder = completed_folder
        
        self.config.ensure_directories()
        
        zip_files = self.find_zip_files(folder)
        if not zip_files:
            Logger.warning("No zip files found")
            return BatchProcessingResult()
        
        Logger.header("DHIS2 Batch Import Processor")
        Logger.info(f"Found {len(zip_files)} zip file(s)")
        Logger.info(f"Work directory: {self.config.work_dir}")
        Logger.info(f"Completed folder: {self.config.completed_folder}")
        
        # Collect user details
        user_details = self.collect_user_details(zip_files)
        if not user_details:
            Logger.error("No files to process")
            return BatchProcessingResult()
        
        # Show summary
        Logger.header("Processing Summary")
        for ud in user_details:
            print(f"  📦 {ud['zip_name']}")
            print(f"     👤 {ud['firstname']} {ud['surname']}")
            print(f"     🔑 {ud['username']} / {ud['password']}")
            print()
        
        input("Press ENTER to start processing...")
        
        # Process each file
        start_time = datetime.now()
        results = []
        
        for i, ud in enumerate(user_details, 1):
            Logger.header(f"FILE {i} OF {len(user_details)}")
            
            result = self.process_single(
                ud['zip_path'], ud['username'], ud['password'],
                ud['firstname'], ud['surname']
            )
            results.append(result)
            
            if result.success:
                Logger.success(f"Completed in {format_duration(result.duration)}")
                self.move_completed_zip(ud['zip_path'])
            else:
                Logger.error(f"Failed: {result.error}")
        
        total_time = (datetime.now() - start_time).total_seconds()
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        # Final summary
        Logger.header("BATCH PROCESSING COMPLETE")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        print(f"  ⏱️  Total time: {format_duration(total_time)}")
        
        return BatchProcessingResult(
            successful=successful,
            failed=failed,
            total_time=total_time,
            results=results
        )
