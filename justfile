# CPMIS Toolkit — Unified DHIS2 Management for CPMIS Malawi
# Author: Resten Madzalo (github.com/madzalo)

# Default recipe
default:
    @just help

# ═══════════════════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════════════════

# Setup — install dependencies via uv (creates .venv automatically)
setup:
    uv sync
    @echo "Setup complete! Virtual environment created in ./.venv"

# Complete setup (same as setup — uv handles everything)
init: setup

# Install build dependencies (pyinstaller + pillow)
setup-build:
    uv sync --extra build

# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED ENTRY POINT — Interactive menu for all tools
# ═══════════════════════════════════════════════════════════════════════════════

# Run the unified toolkit (interactive menu with all 4 tools)
run:
    PYTHONPATH=src uv run python main.py

# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGING — Build standalone Windows .exe
# ═══════════════════════════════════════════════════════════════════════════════

# Generate cpmis.ico from cpmis.png (enlarged to 512x512 for crisp icon at all sizes)
icon:
    uv run python -c "from PIL import Image; img = Image.open('cpmis.png').convert('RGBA'); size = 512; img = img.resize((size, size), Image.LANCZOS); canvas = Image.new('RGBA', (size, size), (255, 255, 255, 0)); canvas.paste(img, (0, 0), img); canvas.save('cpmis.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]); print('Saved cpmis.ico (enlarged to 512x512)')"

# Build a standalone .exe using PyInstaller (with icon)
build: icon
    rm -rf build/ dist/
    uv run pyinstaller cpmis_toolkit.spec --noconfirm
    @echo "Build complete! Check the dist/ folder for 'CPMIS Toolkit v<version>.exe'"

# Setup and build in one go
all: setup setup-build build

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP — Phase 1: Organisation Unit Codes
# ═══════════════════════════════════════════════════════════════════════════════

# Export organisation units from DHIS2 (T1.1)
export-ou:
    PYTHONPATH=src uv run python src/cleanup/phase1/export_org_units.py

# Update OU codes in the CSV file
task1-update:
    PYTHONPATH=src uv run python src/cleanup/phase1/update_ou_codes.py

# Standardize org unit names (capitalize, fix center->centre)
task1-standardize:
    PYTHONPATH=src uv run python src/cleanup/phase1/standardize_names.py

# Update OU codes with district codes from malawi_districts.csv
update-ou-codes:
    PYTHONPATH=src uv run python src/cleanup/phase1/update_ou_codes.py

# Create OU code reference CSV (T1.2)
create-ou-codes:
    PYTHONPATH=src uv run python src/cleanup/phase1/create_ou_codes.py

# Push OU codes to DHIS2 (dry-run, all org units)
push-ou-codes-dry:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --dry-run --all

# Push OU codes to DHIS2 (PRODUCTION, all org units)
push-ou-codes:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --all

# Interactive push (pick scope → preview → push)
phase1-push:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py

# Push OU codes for a single district (e.g. just phase1-district ZA)
phase1-district district_code:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --district {{district_code}}

# Push OU codes for multiple districts (e.g. just phase1-districts "ZA,BL,MU")
phase1-districts district_codes:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --district {{district_codes}}

# Push OU codes for a single org unit by UID
phase1-ou org_unit:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --org-unit {{org_unit}}

# Dry-run push for a single district
phase1-district-dry district_code:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --district {{district_code}} --dry-run

# Validate OU codes in DHIS2 against CSV
validate-ou-codes:
    PYTHONPATH=src uv run python src/cleanup/phase1/push_ou_codes.py --validate

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
    PYTHONPATH=src uv run python src/cleanup/phase2/phase2_workflow.py

# Process a single district by code (e.g. just phase2-district ZA)
phase2-district district_code:
    PYTHONPATH=src uv run python src/cleanup/phase2/phase2_workflow.py --district {{district_code}}

# Process multiple districts (e.g. just phase2-districts "ZA,BL,MU")
phase2-districts district_codes:
    PYTHONPATH=src uv run python src/cleanup/phase2/phase2_workflow.py --district {{district_codes}}

# Process all org units
phase2-all:
    PYTHONPATH=src uv run python src/cleanup/phase2/phase2_workflow.py --all

# Process a single org unit by UID
phase2-ou org_unit:
    PYTHONPATH=src uv run python src/cleanup/phase2/phase2_workflow.py --org-unit {{org_unit}}

# List all DHIS2 programs (read-only)
phase2-list-programs:
    PYTHONPATH=src uv run python src/cleanup/phase2/list_programs.py

# Fetch sample TEIs (interactive)
phase2-fetch-samples:
    PYTHONPATH=src uv run python src/cleanup/phase2/fetch_sample_teis.py

# Apply interactively (pick CSV → pick method → apply)
phase2-apply-interactive:
    PYTHONPATH=src uv run python src/cleanup/phase2/apply_ids.py --interactive

# Apply a previously generated mapping CSV (via API)
phase2-apply csv_file:
    PYTHONPATH=src uv run python src/cleanup/phase2/apply_ids.py --csv {{csv_file}}

# Apply a previously generated mapping CSV (via direct database)
phase2-apply-db csv_file:
    PYTHONPATH=src uv run python src/cleanup/phase2/apply_ids.py --csv {{csv_file}} --use-db

