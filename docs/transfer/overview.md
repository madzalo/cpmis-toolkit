# OU Transfer — Overview

**Purpose:** Transfer TEIs between organisation units with automatic ID regeneration and program ownership transfer  
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
2. **Update orgUnits** on TEIs, enrollments, and all events
3. **Transfer program ownership** to make TEIs visible in Tracker Capture web UI
4. **Regenerate IDs** with correct hierarchical prefixes based on destination OU
5. **Preserve relationships** between households and children during transfer
6. **Maintain audit trails** by preserving `createdBy` metadata

---

## How It Works

### The 4-Step Transfer Process

Each TEI goes through a **4-step process** to ensure complete and correct transfer:

#### Step 1: Update TEI and Events
- **POST** `/api/trackedEntityInstances` with `strategy=CREATE_AND_UPDATE`
- Updates TEI's `orgUnit` field
- Updates all event `orgUnit` fields
- Preserves `createdBy` and `created` metadata

#### Step 2: Update Enrollments
- **POST** `/api/enrollments` with `strategy=UPDATE`
- Updates enrollment `orgUnit` fields
- Required because Step 1 doesn't reliably update enrollment orgUnits (DHIS2 limitation)

#### Step 3: Transfer Program Ownership (CRITICAL!)
- **PUT** `/api/tracker/ownership/transfer`
- Transfers program ownership to destination OU
- **Without this step, TEIs are invisible in Tracker Capture web UI**
- DHIS2 uses `programOwners` table to control query visibility

#### Step 4: Update ID Attributes
- **POST** `/api/trackedEntityInstances` with `strategy=UPDATE`
- Updates Household ID or Child UIC to match destination OU code
- Auto-increments sequence numbers to avoid conflicts
- Example: `DE_DEDZ_HH_00000001` → `DE_KAPH_HH_00000001`

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
 DE_DEDZ_HH_00000001                                      DE_KAPH_HH_00000001
```

### Processing Pipeline

Each transfer operation goes through a **five-step pipeline**:

| Step | Name | What It Does |
|------|------|--------------|
| 1 | **Fetch** | Queries source OU for all TEIs (children + households) enrolled within specified year range. Fetches all enrollments, events, and relationships. Uses `/api/enrollments` API to work around DHIS2 caching. |
| 2 | **Select** | User selects which TEIs to **keep** at source. All non-selected TEIs (and their related TEIs) are marked for transfer. |
| 3 | **Re-ID** | Generates new Household IDs and Child UICs based on destination OU hierarchy. Queries existing IDs at destination to find max sequence number. Ensures no ID collisions. |
| 4 | **Transfer** | Executes the 4-step transfer process for each TEI: (1) POST TEI+events, (2) POST enrollments, (3) Transfer ownership, (4) Update IDs. Preserves `createdBy` metadata. |
| 5 | **Verify** | Confirms all TEIs exist at destination with correct IDs, orgUnits, and intact relationships. Generates verification report. |

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

**Automatic ID generation based on destination OU:**

| Source OU | Old ID | Destination OU | New ID |
|-----------|--------|----------------|--------|
| Dedza Boma (facility) | `DE_DEDZ_HH_00000001` | TA Kaphuka (TA) | `DE_KAPH_HH_00000001` |
| Dedza Boma (facility) | `DE_DEDZ_OVC_00000005` | TA Kaphuka (TA) | `DE_KAPH_OVC_00000001` |

**ID Collision Prevention:**
- Queries destination OU for existing IDs
- Finds maximum sequence number
- Starts new IDs from max + 1
- Auto-increments if conflicts detected during update

### Program Ownership Transfer

**Critical for web UI visibility:**

DHIS2 uses a `programOwners` table to control which OUs can see a TEI in Tracker Capture queries. Without transferring ownership:
- ✅ Data is moved correctly in database
- ✅ Direct API fetch works
- ❌ **TEI queries return 0 results**
- ❌ **Web UI shows nothing**

After ownership transfer:
- ✅ TEI appears in Tracker Capture at destination OU
- ✅ All queries work correctly
- ✅ Reports show correct OU attribution

---

## What Gets Updated

### TEI Level
- `orgUnit` → Destination OU UID
- `programOwners[].ownerOrgUnit` → Destination OU UID
- Household ID or Child UIC attribute → New ID with destination OU code

### Enrollment Level
- `orgUnit` → Destination OU UID
- `enrollmentDate` → Preserved (not changed)
- `incidentDate` → Preserved (not changed)

### Event Level
- `orgUnit` → Destination OU UID
- `eventDate` → Preserved (not changed)
- `dataValues` → Preserved (not changed)

### What's Preserved
- All attributes (except IDs which are updated)
- All enrollment dates
- All event dates
- All data values
- All relationships
- `createdBy` and `created` metadata
- `storedBy` metadata

---

## Safety Features

### Pre-Transfer Validation
- Checks for existing IDs at destination
- Validates relationship integrity
- Confirms user selection
- Shows preview of changes

### Atomic Operations
- Each TEI transfer is independent
- Failures don't affect other TEIs
- Detailed error logging for each step
- Rollback not needed (updates are idempotent)

### Audit Trail
- Transfer logs saved to `outputs/transfer/transfer_log_*.csv`
- Preview saved to `outputs/transfer/transfer_preview.csv`
- Includes: TEI UID, old ID, new ID, status, errors
- Verification results saved separately

### Verification
- Confirms TEI exists at destination
- Checks orgUnit on TEI, enrollments, and events
- Validates ID updates
- Verifies relationship integrity
- Reports any discrepancies

---

## Usage

### Quick Start

```bash
just transfer
```

Follow the interactive prompts to:
1. Select source OU (where data was incorrectly entered)
2. Select destination OU (correct location)
3. Enter enrollment year range
4. Review fetched TEIs
5. Select which TEIs to keep at source
6. Review ID mappings
7. Confirm and execute transfer
8. Review verification results

### Verification

```bash
# Show transferred TEIs from latest transfer
just verify

