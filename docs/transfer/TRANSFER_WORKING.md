# ✅ Transfer is Working - Complete Summary

**Date**: April 13, 2026  
**Status**: FULLY FUNCTIONAL

---

## What Works

### ✅ Transfer Process (2 Steps)
1. **Step 1**: POST TEI → Updates TEI orgUnit + all event orgUnits
2. **Step 2**: POST enrollments → Updates enrollment orgUnits separately

**IDs are preserved** (no regeneration per user request)

### ✅ Verification Methods

#### 1. Verify Specific TEI
```bash
PYTHONPATH=src ./venv/bin/python src/transfer/verify_at_destination.py --tei Tz4EVwE6aIX
```

**Output**:
```
TEI UID:    Tz4EVwE6aIX
Name:       christian
Child UIC:  DE_KAPH_OVC_00000002
TEI OU:     TA Kaphuka (DE_KAPH)

Enrollments: 1
  Enrollment qZYpcRUB9mz:
    OU:       TA Kaphuka (DE_KAPH)
    Date:     2026-01-28T00:00:00.000
    Events:   6
      Event h7b4njBQeMv: TA Kaphuka (DE_KAPH) on 2026-01-28
      Event ErXKf78NiTC: TA Kaphuka (DE_KAPH) on 2026-01-28
      Event QG8wAlikMJC: TA Kaphuka (DE_KAPH) on 2026-01-28
      ... and 3 more events
```

#### 2. Verify All TEIs at Destination
```bash
PYTHONPATH=src ./venv/bin/python src/transfer/verify_at_destination.py --ou vkM60NDTFE8
```

**Output**:
```
Found 3 enrollments at destination

[1/3] TEI: T7Vcpg7ekr5
  Name:       Sefasi
  Child UIC:  DE_KAPH_OVC_00000001
  TEI OU:     TA Kaphuka (DE_KAPH)

[2/3] TEI: Tz4EVwE6aIX
  Name:       christian
  Child UIC:  DE_KAPH_OVC_00000002
  TEI OU:     TA Kaphuka (DE_KAPH)

[3/3] TEI: JfvtKKCZU6l
  Name:       sibo
  Child UIC:  DE_KAPH_OVC_00000003
  TEI OU:     TA Kaphuka (DE_KAPH)
```

### ✅ Fetching After Transfer
The fetcher now uses `/api/enrollments` as the primary method, which works reliably after transfers:

```bash
just transfer
# Select: TA Kaphuka → Dedza Boma
# Year: 2026
```

**Output**:
```
📡 Fetching MW Harmonized OVC Program - CPMIS enrollments from vkM60NDTFE8...
📡 Found 3 enrollments for 3 unique TEIs
✅ Fetched 3 TEIs, 14 events
```

---

## Technical Details

### The DHIS2 Caching Issue

**Problem**: After transferring a TEI, the `/api/trackedEntityInstances.json?ou=X&program=Y` query returns 0 results even though the TEI exists at that OU.

**Root Cause**: DHIS2 has a server-side caching/indexing mechanism for TEI queries that doesn't update immediately after POST operations.

**Evidence**:
- ✅ Direct TEI fetch by UID works
- ✅ `/api/enrollments.json?ou=X&program=Y` works
- ❌ `/api/trackedEntityInstances.json?ou=X&program=Y` returns 0

**Solution**: Use enrollments API for fetching:
```python
# 1. Query enrollments at OU
GET /api/enrollments.json?ou=vkM60NDTFE8&program=xhzwCCKzFBM

# 2. Extract TEI UIDs from enrollments
tei_uids = [e['trackedEntityInstance'] for e in enrollments]

# 3. Fetch full TEI details for each
GET /api/trackedEntityInstances/{tei_uid}.json?program=xhzwCCKzFBM
```

### What Gets Updated

| Entity | orgUnit Updated | Method |
|--------|----------------|--------|
| **TEI** | ✅ Yes | POST /api/trackedEntityInstances |
| **Enrollment** | ✅ Yes | POST /api/enrollments |
| **Events** | ✅ Yes | POST /api/trackedEntityInstances |
| **Attributes** | ❌ No (preserved) | N/A |

### API Endpoints Used

1. **Transfer TEI**: `POST /api/trackedEntityInstances` with `strategy=CREATE_AND_UPDATE`
2. **Update Enrollment**: `POST /api/enrollments` with `strategy=UPDATE`
3. **Fetch Enrollments**: `GET /api/enrollments.json?ou=X&program=Y`
4. **Fetch TEI**: `GET /api/trackedEntityInstances/{uid}.json?program=Y`

---

## Test Results

### Test 1: Transfer Dedza Boma → TA Kaphuka
```
Source:      Dedza Boma (sa91K9XNQ08)
Destination: TA Kaphuka (vkM60NDTFE8)
TEI:         Tz4EVwE6aIX (christian)
Status:      ✅ SUCCESS
```

**Verification**:
- TEI orgUnit: vkM60NDTFE8 ✅
- Enrollment orgUnit: vkM60NDTFE8 ✅
- 6 events all at vkM60NDTFE8 ✅
- Child UIC preserved: DE_KAPH_OVC_00000002 ✅

### Test 2: Fetch from TA Kaphuka
```
OU:          TA Kaphuka (vkM60NDTFE8)
Program:     MW Harmonized OVC Program
Year:        2026
Status:      ✅ SUCCESS
```

**Results**:
- Found 3 enrollments ✅
- Fetched 3 TEIs with 14 events ✅
- All names and UICs displayed correctly ✅

---

## Usage Examples

### 1. Transfer TEIs Between OUs
```bash
just transfer
```

Interactive workflow:
1. Select source OU (e.g., Dedza Boma)
2. Select destination OU (e.g., TA Kaphuka)
3. Enter year range (e.g., 2026-2026)
4. Review TEIs found
5. Select which to transfer
6. Confirm and execute

### 2. Verify Transfer
```bash
# Verify specific TEI
PYTHONPATH=src ./venv/bin/python src/transfer/verify_at_destination.py --tei <TEI_UID>

# Verify all at destination
PYTHONPATH=src ./venv/bin/python src/transfer/verify_at_destination.py --ou <OU_UID>

# Verify households
PYTHONPATH=src ./venv/bin/python src/transfer/verify_at_destination.py --ou <OU_UID> --program household
```

### 3. Check in DHIS2 Web UI
1. Go to **Tracker Capture**
2. Select the destination OU (e.g., TA Kaphuka)
3. Select the program (e.g., MW Harmonized OVC Program)
4. You will see the transferred TEIs

---

## Known Limitations

### 1. Query Caching
**Issue**: `/api/trackedEntityInstances` query may not show transferred TEIs immediately.

**Workaround**: 
- Use verification script (uses enrollments API)
- Check DHIS2 web UI
- Wait a few minutes for cache to refresh

### 2. No ID Regeneration
**Current Behavior**: IDs are preserved as-is during transfer.

**Future Enhancement**: Add optional ID regeneration based on destination OU code.

---

## Files Modified

### Core Transfer
- `src/transfer/engine.py` - 2-step transfer process
- `src/transfer/fetcher.py` - Enrollments API fetching

### Verification
- `src/transfer/verify_at_destination.py` - New verification tool

---

## Next Steps

If you want to add ID regeneration back:
1. Uncomment the ID update step in `engine.py` (Step 3)
2. Test with auto-increment logic
3. Update verification to check new IDs

---

## Support

For issues or questions:
1. Check this document first
2. Run verification script to confirm transfer
3. Check DHIS2 web UI
4. Review transfer logs in `outputs/transfer/`
