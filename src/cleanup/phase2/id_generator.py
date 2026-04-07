import requests
import psycopg2
import sys
import os
from typing import Optional, Literal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD

RecordType = Literal['household', 'child']

class IDGenerator:
    """
    Generate standardised IDs based on org unit code.
    Supports both API and Database approaches.
    """
    
    def __init__(self, use_db: bool = False, db_config: Optional[dict] = None):
        """
        Initialize ID Generator.
        
        Args:
            use_db: If True, use database queries. If False, use DHIS2 API.
            db_config: Database connection config (required if use_db=True)
        """
        self.use_db = use_db
        self.db_conn = None
        self.db_cursor = None
        
        if use_db:
            if not db_config:
                raise ValueError("db_config required when use_db=True")
            self.db_conn = psycopg2.connect(**db_config)
            self.db_cursor = self.db_conn.cursor()
    
    def generate_id(self, org_unit_uid: str, record_type: RecordType) -> str:
        """
        Generate standardised ID based on org unit code.
        Works for any level (district, TA, or facility).
        
        Args:
            org_unit_uid: UID of the org unit (can be level 3, 4, or 5)
            record_type: 'household' or 'child'
        
        Returns:
            Standardised ID: XX_XXXX_HH_######## or XX_XXXX_OVC_########
        """
        ou_code = self._get_org_unit_code(org_unit_uid)
        
        if not ou_code:
            raise ValueError(f"No code found for org unit: {org_unit_uid}")
        
        max_seq = self._get_max_sequence(org_unit_uid, record_type)
        next_seq = str(max_seq + 1).zfill(8)
        
        type_code = 'HH' if record_type == 'household' else 'OVC'
        return f"{ou_code}_{type_code}_{next_seq}"
    
    def _get_org_unit_code(self, org_unit_uid: str) -> Optional[str]:
        """Fetch org unit code from API or Database"""
        if self.use_db:
            return self._get_org_unit_code_from_db(org_unit_uid)
        else:
            return self._get_org_unit_code_from_api(org_unit_uid)
    
    def _get_org_unit_code_from_api(self, org_unit_uid: str) -> Optional[str]:
        """Fetch org unit code from DHIS2 API"""
        url = f"{DHIS2_URL}/api/organisationUnits/{org_unit_uid}.json"
        params = {'fields': 'id,code,name,level'}
        
        try:
            response = requests.get(
                url, 
                params=params, 
                auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
            )
            response.raise_for_status()
            data = response.json()
            return data.get('code')
        except Exception as e:
            print(f"Error fetching org unit from API: {e}")
            return None
    
    def _get_org_unit_code_from_db(self, org_unit_uid: str) -> Optional[str]:
        """Fetch org unit code from database"""
        query = "SELECT code FROM organisationunit WHERE uid = %s"
        self.db_cursor.execute(query, (org_unit_uid,))
        result = self.db_cursor.fetchone()
        return result[0] if result else None
    
    def _get_max_sequence(self, org_unit_uid: str, record_type: RecordType) -> int:
        """Get max sequence number for this org unit and type"""
        if self.use_db:
            return self._get_max_sequence_from_db(org_unit_uid, record_type)
        else:
            return self._get_max_sequence_from_api(org_unit_uid, record_type)
    
    def _get_max_sequence_from_db(self, org_unit_uid: str, record_type: RecordType) -> int:
        """Get max sequence from database"""
        attr_code = 'HOUSEHOLD_ID' if record_type == 'household' else 'CHILD_UIC'
        
        query = """
            SELECT MAX(
                CAST(
                    SUBSTRING(teav.value FROM '.*_([0-9]{8})$') AS INTEGER
                )
            ) as max_seq
            FROM trackedentityattributevalue teav
            JOIN trackedentityinstance tei ON teav.trackedentityinstanceid = tei.trackedentityinstanceid
            JOIN trackedentityattribute tea ON teav.trackedentityattributeid = tea.trackedentityattributeid
            WHERE tea.code = %s 
            AND tei.organisationunitid = (
                SELECT organisationunitid FROM organisationunit WHERE uid = %s
            )
            AND teav.value ~ '.*_[0-9]{8}$'
        """
        
        self.db_cursor.execute(query, (attr_code, org_unit_uid))
        result = self.db_cursor.fetchone()
        return result[0] if result and result[0] else 0
    
    def _get_max_sequence_from_api(self, org_unit_uid: str, record_type: RecordType) -> int:
        """Get max sequence from DHIS2 API"""
        attr_code = 'HOUSEHOLD_ID' if record_type == 'household' else 'CHILD_UIC'
        
        url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
        params = {
            'ou': org_unit_uid,
            'fields': f'attributes[attribute,value]',
            'paging': 'false'
        }
        
        try:
            response = requests.get(
                url,
                params=params,
                auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
            )
            response.raise_for_status()
            data = response.json()
            
            max_seq = 0
            for tei in data.get('trackedEntityInstances', []):
                for attr in tei.get('attributes', []):
                    if attr.get('attribute') == attr_code:
                        value = attr.get('value', '')
                        parts = value.split('_')
                        if len(parts) >= 3 and parts[-1].isdigit():
                            seq = int(parts[-1])
                            max_seq = max(max_seq, seq)
            
            return max_seq
        except Exception as e:
            print(f"Error fetching max sequence from API: {e}")
            return 0
    
    def close(self):
        """Close database connection if open"""
        if self.db_cursor:
            self.db_cursor.close()
        if self.db_conn:
            self.db_conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == "__main__":
    # Example usage with API
    print("Testing ID Generator with API...")
    with IDGenerator(use_db=False) as generator:
        # Example: Generate ID for a facility
        test_ou_uid = "zy1VQ3340OY"  # Example OU UID
        
        try:
            household_id = generator.generate_id(test_ou_uid, 'household')
            print(f"Generated Household ID: {household_id}")
            
            child_id = generator.generate_id(test_ou_uid, 'child')
            print(f"Generated Child ID: {child_id}")
        except Exception as e:
            print(f"Error: {e}")
