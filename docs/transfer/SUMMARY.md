# OU Transfer App — Implementation Summary

**Status:** Documentation Complete, Ready for Development  
**Created:** April 7, 2026  
**Estimated Implementation Time:** ~47.5 hours (~6 working days)

---

## What We've Created

### 1. Comprehensive Overview Document
**File:** `docs/transfer/overview.md`

**Covers:**
- Problem statement (CPWs registering at wrong OU level)
- Complete data flow diagram
- Five-step processing pipeline (Fetch → Select → Re-ID → Transfer → Verify)
- Relationship preservation algorithm
- ID regeneration strategy
- POST-based API approach for audit preservation
- Safety features and verification
- Performance expectations
- Technical considerations

**Key Decisions Documented:**
- ✅ **Selection logic:** User selects what to KEEP (not what to move)
- ✅ **Relationship preservation:** Households and children always transfer together
- ✅ **API method:** Use POST (not PUT) to preserve `createdBy` metadata
- ✅ **ID collision prevention:** Query destination OU for max sequences first

---

### 2. Detailed Task Breakdown
**File:** `docs/transfer/tasks.md`

**Organized into 8 phases:**

#### Phase 0: Shared Utilities Extraction (5 hours)
- Extract OU picker from Phase 2 → `src/shared/ou_picker.py`
- Extract ID generation logic → `src/shared/id_utils.py`
- Create shared DHIS2 API client → `src/shared/dhis2_client.py`

#### Phase 1: Data Fetching & Relationship Resolution (7.5 hours)
- TEI fetcher with enrollment year filtering
- Relationship graph builder
- Transfer set resolver (keeps relationships intact)

#### Phase 2: Selection & Preview (5 hours)
- CSV-based selection interface
- Auto-select by enrollment date
- Transfer preview generator

#### Phase 3: ID Generation (2 hours)
- Reuse shared ID generation logic
- Collision detection at destination OU

#### Phase 4: Transfer Execution (7 hours)
- POST-based API client
- Transfer engine with progress tracking
- Rollback capability

#### Phase 5: Verification (3 hours)
- TEI existence check
- ID correctness verification
- Relationship integrity validation

#### Phase 6: CLI & User Interface (6 hours)
- Interactive workflow
- Direct commands for advanced users

#### Phase 7: Integration & Documentation (4 hours)
- Update justfile
- Update main README
- Create user guide

#### Phase 8: Testing & QA (8 hours)
- Unit tests for core logic
- Integration tests on staging

---

### 3. Updated Main README
**File:** `README.md`

**Changes:**
- Added OU Transfer to apps table
- Created dedicated OU Transfer section with:
  - Background explanation
  - How It Works workflow
  - Typical usage example
  - Key features list
- Updated table of contents
- Added link to detailed documentation

---

## Key Technical Insights

### 1. Relationship Preservation Algorithm
```python
def resolve_transfer_set(selected_to_keep, all_teis):
    """
    Given TEIs selected to KEEP, determine which TEIs must be TRANSFERRED.
    Ensures household-child relationships remain intact.
    """
    keep_set = set(selected_to_keep)
    
    # Expand keep_set to include related TEIs
    for tei in selected_to_keep:
        if tei.type == "Child":
            keep_set.add(tei.household)  # Keep the child's household
        elif tei.type == "Household":
            keep_set.update(tei.children)  # Keep all children
    
    # Everything not in keep_set is transferred
    transfer_set = all_teis - keep_set
    
    # Expand transfer_set to include related TEIs
    for tei in transfer_set:
        if tei.type == "Child":
            if tei.household not in keep_set:
                transfer_set.add(tei.household)
        elif tei.type == "Household":
            transfer_set.update([c for c in tei.children if c not in keep_set])
    
    return transfer_set
```

### 2. POST vs PUT for Audit Preservation
**DHIS2 API Behavior:**
- `PUT /api/trackedEntityInstances/{uid}` → **overwrites** `lastUpdatedBy`
- `POST /api/trackedEntityInstances/{uid}` → **preserves** `createdBy`, updates `lastUpdatedBy`

**Our Approach:**
- Use `POST` for all TEI updates
- `createdBy` remains unchanged (original CPW)
- `lastUpdatedBy` reflects the transfer operation (expected and acceptable)

### 3. ID Generation Strategy
**Reuses Cleanup Phase 2 logic:**
1. Extract destination OU code (e.g., `ZA_CHIK`)
2. Query destination OU for existing TEIs
3. Find max sequence number for Household IDs
4. Find max sequence number for Child UICs
5. Generate new IDs starting from `max + 1`

**Example:**
```
Destination OU: ZA_CHIK
Existing max: ZA_CHIK_HH_00000122

Transferring 3 households:
ZA_CHIK_HH_00000123
ZA_CHIK_HH_00000124
ZA_CHIK_HH_00000125
```

### 4. Entities to Transfer
**Complete transfer includes:**
- ✅ Tracked Entity Instances (TEIs) — `orgUnit` updated
- ✅ Program Enrollments — `orgUnit` updated
- ✅ Events — `orgUnit` updated
- ✅ Relationships — preserved (UID-based, not OU-specific)
- ✅ Attribute Values — preserved except Household ID / Child UIC (regenerated)

---

## Code Reuse Strategy

