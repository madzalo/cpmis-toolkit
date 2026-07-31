import csv
import sys
import os
import json
import re

def load_district_codes():
    district_map = {}
    try:
        with open('src/cleanup/malawi_districts.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                district_name = row['name'].strip().lower()
                district_code = row['code'].strip()
                district_map[district_name] = district_code
    except FileNotFoundError:
        print("Error: src/cleanup/malawi_districts.csv not found")
        sys.exit(1)
    return district_map

def load_org_units_json():
    try:
        with open('outputs/task1/ou_export.json', 'r') as f:
            data = json.load(f)
            return data.get('organisationUnits', [])
    except FileNotFoundError:
        print("Error: outputs/task1/ou_export.json not found")
        sys.exit(1)

def find_district_code(ou_name, district_map):
    ou_name_lower = ou_name.lower()
    for district_name, district_code in district_map.items():
        if district_name in ou_name_lower:
            return district_code
    return None

def get_district_code_from_parent_chain(ou_id, ou_map, district_map):
    if ou_id not in ou_map:
        return None
    
    ou = ou_map[ou_id]
    level = ou.get('level')
    
    if level == 3:
        return find_district_code(ou.get('name', ''), district_map)
    
    parent = ou.get('parent')
    if parent:
        parent_id = parent.get('id')
        return get_district_code_from_parent_chain(parent_id, ou_map, district_map)
    
    return None


def strip_prefix(name):
    """
    Strip TA/STA/Sub TA/T/A prefix from name.
    
    Examples:
    - "TA Chauma"         -> "Chauma"
    - "STA Nkagula"       -> "Nkagula"
    - "Sub TA Phweremwe"  -> "Phweremwe"
    - "T/A Nkalo"         -> "Nkalo"
    - "Lambulira"         -> "Lambulira" (no prefix)
    """
    if name.upper().startswith('SUB TA '):
        return name[7:].strip()
    elif name.upper().startswith('STA '):
        return name[4:].strip()
    elif name.upper().startswith('TA '):
        return name[3:].strip()
    elif name.upper().startswith('T/A '):
        return name[4:].strip()
    return name


def name_to_short_code(name, parent_name=None):
    """
    Extract a short code (4 letters + optional numbers/suffix) from a name.

    Hierarchical code structure:
      L3 District:  XX                        e.g. ZA
      L4 TA:        XX_YYYY                   e.g. ZA_CHIK
      L5 Facility:  XX_YYYY_ZZZZ              e.g. ZA_CHIK_LAMB

    If parent_name is provided (for L5 facilities), common words shared with
    the parent are stripped so the facility code is distinctive.

    Examples:
    - "TA Chauma"                          -> "CHAU"
    - "STA Nkagula"                        -> "NKAG"
    - "Sub TA Phweremwe"                   -> "PHWE"
    - "Lambulira"                          -> "LAMB"
    - "Area 18"                            -> "AREA18"
    - "Area 18 Health Centre" (parent="Area 18")  -> "HC18"   (strips "Area", keeps "Health Centre" → HC)
    - "Area 25 Community Hospital" (parent="Area 25") -> "CH25"
    - "Magomero Health Centre"             -> "MAGO"
    - "Chikowa Health Centre (Lilongwe)"   -> "CHIK"   (strips parenthetical)
    - "Chamba (Machinga)"                  -> "CHAM"
    - "Mchengautuwa East Ward"             -> "MCHE"
    """
    # Strip parenthetical disambiguation — (Lilongwe), (Machinga), (Zomba), etc.
    clean_name = re.sub(r'\s*\([^)]*\)\s*', ' ', name).strip()

    # For L5 facilities: if the parent TA name is embedded in the facility name,
    # strip it so the facility code is distinctive.
    if parent_name:
        parent_clean = strip_prefix(parent_name).strip()
        # Remove the parent name from the facility name (case-insensitive)
        clean_name = re.sub(re.escape(parent_clean), '', clean_name, flags=re.IGNORECASE).strip()
        # Also try removing just the parent's "Area N" pattern
        clean_name = re.sub(r'Area\s*\d+', '', clean_name, flags=re.IGNORECASE).strip()

    # Strip TA/STA/Sub TA prefix
    clean = strip_prefix(clean_name)

    # Strip common facility type words to get the distinctive part
    facility_type_words = [
        'Health Centre', 'Health Center', 'Community Hospital', 'Rural Hospital',
        'District Hospital', 'Central Hospital', 'Mission Hospital',
        'Hospital', 'Clinic', 'Dispensary', 'Maternity',
        'Urban Health Centre', 'Urban Health Center',
        'Game Reserve', 'National Park', 'Mountain Reserve',
        'Boma', 'Town', 'Ward', 'Factory',
    ]

    facility_type_code = None
    for ft in facility_type_words:
        if re.search(re.escape(ft), clean, re.IGNORECASE):
            # Generate a type abbreviation
            ft_words = ft.split()
            if len(ft_words) >= 2:
                facility_type_code = ''.join(w[0] for w in ft_words if w).upper()
            else:
                facility_type_code = ft[:2].upper()
            # Remove the type words from the name
            clean = re.sub(re.escape(ft), '', clean, flags=re.IGNORECASE).strip()
            break

    # Extract numbers (including letter suffixes like 18A, 18B)
    number_match = re.search(r'(\d+[A-Z]?)', clean, re.IGNORECASE)
    number_part = number_match.group(1).upper() if number_match else ''

    # Extract letters from what remains after stripping type words
    letters = re.sub(r'[^A-Za-z]', '', clean)[:4].upper()

    # Build the code
    if letters and number_part:
        # e.g., "Area 18 Health Centre" (parent="Area 18") → letters="" number="18" type="HC" → "HC18"
        if facility_type_code and not letters:
            return f"{facility_type_code}{number_part}"
        elif facility_type_code:
            return f"{letters}{number_part}"
        else:
            return f"{letters}{number_part}"
    elif number_part and not letters:
        if facility_type_code:
            return f"{facility_type_code}{number_part}"
        return f"AREA{number_part}"  # fallback for pure "Area 18"
    elif letters:
        if facility_type_code and len(letters) < 4:
            # Pad with type code, e.g., "Chiringa CHAM" → "CHIR" (already 4), but "Chiringa Maternity" → "CHIR"
            return letters
        return letters
    elif facility_type_code:
        return facility_type_code
    else:
        # Fallback: first 4 letters of original name
        return re.sub(r'[^A-Za-z0-9]', '', name)[:4].upper()


def make_code_unique(base_code, used_codes):
    """
    Make a code unique by appending _1, _2, etc. if it already exists.
    
    Examples:
    - ZA_CHIK       (first)  -> ZA_CHIK
    - ZA_CHIK       (second) -> ZA_CHIK_1
    - ZA_CHIK_LAMB  (first)  -> ZA_CHIK_LAMB
    - ZA_CHIK_LAMB  (second) -> ZA_CHIK_LAMB_1
    """
    if base_code not in used_codes:
        return base_code
    
    counter = 1
    while True:
        unique_code = f"{base_code}_{counter}"
        if unique_code not in used_codes:
            return unique_code
        counter += 1


def update_standardised_codes():
    district_map = load_district_codes()
    org_units = load_org_units_json()
    
    ou_map = {ou['id']: ou for ou in org_units}
    
    input_file = 'outputs/task1/ou_codes.csv'
    output_file = 'outputs/task1/ou_codes_updated.csv'
    
    try:
        with open(input_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"Error: {input_file} not found. Run create_ou_codes.py first.")
        sys.exit(1)
    
    # Build row lookup by UID for easy access
    row_by_uid = {r['dhis2_uid']: r for r in rows}
    
    # Track all used codes to ensure uniqueness
    used_codes = set()
    # Map OU UID -> generated code (needed for L5 to find parent TA code)
    uid_to_code = {}
    
    counters = {'l3': 0, 'l4': 0, 'l5': 0}
    totals = {'l3': 0, 'l4': 0, 'l5': 0}
    not_updated = []
    
    # Count totals
    for row in rows:
        lvl = row['ou_level']
        if lvl == '3': totals['l3'] += 1
        elif lvl == '4': totals['l4'] += 1
        elif lvl == '5': totals['l5'] += 1
    
    # ── PASS 1: Level 3 (Districts) ──
    for row in rows:
        if row['ou_level'] != '3':
            continue
        ou_id = row['dhis2_uid']
        code = find_district_code(row['ou_name'], district_map)
        if code:
            unique = make_code_unique(code, used_codes)
            row['standardised_code'] = unique
            used_codes.add(unique)
            uid_to_code[ou_id] = unique
            counters['l3'] += 1
        else:
            not_updated.append({'uid': ou_id, 'name': row['ou_name'], 'level': '3'})
    
    # ── PASS 2: Level 4 (TAs) ──
    for row in rows:
        if row['ou_level'] != '4':
            continue
        ou_id = row['dhis2_uid']
        ou = ou_map.get(ou_id)
        if not ou:
            not_updated.append({'uid': ou_id, 'name': row['ou_name'], 'level': '4'})
            continue
        
        district_code = get_district_code_from_parent_chain(ou_id, ou_map, district_map)
        if not district_code:
            not_updated.append({'uid': ou_id, 'name': row['ou_name'], 'level': '4'})
            continue
        
        short = name_to_short_code(row['ou_name'])
        base_code = f"{district_code}_{short}"
        unique = make_code_unique(base_code, used_codes)
        row['standardised_code'] = unique
        used_codes.add(unique)
        uid_to_code[ou_id] = unique
        counters['l4'] += 1
    
    # ── PASS 3: Level 5 (Facilities) — includes parent TA code ──
    for row in rows:
        if row['ou_level'] != '5':
            continue
        ou_id = row['dhis2_uid']
        ou = ou_map.get(ou_id)
        if not ou:
            not_updated.append({'uid': ou_id, 'name': row['ou_name'], 'level': '5'})
            continue
        
        # Find parent TA (L4) and its generated code
        parent = ou.get('parent', {})
        parent_id = parent.get('id')
        parent_code = uid_to_code.get(parent_id)
        parent_name = parent.get('name', '') if parent else ''

        if not parent_code:
            # Fallback: use district code directly if parent TA has no code
            district_code = get_district_code_from_parent_chain(ou_id, ou_map, district_map)
            if not district_code:
                not_updated.append({'uid': ou_id, 'name': row['ou_name'], 'level': '5'})
                continue
            parent_code = district_code

        short = name_to_short_code(row['ou_name'], parent_name=parent_name)
        base_code = f"{parent_code}_{short}"
        unique = make_code_unique(base_code, used_codes)
        row['standardised_code'] = unique
        used_codes.add(unique)
        uid_to_code[ou_id] = unique
        counters['l5'] += 1
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['dhis2_uid', 'ou_name', 'ou_level', 'standardised_code'])
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"Successfully generated {sum(counters.values())} unique hierarchical organisation unit codes")
    print(f"\nCode structure:")
    print(f"  L3 District:  XX              (e.g. ZA)")
    print(f"  L4 TA:        XX_YYYY         (e.g. ZA_CHIK)")
    print(f"  L5 Facility:  XX_YYYY_ZZZZ    (e.g. ZA_CHIK_LAMB)")
    print(f"\nBy level:")
    print(f"  - Level 3 (Districts):  {counters['l3']}/{totals['l3']}")
    print(f"  - Level 4 (TAs):       {counters['l4']}/{totals['l4']}")
    print(f"  - Level 5 (Facilities): {counters['l5']}/{totals['l5']}")
    
    if not_updated:
        print(f"\n⚠️  {len(not_updated)} organisation units NOT updated:")
        for item in not_updated:
            print(f"  - Level {item['level']}: {item['name']} (UID: {item['uid']})")
    
    # Show sample hierarchy
    print(f"\n📋 Sample hierarchy:")
    # Find a district with TAs that have facilities
    for row in rows:
        if row['ou_level'] == '5' and row.get('standardised_code', '').count('_') >= 2:
            code = row['standardised_code']
            parts = code.split('_')
            # Find matching district and TA
            district_code = parts[0]
            ta_code = f"{parts[0]}_{parts[1]}"
            district_row = next((r for r in rows if r.get('standardised_code') == district_code), None)
            ta_row = next((r for r in rows if r.get('standardised_code') == ta_code), None)
            if district_row and ta_row:
                print(f"  L3 {district_row['ou_name']:<30} → {district_code}")
                print(f"    L4 {ta_row['ou_name']:<28} → {ta_code}")
                print(f"      L5 {row['ou_name']:<26} → {code}")
                break
    
    print(f"\nOutput saved to: {output_file}")

if __name__ == "__main__":
    update_standardised_codes()
