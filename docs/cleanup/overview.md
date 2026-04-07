# CPMIS Data Standardisation Overview

**Project:** CPMIS Organisation Unit & Tracked Entity ID Standardisation  
**Implementation:** DHIS2 REST API + Direct PostgreSQL  
**Date:** March 2026

---

## Background

The **Malawi Child Protection Management Information System (CPMIS)** runs on DHIS2 and manages data for approximately **53,000 households** and **78,000 children (OVCs)** across 709 organisation units (districts, TAs, and health facilities).

This project standardises:
1. **Organisation unit codes** — unique codes for all 709 org units
2. **Organisation unit names** — consistent capitalisation and British spelling
3. **Household IDs** — standardised format for all 53,000 household records
4. **Child UICs** — standardised format for all 78,000 OVC records

Operations support two update methods: **DHIS2 REST API** (safe, auditable) and **direct PostgreSQL** (100x faster).

---

## Objectives

1. **Standardise organisation unit codes** — assign unique codes to all 709 org units (districts, TAs, facilities)
2. **Standardise organisation unit names** — consistent capitalisation, British spelling ("center" → "Centre")
3. **Generate standardised IDs** — create unique IDs for all households and children following format `{OU_CODE}-{TYPE}-{SEQUENCE}`
4. **Update all records** — via DHIS2 API (safe) or direct PostgreSQL (fast)
5. **Verify updates** — confirm database values match expected values
6. **Provide filtering and interactive tools** — process single org units, districts, or all at once

---

## Scope

| Entity | Count | Action |
|--------|-------|--------|
| Districts (L3) | 32 | Assign 2-letter codes (e.g., `ZA`) |
| TAs (L4) | 443 | Assign hierarchical codes (e.g., `ZA_CHIK`) |
| Facilities (L5) | 230 | Assign hierarchical codes (e.g., `ZA_CHIK_LAMB`) |
| Households | ~53,000 | Generate standardised IDs |
| Children (OVCs) | ~78,000 | Generate standardised UICs |

---

## Code Architecture

### Hierarchical Organisation Unit Codes

Every org unit code encodes its full position in the DHIS2 hierarchy:

```
Level 3 — District:   XX                   e.g. ZA
Level 4 — TA:         XX_YYYY              e.g. ZA_CHIK
Level 5 — Facility:   XX_YYYY_ZZZZ         e.g. ZA_CHIK_LAMB
```

**Example hierarchy (Zomba → TA Chikowi → Lambulira):**

```
ZA                  ← Zomba (district)
├── ZA_CHIK         ← TA Chikowi
│   ├── ZA_CHIK_LAMB   ← Lambulira (facility)
│   ├── ZA_CHIK_MAGO   ← Magomero Health Centre
│   └── ZA_CHIK_ZOMB   ← Zomba Central Hospital
├── ZA_KUNT         ← TA Kuntumanji
│   ├── ZA_KUNT_BIMB   ← Bimbi Health Centre
│   └── ZA_KUNT_MACH   ← Machinjiri Health Centre
└── ZA_MLUM         ← TA Mlumbe
    └── ZA_MLUM_CHAM   ← Chamba
```

**From any code, you can identify the full chain:**
- `ZA_CHIK_LAMB` → Facility `LAMB` under TA `CHIK` in district `ZA`
- `ZA_CHIK` → TA `CHIK` in district `ZA`
- `ZA` → District Zomba

### Generation Rules

**Short code extraction (4 letters per level):**
- First 4 letters of the name (after stripping prefixes)
- Numbers preserved: `Area 18` → `AREA18`

**TA/STA/Sub TA/T/A prefixes are stripped** — only the name after the prefix is used:
- `TA Chauma` → `CHAU` (not `TACH`)
- `STA Nkagula` → `NKAG` (not `STAN`)
- `Sub TA Phweremwe` → `PHWE` (not `SUBT`)
- `T/A Nkalo` → `NKAL` (not `TANK`)

**Duplicate handling** — if two org units produce the same code, a suffix `_1`, `_2` etc. is appended:
- `TA Chamba` (Machinga) → `MH_CHAM`
- `TA Changata` (Thyolo) → `TH_CHAN`
- `Chamba` facility (Machinga, under TA Chamba) → `MH_CHAM_CHAM`
- `Chamba` facility (Zomba, under TA Mlumbe) → `ZA_MLUM_CHAM`
  (no suffix needed — different parent TA makes it unique)

### TEI ID Format

**Household IDs:**
```
{OU_CODE}_HH_{SEQUENCE}

Examples:
  ZA_CHIK_LAMB_HH_00000001     ← Household in Lambulira facility
  ZA_CHIK_HH_00000001          ← Household registered at TA Chikowi
```

