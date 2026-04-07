"""
Shared DHIS2 API client for CPMIS Toolkit.
Provides a reusable, session-based HTTP client for interacting with the DHIS2 API.
"""
import time
import requests
from requests.adapters import HTTPAdapter

from shared.settings import DHIS2_URL as _RAW_URL, DHIS2_USERNAME, DHIS2_PASSWORD

# Strip trailing slash to avoid double-slash in URLs (//api/...)
DHIS2_URL = _RAW_URL.rstrip('/') if _RAW_URL else ''


def create_session(pool_size=8):
    """Create a requests.Session with auth and connection pooling."""
    session = requests.Session()
    session.auth = (DHIS2_USERNAME, DHIS2_PASSWORD)
    session.headers.update({'Content-Type': 'application/json'})
    session.mount('https://', HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size))
    session.mount('http://', HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size))
    return session


# Module-level shared session
SESSION = create_session()


def api_get(path, params=None, timeout=30):
    """GET from DHIS2 API. Returns parsed JSON or None on error."""
    url = f"{DHIS2_URL}{path}"
    try:
        resp = SESSION.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        print(f"  ❌ GET {path} → HTTP {resp.status_code}")
        return None
    except Exception as e:
        print(f"  ❌ GET {path} → {e}")
        return None


def api_post(path, payload, params=None, timeout=90, retries=3):
    """POST to DHIS2 API with retry. Returns (success: bool, response_data: dict)."""
    url = f"{DHIS2_URL}{path}"
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.post(url, json=payload, params=params, timeout=timeout)
            if resp.status_code in (200, 201, 204):
                try:
                    return True, resp.json()
                except Exception:
                    return True, {}
            try:
                body = resp.json()
                msg = body.get('message', '') or body.get('response', {}).get('description', '')
                err = f"HTTP {resp.status_code}: {msg[:200]}" if msg else f"HTTP {resp.status_code}"
            except Exception:
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if attempt == retries:
                return False, {'error': err}
        except Exception as e:
            err = str(e)[:200]
            if attempt == retries:
                return False, {'error': err}
        time.sleep(2 * attempt)
    return False, {'error': 'unknown'}


def api_put(path, payload, params=None, timeout=90, retries=3):
    """PUT to DHIS2 API with retry. Returns (success: bool, response_data: dict)."""
    url = f"{DHIS2_URL}{path}"
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.put(url, json=payload, params=params, timeout=timeout)
            if resp.status_code in (200, 201, 204):
                try:
                    return True, resp.json()
                except Exception:
                    return True, {}
            try:
                body = resp.json()
                msg = body.get('message', '') or body.get('response', {}).get('description', '')
                err = f"HTTP {resp.status_code}: {msg[:200]}" if msg else f"HTTP {resp.status_code}"
            except Exception:
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if attempt == retries:
                return False, {'error': err}
        except Exception as e:
            err = str(e)[:200]
            if attempt == retries:
                return False, {'error': err}
        time.sleep(2 * attempt)
    return False, {'error': 'unknown'}


def fetch_paged(path, params, items_key, page_size=200, label='', silent=False):
    """
    Fetch all pages from a DHIS2 API endpoint.
    Returns a list of all items collected across pages.
    """
    all_items = []
    page = 1
    base_params = dict(params)
    base_params['pageSize'] = page_size
    base_params['totalPages'] = True

    while True:
        base_params['page'] = page
        data = api_get(path, params=base_params)
        if data is None:
            break

        items = data.get(items_key, [])
        pager = data.get('pager', {})
        total = pager.get('total', len(items))
        page_count = pager.get('pageCount', 1)
        all_items.extend(items)

        if not silent and total > 0:
            pct = len(all_items) * 100 // total if total else 100
            print(f"\r  {label}Fetching: [{len(all_items)}/{total}] ({pct}%)".ljust(90), end='', flush=True)

        if page >= page_count:
            break
        page += 1

    if not silent and all_items:
        print(f"\r  {label}✅ Fetched {len(all_items)} items".ljust(90))

    return all_items
