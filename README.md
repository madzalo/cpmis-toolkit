<div align="center">

# CPMIS Toolkit

**Unified DHIS2 Management for CPMIS Malawi**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![DHIS2](https://img.shields.io/badge/DHIS2-Compatible-orange.svg)](https://dhis2.org/)

A collection of tools for managing the CPMIS DHIS2 instance in Malawi — covering data cleanup, ID standardisation, organisation unit transfers, and recovery of unsynced Android app data.

</div>

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Cleanup App](#cleanup-app)
  - [Phase 1 — Organisation Unit Codes](#phase-1--organisation-unit-codes)
  - [Phase 2 — TEI ID Standardisation](#phase-2--tei-id-standardisation)
- [OU Transfer App](#ou-transfer-app)
  - [Background](#background-1)
  - [How It Works](#how-it-works-1)
  - [Typical Workflow](#typical-workflow)
- [Sync Rescue App](#sync-rescue-app)
  - [Background](#background-2)
  - [How It Works](#how-it-works-2)
  - [Batch Processing](#batch-processing-recommended)
  - [Single File Processing](#single-file-processing)
- [Project Structure](#project-structure)
- [All Commands](#all-commands)
- [Technical Stack](#technical-stack)
- [Author](#author)
- [License](#license)

---

## Overview

The **Malawi Child Protection Management Information System (CPMIS)** runs on DHIS2 and manages data for approximately **53,000 households** and **78,000 children (OVCs)** across **709 organisation units**. Community Para Social Workers (CPWs) use the DHIS2 Android Capture app to collect data in the field.

This toolkit provides three apps to support CPMIS operations:

| App | What It Does | Location |
|-----|-------------|----------|
| **Cleanup** | Standardises org unit codes, names, and TEI IDs across the entire DHIS2 hierarchy | `src/cleanup/` |
| **OU Transfer** | Transfers TEIs between organisation units with automatic ID regeneration | `src/transfer/` |
| **Sync Rescue** | Recovers and imports unsynced data from DHIS2 Android Capture app databases | `src/sync/` |

All apps share a single `.env` for credentials, a single virtual environment, and a unified `justfile` command runner.

> **For a deeper understanding of each app**, see the detailed overviews:
> - [Cleanup App Overview](docs/cleanup/overview.md) — code architecture, ID formats, update methods, safety features
> - [OU Transfer App Overview](docs/transfer/overview.md) — background, transfer workflow, relationship preservation, ID regeneration
> - [Sync Rescue App Overview](docs/sync/overview.md) — background, data flow, processing pipeline, extracted entities

---

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/madzalo/cpmis-toolkit.git
cd cpmis-toolkit
just init
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your DHIS2 and database credentials
```

### 3. Verify setup

```bash
just test
```

### 4. Run

```bash
# Cleanup: standardise org unit codes
just phase1-complete

# Cleanup: standardise TEI IDs
just phase2

# Sync Rescue: import unsynced Android data
just sync-batch
```

---

## Configuration

Create a `.env` file in the project root (or copy from `.env.example`):

```env
# DHIS2 API credentials (required for both apps)
DHIS2_URL=https://cpmis.gender.gov.mw
DHIS2_USERNAME=your_username
DHIS2_PASSWORD=your_password

# PostgreSQL credentials (optional — only for Cleanup --use-db mode)
DB_HOST=your_database_host
DB_PORT=5433
DB_NAME=cpmis_copy_clone
DB_USER=your_db_username
DB_PASSWORD=your_db_password

# Sync Rescue settings (optional — defaults shown)
# DHIS2_SERVER defaults to DHIS2_URL if not set
# BATCH_SIZE=200
```

> **Security:** The `.env` file is gitignored and never committed.

### Database Permissions (Cleanup `--use-db` mode only)

If using direct database updates in the Cleanup app, grant permissions to your database user:

```sql
-- Connect as PostgreSQL superuser
psql -h your_database_host -p 5433 -U postgres -d cpmis_copy_clone

-- Grant permissions
GRANT SELECT ON trackedentityattribute TO your_db_username;
GRANT SELECT ON trackedentityinstance TO your_db_username;
GRANT SELECT, INSERT, UPDATE ON trackedentityattributevalue TO your_db_username;
```

**Required permissions:**
- `trackedentityattribute` — `SELECT` to resolve attribute UIDs to internal IDs
- `trackedentityinstance` — `SELECT` to resolve TEI UIDs to internal IDs
- `trackedentityattributevalue` — `SELECT/INSERT/UPDATE` to read and write attribute values

---

## Cleanup App

Standardises org unit codes and TEI IDs across all 709 org units in the DHIS2 hierarchy. This ensures every organisation unit, household, and child record has a unique, human-readable identifier that encodes its position in the hierarchy.

> **Full documentation:** [Cleanup Overview](docs/cleanup/overview.md) · [Task Breakdown](docs/cleanup/tasks.md) · [ID Algorithm](docs/cleanup/ALGORITHM.md)

### Phase 1 — Organisation Unit Codes

Assigns a unique hierarchical code to every org unit. Codes encode the full chain from district to facility:

```
ZA                 ← Zomba (district)
├── ZA_CHIK        ← TA Chikowi
│   └── ZA_CHIK_LAMB  ← Lambulira (facility)
└── ZA_KUNT        ← TA Kuntumanji
```

```bash
just phase1-complete       # Full workflow: export → generate → preview → push
just phase1-push           # Interactive push (pick scope)
just phase1-district ZA    # Push single district
```

### Phase 2 — TEI ID Standardisation

Generates and applies standardised Household IDs (e.g., `ZA_CHIK_LAMB_HH_00000001`) and Child UICs (e.g., `ZA_CHIK_LAMB_OVC_00000001`).

```bash
just phase2                    # Interactive workflow (pick scope → generate → apply)
just phase2-apply-db <csv>     # Fast direct database update
just phase2-verify <csv>       # Verify DB values match CSV
```

**Two update methods are available:**

| Method | Speed | Safety | Best For |
|--------|-------|--------|----------|
| **API** | ~8 TEIs/min | Safe — uses DHIS2 validation and audit logs | Small batches, production |
| **Database** | ~5,000 TEIs/s | Fast — bypasses DHIS2 validation, needs backup | Bulk updates, staging |

---

## OU Transfer App

Transfers TEIs (children and households) between organisation units with automatic ID regeneration when CPWs register data at incorrect org unit levels.

> **Full documentation:** [OU Transfer Overview](docs/transfer/overview.md) · [Task Breakdown](docs/transfer/tasks.md)

### Background

Some CPWs incorrectly register children and households at **facility level** instead of **TA (Traditional Authority) level**. This creates:

- **Wrong hierarchy** — Children appear under facilities instead of TAs
- **Incorrect IDs** — Household IDs and Child UICs contain facility codes instead of TA codes
- **Reporting errors** — Aggregations show incorrect geographical distribution

### How It Works

**OU Transfer** safely moves TEIs between org units while preserving relationships and regenerating IDs:

1. **Select source OU** (facility) and **destination OU** (TA) using interactive picker
2. **Specify enrollment year range** (e.g., 2024-2026) to filter which TEIs to consider
3. **Select which TEIs to KEEP** at source — everything else is transferred
4. **Relationship preservation** — households and children are kept together automatically
5. **ID regeneration** — new Household IDs and Child UICs based on destination OU hierarchy
6. **Transfer execution** — moves TEIs, enrollments, events while preserving `createdBy` metadata
7. **Verification** — confirms all TEIs exist at destination with correct IDs and intact relationships

```
Source OU (Facility)          Transfer Engine              Destination OU (TA)
┌──────────────────┐         ┌──────────────┐            ┌──────────────────┐
│ ZA_CHIK_LAMB     │         │ 1. Fetch     │            │ ZA_CHIK          │
│ 50 children      │────────▶│ 2. Select    │───────────▶│ 40 children      │
│ 35 households    │         │ 3. Re-ID     │            │ 28 households    │
│ (Wrong IDs)      │         │ 4. Transfer  │            │ (Correct IDs)    │
└──────────────────┘         └──────────────┘            └──────────────────┘
```

### Typical Workflow

```bash
# Interactive transfer workflow
just transfer

# 1. Select source org unit (facility where data was incorrectly entered)
# 2. Select destination org unit (correct TA)
# 3. Enter year range: 2024-2026
# 4. Preview: "Found 50 children, 35 households"
# 5. Select which TEIs to KEEP at facility (others will be transferred)
# 6. Review transfer preview CSV
# 7. Confirm and execute
# 8. Verification runs automatically
```

**Key features:**
- ✅ **Relationship preservation** — households and children stay together
- ✅ **ID regeneration** — new IDs reflect destination OU hierarchy
- ✅ **Audit trail preservation** — `createdBy` metadata maintained
- ✅ **Selective transfer** — choose which TEIs to keep vs transfer
- ✅ **Comprehensive** — transfers TEIs, enrollments, events, relationships

---

## Sync Rescue App

Recovers and imports unsynced data from DHIS2 Android Capture app databases when mobile sync fails.

> **Full documentation:** [Sync Rescue Overview](docs/sync/overview.md)

### Background

During retrospective data entry campaigns, CPWs enter large volumes of historical data on their mobile devices using the DHIS2 Android Capture app. When they attempt to sync this data to the central CPMIS server, failures frequently occur due to:

- **Network issues** — unreliable mobile data in rural Malawi
- **Server timeouts** — large payloads overwhelming the DHIS2 server
- **App crashes** — sync interruptions leaving data in an inconsistent state
- **Authentication problems** — expired sessions or changed credentials

When sync fails, the data remains trapped in the device's local SQLite database. Without intervention, this data risks being lost if the device is damaged, reset, or reassigned.

### How It Works

**Sync Rescue** bypasses the Android app's sync mechanism entirely:

1. **CPW exports** their database from the Android app and shares the `.zip` file via **WhatsApp** or email
2. **Admin places** the `.zip` in the `imports/` folder and runs the batch processor
3. **The tool extracts** unsynced records from the SQLite database
4. **Validates** by sending a dry-run to DHIS2 (no data modified)
5. **Imports** via the DHIS2 REST API using the CPW's own credentials
6. **Verifies** the records exist on the server with correct values

```
CPSW Device              WhatsApp/Email           Admin Workstation            DHIS2 Server
┌──────────────┐         ┌─────────┐         ┌───────────────────┐         ┌──────────────┐
│ Android App  │────────▶│ .zip    │────────▶│ Extract → Validate│────────▶│  CPMIS DB    │
│ (unsynced)   │         │ file    │         │ → Import → Verify │         │  (live)      │
└──────────────┘         └─────────┘         └───────────────────┘         └──────────────┘
```

### Batch Processing (Recommended)

Process multiple CPW databases at once:

```bash
# 1. Place received zip files in the imports folder
cp ~/Downloads/*-database.zip imports/

# 2. Run the batch processor
just sync-batch

# 3. When prompted, enter each CPW's surname
#    - Username is auto-extracted from the zip filename
#    - Password is generated as: Surname@2025

# 4. The tool processes each file: extract → validate → import → verify
#    - Successful imports are moved to completed_imports/
#    - Failed imports remain in imports/ for retry
```

### Single File Processing

For processing individual databases:

```bash
just sync-extract <db>              # Extract data from SQLite
just sync-validate <user> <pass>    # Dry-run validation
just sync-import <user> <pass>      # Import to DHIS2
just sync-verify <user> <pass>      # Verify import
```

---

## Project Structure

```
cpmis-toolkit/
├── src/
│   ├── shared/                     # Shared configuration
│   │   └── settings.py             #   DHIS2 + DB credentials from .env
│   ├── cleanup/                    # Cleanup App
│   │   ├── malawi_districts.csv    #   District code reference
│   │   ├── phase1/                 #   OU code generation & push
│   │   │   ├── export_org_units.py
│   │   │   ├── create_ou_codes.py
│   │   │   ├── update_ou_codes.py
│   │   │   ├── standardize_names.py
│   │   │   └── push_ou_codes.py
│   │   └── phase2/                 #   TEI ID generation & apply
│   │       ├── phase2_workflow.py  #     Interactive workflow
│   │       ├── db_update.py        #     Direct database updates
│   │       ├── apply_ids.py        #     CLI for apply/verify
│   │       ├── generate_ids.py
│   │       ├── generate_all_ids.py
│   │       ├── id_generator.py
│   │       ├── bulk_assign.py
│   │       ├── fetch_sample_teis.py
│   │       └── list_programs.py
│   └── sync/                       # Sync Rescue App
│       ├── cli.py                  #   CLI entry point
│       ├── config.py               #   App-specific config
│       ├── extractor.py            #   SQLite data extraction
│       ├── validator.py            #   Dry-run validation
│       ├── importer.py             #   DHIS2 data import
│       ├── verifier.py             #   Post-import verification
│       ├── batch_processor.py      #   Multi-file batch processing
│       └── utils.py                #   Logging, zip handling, utilities
├── docs/
│   ├── cleanup/                    # Cleanup documentation
│   │   ├── overview.md             #   Architecture, ID formats, methods
│   │   ├── tasks.md                #   Task breakdown and status
│   │   └── ALGORITHM.md            #   ID generation algorithm details
│   └── sync/                       # Sync Rescue documentation
│       └── overview.md             #   Background, data flow, pipeline
├── outputs/                        # Generated outputs (gitignored)
│   ├── task1/                      #   Phase 1 outputs
│   ├── phase2/                     #   Phase 2 outputs
│   └── sync/                       #   Sync processing outputs
├── imports/                        # Drop sync .zip files here
├── completed_imports/              # Processed sync .zip files
├── .env                            # Credentials (gitignored)
├── .env.example                    # Credential template
├── justfile                        # Unified command runner
├── pyproject.toml                  # Package configuration
├── requirements.txt                # Python dependencies
├── CONTRIBUTING.md                 # Contribution guidelines
├── LICENSE
└── README.md
```

---

## All Commands

Run `just help` to see all available commands, or refer to the tables below.

### Setup

| Command | Description |
|---------|-------------|
| `just init` | Complete setup (install system deps + create venv) |
| `just setup` | Create virtual environment and install Python packages |
| `just test` | Verify all imports and configuration work correctly |

### Cleanup — Phase 1 (Organisation Unit Codes)

| Command | Description |
|---------|-------------|
| `just phase1-complete` | Full workflow with live update confirmation |
| `just phase1-push` | Interactive push (pick scope) |
| `just phase1-district ZA` | Push a single district by code |
| `just phase1-districts "ZA,BL,MU"` | Push multiple districts |
| `just phase1-ou <UID>` | Push a single org unit by UID |
| `just phase1-district-dry ZA` | Dry-run for a single district |
| `just push-ou-codes-dry` | Dry-run for all org units |
| `just push-ou-codes` | Push ALL org units (production) |
| `just validate-ou-codes` | Validate codes in DHIS2 against CSV |
| `just export-ou` | Export org units from DHIS2 |
| `just create-ou-codes` | Create OU code reference CSV |
| `just update-ou-codes` | Update codes with district mappings |
| `just task1-standardize` | Standardize org unit names |

### Cleanup — Phase 2 (TEI ID Standardisation)

| Command | Description |
|---------|-------------|
| `just phase2` | Interactive workflow (recommended) |
| `just phase2-district ZA` | Process a single district by code |
| `just phase2-districts "ZA,BL,MU"` | Process multiple districts |
| `just phase2-ou <UID>` | Process a single org unit by UID |
| `just phase2-all` | Process all org units |
| `just phase2-list-programs` | List DHIS2 programs (read-only) |
| `just phase2-fetch-samples` | Fetch sample TEIs (interactive) |
| `just phase2-apply <csv>` | Apply mapping CSV via API |
| `just phase2-apply-db <csv>` | Apply mapping CSV via database (fast) |
| `just phase2-verify <csv>` | Verify database values match CSV |

### Sync Rescue (Android Data Import)

| Command | Description |
|---------|-------------|
| `just sync-batch` | Batch import (place `.zip` files in `imports/`) |
| `just sync-extract <db>` | Extract data from a SQLite database |
| `just sync-validate <user> <pass>` | Dry-run validation against DHIS2 |
| `just sync-import <user> <pass>` | Import data to DHIS2 |
| `just sync-verify <user> <pass>` | Verify imported data on server |
| `just sync-show-ignored` | Show ignored items from last import |

### Full Pipeline & Utilities

| Command | Description |
|---------|-------------|
| `just run-all` | Full cleanup pipeline: Phase 1 → Phase 2 → Git commit → push |
| `just clean` | Remove generated output files |
| `just clean-all` | Remove all outputs + completed imports |
| `just clean-venv` | Remove the virtual environment |
| `just help` | Show all available commands |

---

## Technical Stack

| Technology | Purpose |
|------------|---------|
| **Python 3.10+** | Core language for both apps |
| **requests** | HTTP client for DHIS2 REST API |
| **aiohttp** | Async HTTP for high-throughput API updates |
| **psycopg2-binary** | PostgreSQL driver for direct database updates |
| **python-dotenv** | Environment variable management from `.env` |
| **sqlite3** | Read Android app databases (standard library) |
| **just** | Command runner for workflow orchestration |
| **Git** | Version control |

---

## Author

**Resten Madzalo** — [@madzalo](https://github.com/madzalo)

## License

MIT License — see [LICENSE](LICENSE) for details.
