# OU Transfer — Task Breakdown

**App:** CPMIS OU Transfer & Re-ID  
**Status:** Planning Phase  
**Last Updated:** April 2026

---

## Overview

This document breaks down the implementation of the **OU Transfer** app into discrete, actionable tasks. Tasks are organized by phase and include dependencies, estimated complexity, and acceptance criteria.

---

## Phase 0: Shared Utilities Extraction

**Goal:** Extract reusable code from Cleanup Phase 2 into `src/shared/` for use across multiple apps.

### Task 0.1: Extract OU Picker to Shared
**Priority:** High  
**Complexity:** Low  
**Estimated Time:** 1 hour

**Description:**
Extract the interactive organisation unit picker from `src/cleanup/phase2/phase2_workflow.py` into a reusable shared module.

**Files to create:**
- `src/shared/ou_picker.py`

**Functions to extract:**
```python
def select_org_unit_interactive(dhis2_url, username, password, prompt="Select organisation unit"):
    """
    Interactive org unit picker with hierarchy display.
    Returns: (ou_uid, ou_name, ou_code)
    """
    pass

def get_org_unit_hierarchy(dhis2_url, username, password):
    """
    Fetch full org unit hierarchy from DHIS2.
    Returns: Nested dict with OU structure
    """
    pass

def display_org_unit_tree(org_units, level=0):
    """
    Display org units as an indented tree.
    """
    pass
```

**Acceptance Criteria:**
- [ ] Code extracted from Phase 2 workflow
- [ ] Works independently with only DHIS2 credentials
- [ ] Phase 2 workflow updated to import from shared
- [ ] Transfer app can import and use the picker
- [ ] No breaking changes to existing Phase 2 functionality

---

### Task 0.2: Extract ID Generation Logic to Shared
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 2 hours

**Description:**
Extract ID generation logic from `src/cleanup/phase2/id_generator.py` into a reusable shared module.

**Files to create:**
- `src/shared/id_utils.py`

**Functions to extract:**
```python
def generate_household_id(ou_code, sequence_number):
    """
    Generate Household ID: {ou_code}_HH_{sequence:08d}
    Example: ZA_CHIK_HH_00000001
    """
    pass

def generate_child_uic(ou_code, sequence_number):
    """
    Generate Child UIC: {ou_code}_OVC_{sequence:08d}
    Example: ZA_CHIK_OVC_00000001
    """
    pass

def get_max_sequence_number(dhis2_url, username, password, ou_uid, id_pattern):
    """
    Query DHIS2 for max sequence number in given OU.
    Returns: int (max sequence number found)
    """
    pass

def extract_ou_code_from_hierarchy(ou_uid, org_units):
    """
    Extract hierarchical OU code (e.g., ZA_CHIK_LAMB or ZA_CHIK).
    Returns: str (OU code)
    """
    pass
```

**Acceptance Criteria:**
- [ ] Code extracted from Phase 2 id_generator
- [ ] Works independently with DHIS2 API
- [ ] Phase 2 updated to import from shared
- [ ] Transfer app can import and use ID generation
- [ ] No breaking changes to existing Phase 2 functionality
- [ ] Unit tests pass (if they exist)

---

### Task 0.3: Extract DHIS2 API Client to Shared
**Priority:** Medium  
**Complexity:** Medium  
**Estimated Time:** 2 hours

**Description:**
Create a shared DHIS2 API client with common operations used across apps.

**Files to create:**
- `src/shared/dhis2_client.py`

**Functions to include:**
```python
class DHIS2Client:
    def __init__(self, url, username, password):
        self.url = url
        self.auth = (username, password)
    
    def get_tei(self, tei_uid, fields="*"):
        """Fetch single TEI by UID"""
        pass
    
    def get_teis(self, ou_uid=None, program=None, filters=None):
        """Fetch multiple TEIs with filters"""
        pass
    
    def update_tei(self, tei_uid, data):
        """Update TEI using POST (preserves createdBy)"""
        pass
    
    def get_relationships(self, tei_uid):
        """Fetch relationships for a TEI"""
        pass
    
    def get_enrollments(self, tei_uid):
        """Fetch enrollments for a TEI"""
        pass
    
    def update_enrollment(self, enrollment_uid, data):
        """Update enrollment"""
        pass
    
    def get_events(self, tei_uid=None, enrollment_uid=None):
        """Fetch events"""
        pass
    
    def update_event(self, event_uid, data):
        """Update event"""
        pass
```

