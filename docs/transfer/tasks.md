# OU Transfer — Tasks

**Status:** ✅ Complete and Production-Ready  
**Last Updated:** April 13, 2026

---

## Implementation Tasks

### ✅ Task 1: Fetch TEIs from Source OU
**File:** `src/transfer/fetcher.py`

**What it does:**
- Queries enrollments at source OU (more reliable than TEI query)
- Extracts unique TEI UIDs from enrollments
- Fetches full TEI details for each UID with program parameter
- Includes all enrollments, events, and relationships
- Works around DHIS2 TEI query caching issues

**Key functions:**
- `fetch_teis_via_enrollments()` - Primary fetch method using enrollments API
- `fetch_teis_full()` - Main entry point with fallback to direct TEI query
- `fetch_relationships_for_tei()` - Fetch relationships for specific TEI

**Why enrollments API:**
DHIS2's `/api/trackedEntityInstances` query has caching issues after transfers. The `/api/enrollments` API is more reliable and returns current data immediately.

---

### ✅ Task 2: Interactive Selection
**File:** `src/transfer/transfer_workflow.py`

**What it does:**
- Displays all fetched TEIs with names and IDs
- User selects which TEIs to **keep** at source
- Automatically handles related TEIs (households ↔ children)
- Everything not selected is marked for transfer

**Selection modes:**
1. **Keep mode** (default) - Select what stays, rest is transferred
2. **Transfer mode** - Select what moves, rest stays

**Relationship handling:**
- If child is kept → household is kept
- If household is kept → all children are kept
- Prevents broken relationships

---

### ✅ Task 3: Generate New IDs
**File:** `src/transfer/id_generator.py`

**What it does:**
- Queries destination OU for existing IDs
- Finds maximum sequence number for each program
- Generates new IDs starting from max + 1
- Format: `{OU_CODE}_{TYPE}_{SEQUENCE}`
  - Example: `DE_KAPH_HH_00000001`

**ID types:**
- Household ID: `{OU}_HH_{SEQ}` (attribute: `Rdk90NLvLip`)
- Child UIC: `{OU}_OVC_{SEQ}` (attribute: `cxr1eaTGEBO`)

**Collision prevention:**
- Checks all existing IDs at destination
- Auto-increments if conflict detected during update
- Retries up to 10 times with incremented sequence

---

### ✅ Task 4: Execute Transfer (4-Step Process)
**File:** `src/transfer/engine.py`

**The 4-step transfer process:**

#### Step 1: Update TEI and Events
```python
def build_transfer_payload(tei, dest_ou_uid):
    """
    Build payload with updated orgUnits for TEI and all events.
    """
```

- POST `/api/trackedEntityInstances` with `strategy=CREATE_AND_UPDATE`
- Updates TEI `orgUnit`
- Updates all event `orgUnit` fields
- Preserves `createdBy` metadata
- **Limitation:** Doesn't update enrollment orgUnits

#### Step 2: Update Enrollments
```python
def update_enrollment_ou(enrollment_uid, dest_ou_uid):
    """
    Update enrollment orgUnit separately.
    Required because Step 1 doesn't update enrollments reliably.
    """
```

- POST `/api/enrollments` with `strategy=UPDATE`
- Updates enrollment `orgUnit`
- Required due to DHIS2 API limitation

#### Step 3: Transfer Program Ownership (CRITICAL!)
```python
def transfer_program_ownership(tei_uid, program_id, dest_ou_uid):
    """
    Transfer program ownership to destination OU.
    CRITICAL for web UI visibility.
    """
```

- PUT `/api/tracker/ownership/transfer`
- Updates `programOwners` table
- **Without this, TEIs are invisible in Tracker Capture web UI**
- DHIS2 uses ownership to control query visibility

#### Step 4: Update ID Attributes
```python
def update_tei_attribute(tei_uid, attribute_uid, new_value, program_id, dest_ou_code):
    """
    Update ID attribute to match destination OU code.
    Auto-increments if conflict detected.
    """
```

