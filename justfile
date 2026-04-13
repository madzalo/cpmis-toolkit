# CPMIS Toolkit — Unified DHIS2 Management for CPMIS Malawi
# Author: Resten Madzalo (github.com/madzalo)

# Default recipe
default:
    @just help

# ═══════════════════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════════════════

# Install system dependencies (requires sudo)
install-deps:
    @echo "Installing python3-venv..."
    sudo apt install python3.12-venv -y

# Setup virtual environment and install dependencies
setup:
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    @echo "Setup complete! Virtual environment created in ./venv"

# Complete setup (install system deps + setup venv)
init: install-deps setup

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP — Phase 1: Organisation Unit Codes
# ═══════════════════════════════════════════════════════════════════════════════

# Export organisation units from DHIS2 (T1.1)
export-ou:
    ./venv/bin/python src/cleanup/phase1/export_org_units.py

# Update OU codes in the CSV file
task1-update:
    ./venv/bin/python src/cleanup/phase1/update_ou_codes.py

# Standardize org unit names (capitalize, fix center->centre)
task1-standardize:
    ./venv/bin/python src/cleanup/phase1/standardize_names.py

# Update OU codes with district codes from malawi_districts.csv
update-ou-codes:
    ./venv/bin/python src/cleanup/phase1/update_ou_codes.py

# Create OU code reference CSV (T1.2)
create-ou-codes:
    ./venv/bin/python src/cleanup/phase1/create_ou_codes.py

# Push OU codes to DHIS2 (dry-run, all org units)
push-ou-codes-dry:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --dry-run --all

# Push OU codes to DHIS2 (PRODUCTION, all org units)
push-ou-codes:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --all

# Interactive push (pick scope → preview → push)
phase1-push:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py

# Push OU codes for a single district (e.g. just phase1-district ZA)
phase1-district district_code:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --district {{district_code}}

# Push OU codes for multiple districts (e.g. just phase1-districts "ZA,BL,MU")
phase1-districts district_codes:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --district {{district_codes}}

# Push OU codes for a single org unit by UID
phase1-ou org_unit:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --org-unit {{org_unit}}

# Dry-run push for a single district
phase1-district-dry district_code:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --district {{district_code}} --dry-run

# Validate OU codes in DHIS2 against CSV
validate-ou-codes:
    ./venv/bin/python src/cleanup/phase1/push_ou_codes.py --validate

# Run both T1.1 and T1.2
task1: export-ou create-ou-codes

# Run T1.1, T1.2, and auto-update codes
task1-auto: export-ou create-ou-codes update-ou-codes

# Run complete Task 1 workflow (export, create, update, standardize, dry-run push)
task1-complete:
    @echo "Running complete Task 1 workflow..."
    just export-ou
    just create-ou-codes
    just update-ou-codes
    just task1-standardize
    just push-ou-codes-dry
    @echo ""
    @echo "Review the dry-run output above."
    @echo "If everything looks good, run: just push-ou-codes"

# Run complete Phase 1 workflow including live server update
phase1-complete:
    #!/usr/bin/env bash
    set -e
    echo "========================================="
    echo "Phase 1: Complete Workflow with Live Update"
    echo "========================================="
    echo ""
    echo "Step 1: Exporting org units from DHIS2..."
    just export-ou
    echo ""
    echo "Step 2: Creating OU codes..."
    just create-ou-codes
    echo ""
    echo "Step 3: Updating OU codes with district mappings..."
    just update-ou-codes
    echo ""
    echo "Step 4: Standardizing org unit names..."
    just task1-standardize
    echo ""
    echo "Step 5: Running dry-run to preview changes..."
    just push-ou-codes-dry
    echo ""
    echo "========================================="
    read -r -p "Review the changes above. Push to live server? (yes/no): " confirm
    case "$confirm" in
        yes|YES|y|Y)
            echo "Step 6: Pushing to live DHIS2 server..."
            just push-ou-codes
            echo ""
            echo "✅ Phase 1 Complete! All org unit codes and names updated in DHIS2."
            ;;
        *)
            echo "❌ Cancelled. No changes made to live server."
            echo "To push manually later, run: just push-ou-codes"
            ;;
    esac

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP — Phase 2: TEI ID Standardisation
# ═══════════════════════════════════════════════════════════════════════════════

