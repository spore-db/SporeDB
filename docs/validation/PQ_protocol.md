# Performance Qualification Protocol

## SporeDB Self-Hosted Deployment

| Field | Value |
|-------|-------|
| **Document ID** | PQ-SPOREDB-001 |
| **Version** | 1.0 |
| **System** | SporeDB v0.1.0 |
| **Effective Date** | _________________ |
| **Prepared By** | _________________ |
| **Reviewed By** | _________________ |
| **Approved By** | _________________ |

---

## 1. Purpose

This Performance Qualification (PQ) protocol verifies that SporeDB performs reliably under production-like conditions with representative data volumes, concurrent user loads, and end-to-end bioprocess workflows. Successful execution of this protocol confirms that the system is suitable for routine use in a GxP-regulated environment.

This protocol should be executed only after successful completion of:

- Installation Qualification (IQ-SPOREDB-001)
- Operational Qualification (OQ-SPOREDB-001)

## 2. Scope

This PQ protocol covers:

- End-to-end bioprocess data workflows (CSV import through phase detection and alignment)
- Multi-user concurrent access with RBAC role enforcement
- Large dataset handling and query performance
- Audit trail integrity under sustained write loads
- Data export fidelity and round-trip verification
- Backup and restore procedures with data integrity verification

### Out of Scope

- Unit-level testing of individual functions (covered in automated test suite)
- Feature-level testing of individual compliance controls (covered in OQ)
- Network security and penetration testing
- Disaster recovery for infrastructure-level failures (e.g., hardware failure)

## 3. Test Environment

### 3.1 Environment Specification

| Component | Specification |
|-----------|--------------|
| **Deployment** | Self-hosted per IQ-SPOREDB-001 |
| **Hardware** | Per IQ Section 4 hardware requirements |
| **SporeDB Version** | v0.1.0 (as installed during IQ) |
| **Network** | Production-equivalent LAN configuration |

### 3.2 Test Data Requirements

| Dataset | Description | Minimum Size |
|---------|-------------|-------------|
| Fermentation CSV files | Real or representative bioreactor time-series data (DO, pH, temperature, OD, biomass) | 10 files, 50K--500K rows each |
| Large batch dataset | Single batch with dense time-series telemetry | 1M+ telemetry data points |
| Offline assay data | LC-MS/HPLC results with timestamps, values, and uncertainties | 100+ assay measurements across 5+ batches |
| User accounts | Test accounts with different RBAC roles | 5+ accounts (2 admin, 2 editor, 1 viewer) |

### 3.3 Test Duration

| Phase | Duration | Activities |
|-------|----------|-----------|
| Day 1 | Setup | Prepare test data, create user accounts, document baseline system state |
| Day 2--3 | Execution | Execute PQ test cases, record results, document any deviations |
| Day 4 | Stress test | Run concurrent access and large dataset tests |
| Day 5 | Review | Complete documentation, resolve deviations, prepare final report |

## 4. End-User Process Tests

