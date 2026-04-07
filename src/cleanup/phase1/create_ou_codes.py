import json
import csv
import sys
import os

def create_ou_code_reference():
    input_file = 'outputs/task1/ou_export.json'
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {input_file} not found. Run export_org_units.py first.")
        sys.exit(1)
    
    org_units = data.get('organisationUnits', [])
    
    output_file = 'outputs/task1/ou_codes.csv'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['dhis2_uid', 'ou_name', 'ou_level', 'standardised_code'])
        writer.writeheader()
        
        for ou in org_units:
            row = {
                'dhis2_uid': ou.get('id', ''),
                'ou_name': ou.get('name', ''),
                'ou_level': ou.get('level', ''),
                'standardised_code': ou.get('code', '')
            }
            writer.writerow(row)
    
    print(f"Successfully created {output_file} with {len(org_units)} organisation units")
    print("\nNext steps:")
    print("1. Open ou_codes.csv")
    print("2. Fill in standardised_code column:")
    print("   - Districts (level 2): 2 letters (e.g., LL, BT, MZ)")
    print("   - Facilities (level 3): 4 letters (e.g., KABU, KALO, NDRA)")

if __name__ == "__main__":
    create_ou_code_reference()
