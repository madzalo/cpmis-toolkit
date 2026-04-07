"""
DHIS2 data importer with batch processing and detailed reporting.
"""

import json
import time
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from requests.auth import HTTPBasicAuth

from config import Config, get_config
from utils import Logger


@dataclass
class ImportResult:
    """Result of data import."""
    success: bool
    total_created: int = 0
    total_updated: int = 0
    total_ignored: int = 0
    batches: List[Dict[str, Any]] = field(default_factory=list)
    access_denied: List[str] = field(default_factory=list)
    error: Optional[str] = None


class DataImporter:
    """Imports data to DHIS2 server in batches."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
    
    def wait_for_job(self, job_id: str, auth: HTTPBasicAuth) -> Dict[str, Any]:
        """Poll for job completion."""
        url = f"{self.config.server}/api/tracker/jobs/{job_id}"
        for _ in range(self.config.poll_max):
            print(".", end="", flush=True)
            time.sleep(self.config.poll_wait)
            try:
                r = requests.get(url, auth=auth, timeout=30)
                if r.status_code == 200:
                    report = r.json()
                    if report.get("status") in ("OK", "WARNING", "ERROR"):
                        return report
            except Exception:
                pass
        return {"status": "TIMEOUT", "stats": {}, "validationReport": {"errorReports": []}}
    
    def categorize_errors(self, errors: List[Dict]) -> tuple:
        """Categorize errors into types."""
        access_errors = []
        cascade_errors = []
        duplicate_errors = []
        other_errors = []
        
        for e in errors:
            msg = e.get("message", "")
            error_code = e.get("errorCode", "")
            
            if "does not have access" in msg or error_code == "E1102":
                access_errors.append(msg)
            elif "cannot be persisted because" in msg:
                cascade_errors.append(msg)
            elif "already exists" in msg or error_code in ("E1080", "E1081", "E1082"):
                duplicate_errors.append(msg)
            elif "E1" in error_code:
                other_errors.append(f"[{error_code}] {msg[:100]}")
            else:
                other_errors.append(msg[:150])
        
        return access_errors, cascade_errors, duplicate_errors, other_errors
    
    def get_ignore_reasons(self, report: Dict) -> Dict[str, int]:
        """Extract reasons why items were ignored."""
        reasons = {}
        
        # Extract from bundleReport
        bundle_report = report.get("bundleReport", {})
        for entity_type in ["trackedEntities", "enrollments", "events"]:
            type_report = bundle_report.get("typeReportMap", {}).get(entity_type.upper(), {})
            for obj_report in type_report.get("objectReports", []):
                if obj_report.get("errorReports"):
                    for err in obj_report.get("errorReports", []):
                        code = err.get("errorCode", "UNKNOWN")
                        msg = err.get("message", "")[:80]
                        key = f"{code}: {msg}"
                        reasons[key] = reasons.get(key, 0) + 1
        
        # Extract from validationReport
        validation_report = report.get("validationReport", {})
        for err in validation_report.get("errorReports", []):
            code = err.get("errorCode", "UNKNOWN")
            msg = err.get("message", "")[:80]
            key = f"{code}: {msg}"
            reasons[key] = reasons.get(key, 0) + 1
        
        for warn in validation_report.get("warningReports", []):
            code = warn.get("warningCode", warn.get("errorCode", "WARN"))
            msg = warn.get("message", "")[:80]
            key = f"{code}: {msg}"
            reasons[key] = reasons.get(key, 0) + 1
        
        return reasons
    
    def import_data(self, username: str, password: str, payload_file: Optional[str] = None) -> ImportResult:
        """Import data to DHIS2 server."""
        payload_file = payload_file or self.config.payload_file
        auth = HTTPBasicAuth(username, password)
        
        Logger.header("DHIS2 DATA IMPORT")
        
        # Test connection
        try:
            me = requests.get(f"{self.config.server}/api/me?fields=id,username", auth=auth, timeout=20)
            if me.status_code != 200:
                Logger.error("Authentication failed")
                return ImportResult(success=False, error="Authentication failed")
            Logger.success(f"Logged in as: {me.json().get('username')}")
        except Exception as e:
            Logger.error(f"Connection failed: {e}")
            return ImportResult(success=False, error=str(e))
        
        # Load payload
        try:
            with open(payload_file) as f:
                payload = json.load(f)
        except FileNotFoundError:
            Logger.error(f"{payload_file} not found")
            return ImportResult(success=False, error="Payload file not found")
        
        teis = payload.get("trackedEntities", [])
        total_enr = sum(len(t['enrollments']) for t in teis)
        total_ev = sum(len(e['events']) for t in teis for e in t['enrollments'])
        
        Logger.info(f"TEIs: {len(teis)}")
        Logger.info(f"Enrollments: {total_enr}")
        Logger.info(f"Events: {total_ev}")
        
        # Import in batches
        Logger.header("IMPORTING IN BATCHES")
        
        all_results = []
        failed_batches = []
        access_denied = []
        total_created = 0
        total_updated = 0
        total_ignored = 0
        batch_size = self.config.batch_size
        
        for i in range(0, len(teis), batch_size):
            batch = teis[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(teis) + batch_size - 1) // batch_size
            
            print(f"\n  Batch {batch_num}/{total_batches} — TEIs {i+1} to {i+len(batch)}")
            print(f"PROGRESS: Batch {batch_num}/{total_batches} | TEIs {i+1}-{i+len(batch)}/{len(teis)}", flush=True)
            
            try:
                r = requests.post(
                    f"{self.config.server}/api/tracker"
                    f"?strategy=CREATE_AND_UPDATE"
                    f"&atomicMode=OBJECT"
                    f"&skipPatternValidation=true",
                    json={"trackedEntities": batch},
                    auth=auth,
                    headers={"Content-Type": "application/json"},
                    timeout=60
                )
                
                if r.status_code != 200:
                    print(f"    ❌ HTTP {r.status_code}")
                    failed_batches.append({"batch": batch_num, "error": r.text[:300]})
                    continue
                
                job_id = r.json().get("response", {}).get("id")
                if not job_id:
                    print("    ❌ No job ID returned")
                    continue
                
                print(f"    Job ID: {job_id} — polling", end="", flush=True)
                report = self.wait_for_job(job_id, auth)
                print()
                
                status = report.get("status", "?")
                stats = report.get("stats", {})
                errors = report.get("validationReport", {}).get("errorReports", [])
                
                created = stats.get("created", 0)
                updated = stats.get("updated", 0)
                ignored = stats.get("ignored", 0)
                
                total_created += created
                total_updated += updated
                total_ignored += ignored
                
                # Show compact batch result
                status_icon = "✅" if status == "OK" else "⚠️" if status == "WARNING" else "❌"
                print(f"    {status_icon} {status} | ✅ {created} created | 🔄 {updated} updated | ⏭️ {ignored} ignored")
                print(f"PROGRESS: Batch {batch_num}/{total_batches} | ✅{created} 🔄{updated} ⏭️{ignored}", flush=True)
                
                # Show ignore reasons
                if ignored > 0:
                    ignore_reasons = self.get_ignore_reasons(report)
                    if ignore_reasons:
                        top_reasons = sorted(ignore_reasons.items(), key=lambda x: -x[1])[:5]
                        print(f"    📋 Ignore reasons ({len(ignore_reasons)} types):")
                        for reason, count in top_reasons:
                            print(f"       → ({count}x) {reason[:80]}")
                    else:
                        print(f"    📋 {ignored} items ignored (likely already exist on server)")
                
                # Handle errors
                if errors:
                    access_e, cascade_e, dup_e, other_e = self.categorize_errors(errors)
                    
                    if access_e:
                        print(f"    🔒 Access denied ({len(access_e)}):")
                        for msg in access_e[:2]:
                            print(f"       → {msg[:80]}")
                        for t in batch:
                            access_denied.append(t.get("trackedEntity"))
                    
                    if dup_e:
                        print(f"    📋 Duplicates ({len(dup_e)})")
                    
                    if cascade_e:
                        print(f"    ⛓️  Cascade failures ({len(cascade_e)})")
                    
                    if other_e:
                        print(f"    ⚠️  Other errors ({len(other_e)}):")
                        for msg in other_e[:3]:
                            print(f"       → {msg[:80]}")
                
                all_results.append({
                    "batch": batch_num,
                    "job_id": job_id,
                    "status": status,
                    "created": created,
                    "updated": updated,
                    "ignored": ignored,
                    "errors": len(errors)
                })
                
            except Exception as e:
                print(f"    ❌ Error: {e}")
                failed_batches.append({"batch": batch_num, "error": str(e)})
        
        # Save results
        Logger.header("IMPORT SUMMARY")
        Logger.success(f"Total created: {total_created}")
        Logger.info(f"Total updated: {total_updated}")
        Logger.warning(f"Total ignored: {total_ignored}")
        
        if access_denied:
            Logger.warning(f"Access denied TEIs: {len(access_denied)}")
        
        # Save import result
        result_data = {
            "summary": {
                "total_created": total_created,
                "total_updated": total_updated,
                "total_ignored": total_ignored,
                "access_denied": len(access_denied)
            },
            "batches": all_results,
            "failed_batches": failed_batches
        }
        
        with open(self.config.import_result_file, "w") as f:
            json.dump(result_data, f, indent=2)
        
        if access_denied:
            with open(self.config.access_denied_file, "w") as f:
                json.dump(access_denied, f, indent=2)
        
        Logger.info(f"Results saved to: {self.config.import_result_file}")
        
        return ImportResult(
            success=len(failed_batches) == 0,
            total_created=total_created,
            total_updated=total_updated,
            total_ignored=total_ignored,
            batches=all_results,
            access_denied=access_denied
        )
