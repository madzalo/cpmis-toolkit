# Sync Rescue — Overview

**App:** CPMIS Sync Rescue  
**Purpose:** Recover and import unsynced DHIS2 Android Capture data  
**Date:** March 2026

---

## Background

The **Malawi Child Protection Management Information System (CPMIS)** uses DHIS2 as its core platform. Community-level data collection is carried out by **Community Para Social Workers (CPWs)** using the **DHIS2 Android Capture** app on mobile phones and tablets. CPWs register households, enrol children (OVCs), and record case management events in the field — often in areas with limited or no internet connectivity.

### The Sync Problem

During **retrospective data entry campaigns**, CPWs enter large volumes of historical data on their devices. When they attempt to sync this data to the central CPMIS server, a number of issues frequently arise:

- **Network failures** — Unreliable mobile data coverage in rural areas causes sync timeouts and partial uploads
- **Server timeouts** — Large payloads overwhelm the DHIS2 server, especially when many CPWs sync simultaneously
- **Conflicting data** — Records created offline may conflict with server-side changes, causing sync rejections
- **App crashes** — The Android Capture app may crash mid-sync, leaving data in an inconsistent state
- **Authentication issues** — Expired sessions or changed credentials interrupt the sync process

When sync fails, the data remains trapped on the device's local SQLite database. CPWs often cannot resolve these issues themselves, and without intervention the data is at risk of being lost — particularly if the device is damaged, reset, or reassigned.

### The Solution

**Sync Rescue** provides a safe, reliable way to recover this trapped data:

1. **CPWs export** their device's database (the DHIS2 Android app stores all data in a SQLite `.db` file)
2. **CPWs share** the exported database via WhatsApp, email, or any file transfer method — typically as a `.zip` file
3. **An administrator** receives the `.zip`, places it in the `imports/` folder, and runs the batch processor
4. **The tool** extracts, validates, and imports the data directly into DHIS2 via the REST API using the CPW's own credentials
5. **The admin verifies** the import was successful by checking records on the server

This approach bypasses the Android app's sync mechanism entirely, importing data server-side through the DHIS2 Web API.

---

## How It Works

### Data Flow

```
CPSW Device                    Admin Workstation                    DHIS2 Server
┌──────────────┐               ┌──────────────────┐               ┌──────────────┐
│ Android App  │  WhatsApp/    │  Sync Rescue      │  DHIS2 API   │  CPMIS       │
│ SQLite DB    │──── email ───▶│  Extract → Validate│─────────────▶│  Database    │
│ (unsynced)   │  (.zip file)  │  → Import → Verify │              │  (live)      │
└──────────────┘               └──────────────────┘               └──────────────┘
```

### Processing Pipeline

Each database goes through a **four-step pipeline**:

| Step | Name | What It Does |
|------|------|--------------|
| 1 | **Extract** | Opens the SQLite database, reads all unsynced TEIs, enrollments, events, and relationships. Builds a DHIS2-compatible JSON import payload. |
| 2 | **Validate** | Sends the payload to DHIS2 as a **dry run** (`importStrategy: CREATE_AND_UPDATE`, `dryRun: true`). Reports what would be created, updated, or rejected — without touching real data. |
| 3 | **Import** | Sends the payload for real import. Records are created or updated on the server using the CPSSSSSW's own credentials (maintaining correct ownership and audit trail). |
| 4 | **Verify** | Queries the DHIS2 API to confirm that imported TEIs, enrollments, and events exist on the server with the expected attribute values. |

### Batch Processing

In practice, multiple CPWs may need their data rescued at the same time. The **batch processor** handles this efficiently:

1. Admin places all `.zip` files into the `imports/` folder
2. Runs `just sync-batch`
3. The tool lists all `.zip` files and asks for each CPW's surname
   - Username is **auto-extracted** from the zip filename (e.g., `john-database.zip` → username `john`)
   - Password is generated as `Surname@2025` (standard CPMIS password format)
4. Each file is processed through the full pipeline (extract → validate → import → verify)
5. Successfully processed `.zip` files are moved to `completed_imports/`
6. A summary report shows results for all files

---

## Key Features

### Safe Import Process
- **Dry-run validation** before every import — see exactly what will happen before committing
- **Per-user credentials** — data is imported under the CPW's own account, preserving DHIS2 audit trails
- **Automatic rollback** — if import fails, no partial data is left behind