### PQ-001: Full Bioprocess Data Workflow

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-001 |
| **Description** | Verify the complete end-to-end workflow: CSV import, batch creation, automatic phase detection, and cross-run alignment. This represents the primary scientist use case. |
| **Preconditions** | 3+ fermentation CSV files with overlapping time-series variables (DO, pH, temperature). At least 50K rows each. |
| **Procedure** | 1. Import first CSV file via SDK: `sporedb.import_csv("run_001.csv", batch_name="Batch-PQ-001")` <br> 2. Record import time (wall clock). <br> 3. Verify batch is created with correct metadata. <br> 4. Run phase detection: `sporedb.detect_phases("Batch-PQ-001")` <br> 5. Record phase detection time. <br> 6. Verify at least 3 phases detected (lag, exponential, stationary). <br> 7. Import 2 additional CSV files as separate batches. <br> 8. Run cross-run alignment: `sporedb.align(["Batch-PQ-001", "Batch-PQ-002", "Batch-PQ-003"], by="phase")` <br> 9. Record alignment time. <br> 10. Verify aligned data is accessible and phase boundaries are consistent. |
| **Expected Result** | All imports succeed. Phase detection identifies biologically meaningful phases. Alignment produces time-normalized data for all three runs. Total workflow time < 60 seconds for 50K-row files. |
| **Actual Result** | _________________ |
| **Timings** | Import: ____s, Phase detection: ____s, Alignment: ____s |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### PQ-002: Multi-User Concurrent Access with RBAC

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-002 |
| **Description** | Verify that 3+ users with different RBAC roles can operate the system simultaneously without interference, and that role-based access controls are enforced under concurrent conditions. |
| **Preconditions** | 3+ user accounts created (admin, editor, viewer roles). Test batches created during PQ-001. |
| **Procedure** | 1. **User A (Admin):** Create a new batch and import data simultaneously with User B and C operations. <br> 2. **User B (Editor):** Modify batch metadata on an existing batch. <br> 3. **User C (Viewer):** Query and export batch data. <br> 4. All three operations run concurrently (within 10-second window). <br> 5. Verify User C (Viewer) cannot modify data: attempt a write operation and confirm rejection (403). <br> 6. Verify all operations complete without deadlock or data corruption. <br> 7. Verify audit trail captures all three users' actions with correct timestamps and user IDs. |
| **Expected Result** | All concurrent operations complete successfully. Viewer write attempts are rejected. Audit trail shows 3 distinct user IDs with correct chronological ordering. No data corruption or deadlocks. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### PQ-003: Large Dataset Handling

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-003 |
| **Description** | Verify that SporeDB handles a batch with 1M+ telemetry data points and that queries complete within acceptable performance thresholds. |
| **Preconditions** | CSV file with 1M+ rows of time-series data (or generate synthetic data matching bioreactor telemetry patterns). |
| **Procedure** | 1. Import the large CSV: `sporedb.import_csv("large_batch.csv", batch_name="Batch-PQ-Large")` <br> 2. Record import time. <br> 3. Run a time-range query selecting 10% of the data: `sporedb.query("SELECT * FROM 'Batch-PQ-Large' WHERE time > '2025-01-01' AND time < '2025-01-04'")` <br> 4. Record query time. <br> 5. Run phase detection on the large batch. <br> 6. Record phase detection time. <br> 7. Run an aggregation query: `sporedb.query("SELECT avg(dissolved_oxygen), max(ph) FROM 'Batch-PQ-Large' GROUP BY phase")` <br> 8. Record aggregation query time. |
| **Expected Result** | Import completes (time recorded for baseline). Time-range query completes in < 5 seconds. Aggregation query completes in < 5 seconds. Phase detection completes (time recorded for baseline). |
| **Actual Result** | _________________ |
| **Timings** | Import: ____s, Range query: ____s, Phase detection: ____s, Aggregation: ____s |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### PQ-004: Audit Trail Under Sustained Load

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-004 |
| **Description** | Verify that the audit trail maintains hash chain integrity and Ed25519 signature validity after 100+ sequential write operations. |
| **Preconditions** | System running with audit trail enabled (verified in IQ-008). |
| **Procedure** | 1. Perform 100+ sequential data-modifying operations (batch creation, metadata updates, data imports). <br> 2. Record the time to complete all operations. <br> 3. Export the full audit trail: `sporedb audit export --format parquet --output audit_pq004.parquet` <br> 4. Run compliance validation: `sporedb compliance validate --regulation all` <br> 5. Verify hash chain integrity: all entries linked correctly via SHA-256 previous_entry_hash. <br> 6. Verify Ed25519 signatures: all entries have valid signatures. <br> 7. Verify Merkle tree checkpoint consistency. <br> 8. Count total audit entries and verify count >= 100. |
| **Expected Result** | All 100+ operations complete without error. Hash chain is intact (no broken links). All signatures verify successfully. Merkle checkpoint is consistent. Compliance validator reports PASS for all checks. |
| **Actual Result** | _________________ |
| **Audit entry count** | _____ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### PQ-005: Data Export Fidelity

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-005 |
| **Description** | Verify data export and re-import round-trip fidelity. Exported data must match the original source data bit-for-bit (within floating-point representation limits). |
| **Preconditions** | Batch imported during PQ-001 with known source CSV. |
| **Procedure** | 1. Export batch data to CSV: `sporedb export csv "Batch-PQ-001" --output exported_pq005.csv` <br> 2. Compute SHA-256 checksum of the original source CSV (data columns only, excluding headers if format differs): `sha256sum run_001.csv` <br> 3. Compute SHA-256 checksum of the exported CSV (data columns only): `sha256sum exported_pq005.csv` <br> 4. If checksums differ due to formatting (column order, timestamp format), perform column-by-column numerical comparison using pandas: load both DataFrames, sort by timestamp, compare with `pandas.testing.assert_frame_equal(check_dtype=False, atol=1e-10)`. <br> 5. Re-import the exported CSV: `sporedb.import_csv("exported_pq005.csv", batch_name="Batch-PQ-Reimport")` <br> 6. Compare re-imported batch data with original batch data. |
| **Expected Result** | All numerical values match within floating-point tolerance (atol=1e-10). All timestamps match exactly. All metadata fields match. Re-imported batch is identical to original. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### PQ-006: Backup and Restore

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-006 |
| **Description** | Verify that a full system backup (PostgreSQL + MinIO) can be restored to a fresh SporeDB instance with complete data integrity. |
| **Preconditions** | System has data from PQ-001 through PQ-005. At least 3 batches with telemetry data and a populated audit trail. |
| **Procedure** | 1. Record current state: count of batches, total telemetry points, audit trail entry count, last Merkle root hash. <br> 2. Perform PostgreSQL backup: `docker compose exec postgres pg_dump -U sporedb sporedb > backup_pq006.sql` <br> 3. Perform MinIO backup: copy the MinIO data volume or use `mc mirror` to export all objects. <br> 4. Stop the current deployment: `docker compose down -v` (destroy volumes). <br> 5. Start a fresh deployment: `docker compose -f docker-compose.yml -f docker-compose.selfhosted.yml up -d` <br> 6. Restore PostgreSQL: `cat backup_pq006.sql \| docker compose exec -T postgres psql -U sporedb sporedb` <br> 7. Restore MinIO data (copy volume or `mc mirror` back). <br> 8. Verify: count batches, total telemetry points, audit trail entries. <br> 9. Run compliance validation: `sporedb compliance validate --regulation all` <br> 10. Compare all counts and Merkle root hash with pre-backup values. |
| **Expected Result** | All batch counts match pre-backup state. All telemetry point counts match. Audit trail entry count matches. Merkle root hash matches. Compliance validation passes. |
| **Actual Result** | _________________ |
| **Pre-backup counts** | Batches: _____, Telemetry points: _____, Audit entries: _____ |
| **Post-restore counts** | Batches: _____, Telemetry points: _____, Audit entries: _____ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### PQ-007: System Stability Over Extended Operation

