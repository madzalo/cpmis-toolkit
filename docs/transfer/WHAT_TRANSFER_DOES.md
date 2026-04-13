# What Does the Transfer Actually Do?

## TL;DR

**The transfer is a PERMANENT MOVE, not a referral.**

We update the `orgUnit` field on:
1. The TEI itself
2. All enrollments
3. All events

The TEI's home location changes from source OU to destination OU.

---

## Detailed Explanation

### What We Change

When you transfer a TEI from **Source OU** to **Destination OU**, we update these fields in DHIS2:

```javascript
// BEFORE Transfer (at Dedza Boma)
{
  "trackedEntityInstance": "Tz4EVwE6aIX",
  "orgUnit": "sa91K9XNQ08",  // Dedza Boma
  "enrollments": [{
    "enrollment": "qZYpcRUB9mz",
    "orgUnit": "sa91K9XNQ08",  // Dedza Boma
    "events": [
      {
        "event": "h7b4njBQeMv",
        "orgUnit": "sa91K9XNQ08"  // Dedza Boma
      },
      // ... more events
    ]
  }]
}

// AFTER Transfer (at TA Kaphuka)
{
  "trackedEntityInstance": "Tz4EVwE6aIX",
  "orgUnit": "vkM60NDTFE8",  // TA Kaphuka ✅ CHANGED
  "enrollments": [{
    "enrollment": "qZYpcRUB9mz",
    "orgUnit": "vkM60NDTFE8",  // TA Kaphuka ✅ CHANGED
    "events": [
      {
        "event": "h7b4njBQeMv",
        "orgUnit": "vkM60NDTFE8"  // TA Kaphuka ✅ CHANGED
      },
      // ... more events (all updated)
    ]
  }]
}
```

### What We DON'T Change

- **Attributes** (Child UIC, Household ID, names, etc.) - Preserved as-is
- **Enrollment dates** - Preserved
- **Event dates** - Preserved
- **Data values** - Preserved
- **Relationships** - Preserved (UID-based, not OU-specific)
- **Created by** - Preserved (original creator)
- **Created date** - Preserved

---

## Transfer vs Referral

### Transfer (What We Do)
- **Permanent move** of the TEI to a new home location
- The TEI no longer belongs to the source OU
- All historical data moves with it
- The TEI appears in reports for the destination OU
- **Use case**: Correcting data entry errors where a child was registered at the wrong facility

### Referral (What We DON'T Do)
- **Temporary** service provision at another facility
- The TEI still belongs to the original OU
- Creates a new enrollment or event at the referral location
- The TEI appears in reports for BOTH OUs
- **Use case**: A child from Facility A receives services at Facility B

---

## The 3-Step Process

### Step 1: Update TEI and Events
```http
POST /api/trackedEntityInstances
{
  "trackedEntityInstances": [{
    "trackedEntityInstance": "Tz4EVwE6aIX",
    "orgUnit": "vkM60NDTFE8",  // New OU
    "enrollments": [{
      "enrollment": "qZYpcRUB9mz",
      "orgUnit": "vkM60NDTFE8",  // New OU
      "events": [
        {
          "event": "h7b4njBQeMv",
          "orgUnit": "vkM60NDTFE8"  // New OU
        }
      ]
    }]
  }]
}
```

**Parameters**:
- `strategy=CREATE_AND_UPDATE` - Update existing TEI
- `mergeMode=REPLACE` - Replace orgUnit values

**What happens**:
- ✅ TEI orgUnit updated
- ✅ Event orgUnits updated
- ❌ Enrollment orgUnit NOT reliably updated (DHIS2 bug)

### Step 2: Update Enrollments Separately
```http
POST /api/enrollments
{
  "enrollments": [{
    "enrollment": "qZYpcRUB9mz",
    "orgUnit": "vkM60NDTFE8",  // New OU
    "program": "xhzwCCKzFBM",
    "enrollmentDate": "2026-01-28T00:00:00.000"
  }]
}
```

**Parameters**:
- `strategy=UPDATE` - Update existing enrollment

**What happens**:
- ✅ Enrollment orgUnit updated

### Step 3: Transfer Program Ownership (CRITICAL!)
```http
PUT /api/tracker/ownership/transfer?trackedEntityInstance=Tz4EVwE6aIX&program=xhzwCCKzFBM&ou=vkM60NDTFE8
```

**What happens**:
- ✅ Program ownership transferred to destination OU
- ✅ TEI now appears in Tracker Capture queries at destination
- ✅ Web UI can now see the TEI

**Why this is critical**:
- DHIS2 uses program ownership to determine which OUs can see a TEI in queries
- Without this step, the TEI is moved in the database but **invisible in the web UI**
- Direct API fetch works, but Tracker Capture queries return 0 results

---