# Interactive workflow (pick scope → generate → preview → apply)
phase2:
    ./venv/bin/python src/cleanup/phase2/phase2_workflow.py

# Process a single district by code (e.g. just phase2-district ZA)
phase2-district district_code:
    ./venv/bin/python src/cleanup/phase2/phase2_workflow.py --district {{district_code}}

# Process multiple districts (e.g. just phase2-districts "ZA,BL,MU")
phase2-districts district_codes:
    ./venv/bin/python src/cleanup/phase2/phase2_workflow.py --district {{district_codes}}

# Process all org units
phase2-all:
    ./venv/bin/python src/cleanup/phase2/phase2_workflow.py --all

# Process a single org unit by UID
phase2-ou org_unit:
    ./venv/bin/python src/cleanup/phase2/phase2_workflow.py --org-unit {{org_unit}}

# List all DHIS2 programs (read-only)
phase2-list-programs:
    ./venv/bin/python src/cleanup/phase2/list_programs.py

# Fetch sample TEIs (interactive)
phase2-fetch-samples:
    ./venv/bin/python src/cleanup/phase2/fetch_sample_teis.py

# Apply interactively (pick CSV → pick method → apply)
phase2-apply-interactive:
    ./venv/bin/python src/cleanup/phase2/apply_ids.py --interactive

# Apply a previously generated mapping CSV (via API)
phase2-apply csv_file:
    ./venv/bin/python src/cleanup/phase2/apply_ids.py --csv {{csv_file}}

# Apply a previously generated mapping CSV (via direct database)
phase2-apply-db csv_file:
    ./venv/bin/python src/cleanup/phase2/apply_ids.py --csv {{csv_file}} --use-db

# Verify database values match expected CSV values
phase2-verify csv_file:
    ./venv/bin/python src/cleanup/phase2/apply_ids.py --csv {{csv_file}} --verify

# ═══════════════════════════════════════════════════════════════════════════════
# OU TRANSFER — Move TEIs between organisation units
# ═══════════════════════════════════════════════════════════════════════════════

# Interactive transfer workflow (recommended)
transfer:
    PYTHONPATH=src ./venv/bin/python src/transfer/transfer_workflow.py

# Show transferred TEIs from latest transfer (with names and details)
verify:
    PYTHONPATH=src ./venv/bin/python src/transfer/verify_at_destination.py

# Re-run verification on last transfer
transfer-verify:
    PYTHONPATH=src ./venv/bin/python src/transfer/transfer_workflow.py --verify

# ═══════════════════════════════════════════════════════════════════════════════
# SYNC RESCUE — Import unsynced data from Android apps
# ═══════════════════════════════════════════════════════════════════════════════

# Run batch import processing (place zips in imports/ first)
sync-batch:
    cd src/sync && ../../venv/bin/python cli.py batch

# Extract data from a database
sync-extract db:
    cd src/sync && ../../venv/bin/python cli.py extract --db {{db}}

# Validate (dry-run) with credentials
sync-validate username password:
    cd src/sync && ../../venv/bin/python cli.py validate --username {{username}} --password {{password}}

# Import data to DHIS2
sync-import username password:
    cd src/sync && ../../venv/bin/python cli.py import --username {{username}} --password {{password}}

# Verify imported data
sync-verify username password:
    cd src/sync && ../../venv/bin/python cli.py verify --username {{username}} --password {{password}}

# Show ignored items from last import
sync-show-ignored:
    cd src/sync && ../../venv/bin/python -c "from utils import show_ignored_report; show_ignored_report()"

# ═══════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE & UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

