# OU Transfer — Overview

**App:** CPMIS OU Transfer & Re-ID  
**Purpose:** Transfer TEIs between organisation units with automatic ID regeneration  
**Date:** April 2026

---

## Background

### The Problem

During field data collection, some **Community Para Workers (CPWs)** incorrectly register children and households at the **facility level** instead of the correct **TA (Traditional Authority) level**. This creates several issues:

1. **Incorrect hierarchy** — Children appear under facilities instead of TAs in reports
2. **Wrong ID prefixes** — Household IDs and Child UICs contain facility codes instead of TA codes
3. **Data integrity** — Organizational structure doesn't reflect actual service delivery points
4. **Reporting errors** — Aggregations and analytics show incorrect geographical distribution

### The Solution

**OU Transfer** provides a safe, controlled way to:

1. **Move TEIs** from incorrect org units (facilities) to correct ones (TAs)
2. **Regenerate IDs** with correct hierarchical prefixes based on destination OU
3. **Preserve relationships** between households and children during transfer
4. **Maintain audit trails** by preserving `createdBy` metadata
5. **Selective transfer** based on enrollment year ranges and user selection

---

## How It Works

### Data Flow

```
Source OU (Facility)          Transfer Engine              Destination OU (TA)
┌──────────────────┐         ┌──────────────┐            ┌──────────────────┐
│ Children (OVCs)  │         │ 1. Fetch     │            │ Children (OVCs)  │
│ Households       │────────▶│ 2. Select    │───────────▶│ Households       │
│ Enrollments      │         │ 3. Re-ID     │            │ Enrollments      │
│ Events           │         │ 4. Transfer  │            │ Events           │
│ Relationships    │         │ 5. Verify    │            │ Relationships    │
└──────────────────┘         └──────────────┘            └──────────────────┘
     (Wrong IDs)                                               (Correct IDs)
```

### Processing Pipeline

Each transfer operation goes through a **five-step pipeline**:

| Step | Name | What It Does |
|------|------|--------------|
| 1 | **Fetch** | Queries source OU for all TEIs (children + households) enrolled within specified year range. Fetches all enrollments, **events**, and relationships for each TEI. Builds a complete relationship graph. |
| 2 | **Select** | User selects which TEIs to **keep** at source. All non-selected TEIs (and their related TEIs) are marked for transfer. |
| 3 | **Re-ID** | Generates new Household IDs and Child UICs based on destination OU hierarchy. Ensures no ID collisions at destination. |
| 4 | **Transfer** | Moves TEIs to destination OU using DHIS2 API. Updates org unit on the TEI, **every enrollment**, and **every event** (case management records, assessments, service records). Regenerates IDs. Preserves `createdBy` metadata. |
| 5 | **Verify** | Confirms all TEIs exist at destination with correct IDs, intact relationships, and that **all events** have the correct org unit. Generates verification report. |

---

## Key Features

### Intelligent Selection Logic

**User selects what to KEEP, not what to MOVE:**
- Select specific children → their households are automatically kept
- Select specific households → their children are automatically kept
- Everything else in the year range is transferred

**Example:**
```
Source OU has 50 children enrolled in 2024-2026
User selects 10 children to keep at facility
→ Those 10 children + their households stay
→ Remaining 40 children + their households are transferred to TA
```

### Relationship Preservation

**Household-Child links are sacred:**
- If a child is transferred, their household **must** be transferred
- If a household is transferred, **all** their children **must** be transferred
- Relationships are validated before and after transfer
- Transfer fails if relationships would be broken

**Relationship Resolution:**
```
Child A ──belongs to──▶ Household 1
Child B ──belongs to──▶ Household 1
Child C ──belongs to──▶ Household 2

User keeps Child A
→ Household 1 is kept (because Child A needs it)
→ Child B is kept (because Household 1 is kept)
→ Child C is transferred
→ Household 2 is transferred
```

### ID Regeneration

**New IDs reflect destination OU hierarchy:**

Before transfer (at facility `ZA_CHIK_LAMB`):
```
Household: ZA_CHIK_LAMB_HH_00000001
Child:     ZA_CHIK_LAMB_OVC_00000001
```

After transfer (to TA `ZA_CHIK`):
```
Household: ZA_CHIK_HH_00000123
Child:     ZA_CHIK_OVC_00000456
```

**Collision prevention:**
- Queries destination OU for existing max sequence numbers
- New IDs start from `max + 1`
- Ensures uniqueness across the entire destination OU

### Audit Trail Preservation

**`createdBy` is preserved during transfer:**
- Uses `POST` (not `PUT`) to update TEIs via DHIS2 API
- Original creator remains unchanged in audit logs
- `lastUpdatedBy` reflects the transfer operation (expected behavior)

### Comprehensive Entity Transfer

