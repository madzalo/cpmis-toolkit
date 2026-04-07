# CPMIS ID Remediation - Implementation Tasks

## Phase 1: Assign Organisation Unit Codes ✅ COMPLETED

### Task 1.1: Export Organisation Units ✅
```bash
# Using justfile automation
just task1-auto

# This runs:
# 1. Export org units from DHIS2 API to outputs/task1/ou_export.json
# 2. Create ou_codes.csv reference table
# 3. Auto-generate standardised codes for all levels
```

### Task 1.2: Create OU Code Reference Table ✅
Auto-generated CSV file: `outputs/task1/ou_codes_updated.csv` with columns:
- `dhis2_uid`
- `ou_name`
- `ou_level`
- `standardised_code`

**Codes generated:**
- **Level 3 (Districts)**: 2 letters (32/32 updated: BA, BL, CK, CR, CT, DE, DO, KR, KS, LK, LL, MH, MG, MC, MN, MU, MW, MZ, NE, NB, NK, NS, NU, NI, PH, RU, SA, TH, ZA)
- **Level 4 (TAs)**: District prefix + 4 letters (443/443 updated: e.g., BA_BALA, LL_AREA, MN_CHIB)
- **Level 5 (Facilities)**: District prefix + 4 letters (230/230 updated: e.g., LL_KABU, BL_BANG, CK_BERE)

### Task 1.3: Update OU Codes in DHIS2
```python
# Option A: Using API
import requests
import csv

with open('ou_codes.csv') as f:
    for row in csv.DictReader(f):
        url = f"https://your-dhis2.org/api/organisationUnits/{row['dhis2_uid']}"
        data = {"code": row['standardised_code']}
        requests.put(url, json=data, auth=('user', 'pass'))

# Option B: Using Database
psql -d dhis2_db -c "UPDATE organisationunit SET code = 'LL' WHERE uid = 'abc123';"
```

### Task 1.4: Validate OU Codes
```sql
-- Check for nulls
SELECT COUNT(*) FROM organisationunit WHERE code IS NULL AND hierarchylevel IN (2,3);

-- Check for duplicates
SELECT code, COUNT(*) FROM organisationunit GROUP BY code HAVING COUNT(*) > 1;

-- Check format
SELECT COUNT(*) FROM organisationunit WHERE hierarchylevel = 2 AND LENGTH(code) != 2;
SELECT COUNT(*) FROM organisationunit WHERE hierarchylevel = 3 AND LENGTH(code) != 4;
```

---

## Phase 2: TEI ID Standardisation ✅ COMPLETED

### Task 2.1: ID Generation ✅
IDs are generated based on the **org unit** where the TEI is registered (district, TA, or facility).

**Format:** `{OU_CODE}_{TYPE}_{SEQUENCE}`
- Household: `ZA_CHIK_LAMB_HH_00000001`
- Child UIC: `ZA_CHIK_LAMB_OVC_00000001`
- Sequence is 8-digit zero-padded, scoped per org unit per type

**Implementation:** `src/phase2/phase2_workflow.py`
- Fetches TEIs from DHIS2 API per org unit (6 parallel workers)
- Generates standardised IDs using OU codes from Phase 1
- Saves mapping CSV with old → new IDs

### Task 2.2: Update Methods ✅
Two methods available, selectable interactively or via CLI:

**Method 1: DHIS2 API (safe)**
```bash
just phase2-apply outputs/phase2/id_mapping_za.csv
```
- Async `PUT /api/trackedEntityInstances/{uid}` with 4 concurrent connections
- `mergeMode=MERGE` — only updates the ID attribute, preserves all others
- Retry logic with 3 attempts per TEI
- ~8 TEIs/min

**Method 2: Direct PostgreSQL (fast)**
```bash
just phase2-apply-db outputs/phase2/id_mapping_za.csv
```
- UPSERT on `trackedentityattributevalue` table
- Resolves UIDs → internal database IDs:
  - Attribute: `SYUXY9pax4w` → `15311` (Household ID), `cxr1eaTGEBO` → `17304` (Child UIC)
  - TEI UIDs → `trackedentityinstanceid` integers