# Run everything: Phase 1 → Phase 2 → commit → push
run-all:
    #!/usr/bin/env bash
    set -e
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║           CPMIS TOOLKIT — FULL CLEANUP PIPELINE                    ║"
    echo "║  Phase 1 (OU codes) → Phase 2 (TEI IDs) → Commit → Push           ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""

    # ── Phase 1 ──
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  PHASE 1: Organisation Unit Codes"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  [1/5] Exporting org units from DHIS2..."
    just export-ou
    echo ""
    echo "  [2/5] Creating OU codes..."
    just create-ou-codes
    echo ""
    echo "  [3/5] Updating OU codes with district mappings..."
    just update-ou-codes
    echo ""
    echo "  [4/5] Standardizing org unit names..."
    just task1-standardize
    echo ""
    echo "  [5/5] Pushing OU codes to DHIS2 (dry-run)..."
    just push-ou-codes-dry
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    read -r -p "  Push OU codes to live server? (yes/no): " confirm_p1
    case "$confirm_p1" in
        yes|YES|y|Y)
            echo "  Pushing to live DHIS2 server..."
            just push-ou-codes
            echo "  ✅ Phase 1 complete!"
            ;;
        *)
            echo "  ⏭️  Skipping Phase 1 live push."
            ;;
    esac

    echo ""

    # ── Phase 2 ──
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  PHASE 2: TEI ID Standardisation"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    ./venv/bin/python src/cleanup/phase2/phase2_workflow.py

    echo ""

    # ── Git commit & push ──
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  GIT: Commit & Push"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if git diff --quiet && git diff --cached --quiet; then
        echo "  ℹ️  No file changes to commit."
    else
        git add -A
        echo "  Files staged:"
        git diff --cached --stat | sed 's/^/    /'
        echo ""
        read -r -p "  Commit message [CPMIS cleanup run]: " msg
        msg="${msg:-CPMIS cleanup run}"
        git commit -m "$msg"
        echo "  ✅ Committed."
    fi
    echo ""
    read -r -p "  Push to GitHub? (yes/no): " confirm_push
    case "$confirm_push" in
        yes|YES|y|Y)
            git push origin main
            echo "  ✅ Pushed to GitHub."
            ;;
        *)
            echo "  ⏭️  Skipping push. Run 'git push origin main' later."
            ;;
    esac

    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║  ✅ ALL DONE                                                       ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""