**Everything moves together — no orphaned data:**
- ✅ **Tracked Entity Instances (TEIs)** — org unit updated to destination
- ✅ **Program Enrollments** — org unit updated to destination
- ✅ **All Events** — every event (case management, assessments, service records) has its org unit updated. Events are the most numerous entity and must ALL be transferred to avoid split data.
- ✅ **Relationships** — household-child links preserved (UID-based, not OU-specific)
- ✅ **Attribute Values** — preserved except Household ID / Child UIC (regenerated)

---

## Typical Workflow

### For the Administrator

```bash
# 1. Start the interactive transfer workflow
just transfer

# 2. Select source organisation unit (facility)
#    → Interactive picker shows hierarchy
#    → Example: "ZA_CHIK_LAMB (Lambulira)"

# 3. Select destination organisation unit (TA)
#    → Interactive picker shows hierarchy
#    → Example: "ZA_CHIK (TA Chikowi)"

# 4. Enter enrollment year range
#    → Example: "2024-2026"

# 5. Preview affected records
#    → Shows count: "Found 50 children, 35 households"

# 6. Select TEIs to KEEP at source
#    → CSV export with all TEIs
#    → Mark which ones to keep (others will be transferred)
#    → Or specify: "Keep first 10 by enrollment date"

# 7. Review transfer preview
#    → CSV shows: old OU, new OU, old ID, new ID
#    → Relationship graph displayed

# 8. Confirm and execute
#    → Transfer runs with progress tracking
#    → Verification runs automatically

# 9. Review verification report
#    → ✅ All TEIs at destination
#    → ✅ All IDs updated correctly
#    → ✅ All relationships intact
```

### Advanced Commands

```bash
# Preview transfer without executing
just transfer-preview <source_uid> <dest_uid> --years 2024-2026

# Transfer specific TEIs from CSV
just transfer-apply <selection_csv>

# Verify a completed transfer
just transfer-verify <transfer_report_csv>

# Transfer with automatic selection (keep first N)
just transfer-auto <source_uid> <dest_uid> --years 2024-2026 --keep 10
```

---

## Data Transferred

The tool transfers the following DHIS2 entities:

| Entity | What Happens |
|--------|--------------|
| **Tracked Entity Instances (TEIs)** | `orgUnit` updated to destination, Household ID / Child UIC regenerated |
| **Enrollments** | `orgUnit` updated to destination, dates preserved |
| **Events** | **Every event** across all program stages has its `orgUnit` updated to destination. This includes case management events, assessments, and service delivery records. Event dates, data values, and status are all preserved. |
| **Relationships** | Preserved (UID-based, not org-unit-specific) |
| **Attribute Values** | Preserved except Household ID / Child UIC (regenerated) |

---

## Configuration

The app reads credentials from the shared `.env` file in the project root:

```env
# Required
DHIS2_URL=https://cpmis.gender.gov.mw
DHIS2_USERNAME=your_username
DHIS2_PASSWORD=your_password

# Optional (for direct DB verification)
DB_HOST=your_database_host
DB_PORT=5433
DB_NAME=cpmis_copy_clone
DB_USER=your_db_username
DB_PASSWORD=your_db_password
```

Directories are automatically resolved relative to the project root:

| Directory | Purpose |
|-----------|---------|
| `outputs/transfer/` | Transfer previews, selection CSVs, verification reports |
| `outputs/transfer/completed/` | Successfully completed transfer records |

---

## Architecture

```
src/transfer/
├── cli.py                    # Interactive CLI workflow
├── config.py                 # Transfer-specific configuration
├── fetcher.py                # Fetch TEIs by OU + enrollment year range
├── relationship_resolver.py  # Build household-child relationship graph
├── selector.py               # Selection logic (keep vs transfer)
├── id_generator.py           # Generate new IDs for destination OU
├── transfer_engine.py        # Core transfer orchestration
├── api_client.py             # DHIS2 API wrapper (POST-based updates)
├── verifier.py               # Post-transfer verification
└── utils.py                  # Logging, CSV handling, progress tracking
```

### Shared Utilities (Reused from Cleanup)

```
src/shared/
├── settings.py               # DHIS2 + DB credentials (already exists)
├── ou_picker.py              # Interactive org unit selection (extracted from Phase 2)
├── id_utils.py               # ID generation logic (extracted from Phase 2)
└── dhis2_client.py           # Common DHIS2 API operations (extracted from Phase 2)
```

---

## Safety Features

### Pre-Transfer Validation
- ✅ **Relationship integrity check** — ensures all household-child links will remain intact
- ✅ **ID collision check** — verifies new IDs don't already exist at destination
- ✅ **Enrollment validation** — confirms all enrollments are within specified year range
- ✅ **Dry-run preview** — generates CSV showing exactly what will happen