**Acceptance Criteria:**
- [ ] Client handles authentication
- [ ] All methods use appropriate HTTP verbs (POST for updates)
- [ ] Error handling for API failures
- [ ] Can be imported and used by Transfer app
- [ ] Optional: Cleanup and Sync apps can migrate to use it

---

## Phase 1: Data Fetching & Relationship Resolution

**Goal:** Fetch TEIs from source OU and build relationship graph.

### Task 1.1: Create Transfer App Structure
**Priority:** High  
**Complexity:** Low  
**Estimated Time:** 30 minutes

**Description:**
Set up the basic directory structure and configuration for the Transfer app.

**Files to create:**
- `src/transfer/__init__.py`
- `src/transfer/config.py`
- `src/transfer/cli.py`
- `src/transfer/utils.py`

**Acceptance Criteria:**
- [ ] Directory structure created
- [ ] Config loads from shared settings
- [ ] CLI entry point created (empty for now)
- [ ] Utils has logging setup

---

### Task 1.2: Implement TEI Fetcher
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Description:**
Create module to fetch TEIs from source OU filtered by enrollment year range.

**Files to create:**
- `src/transfer/fetcher.py`

**Key functions:**
```python
def fetch_teis_by_enrollment_year(
    dhis2_client,
    ou_uid,
    program_uid,
    start_year,
    end_year
):
    """
    Fetch all TEIs enrolled in specified year range.
    Returns: List of TEI objects with attributes and enrollments
    """
    pass

def fetch_tei_details(dhis2_client, tei_uid):
    """
    Fetch complete TEI details including:
    - Attributes (Household ID, Child UIC, names, etc.)
    - Enrollments
    - Events
    - Relationships
    """
    pass

def categorize_teis(teis):
    """
    Separate TEIs into households and children.
    Returns: (households, children)
    """
    pass
```

**API Endpoints to use:**
```
GET /api/trackedEntityInstances?
    ou={ou_uid}
    &program={program_uid}
    &enrollmentStartDate={start_year}-01-01
    &enrollmentEndDate={end_year}-12-31
    &fields=*
```

**Acceptance Criteria:**
- [ ] Fetches all TEIs in date range
- [ ] Includes all attributes, enrollments, events
- [ ] Correctly categorizes households vs children
- [ ] Handles pagination for large result sets
- [ ] Error handling for API failures
- [ ] Progress tracking for long fetches

---

### Task 1.3: Implement Relationship Resolver
**Priority:** High  
**Complexity:** High  
**Estimated Time:** 4 hours

**Description:**
Build a relationship graph to map household-child connections.

**Files to create:**
- `src/transfer/relationship_resolver.py`

**Key functions:**
```python
class RelationshipGraph:
    """
    Graph structure to represent household-child relationships.
    """
    def __init__(self, teis):
        self.households = {}  # uid -> Household object
        self.children = {}    # uid -> Child object
        self.relationships = []  # List of (child_uid, household_uid)
    
    def build_graph(self):
        """Build the relationship graph from TEI data"""
        pass
    
    def get_household_for_child(self, child_uid):
        """Get household UID for a given child"""
        pass
    
    def get_children_for_household(self, household_uid):
        """Get list of child UIDs for a given household"""
        pass
    
    def validate_integrity(self):
        """
        Validate that all relationships are valid:
        - Every child has exactly one household
        - Every household has at least one child
        Returns: (is_valid, errors)
        """
        pass

def fetch_relationships(dhis2_client, tei_uids):
    """
    Fetch all relationships for given TEIs.
    Returns: List of relationship objects
    """
    pass

def resolve_transfer_set(keep_teis, all_teis, graph):
    """
    Given TEIs to KEEP, determine which TEIs must be TRANSFERRED.
    Ensures relationships remain intact.
    
    Algorithm:
    1. Start with keep_teis
    2. Expand to include related TEIs (children ↔ households)
    3. Everything not in expanded keep_set is transferred
    4. Expand transfer_set to include related TEIs
    5. Validate no broken relationships
    
    Returns: (transfer_set, validation_errors)
    """
    pass
```