- POST `/api/trackedEntityInstances` with `strategy=UPDATE`
- Updates Household ID or Child UIC
- Auto-increments sequence if ID exists
- Example: `DE_DEDZ_HH_00000001` → `DE_KAPH_HH_00000001`

**Key functions:**
- `execute_transfer()` - Main transfer orchestration
- `build_transfer_payload()` - Construct TEI payload
- `update_enrollment_ou()` - Update enrollment orgUnits
- `transfer_program_ownership()` - Transfer ownership
- `update_tei_attribute()` - Update ID attributes

---

### ✅ Task 5: Verify Transfer
**File:** `src/transfer/verifier.py`

**What it does:**
- Fetches each transferred TEI from destination
- Verifies orgUnit on TEI, enrollments, and events
- Checks ID updates
- Validates relationship integrity
- Generates verification report

**Verification checks:**
- ✅ TEI exists at destination
- ✅ TEI orgUnit matches destination
- ✅ All enrollment orgUnits match destination
- ✅ All event orgUnits match destination
- ✅ ID attribute updated correctly
- ✅ Relationships preserved

---

### ✅ Task 6: Show Transferred TEIs
**File:** `src/transfer/verify_at_destination.py`

**What it does:**
- Reads latest transfer log
- Fetches TEI details with program parameter
- Displays names, IDs, and orgUnits
- Shows enrollment and event details

**Usage:**
```bash
# Show from latest transfer log
just verify

# Verify specific TEI
just verify --tei <tei_uid>

# Verify all at destination OU
just verify --ou <ou_uid>
```

**Key features:**
- Auto-detects program from enrollment
- Fetches program-scoped attributes correctly
- Shows human-readable names and IDs
- Displays current orgUnits for verification

---

### ✅ Task 7: Web UI Verification
**File:** `src/transfer/verify_web_ui.py`

**What it does:**
- Performs 3 verification methods:
  1. Direct API fetch (always works)
  2. Enrollment query (works after transfer)
  3. TEI query (may have cache lag)
- Checks analytics status
- Provides clear diagnosis

**Usage:**
```bash
just verify-web <tei_uid> <ou_uid>
```

**Output example:**
```
✅ Direct API: TEI found at TA Kaphuka
✅ Enrollment query: Found (5 enrollments)
⚠️  TEI query: Not found (cache issue)
```

---

### ✅ Task 8: Cache Management
**File:** `src/transfer/clear_dhis2_cache.py`

**What it does:**
- Clears DHIS2 application cache
- Triggers analytics table update
- Provides clear next steps

**Usage:**
```bash
just clear-cache
```

**Note:** Usually not needed after ownership transfer was implemented. The cache issue was actually a missing ownership transfer, not a real cache problem.

---

## Workflow Integration

### Main Workflow
**File:** `src/transfer/transfer_workflow.py`

**Steps:**
1. Select source OU
2. Select destination OU
3. Enter enrollment year range
4. Fetch TEIs from source
5. Select TEIs to keep at source
6. Generate new IDs for destination
7. Execute 4-step transfer
8. Verify transfer results

**Interactive prompts:**
- OU selection with search
- Year range input
- TEI selection with relationship handling
- Transfer confirmation with preview
- Real-time progress display

---

## Justfile Commands

```bash
# Main transfer workflow
just transfer

# Verification
just verify                          # Show from latest transfer log
just verify --tei <uid>              # Verify specific TEI
just verify --ou <ou_uid>            # Verify all at destination
just verify-web <tei> <ou>           # Comprehensive web verification

# Cache management
just clear-cache                     # Clear DHIS2 cache (rarely needed)
```

---

## Technical Implementation Details

### DHIS2 API Limitations Addressed

1. **Enrollment orgUnit not updated by TEI POST**
   - **Problem:** POST to `/api/trackedEntityInstances` doesn't update enrollment orgUnits
   - **Solution:** Separate POST to `/api/enrollments` with `strategy=UPDATE`