### From Cleanup Phase 2
**Extract to `src/shared/`:**
- OU picker (interactive org unit selection)
- ID generation logic (sequence numbering)
- DHIS2 API client (common operations)

**Benefits:**
- Reduces duplication
- Ensures consistency across apps
- Makes Phase 2 code more modular
- Enables future apps to reuse utilities

### From Sync Rescue
**Reuse directly:**
- Verification logic pattern
- Progress tracking utilities
- CSV handling functions

---

## Next Steps for Development

### Immediate (Start Here)
1. **Phase 0.1:** Extract OU picker to `src/shared/ou_picker.py`
2. **Phase 0.2:** Extract ID generation to `src/shared/id_utils.py`
3. **Phase 0.3:** Create shared DHIS2 client `src/shared/dhis2_client.py`

### Then Build Core Features
4. **Phase 1:** Implement TEI fetcher and relationship resolver
5. **Phase 2:** Implement selection logic and preview generator
6. **Phase 3:** Implement ID generator (reusing shared utilities)
7. **Phase 4:** Implement transfer engine with POST-based updates

### Finally Polish & Test
8. **Phase 5:** Implement verification
9. **Phase 6:** Build interactive CLI
10. **Phase 7:** Update documentation and justfile
11. **Phase 8:** Test on staging environment

---

## Critical Success Factors

### Must Have
- ✅ Relationship integrity preserved (no orphaned children/households)
- ✅ ID collision prevention (no duplicate IDs at destination)
- ✅ Audit trail preservation (`createdBy` unchanged)
- ✅ Comprehensive verification (confirm everything transferred correctly)

### Should Have
- ✅ Progress tracking (user knows what's happening)
- ✅ Error handling (graceful failures, clear messages)
- ✅ Rollback capability (undo if something goes wrong)
- ✅ Preview mode (see what will happen before executing)

### Nice to Have
- ⭕ Batch transfers (multiple source OUs at once)
- ⭕ Advanced filtering (beyond enrollment year)
- ⭕ Transfer history tracking (audit log of all transfers)
- ⭕ Automatic undo command

---

## Risks & Mitigations

### Risk 1: Audit Trail Not Preserved
**Mitigation:** Test POST method on staging first. If it fails, document the limitation and accept that `lastUpdatedBy` will change.

### Risk 2: Relationship Graph Too Complex
**Mitigation:** Start with simple cases (1 household → N children). Add support for edge cases incrementally.

### Risk 3: ID Collisions at Destination
**Mitigation:** Always query destination OU for max sequences before generating new IDs. Add verification step to catch collisions.

### Risk 4: Partial Transfer Failures
**Mitigation:** Transfer TEIs one at a time (atomic operations). Log all failures. Provide rollback capability.

---

## Performance Targets

| Operation | Target Speed | Notes |
|-----------|-------------|-------|
| Fetch TEIs | ~100 TEIs/sec | DHIS2 API query |
| Relationship resolution | Instant | In-memory graph |
| ID generation | Instant | Simple sequence increment |
| Transfer (API) | ~5-10 TEIs/sec | DHIS2 API rate limits |
| Verification | ~50 TEIs/sec | DHIS2 API queries |

**Example:** Transferring 100 TEIs should take ~2-3 minutes (fetch + transfer + verify)

---

## Documentation Deliverables

### Completed ✅
- [x] Overview document (`docs/transfer/overview.md`)
- [x] Task breakdown (`docs/transfer/tasks.md`)
- [x] Main README updated
- [x] Summary document (this file)

### Pending ⏳
- [ ] User guide with examples (`docs/transfer/user-guide.md`)
- [ ] API documentation for shared utilities
- [ ] Troubleshooting guide
- [ ] FAQ section

---

## Git Commits

### Commit 1: Documentation
```
commit b5c25b9
Add OU Transfer App documentation

- Create comprehensive overview document
- Create detailed task breakdown
- Update main README with OU Transfer section
- Document relationship preservation logic
- Document ID regeneration strategy
- Document POST-based API updates
- Outline shared utilities extraction plan
- Estimate ~47.5 hours total implementation
```

---

## Questions Answered

### Q: How do we determine which child belongs to which household?
**A:** Use DHIS2 relationships API. Query `/api/relationships?tei={uid}` to get all relationships for a TEI. Build a graph mapping children to households.

### Q: How do we preserve `createdBy` during transfer?
**A:** Use `POST` (not `PUT`) when updating TEIs. DHIS2 preserves `createdBy` with POST requests.

### Q: What if user selects children but not their household?
**A:** The relationship resolver automatically expands the selection to include related TEIs. If a child is kept, their household is kept. If a household is transferred, all their children are transferred.

### Q: How do we prevent ID collisions at destination?
**A:** Before generating new IDs, query the destination OU for existing TEIs and find the max sequence number. Start new IDs from `max + 1`.

### Q: What if the transfer fails halfway?
**A:** Each TEI transfer is atomic. If one fails, others continue. Failed transfers are logged. Rollback capability allows moving TEIs back to source if needed.

---

## Ready to Start Development

All planning and documentation is complete. The implementation can now begin with **Phase 0: Shared Utilities Extraction**.

Refer to `docs/transfer/tasks.md` for detailed task-by-task implementation guidance.