# Clean up generated files
clean:
    rm -rf outputs/task1/*
    rm -rf outputs/phase2/*
    rm -rf outputs/transfer/*
    rm -rf outputs/sync/*
    @echo "✅ Cleaned generated files"

# Remove virtual environment
clean-venv:
    rm -rf venv

# Clean all (including sync completed imports)
clean-all: clean
    rm -rf completed_imports/*
    @echo "✅ Cleaned all processing data"

# Run basic tests
test:
    @echo "── Testing Shared imports ──"
    PYTHONPATH=src ./venv/bin/python -c "from shared.settings import DHIS2_URL; print(f'  ✅ Shared config OK (DHIS2_URL={DHIS2_URL})')"
    PYTHONPATH=src ./venv/bin/python -c "from shared.dhis2_client import DHIS2_URL; print(f'  ✅ DHIS2 client OK (url={DHIS2_URL})')"
    PYTHONPATH=src ./venv/bin/python -c "from shared.ou_picker import load_ou_codes; print('  ✅ OU picker OK')"
    PYTHONPATH=src ./venv/bin/python -c "from shared.id_utils import PROGRAMS; print(f'  ✅ ID utils OK ({len(PROGRAMS)} programs)')"
    @echo "── Testing Transfer imports ──"
    PYTHONPATH=src ./venv/bin/python -c "from transfer.fetcher import fetch_teis_full; print('  ✅ Transfer fetcher OK')"
    PYTHONPATH=src ./venv/bin/python -c "from transfer.engine import execute_transfer; print('  ✅ Transfer engine OK')"
    PYTHONPATH=src ./venv/bin/python -c "from transfer.verifier import verify_transfer; print('  ✅ Transfer verifier OK')"
    @echo "── Testing Sync imports ──"
    cd src/sync && ../../venv/bin/python -c "from config import Config; c = Config.from_env(); print(f'  ✅ Sync config OK (server={c.server})')"
    @echo "✅ All imports successful"

# Show available commands
help:
    @echo "╔══════════════════════════════════════════════════════════════════════╗"
    @echo "║  CPMIS Toolkit — Unified DHIS2 Management for CPMIS Malawi        ║"
    @echo "╚══════════════════════════════════════════════════════════════════════╝"
    @echo ""
    @echo "Setup:"
    @echo "  just init                            - Complete setup (install deps + venv)"
    @echo "  just setup                           - Create venv and install Python packages"
    @echo "  just test                            - Verify imports work"
    @echo ""
    @echo "Cleanup — Phase 1 (Organisation Unit Codes):"
    @echo "  just phase1-complete                 - 🚀 COMPLETE Phase 1 workflow + live update"
    @echo "  just phase1-push                     - Interactive push (pick scope)"
    @echo "  just phase1-district ZA              - Push single district (by code)"
    @echo "  just phase1-districts \"ZA,BL,MU\"     - Push multiple districts"
    @echo "  just phase1-ou <UID>                 - Push single org unit"
    @echo "  just phase1-district-dry ZA          - Dry-run for a district"
    @echo "  just push-ou-codes-dry               - Dry-run all org units"
    @echo "  just push-ou-codes                   - Push ALL to DHIS2 (PRODUCTION)"
    @echo "  just validate-ou-codes               - Validate codes against CSV"
    @echo "  just export-ou                       - Export org units from DHIS2"
    @echo "  just create-ou-codes                 - Create OU code reference CSV"
    @echo "  just update-ou-codes                 - Update codes with district mappings"
    @echo "  just task1-standardize               - Standardize org unit names"
    @echo ""
    @echo "Cleanup — Phase 2 (TEI ID Standardisation):"
    @echo "  just phase2                          - 🚀 Interactive workflow (recommended)"
    @echo "  just phase2-district ZA              - Process single district (by code)"
    @echo "  just phase2-districts \"ZA,BL,MU\"     - Process multiple districts"
    @echo "  just phase2-ou <UID>                 - Process single org unit"
    @echo "  just phase2-all                      - Process ALL org units"
    @echo "  just phase2-list-programs            - List DHIS2 programs (read-only)"
    @echo "  just phase2-fetch-samples            - Fetch sample TEIs (interactive)"
    @echo "  just phase2-apply <csv>              - Apply mapping CSV (via API)"
    @echo "  just phase2-apply-db <csv>           - Apply mapping CSV (via database)"
    @echo "  just phase2-verify <csv>             - Verify DB values match CSV"
    @echo ""
    @echo "OU Transfer (Move TEIs between org units):"
    @echo "  just transfer                        - 🚀 Interactive transfer workflow"
    @echo "  just verify                          - Show transferred TEIs (with names)"
    @echo "  just transfer-verify                 - Re-run verification on last transfer"
    @echo ""
    @echo "Sync Rescue (Import unsynced Android data):"
    @echo "  just sync-batch                      - 🚀 Batch import (place zips in imports/)"
    @echo "  just sync-extract <db>               - Extract data from SQLite database"
    @echo "  just sync-validate <user> <pass>     - Dry-run validation"
    @echo "  just sync-import <user> <pass>       - Import data to DHIS2"
    @echo "  just sync-verify <user> <pass>       - Verify imported data"
    @echo "  just sync-show-ignored               - Show ignored items report"
    @echo ""
    @echo "Full Pipeline:"
    @echo "  just run-all                         - 🚀 Phase 1 → Phase 2 → commit → push"
    @echo ""
    @echo "Utilities:"
    @echo "  just clean                           - Remove generated files"
    @echo "  just clean-all                       - Remove all + completed imports"
    @echo "  just clean-venv                      - Remove virtual environment"
    @echo "  just help                            - Show this help message"