# Comprehensive web UI verification
just verify-web <tei_uid> <ou_uid>

# Clear DHIS2 cache if needed
just clear-cache
```

---

## Technical Details

### API Endpoints Used

1. `/api/enrollments.json` - Fetch enrollments (more reliable than TEI query)
2. `/api/trackedEntityInstances/{uid}.json` - Fetch full TEI details
3. `/api/trackedEntityInstances` - POST to update TEI and events
4. `/api/enrollments` - POST to update enrollment orgUnits
5. `/api/tracker/ownership/transfer` - PUT to transfer program ownership
6. `/api/organisationUnits/{uid}.json` - Fetch OU details

### DHIS2 Limitations Addressed

1. **Enrollment orgUnit not updated by TEI POST** - Solved with separate enrollment POST
2. **Program ownership not transferred automatically** - Solved with explicit ownership transfer
3. **TEI query caching issues** - Solved by using enrollments API for fetching
4. **Attribute updates in bulk POST unreliable** - Solved with separate attribute update POST

### Performance

- Processes ~1.5 TEIs per second
- Includes 4 API calls per TEI (POST TEI, POST enrollment, PUT ownership, POST ID)
- Progress bar shows real-time status
- Handles hundreds of TEIs efficiently

---

## Troubleshooting

### TEIs not showing in web UI after transfer

**Cause**: Program ownership not transferred (Step 3 failed)

**Solution**:
```bash
# Check ownership
just verify-web <tei_uid> <ou_uid>

# If ownership is wrong, re-run transfer
just transfer
```

### IDs not updated

**Cause**: Step 4 failed (ID update)

**Solution**: Check transfer log for errors. Common causes:
- ID already exists at destination (should auto-increment)
- Network timeout during update
- Permission issues

### Relationships broken

**Cause**: Selection logic didn't include related TEIs

**Solution**: The tool prevents this - if relationships would break, transfer is blocked. Review selection carefully.

---

## Best Practices

1. **Start with small batches** - Transfer one year at a time
2. **Verify immediately** - Run `just verify` after each transfer
3. **Check web UI** - Confirm TEIs appear in Tracker Capture
4. **Keep logs** - Transfer logs are saved automatically
5. **Test first** - Try with a single TEI before bulk transfers

---

## Files and Directories

```
src/transfer/
├── transfer_workflow.py    # Main interactive workflow
├── fetcher.py              # Fetch TEIs from source OU
├── engine.py               # Execute 4-step transfer
├── verifier.py             # Verify transfer results
├── verify_at_destination.py # Show transferred TEIs with names
├── verify_web_ui.py        # Comprehensive web UI verification
└── clear_dhis2_cache.py    # Clear DHIS2 cache

outputs/transfer/
├── transfer_log_*.csv      # Transfer execution logs
├── transfer_preview.csv    # Preview of ID mappings
└── verification_*.csv      # Verification results

docs/transfer/
├── overview.md             # This file
└── tasks.md                # Detailed task breakdown
```