**Acceptance Criteria:**
- [ ] Correctly maps all household-child relationships
- [ ] Handles edge cases (orphaned children, empty households)
- [ ] Validates relationship integrity
- [ ] Efficiently resolves transfer set from keep set
- [ ] Returns clear error messages for invalid selections
- [ ] Unit tests for relationship resolution logic

---

## Phase 2: Selection & Preview

**Goal:** Allow user to select which TEIs to keep, generate transfer preview.

### Task 2.1: Implement Selection Logic
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Description:**
Create interactive selection interface for choosing which TEIs to keep at source.

**Files to create:**
- `src/transfer/selector.py`

**Key functions:**
```python
def export_selection_csv(teis, output_path):
    """
    Export TEIs to CSV for manual selection.
    Columns: tei_uid, type, name, household_id, child_uic, enrollment_date, keep
    """
    pass

def import_selection_csv(csv_path):
    """
    Import user's selection from CSV.
    Returns: List of TEI UIDs marked to keep
    """
    pass

def auto_select_by_enrollment_date(teis, keep_count):
    """
    Automatically select first N TEIs by enrollment date.
    Returns: List of TEI UIDs to keep
    """
    pass

def validate_selection(keep_teis, all_teis, graph):
    """
    Validate that selection won't break relationships.
    Returns: (is_valid, warnings)
    """
    pass
```

**Acceptance Criteria:**
- [ ] CSV export includes all relevant TEI info
- [ ] CSV import correctly parses user selections
- [ ] Auto-select by date works correctly
- [ ] Validation catches relationship issues
- [ ] Clear warnings for problematic selections

---

### Task 2.2: Implement Transfer Preview Generator
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 2 hours

**Description:**
Generate preview CSV showing what will happen during transfer.

**Files to create:**
- `src/transfer/preview_generator.py`

**Key functions:**
```python
def generate_transfer_preview(
    transfer_teis,
    source_ou,
    dest_ou,
    id_mappings,
    output_path
):
    """
    Generate CSV preview of transfer.
    Columns:
    - tei_uid
    - type (Household/Child)
    - name
    - old_ou_uid
    - old_ou_name
    - new_ou_uid
    - new_ou_name
    - old_household_id / old_child_uic
    - new_household_id / new_child_uic
    - enrollment_count
    - event_count
    - relationship_count
    """
    pass

def display_transfer_summary(transfer_teis, source_ou, dest_ou):
    """
    Display summary statistics:
    - Total TEIs to transfer
    - Households: X
    - Children: Y
    - Total enrollments: Z
    - Total events: W
    """
    pass
```

**Acceptance Criteria:**
- [ ] Preview CSV is human-readable
- [ ] Includes all relevant information
- [ ] Summary statistics are accurate
- [ ] Can be reviewed before executing transfer

---

## Phase 3: ID Generation

**Goal:** Generate new IDs for transferred TEIs based on destination OU.

### Task 3.1: Implement ID Generator for Transfer
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 2 hours

**Description:**
Generate new Household IDs and Child UICs for destination OU.

**Files to create:**
- `src/transfer/id_generator.py`