| Field | Value |
|-------|-------|
| **Test Case ID** | PQ-007 |
| **Description** | Verify system stability over an extended operation period (minimum 24 hours of continuous availability). |
| **Preconditions** | System deployed and operational with data from previous PQ tests. |
| **Procedure** | 1. Record system start time and resource utilization (CPU, RAM, disk). <br> 2. Schedule periodic health checks every 15 minutes for 24 hours: `curl http://localhost:8000/health` <br> 3. During the 24-hour period, perform occasional data operations (imports, queries) to simulate low-level production use. <br> 4. After 24 hours, record resource utilization. <br> 5. Verify no container restarts: `docker compose ps` (check restart count). <br> 6. Verify audit trail integrity: `sporedb compliance validate --regulation all` |
| **Expected Result** | All health checks return 200. No container restarts. Memory usage does not grow unboundedly (no memory leaks). Audit trail integrity maintained. |
| **Actual Result** | _________________ |
| **Health check failures** | _____ / _____ (failed / total) |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

## 5. Acceptance Criteria

All quantitative acceptance criteria must be met for PQ approval.

| Metric | Threshold | Test Case | Result | Pass/Fail |
|--------|-----------|-----------|--------|-----------|
| CSV import (50K rows) | < 30 seconds | PQ-001 | _____ | _____ |
| Phase detection (50K rows) | < 30 seconds | PQ-001 | _____ | _____ |
| Time-range query (1M rows, 10% selection) | < 5 seconds | PQ-003 | _____ | _____ |
| Aggregation query (1M rows) | < 5 seconds | PQ-003 | _____ | _____ |
| API response time (95th percentile) | < 2 seconds | PQ-001 through PQ-006 | _____ | _____ |
| Data integrity (export/re-import fidelity) | 100% match | PQ-005 | _____ | _____ |
| Audit trail integrity | Zero gaps, all signatures valid | PQ-004 | _____ | _____ |
| Concurrent user operations | Zero deadlocks, zero data corruption | PQ-002 | _____ | _____ |
| Backup/restore data fidelity | 100% match (counts + Merkle root) | PQ-006 | _____ | _____ |
| System stability (24h uptime) | Zero unplanned restarts | PQ-007 | _____ | _____ |