### Intelligent Data Handling
- **Unsynced records only** — extracts only data that hasn't been synced to the server
- **Excluded attributes** — certain sensitive or auto-generated attributes are filtered out during extraction
- **Duplicate detection** — DHIS2's own deduplication handles records that may already exist on the server
- **Name extraction** — child and household names are correctly mapped from source to destination attributes

### Flexible Input
- **Zip files** — supports standard `.zip` and password-protected `.zip` archives
- **Nested archives** — handles zip-within-zip structures (common with some Android backup tools)
- **Auto-detection** — locates the SQLite database file inside the archive automatically

### Reporting
- **Detailed import reports** — JSON and CSV summaries of what was created, updated, and ignored
- **Access denied tracking** — records which TEIs the user doesn't have permission to modify
- **Ignored items report** — shows records that were skipped and why

---

## Typical Workflow

### For the CPW (in the field)

1. Open the DHIS2 Android Capture app
2. Go to **Settings → Export database** (or use a file manager to locate the app's database)
3. Send the exported `.zip` file to the admin via **WhatsApp** or email
4. Inform the admin of their **surname** (for password generation)

### For the Administrator

```bash
# 1. Place received zip files in the imports folder
cp ~/Downloads/*-database.zip imports/

# 2. Run the batch processor
just sync-batch

# 3. When prompted, enter each CPW's surname
#    The tool auto-extracts the username from the filename
#    Password is generated as: Surname@2025

# 4. Review the summary
#    ✅ Successful imports are moved to completed_imports/
#    ❌ Failed imports remain in imports/ for retry
```

### Single File Processing

For processing individual databases outside of the batch workflow:

```bash
# Step-by-step
just sync-extract <path-to-db>           # Extract from SQLite
just sync-validate <username> <password>  # Dry-run
just sync-import <username> <password>    # Import to DHIS2
just sync-verify <username> <password>    # Confirm on server
```

---

## Data Extracted

The tool extracts the following DHIS2 entities from the Android app's local database:

| Entity | Description |
|--------|-------------|
| **Tracked Entity Instances (TEIs)** | Households and children (OVCs) registered by the CPW |
| **Enrollments** | Program enrollments for each TEI (household programme, OVC programme) |
| **Events** | Case management events, assessments, and service records |
| **Relationships** | Links between households and children |
| **Attribute Values** | Names, IDs, dates, and other demographic data |

Only **unsynced** records are extracted — data that has already been successfully synced to the server is skipped.

---

## Configuration

The app reads credentials from the shared `.env` file in the project root:

```env
# Required
DHIS2_URL=https://cpmis.gender.gov.mw

# Optional (defaults shown)
DHIS2_SERVER=https://cpmis.gender.gov.mw   # Falls back to DHIS2_URL
BATCH_SIZE=200                               # Records per API request
```

Directories are automatically resolved relative to the project root:

| Directory | Purpose |
|-----------|---------|
| `imports/` | Drop `.zip` files here for batch processing |
| `completed_imports/` | Successfully processed `.zip` files are moved here |
| `outputs/sync/` | Working directory for extraction and intermediate files |

---

## Architecture

```
src/sync/
├── cli.py              # Command-line interface (argparse)
├── config.py           # Configuration dataclass with env var loading
├── extractor.py        # SQLite data extraction → JSON payload
├── validator.py        # DHIS2 dry-run validation
├── importer.py         # DHIS2 live import
├── verifier.py         # Post-import server verification
├── batch_processor.py  # Multi-file batch processing orchestrator
└── utils.py            # Logging, zip handling, progress tracking
```

### Module Responsibilities

- **`extractor.py`** — Connects to the SQLite database, queries unsynced TEIs/enrollments/events, filters excluded attributes, and writes a DHIS2-compatible JSON payload
- **`validator.py`** — Sends the payload to DHIS2 with `dryRun: true` to preview the import without modifying data
- **`importer.py`** — Sends the payload for real import, handles batch splitting for large payloads, and tracks created/updated/ignored counts
- **`verifier.py`** — Queries DHIS2 API to confirm imported records exist with correct attribute values
- **`batch_processor.py`** — Orchestrates the full pipeline for multiple zip files, manages user input, file movement, and summary reporting

---

## Technical Stack

- **Python 3.10+**
- **requests** — HTTP client for DHIS2 REST API
- **sqlite3** — Read Android app databases (standard library)
- **python-dotenv** — Environment variable management
- **just** — Command runner

---

## Getting Started

See the main [README.md](../../README.md) for installation and setup instructions.

For contributing guidelines, see [CONTRIBUTING.md](../../CONTRIBUTING.md).
