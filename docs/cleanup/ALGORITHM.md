# Organisation Unit Code Generation Algorithm

## Overview

This document describes the algorithm used to generate standardised organisation unit codes for the CPMIS system in Malawi.

## Code Format

### Level 3: Districts
**Format:** `XX` (2 letters)

**Source:** Codes are mapped from `malawi_districts.csv`

**Examples:**
- Balaka → `BA`
- Blantyre → `BL`
- Lilongwe → `LL`
- Mzuzu City → `MN`
- Nkhatabay → `NB`

### Level 4: Traditional Authorities (TAs)
**Format:** `{DISTRICT}_{XXXX}` (District code + underscore + 4 letters)

**Algorithm:**
1. Get parent district code (e.g., `BA`)
2. Extract first 4 alphanumeric characters from TA name
3. Combine: `{district}_{name}`

**Examples:**
- TA Balaka in Balaka District → `BA_BALA`
- TA Kabudula in Lilongwe District → `LL_KABU`
- TA Chibanja in Mzuzu City → `MN_CHIB`

### Level 5: Facilities
**Format:** `{DISTRICT}_{XXXX}` (District code + underscore + 4 letters)

**Algorithm:**
1. Get parent district code by traversing up the hierarchy
2. Extract first 4 alphanumeric characters from facility name
3. Combine: `{district}_{name}`

**Examples:**
- Kabudula Health Centre in Lilongwe → `LL_KABU`
- Bangwe Health Centre in Blantyre → `BL_BANG`
- Bereu Health Centre in Chikwawa → `CK_BERE`

### Number Extraction from Names

**Key Feature:** If an org unit name contains numbers, those numbers are extracted and included in the code.

**Examples:**
- `Area 1` → `LL_AREA1` (number 1 from name)
- `Area 10` → `LL_AREA10` (number 10 from name)
- `Area 25` → `LL_AREA25` (number 25 from name)
- `Area 18 Health Center` → `LL_AREA18` (number 18 from name)

This ensures that numbered org units automatically get unique codes based on their actual numbers.

### Duplicate Handling

### Problem
Multiple org units may have similar names, resulting in identical codes.

**Two scenarios:**

1. **Names with numbers that conflict:**
   - `Area 18` → `LL_AREA18`
   - `Area 18 Health Center` → `LL_AREA18_1` (same number, so gets suffix)

2. **Names without numbers that are identical:**
   - `STA Chaima` → `KS_STAC`
   - `STA Chambwe` → `KS_STAC_1` (duplicate base code)
   - `STA Chisikwa` → `KS_STAC_2` (duplicate base code)

### Solution
1. **Extract numbers from names first** (if present)
2. **Only use incremental suffix** when codes still conflict

**Algorithm:**
```python
def generate_base_code_for_ou(ou, ou_map, district_map):
    # Extract letters (first 4 letters only)
    letters = re.sub(r'[^A-Za-z]', '', clean_name)[:4].upper()
    
    # Extract numbers from the original name
    numbers = re.findall(r'\d+', name)
    
    if numbers:
        # Include number from name
        return f"{district_code}_{letters}{numbers[0]}"
    else:
        # No numbers in name
        return f"{district_code}_{letters}"

def make_code_unique(base_code, used_codes, ou_name):
    if base_code not in used_codes:
        return base_code
    
    # Code exists, append _1, _2, _3, etc.
    counter = 1
    while True:
        unique_code = f"{base_code}_{counter}"
        if unique_code not in used_codes:
            return unique_code
        counter += 1
```

### Example: Lilongwe Areas
```
Area 1  → LL_AREA1
Area 2  → LL_AREA2
Area 10 → LL_AREA10
Area 18 → LL_AREA18
Area 18 Health Center → LL_AREA18_1
Area 25 → LL_AREA25
Area 25 community hospital → LL_AREA25_1
```

## Implementation Details

### Name Cleaning

**Special Handling for Traditional Authority Prefixes:**
For org units starting with "STA ", "Sub TA ", "TA ", or "T/A ", the prefix is skipped and only letters after the prefix are used:

```python
if name.upper().startswith('SUB TA '):
    clean_name = re.sub(r'[^A-Za-z0-9]', '', name[7:].strip())
elif name.upper().startswith('STA '):
    clean_name = re.sub(r'[^A-Za-z0-9]', '', name[4:].strip())
elif name.upper().startswith('TA '):
    clean_name = re.sub(r'[^A-Za-z0-9]', '', name[3:].strip())
elif name.upper().startswith('T/A '):
    clean_name = re.sub(r'[^A-Za-z0-9]', '', name[4:].strip())
else:
    clean_name = re.sub(r'[^A-Za-z0-9]', '', name)
```

**Examples:**
- "STA Chaima" → "Chaima" → "CHAI" → `KS_CHAI`
- "STA Chambwe" → "Chambwe" → "CHAM" → `KS_CHAM`
- "Sub TA Phweremwe" → "Phweremwe" → "PHWE" → `XX_PHWE`
- "TA Balaka" → "Balaka" → "BALA" → `BA_BALA`
- "T/A Nkalo" → "Nkalo" → "NKAL" → `XX_NKAL`
- "Area 25 community hospital" → "AREA" → `LL_AREA`

### District Code Lookup
District codes are looked up by matching the org unit name against entries in `malawi_districts.csv`:

```csv
code,name
BA,Balaka
BL,Blantyre
LL,Lilongwe
MN,Mzuzu City
NB,Nkhatabay
```

For level 4 and 5 units, the algorithm traverses up the parent chain until it finds a level 3 district.

## Statistics

From the current CPMIS dataset:
- **Total org units processed:** 705
- **Level 3 (Districts):** 32/32
- **Level 4 (TAs):** 443/443
- **Level 5 (Facilities):** 230/230
- **Codes with incremental suffixes:** 125 (true duplicates only)
- **Codes with numbers from names:** ~180 (e.g., Area 1-60)

## Benefits

1. **Predictable:** Codes follow a consistent pattern
2. **Readable:** Human-readable district and name components
3. **Unique:** Automatic duplicate handling ensures no conflicts
4. **Scalable:** Algorithm handles any number of duplicates
5. **Traceable:** Easy to identify which district an org unit belongs to

## Usage

```bash
# Generate codes
just task1-auto

# Review generated codes
cat outputs/task1/ou_codes_updated.csv

# Push to DHIS2 (dry-run first)
just push-ou-codes-dry

# Push to DHIS2 (production)
just push-ou-codes
```
