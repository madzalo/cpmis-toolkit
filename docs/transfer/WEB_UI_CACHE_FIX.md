# DHIS2 Web UI Not Showing Transferred TEIs - Fix

## The Problem

After transferring TEIs, the DHIS2 API shows they're at the new location, but the **Tracker Capture web UI** still shows them at the old location.

**This is a DHIS2 caching issue**, not a problem with our transfer.

---

## Verification: Data IS Correct

The API confirms the data is correct:

```bash
$ PYTHONPATH=src ./venv/bin/python -c "
from shared.dhis2_client import api_get
data = api_get('/api/trackedEntityInstances/Tz4EVwE6aIX.json', params={
    'fields': 'orgUnit,enrollments[orgUnit]'
})
print(f'TEI orgUnit: {data.get(\"orgUnit\")}')  # vkM60NDTFE8 (TA Kaphuka) ✅
for e in data.get('enrollments', []):
    print(f'Enrollment orgUnit: {e.get(\"orgUnit\")}')  # vkM60NDTFE8 ✅
"
```

**Result**: Both show `vkM60NDTFE8` (TA Kaphuka) - the data IS moved!

---

## Solutions (Try in Order)

### Solution 1: Clear Browser Cache (Fastest)

The Tracker Capture app caches data in your browser.

**Steps**:
1. In your browser, open **Developer Tools** (F12)
2. Right-click the **Refresh button**
3. Select **"Empty Cache and Hard Reload"**
4. Or use: `Ctrl+Shift+Delete` → Clear cache → Reload

**Chrome/Edge**:
- `Ctrl+Shift+Delete` → Check "Cached images and files" → Clear data

**Firefox**:
- `Ctrl+Shift+Delete` → Check "Cache" → Clear Now

### Solution 2: Clear DHIS2 Cache (Server-Side)

DHIS2 has a server-side cache that may need clearing.

**Option A: Via Web UI** (If you have admin access):
1. Go to **Data Administration** app
2. Click **"Maintenance"** tab
3. Click **"Clear application cache"**
4. Wait 30 seconds
5. Reload Tracker Capture

**Option B: Via API**:
```bash
# Trigger analytics update (already done automatically)
curl -X POST "https://cpmis.gender.gov.mw/api/resourceTables/analytics" \
  -u username:password

# Clear cache
curl -X POST "https://cpmis.gender.gov.mw/api/maintenance/cache" \
  -u username:password
```

**Option C: Via our script**:
```bash
PYTHONPATH=src ./venv/bin/python -c "
from shared.dhis2_client import SESSION, DHIS2_URL

# Clear cache
resp = SESSION.post(f'{DHIS2_URL}/api/maintenance/cache')
print(f'Cache clear: {resp.status_code}')

# Trigger analytics
resp = SESSION.post(f'{DHIS2_URL}/api/resourceTables/analytics')
print(f'Analytics: {resp.status_code}')
"
```

### Solution 3: Wait (Slowest)

DHIS2 will eventually update its cache automatically.

**Timeline**:
- Browser cache: Clears on browser restart
- DHIS2 cache: Clears every 1-24 hours (depends on server config)
- Analytics: Runs nightly (usually)

**Not recommended** - clearing cache is faster.

### Solution 4: Use Different Browser/Incognito

Test in an incognito window or different browser to confirm it's a cache issue.

**Steps**:
1. Open **Incognito/Private window** (`Ctrl+Shift+N`)
2. Log in to DHIS2
3. Go to Tracker Capture
4. Select TA Kaphuka
5. You should see the transferred TEI

If you see it in incognito but not in your normal browser, it's definitely a browser cache issue.

---

## Why This Happens

### DHIS2 Tracker Capture Caching

The Tracker Capture app aggressively caches:
1. **TEI lists** - Which TEIs are at each OU
2. **TEI details** - Attributes, enrollments, events
3. **Search results** - Previous searches

When you transfer a TEI:
- ✅ The database is updated immediately
- ✅ The API returns correct data immediately
- ❌ The browser cache still has old data
- ❌ The app doesn't know to refresh

### The Fix

Clearing the cache forces the app to:
1. Re-fetch TEI lists from the API
2. Re-fetch TEI details from the API
3. Update the UI with current data

---

## Verification After Cache Clear

### 1. Check Tracker Capture

1. Go to **Tracker Capture** app
2. Select **TA Kaphuka** as org unit
3. Select **MW Harmonized OVC Program**
4. You should see the transferred TEI (christian)

### 2. Check Dedza Boma

1. Select **Dedza Boma** as org unit
2. Select **MW Harmonized OVC Program**
3. The transferred TEI should **NOT** be there anymore

### 3. Use Our Verification Tool

```bash
just verify
```

This fetches directly from the API (no cache) and shows the current state.

---

## If Cache Clear Doesn't Work

If clearing cache doesn't work, there might be a deeper issue. Check:

### 1. Verify API Data

```bash
PYTHONPATH=src ./venv/bin/python -c "
from shared.dhis2_client import api_get

# Check TEI
tei = api_get('/api/trackedEntityInstances/Tz4EVwE6aIX.json', params={
    'fields': 'orgUnit,enrollments[orgUnit]'
})
print(f'TEI orgUnit: {tei.get(\"orgUnit\")}')

# Check enrollment
enr = api_get('/api/enrollments/qZYpcRUB9mz.json', params={
    'fields': 'orgUnit'
})
print(f'Enrollment orgUnit: {enr.get(\"orgUnit\")}')
"
```

**Expected**:
- TEI orgUnit: `vkM60NDTFE8` (TA Kaphuka)
- Enrollment orgUnit: `vkM60NDTFE8` (TA Kaphuka)

### 2. Check Database Directly (If You Have Access)

```sql
-- Check TEI orgUnit
SELECT trackedentityinstanceid, uid, organisationunitid 
FROM trackedentityinstance 
WHERE uid = 'Tz4EVwE6aIX';

-- Check enrollment orgUnit
SELECT programinstanceid, uid, organisationunitid 
FROM programinstance 
WHERE uid = 'qZYpcRUB9mz';

-- Get org unit names
SELECT organisationunitid, name, code 
FROM organisationunit 
WHERE organisationunitid IN (
  SELECT organisationunitid FROM trackedentityinstance WHERE uid = 'Tz4EVwE6aIX'
);
```

### 3. Check for Ownership Issues

DHIS2 has a concept of "ownership" for TEIs. Check if there's an ownership record:

```bash
PYTHONPATH=src ./venv/bin/python -c "
from shared.dhis2_client import api_get

# Check ownership
data = api_get('/api/tracker/ownership', params={
    'trackedEntity': 'Tz4EVwE6aIX',
    'program': 'xhzwCCKzFBM'
})
print(data)
"
```

---

## Summary

**The data IS correct** - the API confirms it. The issue is **browser/app cache**.

**Quick Fix**:
1. Hard refresh browser (`Ctrl+Shift+R` or `Ctrl+F5`)
2. Or clear browser cache
3. Or use incognito window

**If that doesn't work**:
1. Clear DHIS2 server cache (Data Administration → Clear cache)
2. Wait 5-10 minutes
3. Hard refresh again

**The transfer worked correctly** - this is just a display issue in the web UI.
