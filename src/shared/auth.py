"""
Shared authentication for CPMIS Toolkit.

Provides a single login step that validates DHIS2 credentials and returns
a reusable requests.Session. All toolkit apps import this to avoid
duplicating auth logic.
"""

import os
import getpass
import requests
from requests.adapters import HTTPAdapter

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shared.ui import console, ok, err, _DIM

DHIS2_URL      = os.environ.get("DHIS2_URL", "https://cpmis.gender.gov.mw")
DHIS2_USERNAME = os.environ.get("DHIS2_USERNAME")
DHIS2_PASSWORD = os.environ.get("DHIS2_PASSWORD")

_session = None
_user_info = None


def prompt_credentials():
    """Prompt for DHIS2 username/password if not in env, validate, return True on success."""
    global DHIS2_USERNAME, DHIS2_PASSWORD
    if not DHIS2_USERNAME:
        console.print(f"\n  [{_DIM}]Username:[/{_DIM}] ", end="")
        DHIS2_USERNAME = input().strip()
    if not DHIS2_PASSWORD:
        console.print(f"  [{_DIM}]Password:[/{_DIM}] ", end="")
        DHIS2_PASSWORD = getpass.getpass("")
    if not DHIS2_USERNAME or not DHIS2_PASSWORD:
        err("Username and password are required.")
        return False

    with console.status(f"  [{_DIM}]Validating credentials...[/{_DIM}]",
                        spinner="dots", spinner_style="cyan"):
        s = get_session()
        try:
            r = s.get(DHIS2_URL.rstrip("/") + "/api/me.json",
                      params={"fields": "id,username,displayName,firstName,surname,organisationUnits[id,name,level]"},
                      timeout=30)
            r.raise_for_status()
        except Exception:
            err("Invalid credentials. Please check your username and password.")
            return False

    global _user_info
    _user_info = r.json()
    name = (
        _user_info.get("displayName")
        or f"{_user_info.get('firstName', '')} {_user_info.get('surname', '')}".strip()
        or _user_info.get("username")
    )
    ok(f"Logged in as [bold]{name}[/bold]")
    console.print()
    return True


def get_session():
    """Return a shared requests.Session with auth configured."""
    global _session
    if _session:
        return _session
    _session = requests.Session()
    _session.auth = (DHIS2_USERNAME, DHIS2_PASSWORD)
    _session.headers.update({"Content-Type": "application/json"})
    adapter = HTTPAdapter(max_retries=3, pool_connections=8, pool_maxsize=8)
    _session.mount("https://", adapter)
    _session.mount("http://", adapter)
    return _session


def get_user_info():
    """Return the cached /api/me.json result from login."""
    return _user_info


def api_get(path, params=None, timeout=60):
    """GET from DHIS2 API using the shared session. Returns parsed JSON."""
    s = get_session()
    url = DHIS2_URL.rstrip("/") + path
    for attempt in range(3):
        try:
            r = s.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 2:
                raise
            import time
            time.sleep(2 ** attempt)
