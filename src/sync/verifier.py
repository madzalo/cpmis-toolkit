"""
Server-based verification of imported DHIS2 data.
"""

import json
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict
from requests.auth import HTTPBasicAuth

from config import Config, get_config
from utils import Logger, Colors


@dataclass
class VerificationResult:
    """Result of import verification."""
    success: bool
    teis_on_server: int = 0
    teis_in_payload: int = 0
    enrollments: int = 0
    events: int = 0
    children: int = 0
    households: int = 0
    records: List[Dict[str, Any]] = field(default_factory=list)
    org_units: List[str] = field(default_factory=list)
    programs: List[str] = field(default_factory=list)
    error: Optional[str] = None


class DataVerifier:
    """Verifies imported data by querying the DHIS2 server."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
    
    def batch_resolve(self, endpoint: str, uids: List[str], auth: HTTPBasicAuth) -> Dict[str, str]:
        """Batch resolve UIDs to names."""
        if not uids:
            return {}
        uid_filter = ",".join(uids)
        try:
            r = requests.get(
                f"{self.config.server}/api/{endpoint}?filter=id:in:[{uid_filter}]&fields=id,name&paging=false",
                auth=auth, timeout=30
            )
            if r.status_code == 200:
                return {item["id"]: item["name"] for item in r.json().get(endpoint, [])}
        except Exception:
            pass
        return {uid: uid for uid in uids}
    
    def fetch_teis_from_server(self, tei_uids: List[str], auth: HTTPBasicAuth) -> Dict[str, Dict]:
        """Fetch TEIs from server in batches."""
        server_teis = {}
        for i in range(0, len(tei_uids), 50):
            chunk = tei_uids[i:i+50]
            try:
                r = requests.get(
                    f"{self.config.server}/api/trackedEntityInstances.json"
                    f"?trackedEntityInstance={','.join(chunk)}"
                    f"&fields=trackedEntityInstance,trackedEntityType,orgUnit,attributes,enrollments"
                    f"&paging=false",
                    auth=auth, timeout=60
                )
                if r.status_code == 200:
                    for tei in r.json().get('trackedEntityInstances', []):
                        server_teis[tei.get('trackedEntityInstance')] = tei
            except Exception:
                pass
            print(".", end="", flush=True)
        return server_teis
    
    def get_display_name(self, tei_type: str, attrs: Dict[str, str]) -> str:
        """Get display name for a TEI."""
        if tei_type == self.config.child_tei_type:
            return attrs.get(self.config.child_first_name_attr) or "Unknown Child"
        elif tei_type == self.config.household_tei_type:
            first = attrs.get(self.config.household_firstname_attr, "")
            last = attrs.get(self.config.household_surname_attr, "")
            return f"HH: {first} {last}".strip() or "Unknown Household"
        return "Unknown"
    
    def verify(self, username: str, password: str, payload_file: Optional[str] = None) -> VerificationResult:
        """Verify imported data from server."""
        payload_file = payload_file or self.config.payload_file
        auth = HTTPBasicAuth(username, password)
        
        Logger.header("IMPORT VERIFICATION")
        
        try:
            with open(payload_file) as f:
                payload = json.load(f)
        except FileNotFoundError:
            return VerificationResult(success=False, error="Payload not found")
        
        teis = payload.get("trackedEntities", [])
        tei_uids = [t["trackedEntity"] for t in teis]
        
        print("  Fetching TEIs from server...", end="", flush=True)
        server_teis = self.fetch_teis_from_server(tei_uids, auth)
        print(f" found {len(server_teis)}/{len(tei_uids)}")
        
        # Resolve names
        org_uids = list(set(t.get("orgUnit") for t in server_teis.values()))
        prog_uids = list(set(e.get("program") for t in server_teis.values() for e in t.get("enrollments", [])))
        
        print("  Resolving names...", end="", flush=True)
        org_names = self.batch_resolve("organisationUnits", org_uids, auth)
        prog_names = self.batch_resolve("programs", prog_uids, auth)
        print(" done")
        
        # Build records from server data
        records = []
        total_events = 0
        
        for tei_uid, tei_data in server_teis.items():
            tei_type = tei_data.get("trackedEntityType", "")
            org_uid = tei_data.get("orgUnit", "")
            attrs = {a["attribute"]: a["value"] for a in tei_data.get("attributes", [])}
            
            for enr in tei_data.get("enrollments", []):
                num_events = len(enr.get("events", []))
                total_events += num_events
                records.append({
                    "tei": tei_uid,
                    "name": self.get_display_name(tei_type, attrs),
                    "tei_type": tei_type,
                    "org_name": org_names.get(org_uid, org_uid),
                    "program": prog_names.get(enr.get("program"), enr.get("program")),
                    "events": num_events
                })
        
        children = sum(1 for r in records if r["tei_type"] == self.config.child_tei_type)
        households = sum(1 for r in records if r["tei_type"] == self.config.household_tei_type)
        
        Logger.success(f"Verified: {len(server_teis)} TEIs, {children} children, {households} households")
        
        return VerificationResult(
            success=True,
            teis_on_server=len(server_teis),
            teis_in_payload=len(teis),
            enrollments=len(records),
            events=total_events,
            children=children,
            households=households,
            records=records,
            org_units=list(org_names.values()),
            programs=list(prog_names.values())
        )
