"""
Data extraction from DHIS2 Android app SQLite database.
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from config import Config, get_config
from utils import Logger


@dataclass
class ExtractionResult:
    """Result of data extraction."""
    teis: List[Dict[str, Any]]
    total_enrollments: int
    total_events: int
    payload_file: str
    success: bool
    error: Optional[str] = None


class DataExtractor:
    """Extracts unsynced data from DHIS2 Android app SQLite database."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
    
    def is_excluded(self, attr_uid: str) -> bool:
        """Check if an attribute should be excluded."""
        uid = str(attr_uid).strip()
        return (
            uid in self.config.excluded_attributes or
            uid.strip() in self.config.excluded_attributes or
            uid.lower().strip() in {e.lower() for e in self.config.excluded_attributes}
        )
    
    def clean_attrs(self, attrs: List[Dict]) -> List[Dict]:
        """Remove excluded attributes from a list of attribute dicts."""
        return [a for a in attrs if not self.is_excluded(a.get("attribute", ""))]
    
    def extract(self, db_path: str, reference_date: Optional[str] = None) -> ExtractionResult:
        """Extract unsynced data from the database."""
        reference_date = reference_date or self.config.reference_date
        
        Logger.header("EXTRACTING FROM LOCAL DATABASE")
        Logger.info(f"Database: {db_path}")
        Logger.info(f"Reference date: {reference_date}")
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Extract TEIs (only unsynced)
            cur.execute("""
                SELECT uid, organisationUnit, trackedEntityType,
                       created, lastUpdated, createdAtClient,
                       lastUpdatedAtClient, syncState, deleted
                FROM TrackedEntityInstance
                WHERE syncState IN ('TO_POST', 'TO_UPDATE', 'ERROR')
            """)
            teis = [dict(r) for r in cur.fetchall()]
            tei_uids = [t['uid'] for t in teis]
            Logger.info(f"TEIs found: {len(teis)}")
            
            # Extract attribute values
            attr_values = []
            if tei_uids:
                ph = ','.join('?' * len(tei_uids))
                excluded_ph = ','.join(f"'{e}'" for e in self.config.excluded_attributes)
                cur.execute(f"""
                    SELECT trackedEntityInstance, trackedEntityAttribute, value
                    FROM TrackedEntityAttributeValue
                    WHERE trackedEntityInstance IN ({ph})
                    AND trackedEntityAttribute NOT IN ({excluded_ph})
                """, tei_uids)
                attr_values = [dict(r) for r in cur.fetchall()]
            
            # Double-check exclusion
            attr_values = [a for a in attr_values if not self.is_excluded(a["trackedEntityAttribute"])]
            Logger.info(f"Attribute values: {len(attr_values)}")
            
            # Extract enrollments
            enrollments = []
            if tei_uids:
                ph = ','.join('?' * len(tei_uids))
                cur.execute(f"""
                    SELECT uid, trackedEntityInstance, program, organisationUnit,
                           enrollmentDate, incidentDate, status, syncState,
                           created, lastUpdated
                    FROM Enrollment
                    WHERE trackedEntityInstance IN ({ph})
                    AND syncState IN ('TO_POST', 'TO_UPDATE', 'ERROR', 'SYNCED')
                """, tei_uids)
                enrollments = [dict(r) for r in cur.fetchall()]
            enr_uids = [e['uid'] for e in enrollments]
            Logger.info(f"Enrollments: {len(enrollments)}")
            
            # Extract events
            events = []
            if enr_uids:
                ph = ','.join('?' * len(enr_uids))
                cur.execute(f"""
                    SELECT uid, enrollment, program, programStage, organisationUnit,
                           eventDate, status, syncState, created, lastUpdated,
                           attributeOptionCombo, completedDate
                    FROM Event
                    WHERE enrollment IN ({ph})
                    AND syncState IN ('TO_POST', 'TO_UPDATE', 'ERROR', 'SYNCED')
                """, enr_uids)
                events = [dict(r) for r in cur.fetchall()]
            ev_uids = [e['uid'] for e in events]
            Logger.info(f"Events: {len(events)}")
            
            # Extract data values
            data_values = []
            if ev_uids:
                ph = ','.join('?' * len(ev_uids))
                cur.execute(f"""
                    SELECT event, dataElement, value
                    FROM TrackedEntityDataValue
                    WHERE event IN ({ph})
                """, ev_uids)
                data_values = [dict(r) for r in cur.fetchall()]
            Logger.info(f"Data values: {len(data_values)}")
            
            conn.close()
            
            # Build payload
            payload = self._build_payload(
                teis, attr_values, enrollments, events, data_values, reference_date
            )
            
            # Save payload
            with open(self.config.payload_file, 'w') as f:
                json.dump(payload, f, indent=2)
            
            total_teis = len(payload.get("trackedEntities", []))
            total_enrollments = sum(len(t.get("enrollments", [])) for t in payload.get("trackedEntities", []))
            total_events = sum(
                len(e.get("events", []))
                for t in payload.get("trackedEntities", [])
                for e in t.get("enrollments", [])
            )
            
            Logger.success(f"Payload saved to {self.config.payload_file}")
            Logger.info(f"Total TEIs: {total_teis}")
            Logger.info(f"Total enrollments: {total_enrollments}")
            Logger.info(f"Total events: {total_events}")
            
            return ExtractionResult(
                teis=payload.get("trackedEntities", []),
                total_enrollments=total_enrollments,
                total_events=total_events,
                payload_file=self.config.payload_file,
                success=True
            )
            
        except Exception as e:
            Logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                teis=[],
                total_enrollments=0,
                total_events=0,
                payload_file="",
                success=False,
                error=str(e)
            )
    
    def _build_payload(
        self,
        teis: List[Dict],
        attr_values: List[Dict],
        enrollments: List[Dict],
        events: List[Dict],
        data_values: List[Dict],
        reference_date: str
    ) -> Dict[str, Any]:
        """Build the DHIS2 import payload."""
        # Index data for fast lookup
        attrs_by_tei = {}
        for av in attr_values:
            tei = av["trackedEntityInstance"]
            attrs_by_tei.setdefault(tei, []).append({
                "attribute": av["trackedEntityAttribute"],
                "value": av["value"]
            })
        
        enr_by_tei = {}
        for e in enrollments:
            tei = e["trackedEntityInstance"]
            enr_by_tei.setdefault(tei, []).append(e)
        
        ev_by_enr = {}
        for ev in events:
            enr = ev["enrollment"]
            ev_by_enr.setdefault(enr, []).append(ev)
        
        dv_by_ev = {}
        for dv in data_values:
            ev = dv["event"]
            dv_by_ev.setdefault(ev, []).append({
                "dataElement": dv["dataElement"],
                "value": dv["value"]
            })
        
        # Build tracked entities
        tracked_entities = []
        for t in teis:
            uid = t["uid"]
            
            # Build enrollments for this TEI
            tei_enrollments = []
            for e in enr_by_tei.get(uid, []):
                # Build events for this enrollment
                enr_events = []
                for ev in ev_by_enr.get(e["uid"], []):
                    event_date = ev.get("eventDate") or ""
                    if event_date > reference_date:
                        event_date = reference_date
                    
                    enr_events.append({
                        "event": ev["uid"],
                        "program": ev["program"],
                        "programStage": ev["programStage"],
                        "orgUnit": ev["organisationUnit"],
                        "occurredAt": event_date,
                        "status": ev.get("status", "ACTIVE"),
                        "dataValues": dv_by_ev.get(ev["uid"], [])
                    })
                
                enroll_date = e.get("enrollmentDate") or ""
                incident_date = e.get("incidentDate") or enroll_date
                if enroll_date > reference_date:
                    enroll_date = reference_date
                if incident_date > reference_date:
                    incident_date = reference_date
                
                tei_enrollments.append({
                    "enrollment": e["uid"],
                    "program": e["program"],
                    "orgUnit": e["organisationUnit"],
                    "enrolledAt": enroll_date,
                    "occurredAt": incident_date,
                    "status": e.get("status", "ACTIVE"),
                    "events": enr_events
                })
            
            tracked_entities.append({
                "trackedEntity": uid,
                "trackedEntityType": t["trackedEntityType"],
                "orgUnit": t["organisationUnit"],
                "attributes": self.clean_attrs(attrs_by_tei.get(uid, [])),
                "enrollments": tei_enrollments
            })
        
        return {"trackedEntities": tracked_entities}