## 6. Deviations

Record any deviations from expected results during PQ execution. All deviations must be documented, assessed for impact, and resolved.

| Deviation # | Test Case | Description | Impact Assessment | Resolution | Resolved By | Date |
|-------------|-----------|-------------|-------------------|------------|-------------|------|
| | | | | | | |
| | | | | | | |
| | | | | | | |

## 7. Summary of Results

| Category | Count |
|----------|-------|
| Total Test Cases | 7 |
| Passed | _____ |
| Failed | _____ |
| Acceptance Criteria Met | _____ / 10 |
| Deviations Recorded | _____ |
| Deviations Resolved | _____ |

## 8. Conclusion

Based on the results documented in this protocol:

- [ ] All PQ tests PASSED and all acceptance criteria MET -- the system is qualified for production use in a GxP-regulated environment.
- [ ] One or more tests FAILED but deviations have been resolved -- the system is qualified for production use upon deviation closure and re-test confirmation.
- [ ] One or more acceptance criteria NOT MET -- the system requires remediation before production deployment. Root cause analysis and corrective actions are required.

**Comments:**

_________________________________________________________________________________

_________________________________________________________________________________

## 9. Approval Signatures

By signing below, I confirm that I have reviewed the results of this Performance Qualification protocol and that the conclusions are accurate and supported by the documented evidence.

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **QA Reviewer** | _________________ | _________________ | _________________ |
| **System Administrator** | _________________ | _________________ | _________________ |
| **Quality Head** | _________________ | _________________ | _________________ |

---

## Appendix A: Reference Documents

| Document | ID | Description |
|----------|-----|-------------|
| IQ Protocol | IQ-SPOREDB-001 | Installation Qualification protocol for SporeDB |
| OQ Protocol | OQ-SPOREDB-001 | Operational Qualification protocol for SporeDB |
| Traceability Matrix | RTM-SPOREDB-001 | Requirements Traceability Matrix |
| Deployment SOP | _(site-specific)_ | Standard operating procedure for SporeDB deployment |
| Backup SOP | _(site-specific)_ | Standard operating procedure for backup and restore |

## Appendix B: Test Data Inventory

Record all test data files used during PQ execution.

| File Name | Description | Row Count | SHA-256 Checksum |
|-----------|-------------|-----------|-----------------|
| | | | |
| | | | |
| | | | |

## Appendix C: Version History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | _________________ | _________________ | Initial PQ protocol |