### During Transfer
- ✅ **Atomic operations** — each TEI transfer is independent (partial failures don't corrupt data)
- ✅ **Progress tracking** — real-time updates on transfer status
- ✅ **Error logging** — detailed logs for any failed transfers

### Post-Transfer Verification
- ✅ **Existence check** — confirms all TEIs exist at destination
- ✅ **ID verification** — confirms Household IDs and Child UICs updated correctly
- ✅ **Relationship verification** — confirms all household-child links intact
- ✅ **Enrollment verification** — confirms enrollments moved to destination OU
- ✅ **Event verification** — confirms events moved to destination OU

### Rollback Plan
If a transfer needs to be reversed:
1. Use the transfer report CSV (contains old OU, old IDs)
2. Run reverse transfer: destination → source
3. Restore original IDs from CSV
4. Verify relationships intact

---

## Technical Considerations

### Why POST Instead of PUT?

**DHIS2 API behavior:**
- `PUT /api/trackedEntityInstances/{uid}` → **overwrites** `lastUpdatedBy`
- `POST /api/trackedEntityInstances` with full payload → **preserves** `createdBy`, updates `lastUpdatedBy`

**Our approach:**
- Use `POST` for TEI updates (create-and-update import strategy)
- `createdBy` remains unchanged (original CPW)
- `lastUpdatedBy` reflects the transfer operation (expected and acceptable)

### Event Transfer Strategy

**Events are the most numerous entity** — a single child may have dozens of events across multiple program stages. All events must be transferred:

1. Fetch all events for each TEI being transferred
2. Update `orgUnit` on every event to the destination OU
3. Verify every event exists at destination after transfer
4. If any event fails to transfer, log it for manual resolution

### Relationship Resolution Algorithm

```python
def resolve_transfer_set(selected_to_keep, all_teis):
    """
    Given TEIs selected to KEEP, determine which TEIs must be TRANSFERRED.
    Ensures household-child relationships remain intact.
    """
    keep_set = set(selected_to_keep)
    
    # Expand keep_set to include related TEIs
    for tei in selected_to_keep:
        if tei.type == "Child":
            # Keep the child's household
            keep_set.add(tei.household)
        elif tei.type == "Household":
            # Keep all children of this household
            keep_set.update(tei.children)
    
    # Everything not in keep_set is transferred
    transfer_set = all_teis - keep_set
    
    # Expand transfer_set to include related TEIs
    for tei in transfer_set:
        if tei.type == "Child":
            # Transfer the child's household (if not already kept)
            if tei.household not in keep_set:
                transfer_set.add(tei.household)
        elif tei.type == "Household":
            # Transfer all children of this household (if not already kept)
            transfer_set.update([c for c in tei.children if c not in keep_set])
    
    return transfer_set
```

### ID Generation Strategy

**Reuses Cleanup Phase 2 logic:**
1. Extract destination OU code from hierarchy (e.g., `ZA_CHIK`)
2. Query destination OU for existing TEIs
3. Find max sequence number for Household IDs
4. Find max sequence number for Child UICs
5. Generate new IDs starting from `max + 1`

**Example:**
```python
# Destination OU: ZA_CHIK
# Existing max: ZA_CHIK_HH_00000122

# Transferring 3 households:
ZA_CHIK_HH_00000123
ZA_CHIK_HH_00000124
ZA_CHIK_HH_00000125
```

---

## Performance Expectations

| Operation | Speed | Notes |
|-----------|-------|-------|
| **Fetch TEIs** | ~100 TEIs/sec | DHIS2 API query with filters |
| **Relationship resolution** | Instant | In-memory graph traversal |
| **ID generation** | Instant | Simple sequence increment |
| **Transfer (API)** | ~5-10 TEIs/sec | DHIS2 API rate limits apply |
| **Verification** | ~50 TEIs/sec | DHIS2 API queries |

**Estimated time for 100 TEIs:** ~2-3 minutes (fetch + transfer + verify)

---

## Limitations & Known Issues

### Current Limitations
1. **Single source → single destination** — cannot split TEIs across multiple destinations in one operation
2. **Year-based filtering only** — cannot filter by other criteria (e.g., case status, service type)
3. **Manual selection** — no automatic rules for which TEIs to keep vs transfer

### Future Enhancements
- [ ] Batch transfer (multiple source OUs → multiple destinations)
- [ ] Advanced filtering (by program stage, data element values, etc.)
- [ ] Automatic selection rules (e.g., "keep TEIs with recent events")
- [ ] Transfer history tracking (audit log of all transfers)
- [ ] Undo/rollback command (automatic reversal of transfers)

---

## Getting Started

See the main [README.md](../../README.md) for installation and setup instructions.

For task breakdown and implementation status, see [tasks.md](tasks.md).

For contributing guidelines, see [CONTRIBUTING.md](../../CONTRIBUTING.md).