# Verify database values match expected CSV values
phase2-verify csv_file:
    PYTHONPATH=src uv run python src/cleanup/phase2/apply_ids.py --csv {{csv_file}} --verify

# ═══════════════════════════════════════════════════════════════════════════════
# OU TRANSFER — Move TEIs between organisation units
# ═══════════════════════════════════════════════════════════════════════════════

# Interactive transfer workflow (recommended)
transfer:
    PYTHONPATH=src uv run python src/transfer/transfer_workflow.py

# Show transferred TEIs from latest transfer (with names and details)
verify:
    PYTHONPATH=src uv run python src/transfer/verify_at_destination.py

# Comprehensive web UI verification (checks API, enrollments, TEI query, analytics)
verify-web tei_uid ou_uid:
    PYTHONPATH=src uv run python src/transfer/verify_web_ui.py --tei {{tei_uid}} --ou {{ou_uid}}

# Clear DHIS2 cache (fixes web UI not showing transferred TEIs)
clear-cache:
    PYTHONPATH=src uv run python src/transfer/clear_dhis2_cache.py

# Re-run verification on last transfer
transfer-verify:
    PYTHONPATH=src uv run python src/transfer/transfer_workflow.py --verify

# ═══════════════════════════════════════════════════════════════════════════════
# SYNC RESCUE — Import unsynced data from Android apps
# ═══════════════════════════════════════════════════════════════════════════════

# Run batch import processing (place zips in imports/ first)
sync-batch:
    cd src/sync && PYTHONPATH=. uv run python cli.py batch

# Extract data from a database
sync-extract db:
    cd src/sync && PYTHONPATH=. uv run python cli.py extract --db {{db}}

# Validate (dry-run) with credentials
sync-validate username password:
    cd src/sync && PYTHONPATH=. uv run python cli.py validate --username {{username}} --password {{password}}

# Import data to DHIS2
sync-import username password:
    cd src/sync && PYTHONPATH=. uv run python cli.py import --username {{username}} --password {{password}}

# Verify imported data
sync-verify username password:
    cd src/sync && PYTHONPATH=. uv run python cli.py verify --username {{username}} --password {{password}}

# Show ignored items from last import
sync-show-ignored:
    cd src/sync && PYTHONPATH=. uv run python -c "from utils import show_ignored_report; show_ignored_report()"

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
    PYTHONPATH=src uv run python src/cleanup/phase2/phase2_workflow.py

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
    rm -rf build/ dist/
    @echo "✅ Cleaned generated files"

# Remove virtual environment
clean-venv:
    rm -rf .venv

# Clean all (including sync completed imports)
clean-all: clean
    rm -rf completed_imports/*
    @echo "✅ Cleaned all processing data"

# Run basic tests
test:
    @echo "── Testing Shared imports ──"
    PYTHONPATH=src uv run python -c "from shared.settings import DHIS2_URL; print(f'  ✅ Shared config OK (DHIS2_URL={DHIS2_URL})')"
    PYTHONPATH=src uv run python -c "from shared.dhis2_client import DHIS2_URL; print(f'  ✅ DHIS2 client OK (url={DHIS2_URL})')"
    PYTHONPATH=src uv run python -c "from shared.ou_picker import load_ou_codes; print('  ✅ OU picker OK')"
    PYTHONPATH=src uv run python -c "from shared.id_utils import PROGRAMS; print(f'  ✅ ID utils OK ({len(PROGRAMS)} programs)')"
    @echo "── Testing Transfer imports ──"
    PYTHONPATH=src uv run python -c "from transfer.fetcher import fetch_teis_full; print('  ✅ Transfer fetcher OK')"
    PYTHONPATH=src uv run python -c "from transfer.engine import execute_transfer; print('  ✅ Transfer engine OK')"
    PYTHONPATH=src uv run python -c "from transfer.verifier import verify_transfer; print('  ✅ Transfer verifier OK')"
    @echo "── Testing Sync imports ──"
    cd src/sync && PYTHONPATH=. uv run python -c "from config import Config; c = Config.from_env(); print(f'  ✅ Sync config OK (server={c.server})')"
    @echo "✅ All imports successful"

# Show available commands
help:
    @echo "╔══════════════════════════════════════════════════════════════════════╗"
    @echo "║  CPMIS Toolkit — Unified DHIS2 Management for CPMIS Malawi        ║"
    @echo "╚══════════════════════════════════════════════════════════════════════╝"
    @echo ""
    @echo "Setup:"
    @echo "  just init                            - Setup (uv sync — creates .venv automatically)"
    @echo "  just setup                           - Same as init (uv sync)"
    @echo "  just setup-build                     - Install build deps (pyinstaller + pillow)"
    @echo "  just test                            - Verify imports work"
    @echo ""
    @echo "Unified Entry Point:"
    @echo "  just run                             - 🚀 Interactive menu (all 4 tools)"
    @echo ""
    @echo "Packaging (Windows .exe):"
    @echo "  just icon                            - Generate cpmis.ico from cpmis.png (enlarged)"
    @echo "  just build                            - Build standalone .exe with icon"
    @echo "  just all                             - Setup + build in one go"
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
    @echo "  just verify-web <tei> <ou>           - Comprehensive web UI verification"
    @echo "  just clear-cache                     - Clear DHIS2 cache (fixes web UI)"
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
