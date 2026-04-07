import requests
import psycopg2
import sys
import os
import csv
from datetime import datetime
from typing import Literal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD
from cleanup.phase2.id_generator import IDGenerator

RecordType = Literal['household', 'child']

class BulkIDAssigner:
    """
    Assign IDs to records that don't have them.
    Supports both API and Database approaches.
    """
    
    def __init__(self, use_db: bool = False, db_config: dict = None):
        """
        Initialize Bulk ID Assigner.
        
        Args:
            use_db: If True, use database queries. If False, use DHIS2 API.
            db_config: Database connection config (required if use_db=True)
        """
        self.use_db = use_db
        self.db_config = db_config
        self.db_conn = None
        self.db_cursor = None
        self.log_file = f"outputs/phase2/bulk_assign_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        os.makedirs('outputs/phase2', exist_ok=True)
        
        if use_db:
            if not db_config:
                raise ValueError("db_config required when use_db=True")
            self.db_conn = psycopg2.connect(**db_config)
            self.db_cursor = self.db_conn.cursor()
    
    def assign_ids(self, record_type: RecordType, dry_run: bool = False):
        """
        Assign IDs to all records without IDs.
        
        Args:
            record_type: 'household' or 'child'
            dry_run: If True, only simulate without making changes
        """
        print(f"\n{'DRY RUN: ' if dry_run else ''}Assigning {record_type} IDs...")
        
        if self.use_db:
            self._assign_ids_via_db(record_type, dry_run)
        else:
            self._assign_ids_via_api(record_type, dry_run)
    
    def _assign_ids_via_api(self, record_type: RecordType, dry_run: bool):
        """Assign IDs using DHIS2 API"""
        attr_code = 'HOUSEHOLD_ID' if record_type == 'household' else 'CHILD_UIC'
        
        # Get attribute ID
        attr_url = f"{DHIS2_URL}/api/trackedEntityAttributes.json"
        attr_params = {'filter': f'code:eq:{attr_code}', 'fields': 'id,code'}
        attr_response = requests.get(
            attr_url,
            params=attr_params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
        )
        attributes = attr_response.json().get('trackedEntityAttributes', [])
        
        if not attributes:
            print(f"Error: Attribute {attr_code} not found")
            return
        
        attr_id = attributes[0]['id']
        
        # Get all tracked entity instances
        tei_url = f"{DHIS2_URL}/api/trackedEntityInstances.json"
        tei_params = {
            'fields': 'trackedEntityInstance,orgUnit,attributes[attribute,value]',
            'paging': 'false'
        }
        
        tei_response = requests.get(
            tei_url,
            params=tei_params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
        )
        teis = tei_response.json().get('trackedEntityInstances', [])
        
        # Filter records without IDs
        records_without_ids = []
        for tei in teis:
            has_id = False
            for attr in tei.get('attributes', []):
                if attr.get('attribute') == attr_id and attr.get('value'):
                    has_id = True
                    break
            
            if not has_id:
                records_without_ids.append({
                    'uid': tei['trackedEntityInstance'],
                    'orgUnit': tei['orgUnit'],
                    'attr_id': attr_id
                })
        
        print(f"Found {len(records_without_ids)} records without {record_type} IDs")
        
        # Generate and assign IDs
        with IDGenerator(use_db=False) as generator:
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['tei_uid', 'org_unit', 'new_id', 'status'])
                writer.writeheader()
                
                for i, record in enumerate(records_without_ids, 1):
                    try:
                        new_id = generator.generate_id(record['orgUnit'], record_type)
                        
                        if not dry_run:
                            # Update via API
                            update_url = f"{DHIS2_URL}/api/trackedEntityInstances/{record['uid']}"
                            update_data = {
                                "attributes": [
                                    {"attribute": record['attr_id'], "value": new_id}
                                ]
                            }
                            update_response = requests.put(
                                update_url,
                                json=update_data,
                                auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
                            )
                            
                            status = 'success' if update_response.status_code == 200 else f'error_{update_response.status_code}'
                        else:
                            status = 'dry_run'
                        
                        writer.writerow({
                            'tei_uid': record['uid'],
                            'org_unit': record['orgUnit'],
                            'new_id': new_id,
                            'status': status
                        })
                        
                        if i % 100 == 0:
                            print(f"Processed {i}/{len(records_without_ids)} records...")
                    
                    except Exception as e:
                        print(f"Error processing record {record['uid']}: {e}")
                        writer.writerow({
                            'tei_uid': record['uid'],
                            'org_unit': record['orgUnit'],
                            'new_id': '',
                            'status': f'error: {str(e)}'
                        })
        
        print(f"\n{'DRY RUN ' if dry_run else ''}Complete! Log saved to: {self.log_file}")
    
    def _assign_ids_via_db(self, record_type: RecordType, dry_run: bool):
        """Assign IDs using database queries"""
        attr_code = 'HOUSEHOLD_ID' if record_type == 'household' else 'CHILD_UIC'
        
        # Get records without IDs
        query = """
            SELECT tei.uid, tei.trackedentityinstanceid, ou.uid as ou_uid, 
                   tea.trackedentityattributeid, tea.code
            FROM trackedentityinstance tei
            JOIN organisationunit ou ON tei.organisationunitid = ou.organisationunitid
            CROSS JOIN trackedentityattribute tea
            WHERE tea.code = %s
            AND NOT EXISTS (
                SELECT 1 FROM trackedentityattributevalue teav
                WHERE teav.trackedentityinstanceid = tei.trackedentityinstanceid
                AND teav.trackedentityattributeid = tea.trackedentityattributeid
            )
        """
        
        self.db_cursor.execute(query, (attr_code,))
        records = self.db_cursor.fetchall()
        
        print(f"Found {len(records)} records without {record_type} IDs")
        
        # Generate and assign IDs
        with IDGenerator(use_db=True, db_config=self.db_config) as generator:
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['tei_uid', 'org_unit', 'new_id', 'status'])
                writer.writeheader()
                
                for i, record in enumerate(records, 1):
                    try:
                        tei_uid, tei_id, ou_uid, attr_id, _ = record
                        new_id = generator.generate_id(ou_uid, record_type)
                        
                        if not dry_run:
                            # Insert into database
                            insert_query = """
                                INSERT INTO trackedentityattributevalue 
                                (trackedentityinstanceid, trackedentityattributeid, value)
                                VALUES (%s, %s, %s)
                            """
                            self.db_cursor.execute(insert_query, (tei_id, attr_id, new_id))
                            status = 'success'
                        else:
                            status = 'dry_run'
                        
                        writer.writerow({
                            'tei_uid': tei_uid,
                            'org_unit': ou_uid,
                            'new_id': new_id,
                            'status': status
                        })
                        
                        if i % 100 == 0:
                            print(f"Processed {i}/{len(records)} records...")
                            if not dry_run:
                                self.db_conn.commit()
                    
                    except Exception as e:
                        print(f"Error processing record {tei_uid}: {e}")
                        writer.writerow({
                            'tei_uid': tei_uid,
                            'org_unit': ou_uid,
                            'new_id': '',
                            'status': f'error: {str(e)}'
                        })
                
                if not dry_run:
                    self.db_conn.commit()
        
        print(f"\n{'DRY RUN ' if dry_run else ''}Complete! Log saved to: {self.log_file}")
    
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
    import argparse
    
    parser = argparse.ArgumentParser(description='Bulk assign IDs to records')
    parser.add_argument('--type', choices=['household', 'child'], required=True,
                        help='Record type to process')
    parser.add_argument('--method', choices=['api', 'db'], default='api',
                        help='Method to use: api or db')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simulate without making changes')
    parser.add_argument('--db-host', help='Database host (required for db method)')
    parser.add_argument('--db-name', help='Database name (required for db method)')
    parser.add_argument('--db-user', help='Database user (required for db method)')
    parser.add_argument('--db-password', help='Database password (required for db method)')
    
    args = parser.parse_args()
    
    use_db = args.method == 'db'
    db_config = None
    
    if use_db:
        if not all([args.db_host, args.db_name, args.db_user, args.db_password]):
            print("Error: Database credentials required for db method")
            sys.exit(1)
        
        db_config = {
            'host': args.db_host,
            'database': args.db_name,
            'user': args.db_user,
            'password': args.db_password
        }
    
    with BulkIDAssigner(use_db=use_db, db_config=db_config) as assigner:
        assigner.assign_ids(args.type, dry_run=args.dry_run)
