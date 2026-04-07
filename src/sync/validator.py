"""
Dry-run validation for DHIS2 data import.
"""

import json
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from requests.auth import HTTPBasicAuth

from config import Config, get_config
from utils import Logger


@dataclass
class ValidationResult:
    """Result of dry-run validation."""
    success: bool
    batches_ok: int
    batches_failed: int
    errors: List[Dict[str, Any]]
    error: Optional[str] = None


class DataValidator:
    """Performs dry-run validation of data before import."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
    
    def validate(self, username: str, password: str, payload_file: Optional[str] = None) -> ValidationResult:
        """Run dry-run validation against DHIS2 server."""
        payload_file = payload_file or self.config.payload_file
        auth = HTTPBasicAuth(username, password)
        
        Logger.header("DRY-RUN VALIDATION")
        
        # Test connection
        try:
            r = requests.get(f"{self.config.server}/api/system/info", auth=auth, timeout=30)
            if r.status_code == 200:
                Logger.success(f"Connected — DHIS2 {r.json().get('version')}")
            elif r.status_code == 401:
                Logger.error("Wrong username or password")
                return ValidationResult(success=False, batches_ok=0, batches_failed=0, errors=[], error="Authentication failed")
            else:
                Logger.error(f"Server error: {r.status_code}")
                return ValidationResult(success=False, batches_ok=0, batches_failed=0, errors=[], error=f"Server error: {r.status_code}")
        except Exception as e:
            Logger.error(f"Connection failed: {e}")
            return ValidationResult(success=False, batches_ok=0, batches_failed=0, errors=[], error=str(e))
        
        # Load payload
        try:
            with open(payload_file) as f:
                payload = json.load(f)
        except FileNotFoundError:
            Logger.error(f"{payload_file} not found")
            return ValidationResult(success=False, batches_ok=0, batches_failed=0, errors=[], error="Payload file not found")
        
        teis = payload.get("trackedEntities", [])
        total_enr = sum(len(t['enrollments']) for t in teis)
        total_ev = sum(len(e['events']) for t in teis for e in t['enrollments'])
        
        Logger.info(f"TEIs: {len(teis)}")
        Logger.info(f"Enrollments: {total_enr}")
        Logger.info(f"Events: {total_ev}")
        
        # Run batched dry-run
        Logger.header("BATCH DRY RUN")
        
        failed_batches = []
        all_results = []
        batch_size = self.config.batch_size
        
        for i in range(0, len(teis), batch_size):
            batch = teis[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(teis) + batch_size - 1) // batch_size
            
            print(f"  Batch {batch_num}/{total_batches} — TEIs {i+1} to {i+len(batch)}...", end=" ", flush=True)
            print(f"PROGRESS: Dry-run batch {batch_num}/{total_batches} | TEIs {i+1}-{i+len(batch)}/{len(teis)}", flush=True)
            
            try:
                r = requests.post(
                    f"{self.config.server}/api/tracker?dryRun=true&strategy=CREATE_AND_UPDATE",
                    json={"trackedEntities": batch},
                    auth=auth,
                    headers={"Content-Type": "application/json"},
                    timeout=120
                )
                
                if r.status_code == 200:
                    result = r.json()
                    errors = result.get("validationReport", {}).get("errorReports", [])
                    if errors:
                        print(f"  ⚠️  {len(errors)} error(s)")
                        print(f"PROGRESS: Dry-run batch {batch_num}/{total_batches} completed | Errors: {len(errors)}", flush=True)
                        for e in errors[:3]:
                            print(f"       → {e.get('message', e)}")
                        failed_batches.append({"batch": batch_num, "errors": errors})
                    else:
                        print(f"  ✅ OK")
                        print(f"PROGRESS: Dry-run batch {batch_num}/{total_batches} completed | Status: OK", flush=True)
                else:
                    print(f"  ❌ HTTP {r.status_code}")
                    print(f"PROGRESS: Dry-run batch {batch_num}/{total_batches} failed | HTTP {r.status_code}", flush=True)
                    failed_batches.append({"batch": batch_num, "raw": r.text[:300]})
                
                all_results.append({"batch": batch_num, "status": r.status_code})
                
            except Exception as e:
                print(f"  ❌ Error: {e}")
                failed_batches.append({"batch": batch_num, "error": str(e)})
                all_results.append({"batch": batch_num, "status": 0})
        
        # Summary
        ok = sum(1 for r in all_results if r["status"] == 200)
        fail = len(all_results) - ok
        
        Logger.header("VALIDATION SUMMARY")
        Logger.info(f"Batches OK: {ok}")
        Logger.info(f"Batches failed: {fail}")
        
        # Save results
        with open(self.config.dry_run_result_file, "w") as f:
            json.dump({"summary": all_results, "failed_batches": failed_batches}, f, indent=2)
        
        Logger.info(f"Results saved to: {self.config.dry_run_result_file}")
        
        if not failed_batches:
            Logger.success("All clear — ready for import")
        else:
            Logger.warning("Fix errors above before importing")
        
        return ValidationResult(
            success=fail == 0,
            batches_ok=ok,
            batches_failed=fail,
            errors=failed_batches
        )
