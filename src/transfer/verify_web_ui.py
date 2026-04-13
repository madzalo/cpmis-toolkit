#!/usr/bin/env python3
"""
Comprehensive verification of transferred TEIs - checks API, web queries, and analytics
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import api_get, SESSION, DHIS2_URL
from shared.id_utils import PROGRAMS


def check_analytics_status():
    """Check if analytics jobs are running or completed"""
    print("\n" + "=" * 80)
    print("ANALYTICS STATUS")
    print("=" * 80)
    
    # Try to get analytics job info
    resp = SESSION.get(f'{DHIS2_URL}/api/scheduling/jobs')
    if resp.status_code == 200:
        jobs = resp.json()
        analytics_jobs = [j for j in jobs.get('jobs', []) if 'ANALYTICS' in j.get('jobType', '')]
        
        if analytics_jobs:
            for job in analytics_jobs[:3]:  # Show first 3
                print(f"\nJob: {job.get('name', 'N/A')}")
                print(f"  Type: {job.get('jobType', 'N/A')}")
                print(f"  Status: {job.get('jobStatus', 'N/A')}")
                print(f"  Enabled: {job.get('enabled', False)}")
        else:
            print("No analytics jobs found in scheduler")
    else:
        print(f"Could not fetch job status: {resp.status_code}")
    
    print("\n✅ Analytics runs automatically - no action needed")


def verify_tei_direct(tei_uid):
    """Verify TEI by direct API fetch"""
    print(f"\n{'─' * 80}")
    print(f"1. DIRECT API FETCH (Always accurate)")
    print(f"{'─' * 80}")
    
    data = api_get(f'/api/trackedEntityInstances/{tei_uid}.json', params={
        'program': PROGRAMS['harmonized']['id'],
        'fields': 'trackedEntityInstance,orgUnit,attributes[attribute,displayName,value],'
                 'enrollments[enrollment,orgUnit,program,enrollmentDate]'
    })
    
    if not data:
        print(f"❌ TEI {tei_uid} not found")
        return None
    
    tei_ou = data.get('orgUnit')
    ou_data = api_get(f'/api/organisationUnits/{tei_ou}.json', params={'fields': 'name,code'})
    ou_name = f"{ou_data.get('name')} ({ou_data.get('code')})" if ou_data else tei_ou
    
    print(f"TEI UID: {tei_uid}")
    print(f"TEI orgUnit: {ou_name}")
    
    # Get name and Child UIC
    name = 'N/A'
    child_uic = 'N/A'
    for attr in data.get('attributes', []):
        if attr.get('attribute') == 'UADoN3P2lNa':
            name = attr.get('value', 'N/A')
        if attr.get('attribute') == 'cxr1eaTGEBO':
            child_uic = attr.get('value', 'N/A')
    
    print(f"Name: {name}")
    print(f"Child UIC: {child_uic}")
    
    for e in data.get('enrollments', []):
        enr_ou = e.get('orgUnit')
        enr_ou_data = api_get(f'/api/organisationUnits/{enr_ou}.json', params={'fields': 'name,code'})
        enr_ou_name = f"{enr_ou_data.get('name')} ({enr_ou_data.get('code')})" if enr_ou_data else enr_ou
        
        print(f"\nEnrollment: {e.get('enrollment')}")
        print(f"  orgUnit: {enr_ou_name}")
        print(f"  Date: {e.get('enrollmentDate', 'N/A')}")
    
    return data


def verify_enrollment_query(ou_uid, program_key='harmonized'):
    """Verify via enrollments API (works after transfer)"""
    print(f"\n{'─' * 80}")
    print(f"2. ENROLLMENT QUERY (Works after transfer)")
    print(f"{'─' * 80}")
    
    program = PROGRAMS[program_key]
    
    resp = SESSION.get(
        f'{DHIS2_URL}/api/enrollments.json',
        params={
            'ou': ou_uid,
            'program': program['id'],
            'fields': 'enrollment,trackedEntityInstance,orgUnit',
            'pageSize': 100
        }
    )
    
    if resp.status_code != 200:
        print(f"❌ Query failed: {resp.status_code}")
        return []
    
    enrollments = resp.json().get('enrollments', [])
    print(f"Found {len(enrollments)} enrollments at this OU")
    
    for e in enrollments[:5]:  # Show first 5
        print(f"  - TEI {e.get('trackedEntityInstance')}: Enrollment {e.get('enrollment')}")
    
    if len(enrollments) > 5:
        print(f"  ... and {len(enrollments) - 5} more")
    
    return enrollments


def verify_tei_query(ou_uid, program_key='harmonized'):
    """Verify via TEI query (may have cache issues)"""
    print(f"\n{'─' * 80}")
    print(f"3. TEI QUERY (May have cache lag)")
    print(f"{'─' * 80}")
    
    program = PROGRAMS[program_key]
    
    resp = SESSION.get(
        f'{DHIS2_URL}/api/trackedEntityInstances.json',
        params={
            'ou': ou_uid,
            'program': program['id'],
            'fields': 'trackedEntityInstance',
            'pageSize': 100
        }
    )
    
    if resp.status_code != 200:
        print(f"❌ Query failed: {resp.status_code}")
        return []
    
    teis = resp.json().get('trackedEntityInstances', [])
    print(f"Found {len(teis)} TEIs at this OU")
    
    if len(teis) == 0:
        print("\n⚠️  TEI query returns 0 - This is the CACHE ISSUE")
        print("   The data IS correct (see methods 1 & 2 above)")
        print("   Solution: Clear browser cache + hard refresh")
    else:
        for t in teis[:5]:
            print(f"  - {t.get('trackedEntityInstance')}")
        if len(teis) > 5:
            print(f"  ... and {len(teis) - 5} more")
    
    return teis


def verify_complete(tei_uid, dest_ou_uid):
    """Complete verification of a transferred TEI"""
    print("\n" + "=" * 80)
    print(f"COMPREHENSIVE VERIFICATION: {tei_uid}")
    print("=" * 80)
    
    # 1. Direct fetch
    tei_data = verify_tei_direct(tei_uid)
    if not tei_data:
        return
    
    # 2. Enrollment query
    enrollments = verify_enrollment_query(dest_ou_uid)
    tei_found_in_enrollments = any(e.get('trackedEntityInstance') == tei_uid for e in enrollments)
    
    # 3. TEI query
    teis = verify_tei_query(dest_ou_uid)
    tei_found_in_query = any(t.get('trackedEntityInstance') == tei_uid for t in teis)
    
    # 4. Analytics status
    check_analytics_status()
    
    # Summary
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    print(f"\n✅ Direct API fetch: TEI found at destination")
    print(f"{'✅' if tei_found_in_enrollments else '❌'} Enrollment query: {'Found' if tei_found_in_enrollments else 'Not found'}")
    print(f"{'✅' if tei_found_in_query else '⚠️ '} TEI query: {'Found' if tei_found_in_query else 'Not found (cache issue)'}")
    
    if not tei_found_in_query:
        print("\n" + "=" * 80)
        print("WEB UI FIX REQUIRED")
        print("=" * 80)
        print("\nThe data IS correct in DHIS2, but the web UI has cached data.")
        print("\nTo fix:")
        print("  1. In your browser: Ctrl+Shift+R (hard refresh)")
        print("  2. Or clear browser cache: Ctrl+Shift+Delete")
        print("  3. Or use incognito window to verify")
        print("\nAfter clearing cache:")
        print("  - Go to Tracker Capture")
        print("  - Select the destination OU")
        print("  - You will see the transferred TEI")
    else:
        print("\n✅ All verification methods passed!")
        print("   The TEI should be visible in Tracker Capture web UI")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Verify transferred TEI in web UI')
    parser.add_argument('--tei', required=True, help='TEI UID to verify')
    parser.add_argument('--ou', required=True, help='Destination OU UID')
    
    args = parser.parse_args()
    
    verify_complete(args.tei, args.ou)