**Key functions:**
```python
def generate_new_ids(
    transfer_teis,
    dest_ou_uid,
    dest_ou_code,
    dhis2_client
):
    """
    Generate new IDs for all transferred TEIs.
    
    Steps:
    1. Query destination OU for max sequence numbers
    2. Generate new Household IDs (starting from max + 1)
    3. Generate new Child UICs (starting from max + 1)
    4. Return mapping: tei_uid -> new_id
    """
    pass

def check_id_collisions(new_ids, dest_ou_uid, dhis2_client):
    """
    Verify that new IDs don't already exist at destination.
    Returns: (has_collisions, collision_list)
    """
    pass
```

**Acceptance Criteria:**
- [ ] Reuses shared ID generation logic
- [ ] Queries destination OU for max sequences
- [ ] Generates sequential IDs without gaps
- [ ] Checks for collisions before returning
- [ ] Returns clear mapping of old UID -> new ID

---

## Phase 4: Transfer Execution

**Goal:** Execute the transfer using DHIS2 API.

### Task 4.1: Implement API Client for Transfer
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Description:**
Create API client wrapper specifically for transfer operations.

**Files to create:**
- `src/transfer/api_client.py`

**Key functions:**
```python
def update_tei_org_unit(dhis2_client, tei_uid, new_ou_uid):
    """
    Update TEI's organisation unit using POST.
    Preserves createdBy, updates lastUpdatedBy.
    """
    pass

def update_tei_attributes(dhis2_client, tei_uid, attributes):
    """
    Update TEI attributes (Household ID, Child UIC) using POST.
    """
    pass

def update_enrollment_org_unit(dhis2_client, enrollment_uid, new_ou_uid):
    """
    Update enrollment's organisation unit.
    """
    pass

def update_event_org_unit(dhis2_client, event_uid, new_ou_uid):
    """
    Update event's organisation unit.
    """
    pass
```

**API calls to use:**
```http
POST /api/trackedEntityInstances/{uid}
{
  "orgUnit": "{new_ou_uid}",
  "attributes": [...]
}

POST /api/enrollments/{uid}
{
  "orgUnit": "{new_ou_uid}"
}

POST /api/events/{uid}
{
  "orgUnit": "{new_ou_uid}"
}
```

**Acceptance Criteria:**
- [ ] Uses POST (not PUT) for all updates
- [ ] Correctly updates org unit for TEIs
- [ ] Correctly updates attributes (IDs)
- [ ] Correctly updates enrollments
- [ ] Correctly updates events
- [ ] Error handling for API failures
- [ ] Preserves createdBy metadata

---

### Task 4.2: Implement Transfer Engine
**Priority:** High  
**Complexity:** High  
**Estimated Time:** 4 hours

**Description:**
Orchestrate the complete transfer process.

**Files to create:**
- `src/transfer/transfer_engine.py`

**Key functions:**
```python
def transfer_tei(
    tei,
    new_ou_uid,
    new_id,
    dhis2_client
):
    """
    Transfer a single TEI:
    1. Update TEI org unit
    2. Update TEI attributes (Household ID / Child UIC)
    3. Update all enrollments
    4. Update all events
    
    Returns: (success, error_message)
    """
    pass

def transfer_batch(
    transfer_teis,
    dest_ou_uid,
    id_mappings,
    dhis2_client,
    progress_callback=None
):
    """
    Transfer multiple TEIs with progress tracking.
    
    Returns: TransferReport with:
    - successful_transfers: List[tei_uid]
    - failed_transfers: List[(tei_uid, error)]
    - total_enrollments_updated: int
    - total_events_updated: int
    """
    pass

def rollback_transfer(transfer_report, dhis2_client):
    """
    Rollback a failed transfer (move TEIs back to source).
    """
    pass
```

**Acceptance Criteria:**
- [ ] Transfers TEIs one at a time (atomic operations)
- [ ] Updates all related entities (enrollments, events)
- [ ] Progress tracking with callbacks
- [ ] Detailed error reporting
- [ ] Rollback capability for failed transfers
- [ ] Generates transfer report

---

## Phase 5: Verification

**Goal:** Verify transfer completed successfully.

### Task 5.1: Implement Transfer Verifier
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 3 hours

**Description:**
Verify that transferred TEIs exist at destination with correct data.

