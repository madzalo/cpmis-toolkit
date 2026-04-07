<div align="center">

# CPMIS Toolkit

**Unified DHIS2 Management for CPMIS Malawi**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![DHIS2](https://img.shields.io/badge/DHIS2-Compatible-orange.svg)](https://dhis2.org/)

A monorepo containing two sub-projects for managing the CPMIS DHIS2 instance in Malawi.

[Quick Start](#-quick-start) • [Cleanup](#-cleanup-data-standardisation) • [Sync Rescue](#-sync-rescue-android-data-import) • [Commands](#-all-commands)

</div>

---

## Overview

This toolkit combines two DHIS2 management tools into a single repository:

| Sub-Project | Purpose | Location |
|---|---|---|
| **Cleanup** | Standardise org unit codes and TEI IDs across the DHIS2 hierarchy | `src/cleanup/` |
| **Sync Rescue** | Import unsynced data from DHIS2 Android Capture app databases | `src/sync/` |

Both projects share credentials (`.env`), a virtual environment (`venv/`), and a unified command runner (`justfile`).

---

## 🚀 Quick Start

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
# DHIS2 API credentials (required for both projects)
DHIS2_URL=https://cpmis.gender.gov.mw
DHIS2_USERNAME=your_username
DHIS2_PASSWORD=your_password

# PostgreSQL credentials (optional — only for cleanup --use-db)
DB_HOST=your_database_host
DB_PORT=5433
DB_NAME=cpmis_copy_clone
DB_USER=your_db_username
DB_PASSWORD=your_db_password

# Sync settings (optional — defaults shown)
# DHIS2_SERVER defaults to DHIS2_URL if not set
# BATCH_SIZE=200
```

> **Security:** The `.env` file is gitignored and never committed.

### Database Permissions (for `--use-db` mode)

If using direct database updates, grant permissions to your database user:

```sql
-- Connect as PostgreSQL superuser
psql -h your_database_host -p 5433 -U postgres -d cpmis_copy_clone

-- Grant permissions
GRANT SELECT ON trackedentityattribute TO your_db_username;
GRANT SELECT ON trackedentityinstance TO your_db_username;
GRANT SELECT, INSERT, UPDATE ON trackedentityattributevalue TO your_db_username;
```

---

## 🧹 Cleanup (Data Standardisation)

Standardises org unit codes and TEI IDs across 709 org units in the DHIS2 hierarchy.

**Detailed docs:** [docs/cleanup/overview.md](docs/cleanup/overview.md) · [docs/cleanup/tasks.md](docs/cleanup/tasks.md) · [docs/cleanup/ALGORITHM.md](docs/cleanup/ALGORITHM.md)

### Phase 1 — Organisation Unit Codes

Assigns a unique standardised code to every org unit (e.g., `BL_KAPE_ZING`).

```bash
just phase1-complete    # Full workflow: export → generate → preview → push
just phase1-push        # Interactive push (pick scope)
just phase1-district ZA # Single district
```

### Phase 2 — TEI ID Standardisation

Generates and applies standardised Household IDs and Child UICs.

```bash
just phase2             # Interactive workflow (pick scope → generate → apply)
just phase2-apply-db <csv>   # Fast direct database update
just phase2-verify <csv>     # Verify DB values match CSV
```

**Update methods:**
- **API** — Safe, uses DHIS2 REST API with validation (~2700 min for 21k TEIs)
- **Database** — Fast, direct PostgreSQL update (~5s for 21k TEIs)

---

## 🔄 Sync Rescue (Android Data Import)

Rescues unsynced data from DHIS2 Android Capture app SQLite databases when mobile sync fails.

**Detailed docs:** [docs/sync/CONTRIBUTING.md](docs/sync/CONTRIBUTING.md)

### Batch Processing (Recommended)

```bash
# 1. Place zip files in imports/ folder
cp ~/Downloads/*-database.zip imports/

# 2. Run batch processor
just sync-batch

# 3. Enter surname for each user when prompted
#    Username is auto-extracted from filename
#    Password format: Surname@2025

# 4. Completed zips are moved to completed_imports/
```

### Single File Processing

```bash
just sync-extract <db>              # Extract data from SQLite
just sync-validate <user> <pass>    # Dry-run validation
just sync-import <user> <pass>      # Import to DHIS2
just sync-verify <user> <pass>      # Verify import
```

---

## 📁 Project Structure

```
cpmis-toolkit/
├── src/
│   ├── shared/                     # Shared configuration
│   │   └── settings.py             # DHIS2 + DB credentials from .env
│   ├── cleanup/                    # Data standardisation
│   │   ├── phase1/                 # OU code generation & push
│   │   │   ├── export_org_units.py
│   │   │   ├── create_ou_codes.py
│   │   │   ├── update_ou_codes.py
│   │   │   ├── standardize_names.py
│   │   │   └── push_ou_codes.py
│   │   └── phase2/                 # TEI ID generation & apply
│   │       ├── phase2_workflow.py  # Interactive workflow
│   │       ├── db_update.py        # Direct database updates
│   │       ├── apply_ids.py        # CLI for apply/verify
│   │       └── ...
│   └── sync/                       # Android data import
│       ├── cli.py                  # CLI entry point
│       ├── config.py               # Sync-specific config
│       ├── extractor.py            # SQLite data extraction
│       ├── validator.py            # Dry-run validation
│       ├── importer.py             # DHIS2 data import
│       ├── verifier.py             # Server verification
│       ├── batch_processor.py      # Batch processing
│       └── utils.py                # Utilities
├── docs/
│   ├── cleanup/                    # Cleanup documentation
│   │   ├── overview.md
│   │   ├── tasks.md
│   │   └── ALGORITHM.md
│   └── sync/                       # Sync documentation
│       └── CONTRIBUTING.md
├── outputs/                        # Generated outputs (gitignored)
│   ├── task1/                      # Phase 1 outputs
│   ├── phase2/                     # Phase 2 outputs
│   └── sync/                       # Sync outputs
├── imports/                        # Place sync zip files here
├── completed_imports/              # Processed sync zips
├── malawi_districts.csv            # District code reference
├── .env                            # Credentials (gitignored)
├── .env.example                    # Credential template
├── justfile                        # Unified command runner
├── pyproject.toml                  # Package configuration
├── requirements.txt                # Python dependencies
├── LICENSE
└── README.md
```

---

## 📋 All Commands

Run `just help` to see all available commands:

### Setup
| Command | Description |
|---|---|
| `just init` | Complete setup (install deps + venv) |
| `just setup` | Create venv and install Python packages |
| `just test` | Verify imports work |

### Cleanup — Phase 1
| Command | Description |
|---|---|
| `just phase1-complete` | 🚀 Full workflow + live update |
| `just phase1-push` | Interactive push (pick scope) |
| `just phase1-district ZA` | Push single district |
| `just phase1-districts "ZA,BL"` | Push multiple districts |
| `just push-ou-codes-dry` | Dry-run all org units |
| `just push-ou-codes` | Push ALL (production) |
| `just validate-ou-codes` | Validate codes against CSV |

### Cleanup — Phase 2
| Command | Description |
|---|---|
| `just phase2` | 🚀 Interactive workflow |
| `just phase2-district ZA` | Process single district |
| `just phase2-all` | Process all org units |
| `just phase2-apply <csv>` | Apply mapping CSV (API) |
| `just phase2-apply-db <csv>` | Apply mapping CSV (database) |
| `just phase2-verify <csv>` | Verify DB matches CSV |

### Sync Rescue
| Command | Description |
|---|---|
| `just sync-batch` | 🚀 Batch import from Android |
| `just sync-extract <db>` | Extract from SQLite |
| `just sync-validate <u> <p>` | Dry-run validation |
| `just sync-import <u> <p>` | Import to DHIS2 |
| `just sync-verify <u> <p>` | Verify import |
| `just sync-show-ignored` | Show ignored items |

### Full Pipeline & Utilities
| Command | Description |
|---|---|
| `just run-all` | 🚀 Phase 1 → Phase 2 → commit → push |
| `just clean` | Remove generated files |
| `just clean-all` | Remove all + completed imports |
| `just clean-venv` | Remove virtual environment |

---

## Technical Stack

- **Python 3.10+** with `requests`, `aiohttp`, `psycopg2-binary`, `python-dotenv`
- **DHIS2 Web API** for org unit and TEI operations
- **PostgreSQL** for direct database updates (optional)
- **SQLite** for Android app database extraction
- **just** command runner for workflow orchestration

---

## 👤 Author

**Resten Madzalo** — [@madzalo](https://github.com/madzalo)

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