2. **Program ownership not transferred**
   - **Problem:** TEIs invisible in web UI queries after transfer
   - **Solution:** PUT to `/api/tracker/ownership/transfer`

3. **TEI query caching**
   - **Problem:** `/api/trackedEntityInstances` query returns stale data
   - **Solution:** Use `/api/enrollments` API for fetching

4. **Attribute updates unreliable in bulk POST**
   - **Problem:** ID attributes not updated in Step 1
   - **Solution:** Separate POST with `strategy=UPDATE` and `mergeMode=MERGE`

### Performance Optimizations

- **Batch operations:** Process multiple TEIs in single workflow
- **Progress tracking:** Real-time progress bar with ETA
- **Error handling:** Continue on individual failures, log errors
- **Verification:** Parallel verification of multiple TEIs

### Data Integrity

- **Relationship validation:** Check before and after transfer
- **Atomic operations:** Each TEI transfer is independent
- **Audit trail:** Complete logs of all operations
- **Rollback safety:** Updates are idempotent (can re-run safely)

---

## Testing Checklist

### Pre-Transfer
- [ ] Source OU has TEIs to transfer
- [ ] Destination OU exists and is accessible
- [ ] User has permissions for both OUs
- [ ] Enrollment year range is correct

### During Transfer
- [ ] All 4 steps complete successfully
- [ ] Progress bar shows accurate status
- [ ] No errors in transfer log
- [ ] Transfer completes in reasonable time

### Post-Transfer
- [ ] `just verify` shows all TEIs with correct names
- [ ] All TEIs have correct orgUnits
- [ ] All IDs updated to destination OU code
- [ ] TEIs visible in Tracker Capture web UI
- [ ] Relationships intact
- [ ] Events have correct orgUnits

### Web UI Verification
- [ ] Go to Tracker Capture
- [ ] Select destination OU
- [ ] Select program
- [ ] TEIs appear in list
- [ ] Can open and view TEI details
- [ ] All data is correct

---

## Troubleshooting

### Issue: TEIs not showing in web UI

**Diagnosis:**
```bash
just verify-web <tei_uid> <ou_uid>
```

**If ownership is wrong:**
- Re-run transfer (ownership transfer is now included)

### Issue: IDs not updated

**Check transfer log:**
```bash
cat outputs/transfer/transfer_log_*.csv
```

**Common causes:**
- ID already exists (should auto-increment)
- Network timeout
- Permission issues

**Solution:** Re-run transfer (ID updates are idempotent)

### Issue: Relationships broken

**This should never happen** - the selection logic prevents it.

**If it does:**
- Check transfer log for errors
- Verify relationship data in DHIS2
- Report as bug

---

## Future Enhancements

### Potential Improvements

1. **Bulk transfer from CSV**
   - Upload CSV with TEI UIDs to transfer
   - Skip interactive selection

2. **Transfer history**
   - Track all transfers in database
   - Show transfer history for TEI
   - Undo/reverse transfers

3. **Dry-run mode**
   - Simulate transfer without executing
   - Show what would change
   - Validate before running

4. **Parallel processing**
   - Transfer multiple TEIs simultaneously
   - Faster for large batches
   - Requires careful error handling

5. **Web UI**
   - Browser-based transfer interface
   - Visual OU selection
   - Real-time progress tracking

---

## Maintenance

### Regular Tasks

1. **Monitor transfer logs**
   - Check for recurring errors
   - Identify problematic OUs
   - Track transfer volumes

2. **Update documentation**
   - Keep examples current
   - Add new troubleshooting cases
   - Document edge cases

3. **Test with new DHIS2 versions**
   - Verify API compatibility
   - Check for new limitations
   - Update workarounds if needed

### Code Maintenance

- **Keep dependencies updated:** `pip install --upgrade -r requirements.txt`
- **Run tests before changes:** `just test`
- **Commit frequently:** Small, focused commits
- **Document changes:** Update this file when adding features