**Files to create:**
- `src/transfer/verifier.py`

**Key functions:**
```python
def verify_tei_transfer(
    tei_uid,
    expected_ou_uid,
    expected_id,
    dhis2_client
):
    """
    Verify single TEI:
    1. Exists at destination OU
    2. Has correct Household ID / Child UIC
    3. Enrollments at destination OU
    4. Events at destination OU
    
    Returns: (is_valid, errors)
    """
    pass

def verify_relationships(
    transfer_teis,
    dhis2_client
):
    """
    Verify all household-child relationships intact.
    Returns: (is_valid, broken_relationships)
    """
    pass

def verify_batch(
    transfer_report,
    id_mappings,
    dest_ou_uid,
    dhis2_client
):
    """
    Verify all transferred TEIs.
    
    Returns: VerificationReport with:
    - verified_teis: List[tei_uid]
    - failed_verifications: List[(tei_uid, error)]
    - relationship_status: (is_valid, errors)
    """
    pass

def generate_verification_report(
    verification_report,
    output_path
):
    """
    Generate CSV verification report.
    Columns:
    - tei_uid
    - verification_status (✅ / ❌)
    - ou_correct (✅ / ❌)
    - id_correct (✅ / ❌)
    - enrollments_correct (✅ / ❌)
    - events_correct (✅ / ❌)
    - error_message
    """
    pass
```

**Acceptance Criteria:**
- [ ] Verifies TEI exists at destination
- [ ] Verifies IDs updated correctly
- [ ] Verifies enrollments transferred
- [ ] Verifies events transferred
- [ ] Verifies relationships intact
- [ ] Generates detailed verification report
- [ ] Clear pass/fail status for each TEI

---

## Phase 6: CLI & User Interface

**Goal:** Create interactive CLI workflow.

### Task 6.1: Implement Interactive CLI Workflow
**Priority:** High  
**Complexity:** Medium  
**Estimated Time:** 4 hours

**Description:**
Create the main interactive workflow for transfers.

**Files to update:**
- `src/transfer/cli.py`

**Workflow steps:**
```python
def run_interactive_transfer():
    """
    1. Select source OU (interactive picker)
    2. Select destination OU (interactive picker)
    3. Enter enrollment year range
    4. Fetch TEIs from source
    5. Display summary (X children, Y households)
    6. Export selection CSV
    7. Wait for user to edit CSV
    8. Import selection CSV
    9. Resolve transfer set (relationship graph)
    10. Generate new IDs
    11. Generate transfer preview CSV
    12. Confirm with user
    13. Execute transfer
    14. Run verification
    15. Display results
    """
    pass
```

**Acceptance Criteria:**
- [ ] Clear prompts at each step
- [ ] Progress indicators for long operations
- [ ] Confirmation before executing transfer
- [ ] Graceful error handling
- [ ] Can be interrupted safely (Ctrl+C)

---

### Task 6.2: Implement Direct Commands
**Priority:** Medium  
**Complexity:** Low  
**Estimated Time:** 2 hours

**Description:**
Create direct CLI commands for advanced users.

**Commands to implement:**
```bash
just transfer-preview <source_uid> <dest_uid> --years 2024-2026
just transfer-apply <selection_csv>
just transfer-verify <transfer_report_csv>
just transfer-auto <source_uid> <dest_uid> --years 2024-2026 --keep 10
```

**Acceptance Criteria:**
- [ ] All commands work independently
- [ ] Clear help text for each command
- [ ] Proper error messages for invalid inputs

---

## Phase 7: Integration & Documentation

**Goal:** Integrate with existing toolkit and document.

### Task 7.1: Update Justfile
**Priority:** High  
**Complexity:** Low  
**Estimated Time:** 1 hour

**Description:**
Add transfer commands to the main justfile.

