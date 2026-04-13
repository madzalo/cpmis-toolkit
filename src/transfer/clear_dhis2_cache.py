#!/usr/bin/env python3
"""
Clear DHIS2 cache to force web UI to refresh after transfers
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.dhis2_client import SESSION, DHIS2_URL


def clear_cache():
    """Clear DHIS2 application cache"""
    print("\n" + "=" * 80)
    print("CLEARING DHIS2 CACHE")
    print("=" * 80)
    
    print("\n1. Clearing application cache...")
    resp = SESSION.post(f'{DHIS2_URL}/api/maintenance/cache')
    if resp.status_code == 200:
        print("   ✅ Cache cleared successfully")
    else:
        print(f"   ⚠️  Cache clear returned: {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
    
    print("\n2. Triggering analytics update...")
    resp = SESSION.post(f'{DHIS2_URL}/api/resourceTables/analytics')
    if resp.status_code == 200:
        result = resp.json()
        print("   ✅ Analytics update triggered")
        print(f"   Job ID: {result.get('response', {}).get('id', 'N/A')}")
        print(f"   Status: {result.get('response', {}).get('jobStatus', 'N/A')}")
    else:
        print(f"   ⚠️  Analytics trigger returned: {resp.status_code}")
        print(f"   Response: {resp.text[:200]}")
    
    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("\n1. In your browser:")
    print("   - Press Ctrl+Shift+R (or Ctrl+F5) for hard refresh")
    print("   - Or clear browser cache (Ctrl+Shift+Delete)")
    print("\n2. In DHIS2 Tracker Capture:")
    print("   - Select the destination OU (e.g., TA Kaphuka)")
    print("   - Select the program (e.g., MW Harmonized OVC Program)")
    print("   - You should now see the transferred TEIs")
    print("\n3. If still not showing:")
    print("   - Wait 2-3 minutes for analytics to complete")
    print("   - Try in an incognito/private window")
    print("   - Check with: just verify")
    print("\n" + "=" * 80)


if __name__ == '__main__':
    clear_cache()
