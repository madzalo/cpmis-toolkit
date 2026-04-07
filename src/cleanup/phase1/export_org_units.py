import requests
import json
import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.settings import DHIS2_URL, DHIS2_USERNAME, DHIS2_PASSWORD

def export_organisation_units():
    url = f"{DHIS2_URL}/api/organisationUnits.json"
    params = {
        'fields': 'id,code,name,level,parent[id,name]',
        'paging': 'false'
    }
    
    try:
        response = requests.get(
            url,
            params=params,
            auth=(DHIS2_USERNAME, DHIS2_PASSWORD),
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        
        output_file = 'outputs/task1/ou_export.json'
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Successfully exported {len(data.get('organisationUnits', []))} organisation units to {output_file}")
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Error exporting organisation units: {e}")
        sys.exit(1)

if __name__ == "__main__":
    export_organisation_units()