**Child UICs:**
```
{OU_CODE}_OVC_{SEQUENCE}

Examples:
  ZA_CHIK_LAMB_OVC_00000001    ← Child in Lambulira facility
  ZA_CHIK_OVC_00000001         ← Child registered at TA Chikowi
```

**Components:**
- **OU Code:** Hierarchical code from Phase 1 — encodes district, TA, and facility
- **Type:** `HH` (household) or `OVC` (child)
- **Sequence:** 8-digit zero-padded number, scoped per org unit per type

---

## Implementation Phases

---

### Phase 1: Organisation Unit Codes & Names

**What it does:**
1. **Exports** all 709 org units from DHIS2 via API
2. **Generates** standardised codes for each org unit
3. **Standardises** names (capitalisation, "center" → "Centre")
4. **Pushes** codes and names back to DHIS2 via API

**API Operations:**
- `GET /api/organisationUnits.json` — export all org units
- `POST /api/metadata` — bulk update with 1000 OUs per batch
- Fallback: `PATCH /api/organisationUnits/{uid}` — individual updates if bulk times out

**Commands:**
```bash
just phase1-complete          # Full workflow with confirmation
just phase1-push              # Interactive push (pick scope)
just phase1-district ZA       # Push single district
just push-ou-codes            # Push all org units
```

**Output:** `outputs/task1/ou_codes_standardized.csv` — master reference for Phase 2

---

### Phase 2: Tracked Entity Instance IDs

**What it does:**
1. **Fetches** all TEIs (households and children) from DHIS2 via API
2. **Generates** standardised IDs using org unit codes from Phase 1
3. **Previews** changes before applying
4. **Selects update method** — API (safe) or Database (fast)
5. **Updates** TEI attributes via chosen method
6. **Verifies** database values match expected values (DB mode)

**Update Methods:**

| Method | Speed | Safety | Command |
|--------|-------|--------|---------|
| API | ~8 TEIs/min | Safe, auditable, uses DHIS2 validation | `just phase2-apply <csv>` |
| Database | ~5,000 TEIs/s | Fast, bypasses validation, needs backup | `just phase2-apply-db <csv>` |

**API Operations (API mode):**
- `GET /api/trackedEntityInstances.json` — fetch TEIs by org unit and program
- `PUT /api/trackedEntityInstances/{uid}` — async update with 4 concurrent connections

**Database Operations (DB mode):**
- Resolves attribute UIDs to internal database IDs (e.g., `SYUXY9pax4w` → `15311`)
- Resolves TEI UIDs to internal database IDs
- `INSERT ... ON CONFLICT DO UPDATE` (UPSERT) on `trackedentityattributevalue` table
- Batched execution with real-time progress (500 rows per batch)
- Automatic rollback on failure

**Commands:**
```bash
just phase2                           # Interactive workflow (recommended)
just phase2-district ZA               # Single district
just phase2-districts "ZA,BL"         # Multiple districts
just phase2-all                       # All org units
just phase2-apply <csv>               # Re-apply via API
just phase2-apply-db <csv>            # Re-apply via database (fast)
just phase2-verify <csv>              # Verify DB values match CSV
```

**Performance optimizations:**
- Connection reuse via `requests.Session()` (avoids TCP/TLS handshake per request)
- Parallel TEI fetching (6 concurrent workers)
- Async API updates with 4 concurrent connections and retry logic
- Direct DB: batched UPSERT with 500 rows/batch, ~5s for 20,000 TEIs

**Outputs:**
- `outputs/phase2/id_mapping_*.csv` — mapping of old → new IDs
- `outputs/phase2/id_mapping_*_db_log_*.csv` — timestamped log of DB changes

---

## Safety & Features

**Read-only until confirmed:**
- All generation and preview steps are read-only
- Changes only applied after explicit user confirmation
- DB updates require double confirmation (start + execute)
- Dry-run modes available for all operations

**Filtering & Scope:**
- Process single org units, districts, or all at once
- Interactive search and selection
- Preview changes before applying

**Progress & Error Handling:**
- Real-time progress updates with ETA and rows/s
- Detailed error reporting
- Automatic retry with fallback strategies (API mode)
- Automatic rollback on failure (DB mode)
- Connection reuse for optimal performance

**Verification & Audit:**
- CSV mappings of all changes (old → new IDs)
- Timestamped DB update logs
- `just phase2-verify <csv>` — queries DB and compares actual vs expected values
- Matched/mismatched/not-found counts with detail table

---

## Technical Stack

- **Language:** Python 3.10+
- **DHIS2 API:** REST API for fetching + safe updates
- **Database:** Direct PostgreSQL for fast updates (`psycopg2`)
- **Libraries:** `requests`, `aiohttp` (async HTTP), `psycopg2-binary` (PostgreSQL), `python-dotenv`
- **Command runner:** `just` (justfile)
- **Version control:** Git

---

## Getting Started

See the main [README.md](../../README.md) for installation, configuration, and the complete command reference.
