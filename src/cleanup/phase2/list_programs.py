#!/usr/bin/env python3
"""
List all DHIS2 programs (read-only operation).
This script fetches and displays all programs available in the DHIS2 instance.
"""
import requests
import json
import sys
import os

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD


def list_programs():
    """
    Fetch and display all programs from DHIS2.
    This is a read-only operation - no data is modified.
    """
    url = f"{DHIS2_URL}/api/programs.json"
    params = {
        'fields': 'id,name,displayName,programType,trackedEntityType[id,name],organisationUnits[id,name]',
        'paging': 'false'
    }
    
    try:
        print(f"Fetching programs from: {DHIS2_URL}")
        print("=" * 80)
        
        response = requests.get(
            url,
            params=params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD)
        )
        
        if response.status_code == 200:
            data = response.json()
            programs = data.get('programs', [])
            
            print(f"\nFound {len(programs)} programs:\n")
            
            for i, program in enumerate(programs, 1):
                program_id = program.get('id', 'N/A')
                program_name = program.get('name', 'N/A')
                display_name = program.get('displayName', program_name)
                program_type = program.get('programType', 'N/A')
                
                # Get tracked entity type info
                tet = program.get('trackedEntityType', {})
                tet_name = tet.get('name', 'N/A') if tet else 'N/A'
                
                # Count org units
                org_units = program.get('organisationUnits', [])
                ou_count = len(org_units)
                
                print(f"{i}. {display_name}")
                print(f"   ID: {program_id}")
                print(f"   Type: {program_type}")
                print(f"   Tracked Entity Type: {tet_name}")
                print(f"   Organisation Units: {ou_count}")
                print()
            
            # Save detailed output to file
            output_dir = 'outputs/phase2'
            os.makedirs(output_dir, exist_ok=True)
            output_file = f'{output_dir}/programs_list.json'
            
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print("=" * 80)
            print(f"✅ Detailed program data saved to: {output_file}")
            print("\nNext steps:")
            print("1. Review the programs above")
            print("2. Identify the 2 programs you want to work with")
            print("3. Note their IDs for the next script")
            
        else:
            print(f"❌ Error fetching programs: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    list_programs()