**Commands to add:**
```makefile
# Transfer commands
transfer:
    python -m src.transfer.cli interactive

transfer-preview source dest years:
    python -m src.transfer.cli preview {{source}} {{dest}} --years {{years}}

transfer-apply csv:
    python -m src.transfer.cli apply {{csv}}

transfer-verify csv:
    python -m src.transfer.cli verify {{csv}}

transfer-auto source dest years keep:
    python -m src.transfer.cli auto {{source}} {{dest}} --years {{years}} --keep {{keep}}
```

**Acceptance Criteria:**
- [ ] All commands work from project root
- [ ] Help text displays correctly
- [ ] Integrated with existing just commands

---

### Task 7.2: Update Main README
**Priority:** High  
**Complexity:** Low  
**Estimated Time:** 1 hour

**Description:**
Add Transfer app section to main README.

**Sections to add:**
- Overview of Transfer app
- Quick start example
- Command reference table
- Link to detailed docs

**Acceptance Criteria:**
- [ ] README updated with Transfer section
- [ ] Consistent formatting with existing sections
- [ ] Links to detailed docs work

---

### Task 7.3: Create User Guide
**Priority:** Medium  
**Complexity:** Low  
**Estimated Time:** 2 hours

**Description:**
Create step-by-step user guide with examples.

**Files to create:**
- `docs/transfer/user-guide.md`

**Content to include:**
- Common scenarios (facility → TA transfer)
- Step-by-step walkthrough with screenshots
- Troubleshooting common issues
- FAQ section

**Acceptance Criteria:**
- [ ] User guide is comprehensive
- [ ] Examples are realistic
- [ ] Troubleshooting covers common issues

---

## Phase 8: Testing & Quality Assurance

**Goal:** Ensure reliability and correctness.

### Task 8.1: Unit Tests
**Priority:** Medium  
**Complexity:** Medium  
**Estimated Time:** 4 hours

**Description:**
Write unit tests for core logic.

**Files to create:**
- `tests/transfer/test_relationship_resolver.py`
- `tests/transfer/test_selector.py`
- `tests/transfer/test_id_generator.py`

**Test coverage:**
- [ ] Relationship graph building
- [ ] Transfer set resolution
- [ ] ID generation
- [ ] Selection validation

**Acceptance Criteria:**
- [ ] All core logic has unit tests
- [ ] Tests pass consistently
- [ ] Edge cases covered

---

### Task 8.2: Integration Tests
**Priority:** Medium  
**Complexity:** High  
**Estimated Time:** 4 hours

**Description:**
Test complete transfer workflow on staging environment.

**Test scenarios:**
1. Transfer all TEIs from facility to TA
2. Transfer partial set (keep some, move others)
3. Transfer with complex relationship graph
4. Verify rollback works correctly
5. Verify audit trails preserved

**Acceptance Criteria:**
- [ ] All scenarios tested on staging
- [ ] No data corruption
- [ ] Relationships intact
- [ ] IDs correct
- [ ] Audit trails preserved

---

## Summary

### Total Estimated Time
- **Phase 0 (Shared Utilities):** 5 hours
- **Phase 1 (Fetching & Relationships):** 7.5 hours
- **Phase 2 (Selection & Preview):** 5 hours
- **Phase 3 (ID Generation):** 2 hours
- **Phase 4 (Transfer Execution):** 7 hours
- **Phase 5 (Verification):** 3 hours
- **Phase 6 (CLI & UI):** 6 hours
- **Phase 7 (Integration & Docs):** 4 hours
- **Phase 8 (Testing & QA):** 8 hours

**Total:** ~47.5 hours (~6 working days)

### Priority Order
1. **Phase 0** — Shared utilities (enables other work)
2. **Phase 1** — Data fetching (foundation)
3. **Phase 2** — Selection logic (core feature)
4. **Phase 3** — ID generation (reuses existing code)
5. **Phase 4** — Transfer execution (critical path)
6. **Phase 5** — Verification (quality assurance)
7. **Phase 6** — CLI (user interface)
8. **Phase 7** — Documentation (usability)
9. **Phase 8** — Testing (reliability)

### Critical Path
```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
```

All other phases can be done in parallel or deferred.
