"""
CPMIS Toolkit — Entry Point

Run:
    python main.py        # or
    just run
"""

import sys
import os
import subprocess

# Add src/ to path so shared modules are importable both in dev and
# when bundled by PyInstaller (pathex=['src'] in the spec handles the build).
_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

APP_NAME  = "CPMIS Toolkit"
DHIS2_URL = os.environ.get("DHIS2_URL", "https://cpmis.gender.gov.mw")

# Resolve the Python executable (use sys.executable for the current interpreter)
_PYTHON = sys.executable

# File that Phase 1 generation produces — needed by tools 2, 3
OU_CODES_CSV = os.path.join("outputs", "task1", "ou_codes_standardized.csv")

# Phase 1 generation pipeline (run in order to produce OU_CODES_CSV)
PHASE1_PIPELINE = [
    (os.path.join("src", "cleanup", "phase1", "export_org_units.py"),   None, {}),
    (os.path.join("src", "cleanup", "phase1", "create_ou_codes.py"),    None, {}),
    (os.path.join("src", "cleanup", "phase1", "update_ou_codes.py"),    None, {}),
    (os.path.join("src", "cleanup", "phase1", "standardize_names.py"),  None, {}),
]

# Tool definitions: (key, label, description, script_path, cwd, env_extra, needs_ou_codes, args)
TOOLS = [
    ("1", "Standardise Org Units",  "Push codes & names to DHIS2",
     os.path.join("src", "cleanup", "phase1", "push_ou_codes.py"), None, {}, False, []),
    ("2", "Standardise TEI IDs",    "Generate & apply UIC IDs",
     os.path.join("src", "cleanup", "phase2", "phase2_workflow.py"), None, {}, True, []),
    ("3", "Transfer TEIs",          "Move between org units",
     os.path.join("src", "transfer", "transfer_workflow.py"), None, {"PYTHONPATH": "src"}, True, []),
    ("4", "Sync Rescue",            "Import unsynced Android data",
     "cli.py", os.path.join("src", "sync"), {"PYTHONPATH": "."}, False, ["batch"]),
]


def run_script(script_path, cwd, env_extra, args=None):
    """Run a script as a subprocess with the right environment."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    cmd = [_PYTHON, script_path]
    result = subprocess.run(cmd, cwd=cwd, env=env)
    return result.returncode == 0


def ensure_ou_codes():
    """Auto-generate ou_codes_standardized.csv if it doesn't exist.
    Runs the Phase 1 pipeline (export → create → update → standardize) silently."""
    from shared.ui import console, ok, warn, err, _DIM, _PRI

    if os.path.exists(OU_CODES_CSV):
        return True

    console.print(f"\n  [{'bold yellow'}]⚠  OU codes CSV not found — auto-generating Phase 1 data...[/{'bold yellow'}]")
    console.print()

    steps = [
        "Exporting org units from DHIS2",
        "Creating OU code reference",
        "Generating standardised codes",
        "Standardising org unit names",
    ]

    for i, (script, cwd, env_extra) in enumerate(PHASE1_PIPELINE):
        label = steps[i] if i < len(steps) else script
        console.print(f"  [{_DIM}][{i+1}/{len(PHASE1_PIPELINE)}][/{_DIM}] {label}...", end=" ")
        sys.stdout.flush()
        success = run_script(script, cwd, env_extra)
        if success:
            console.print(f"[{'bold green'}]✓[/{'bold green'}]")
        else:
            console.print(f"[{'bold red'}]✗[/{'bold red'}]")
            err("Phase 1 auto-generation failed. Run manually: just task1-complete")
            return False

    if os.path.exists(OU_CODES_CSV):
        ok("OU codes generated successfully")
        console.print()
        return True
    else:
        err("OU codes CSV still missing after generation")
        return False


def main():
    from shared.ui import header, section, menu_item, blank, ask, warn, _DIM
    from shared.ui import console
    import shared.auth as auth

    header(APP_NAME, f"DHIS2 · {DHIS2_URL}")

    if not auth.prompt_credentials():
        sys.exit(1)

    while True:
        section("SELECT TOOL")
        for key, label, desc, _, _, _, _, _ in TOOLS:
            menu_item(key, label, desc)
        blank()
        menu_item("q", "Quit")
        choice = ask("").lower()

        if choice in ("q", "quit", "exit"):
            console.print(f"\n  [{_DIM}]Goodbye.[/{_DIM}]\n")
            break
        else:
            match = next((t for t in TOOLS if t[0] == choice), None)
            if match:
                _, label, _, script, cwd, env_extra, needs_ou, args = match
                console.print(f"\n  [{_DIM}]Launching {label}...[/{_DIM}]\n")

                if needs_ou:
                    if not ensure_ou_codes():
                        continue

                env = os.environ.copy()
                # Pass credentials to subprocess to avoid re-prompting
                from shared.auth import DHIS2_USERNAME, DHIS2_PASSWORD
                if DHIS2_USERNAME:
                    env["DHIS2_USERNAME"] = DHIS2_USERNAME
                if DHIS2_PASSWORD:
                    env["DHIS2_PASSWORD"] = DHIS2_PASSWORD
                if env_extra:
                    env.update(env_extra)
                subprocess.run([_PYTHON, script] + args, cwd=cwd, env=env)
                console.print()
            else:
                warn("Enter 1, 2, 3, 4, or q.")


if __name__ == "__main__":
    main()