## Why 3 Steps?

**DHIS2 API Limitations**:

1. **Step 1 limitation**: When you POST a TEI with enrollments, DHIS2:
   - ✅ Updates the TEI's orgUnit
   - ✅ Updates event orgUnits
   - ❌ **Does NOT update enrollment orgUnits** (even though they're in the payload!)

2. **Step 2 limitation**: Even after updating enrollment orgUnits, DHIS2:
   - ✅ Data is correct in database
   - ✅ Direct API fetch works
   - ❌ **TEI queries return 0** because ownership wasn't transferred

3. **Step 3 fixes visibility**: Transferring program ownership:
   - ✅ Updates the `programOwners` table
   - ✅ Makes TEI visible in Tracker Capture queries
   - ✅ Web UI can now find and display the TEI

---

## Verification

After transfer, you can verify using:

### 1. Direct TEI Fetch (Always Works)
```bash
GET /api/trackedEntityInstances/Tz4EVwE6aIX.json
```

### 2. Enrollment Query (Works After Transfer)
```bash
GET /api/enrollments.json?ou=vkM60NDTFE8&program=xhzwCCKzFBM
```

### 3. TEI Query (May Have Caching Issues)
```bash
GET /api/trackedEntityInstances.json?ou=vkM60NDTFE8&program=xhzwCCKzFBM
# May return 0 results due to DHIS2 caching - wait a few minutes
```

### 4. DHIS2 Web UI (Always Works)
1. Go to Tracker Capture
2. Select destination OU (e.g., TA Kaphuka)
3. Select program (e.g., MW Harmonized OVC Program)
4. You will see the transferred TEI

### 5. Our Verification Tool
```bash
just verify                    # Show from latest transfer log
just verify --tei Tz4EVwE6aIX  # Verify specific TEI
just verify --ou vkM60NDTFE8   # Verify all at destination OU
```

---

## Example: Real Transfer

**Scenario**: Christian was incorrectly registered at Dedza Boma (facility) instead of TA Kaphuka (TA level).

**Before Transfer**:
```
TEI: Tz4EVwE6aIX (christian)
├─ TEI orgUnit: Dedza Boma (sa91K9XNQ08)
├─ Child UIC: DE_KAPH_OVC_00000002
├─ Enrollment: qZYpcRUB9mz
│  └─ orgUnit: Dedza Boma (sa91K9XNQ08)
└─ Events: 6
   └─ All at Dedza Boma (sa91K9XNQ08)
```

**After Transfer**:
```
TEI: Tz4EVwE6aIX (christian)
├─ TEI orgUnit: TA Kaphuka (vkM60NDTFE8) ✅
├─ Child UIC: DE_KAPH_OVC_00000002 (unchanged)
├─ Enrollment: qZYpcRUB9mz
│  └─ orgUnit: TA Kaphuka (vkM60NDTFE8) ✅
└─ Events: 6
   └─ All at TA Kaphuka (vkM60NDTFE8) ✅
```

**Verification**:
```bash
$ just verify

[1/1] Tz4EVwE6aIX
  Name:       christian
  Child UIC:  DE_KAPH_OVC_00000002
  Current OU: TA Kaphuka (DE_KAPH)
  Old ID:     DE_KAPH_OVC_00000002
  New ID:     DE_KAPH_OVC_00000002
  Status:     OK
  Enrollment: qZYpcRUB9mz
    OU:       TA Kaphuka (DE_KAPH)
    Date:     2026-01-28T00:00:00.000
```

---

## Impact on Reports

### Before Transfer
- Christian appears in **Dedza Boma** reports
- TA Kaphuka reports show 0 children

### After Transfer
- Christian appears in **TA Kaphuka** reports
- Dedza Boma reports no longer include Christian
- Historical data (enrollment date, events) is preserved

---

## Common Questions

### Q: Can I undo a transfer?
**A**: Yes! Just transfer back to the original OU. The transfer is reversible.

### Q: What happens to relationships?
**A**: Relationships are preserved. They're UID-based, not OU-specific, so household-child links remain intact.

### Q: Do I lose any data?
**A**: No. All data is preserved - only the `orgUnit` fields change.

### Q: Can I transfer to multiple OUs at once?
**A**: No. Each transfer operation moves TEIs from one source OU to one destination OU.

### Q: What if the TEI has multiple enrollments?
**A**: All enrollments are updated to the destination OU.

### Q: What about events in different program stages?
**A**: All events across all program stages are updated to the destination OU.

---

## Summary

**Transfer = Permanent Move**

- Changes: `orgUnit` on TEI, enrollments, and events
- Preserves: All attributes, dates, data values, relationships
- Use case: Correcting data entry errors
- Reversible: Yes, transfer back to original OU
- Impact: TEI appears in destination OU reports, not source OU reports