- Batched execution (500 rows/batch) with real-time progress
- Automatic rollback on failure
- ~5,000 TEIs/s (~5s for 20,000 TEIs)
- **Requires:** DB credentials in `.env`, database backup before use

### Task 2.3: Verification ✅
```bash
just phase2-verify outputs/phase2/id_mapping_za.csv
```
- Queries database for actual attribute values
- Compares against expected values from CSV
- Reports: matched, mismatched, not found
- Auto-runs after DB updates in the interactive workflow

### Task 2.4: Interactive Workflow ✅
```bash
just phase2
```
Steps:
1. Select scope (org unit / district / multiple districts / all)
2. Select program (Household / OVC / both)
3. Generate IDs — fetches TEIs, generates new IDs
4. Preview changes — summary + sample table
5. Select update method — API (safe) or DB (fast)
6. Confirm and apply — double confirmation for DB mode
7. Verify — auto-checks DB values match (DB mode only)

### Task 2.5: Commands Reference ✅
```bash
just phase2                           # Interactive workflow (recommended)
just phase2-district ZA               # Single district
just phase2-districts "ZA,BL,MU"      # Multiple districts
just phase2-all                       # All org units
just phase2-apply <csv>               # Re-apply via API
just phase2-apply-db <csv>            # Re-apply via database (fast)
just phase2-verify <csv>              # Verify DB values match CSV
```

### Task 2.6: Outputs ✅
- `outputs/phase2/id_mapping_*.csv` — mapping of old → new IDs
- `outputs/phase2/id_mapping_*_db_log_*.csv` — timestamped DB update log

---

## Phase 3: Production Execution

### Task 3.1: Backup Production Database
```bash
pg_dump dhis2_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Task 3.2: Run Per District
Process each district one at a time, verify, then move to the next:
```bash
just phase2-district ZA    # Pick method 2 (DB), verify auto-runs
just phase2-district BL    # Repeat for each district
```

### Task 3.3: Verify All Districts
```bash
just phase2-verify outputs/phase2/id_mapping_za.csv
just phase2-verify outputs/phase2/id_mapping_bl.csv
# etc.
```

### Task 3.4: Validate Production Data
```sql
-- Check for duplicates within each program
SELECT value, COUNT(*) FROM trackedentityattributevalue
WHERE trackedentityattributeid = 15311  -- Household ID
GROUP BY value HAVING COUNT(*) > 1;

SELECT value, COUNT(*) FROM trackedentityattributevalue
WHERE trackedentityattributeid = 17304  -- Child UIC
GROUP BY value HAVING COUNT(*) > 1;
```

---

## Phase 4: Enable Auto-Generation (Future)

### Task 4.1: Configure DHIS2 Auto-ID
- Configure tracked entity attributes with auto-generation pattern
- Set `Unique = true` and `Generated = true`

### Task 4.2: Initialize Sequence Starting Points
- Use max sequence from standardised IDs as starting point
- Test concurrent registrations for uniqueness

---

## Phase 5: Documentation ✅

### Task 5.1: Repository Documentation ✅
- `README.md` — comprehensive usage guide with all commands
- `overview.md` — technical architecture and design decisions
- `ALGORITHM.md` — detailed algorithm documentation
- `tasks.md` — this file (task tracking)

---

## Quick Reference

**ID Formats:**
- Household: `ZA_CHIK_LAMB_HH_00000001`
- Child UIC: `ZA_CHIK_LAMB_OVC_00000001`

**DHIS2 Attributes:**
- Household ID: `SYUXY9pax4w` (DB internal ID: `15311`)
- Child UIC: `cxr1eaTGEBO` (DB internal ID: `17304`)

**Key Commands:**
- `just phase2` — interactive workflow
- `just phase2-apply-db <csv>` — fast database update
- `just phase2-verify <csv>` — verify database values
