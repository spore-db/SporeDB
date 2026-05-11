# Operational Qualification Protocol

## SporeDB Self-Hosted Deployment

| Field | Value |
|-------|-------|
| **Document ID** | OQ-SPOREDB-001 |
| **Version** | 1.0 |
| **System** | SporeDB v0.1.0 |
| **Effective Date** | _________________ |
| **Prepared By** | _________________ |
| **Reviewed By** | _________________ |
| **Approved By** | _________________ |

---

## 1. Purpose

This Operational Qualification (OQ) protocol verifies that SporeDB functions correctly per its design specifications across all compliance-relevant features. Successful execution confirms that audit trail integrity, role-based access control, electronic signatures, data integrity, and batch management all operate as intended.

This protocol tests compliance with:

- FDA 21 CFR Part 11 -- Electronic Records; Electronic Signatures
- EU Annex 11 -- Computerised Systems (including 2025 draft provisions)
- GAMP 5 guidelines for computerized system validation

This protocol should be executed only after successful completion of Installation Qualification (IQ-SPOREDB-001).

## 2. Scope

This OQ protocol covers functional verification of:

- **Audit trail** -- Ed25519 signing, SHA-256 hash chain, Merkle tree checkpoints, tamper detection
- **Role-Based Access Control (RBAC)** -- Admin, Editor, and Viewer role enforcement
- **Electronic signatures** -- Re-authentication, signer identity, record linking
- **Data integrity** -- Import fidelity, timestamp normalization, unit conversions, metadata persistence
- **Batch management** -- Create, search/filter, delete cascade operations
- **21 CFR Part 11 compliance** -- All applicable sections (11.10 a-k, 11.50, 11.70, 11.100, 11.200)
- **EU Annex 11 compliance** -- Data storage, audit trail, e-signatures, access control, data integrity
- **Boundary and negative tests** -- Invalid inputs, concurrent writes, error handling

### Out of Scope

- Performance under production-level loads (covered in PQ-SPOREDB-001)
- Installation verification (covered in IQ-SPOREDB-001)
- Network penetration testing and external security assessment

## 3. Test Environment

| Component | Specification |
|-----------|--------------|
| **Deployment** | Self-hosted per IQ-SPOREDB-001 (all IQ tests passed) |
| **SporeDB Version** | v0.1.0 |
| **Test Users** | Admin (oq-admin), Editor (oq-editor), Viewer (oq-viewer) |
| **Test Data** | 3 fermentation CSV files (10K-50K rows), sample metadata records |
| **Access** | CLI (`sporedb` command), HTTP API (curl/httpx), Python SDK |

---

## 4. Functional Test Cases by Feature Area

### 4.1 Audit Trail Tests

#### OQ-001: Data Write Produces Signed Audit Entry

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-001 |
| **Description** | Verify that every data write operation produces a cryptographically signed audit trail entry with an Ed25519 signature. |
| **Procedure** | 1. Authenticate as oq-editor user. <br> 2. Create a new batch: `sporedb batch create "OQ-Test-Batch-001" --organism "E. coli" --reactor "BR-01"` <br> 3. Query the audit trail for the most recent entry: `sporedb audit list --limit 1` <br> 4. Verify the entry contains: entry_id (UUIDv7), timestamp (UTC), user_id (oq-editor), action (create), entity_type (batch), signature (non-empty bytes), public_key_pem (non-empty). <br> 5. Verify the Ed25519 signature: `sporedb audit verify --entry-id <entry_id>` |
| **Expected Result** | Audit entry is created with all required fields. Ed25519 signature is valid and verifiable with the system public key. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-002: SHA-256 Hash Chain Integrity

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-002 |
| **Description** | Verify that the SHA-256 hash chain links consecutive audit entries correctly. |
| **Procedure** | 1. Perform 10 sequential write operations (batch create, metadata update, data import, etc.). <br> 2. Export the audit trail: `sporedb audit export --format json --output oq002_trail.json` <br> 3. For each entry after the first, verify that `previous_entry_hash` equals the SHA-256 hash of the preceding entry. <br> 4. Verify the first entry has an empty `previous_entry_hash`. <br> 5. Alternatively, run: `sporedb compliance validate --check hash_chain` |
| **Expected Result** | All 10 entries are linked. First entry has empty previous_entry_hash. Each subsequent entry's previous_entry_hash matches the computed hash of the prior entry. Compliance validator reports PASS for hash_chain check. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-003: Merkle Tree Checkpoint Verification

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-003 |
| **Description** | Verify that after N audit entries, a Merkle tree checkpoint is created and the Merkle root can be verified against the entries. |
| **Procedure** | 1. Ensure at least 10 audit entries exist (from OQ-001 and OQ-002). <br> 2. Trigger a Merkle checkpoint: `sporedb compliance checkpoint` <br> 3. Retrieve the Merkle root hash. <br> 4. Run: `sporedb compliance validate --check merkle` <br> 5. Verify the Merkle tree leaf count matches the number of audit entries. |
| **Expected Result** | Merkle checkpoint is created. Merkle root hash is non-empty. Leaf count equals entry count. Compliance validator reports PASS for merkle check. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-004: Audit Trail Export Completeness

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-004 |
| **Description** | Verify that the audit trail can be exported in its entirety and that the export contains all entries. |
| **Procedure** | 1. Count current audit entries: `sporedb audit list --count` <br> 2. Export to Parquet: `sporedb audit export --format parquet --output oq004_full_trail.parquet` <br> 3. Export to JSON: `sporedb audit export --format json --output oq004_full_trail.json` <br> 4. Count entries in each export file. <br> 5. Verify export counts match the live count from step 1. |
| **Expected Result** | Parquet and JSON exports both contain the exact number of entries matching the live count. No entries are missing or duplicated. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-005: Tamper Detection

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-005 |
| **Description** | Verify that the compliance validator detects when an audit trail entry has been tampered with (modified, deleted, or reordered). |
| **Procedure** | 1. Export the audit trail to a file. <br> 2. Copy the Parquet audit trail file: `cp data/audit/trail.parquet data/audit/trail_backup.parquet` <br> 3. Tamper with an entry: modify one byte of a hash or timestamp in the Parquet file using a hex editor or Python script. <br> 4. Run compliance validation: `sporedb compliance validate --regulation all` <br> 5. Verify the validator reports FAIL with details about the tampered entry. <br> 6. Restore the original file: `cp data/audit/trail_backup.parquet data/audit/trail.parquet` <br> 7. Re-run validation and confirm PASS. |
| **Expected Result** | Tampered file triggers a FAIL result with specific details (entry index, expected vs actual hash). Restored file triggers PASS. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

### 4.2 RBAC Tests

#### OQ-006: Admin User Management

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-006 |
| **Description** | Verify that an admin user can create, modify, and delete other user accounts. |
| **Procedure** | 1. Authenticate as oq-admin. <br> 2. Create a new user: `sporedb admin create-user --username oq-test-user --role editor --password <password>` <br> 3. Verify user exists: `sporedb admin list-users` <br> 4. Modify user role: `sporedb admin update-user --username oq-test-user --role viewer` <br> 5. Verify role changed: `sporedb admin get-user --username oq-test-user` <br> 6. Delete user: `sporedb admin delete-user --username oq-test-user` <br> 7. Verify user no longer exists: `sporedb admin list-users` |
| **Expected Result** | All CRUD operations succeed for admin. Created user appears in list. Role change is reflected. Deleted user no longer appears. Each operation produces an audit trail entry. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-007: Editor Batch Permissions

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-007 |
| **Description** | Verify that an editor user can create and modify batches but cannot manage users. |
| **Procedure** | 1. Authenticate as oq-editor. <br> 2. Create a batch: `sporedb batch create "OQ-Editor-Batch"` -- expect success. <br> 3. Update batch metadata: `sporedb batch update "OQ-Editor-Batch" --notes "Updated by editor"` -- expect success. <br> 4. Import data into batch: `sporedb import csv test_data.csv --batch "OQ-Editor-Batch"` -- expect success. <br> 5. Attempt to create a user: `sporedb admin create-user --username hacker --role admin --password <password>` -- expect rejection (403 Forbidden). <br> 6. Attempt to delete a user: `sporedb admin delete-user --username oq-viewer` -- expect rejection (403 Forbidden). |
| **Expected Result** | Batch operations succeed. User management operations are rejected with 403 status. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-008: Viewer Read-Only Access

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-008 |
| **Description** | Verify that a viewer user can read data but cannot modify any records. |
| **Procedure** | 1. Authenticate as oq-viewer. <br> 2. List batches: `sporedb batch list` -- expect success with results. <br> 3. Query batch data: `sporedb query "SELECT * FROM 'OQ-Test-Batch-001' LIMIT 10"` -- expect success. <br> 4. Export data: `sporedb export csv "OQ-Test-Batch-001" --output viewer_export.csv` -- expect success. <br> 5. Attempt to create a batch: `sporedb batch create "Viewer-Illegal-Batch"` -- expect rejection (403). <br> 6. Attempt to delete a batch: `sporedb batch delete "OQ-Test-Batch-001"` -- expect rejection (403). <br> 7. Attempt to import data: `sporedb import csv test_data.csv --batch "OQ-Test-Batch-001"` -- expect rejection (403). |
| **Expected Result** | Read operations succeed. All write/delete operations are rejected with 403 status. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-009: Unauthorized Access Denial

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-009 |
| **Description** | Verify that unauthenticated requests are denied with appropriate error responses. |
| **Procedure** | 1. Send API request without authentication token: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/batches` <br> 2. Send API request with an expired/invalid JWT token: `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer invalid-token" http://localhost:8000/api/batches` <br> 3. Send API request with a malformed Authorization header: `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: NotBearer abc" http://localhost:8000/api/batches` |
| **Expected Result** | All three requests return HTTP 401 (Unauthorized) or 403 (Forbidden). Response body contains an error message. No data is returned. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-010: Role Changes Take Effect Immediately

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-010 |
| **Description** | Verify that when a user's role is changed, the new permissions are enforced on the very next request without requiring re-login. |
| **Procedure** | 1. Authenticate as oq-admin. <br> 2. Create test user with editor role: `sporedb admin create-user --username oq-role-test --role editor --password <password>` <br> 3. Authenticate as oq-role-test and create a batch -- expect success. <br> 4. From oq-admin session, change oq-role-test to viewer: `sporedb admin update-user --username oq-role-test --role viewer` <br> 5. Using oq-role-test's existing session/token, attempt to create another batch -- expect rejection (403). <br> 6. Clean up: delete oq-role-test user. |
| **Expected Result** | Role change is enforced immediately. The user's next write operation is rejected after downgrade to viewer. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

### 4.3 Electronic Signature Tests

#### OQ-011: E-Signature Requires Re-Authentication

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-011 |
| **Description** | Verify that applying an electronic signature to a record requires the signer to re-enter their password (re-authentication) per 21 CFR Part 11 Section 11.200. |
| **Procedure** | 1. Authenticate as oq-editor. <br> 2. Create a batch and import data to produce a record. <br> 3. Attempt to sign the record without re-authentication (if API allows): `sporedb sign --batch "OQ-Sig-Test" --meaning "approved"` -- should prompt for password or reject. <br> 4. Sign with re-authentication: `sporedb sign --batch "OQ-Sig-Test" --meaning "approved" --password <correct-password>` -- expect success. <br> 5. Attempt to sign with incorrect password: `sporedb sign --batch "OQ-Sig-Test" --meaning "reviewed" --password wrong-password` -- expect rejection. |
| **Expected Result** | Signing without password is rejected. Signing with correct password succeeds. Signing with incorrect password is rejected. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-012: Signed Record Contains Required Manifestations

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-012 |
| **Description** | Verify that an electronic signature includes the signer's identity, the meaning of the signature, and a timestamp per 21 CFR Part 11 Section 11.50. |
| **Procedure** | 1. Sign a record as oq-editor with meaning "approved" (from OQ-011). <br> 2. Retrieve the signed record: `sporedb sign show --batch "OQ-Sig-Test"` <br> 3. Verify the signature record contains: signer_name (oq-editor's full name), signer_id (oq-editor), timestamp (UTC), meaning (one of: approved, reviewed, verified, released, rejected). |
| **Expected Result** | Signed record clearly displays: (a) printed name of the signer, (b) date and time of signing in UTC, (c) meaning associated with the signature (e.g., "approved"). |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-013: E-Signature Permanently Linked to Record

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-013 |
| **Description** | Verify that an electronic signature is cryptographically and permanently linked to the signed record and cannot be excised, copied, or transferred to a different record per 21 CFR Part 11 Section 11.70. |
| **Procedure** | 1. Sign a record as oq-editor (from OQ-011/OQ-012). <br> 2. Retrieve the signature and its cryptographic binding (record hash included in signed payload). <br> 3. Verify the signature JWT includes the record's content hash in its claims. <br> 4. Modify the record data (e.g., update batch metadata). <br> 5. Verify the original signature is now invalidated for the modified record: `sporedb sign verify --batch "OQ-Sig-Test"` -- should report signature mismatch or require re-signing. |
| **Expected Result** | Signature includes record hash. After record modification, the original signature does not validate against the new record state. Signature cannot be detached and reattached to a different record. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-014: Two-Component E-Signature

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-014 |
| **Description** | Verify that electronic signatures employ at least two distinct identification components (user ID + password) per 21 CFR Part 11 Section 11.200. |
| **Procedure** | 1. Attempt to sign with user ID only (no password): expect rejection. <br> 2. Attempt to sign with password only (no user ID / not authenticated): expect rejection. <br> 3. Sign with both user ID (authenticated session) + password (re-entry): expect success. <br> 4. Verify the signed record audit entry contains both components: user_id is recorded, and the signature creation required password re-verification. |
| **Expected Result** | Both identification components (user ID and password) are required for signing. Single-component attempts are rejected. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

### 4.4 Data Integrity Tests

#### OQ-015: Import Data Matches Source Bit-for-Bit

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-015 |
| **Description** | Verify that imported CSV data matches the source file with exact numerical precision. |
| **Procedure** | 1. Compute SHA-256 checksum of source CSV data columns: `sha256sum test_data.csv` <br> 2. Import: `sporedb import csv test_data.csv --batch "OQ-Integrity-Test"` <br> 3. Export the batch: `sporedb export csv "OQ-Integrity-Test" --output oq015_export.csv` <br> 4. Compare numerical values column by column using pandas: `pd.testing.assert_frame_equal(source_df, export_df, check_dtype=False, atol=1e-10)` <br> 5. Specifically verify: dissolved_oxygen, pH, temperature, biomass columns match to full float64 precision. |
| **Expected Result** | All numerical values match within floating-point tolerance (1e-10). No data loss or rounding beyond source precision. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-016: Timestamp Normalization to UTC

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-016 |
| **Description** | Verify that all timestamps are correctly normalized to UTC, regardless of the source timezone. |
| **Procedure** | 1. Prepare a CSV with timestamps in a non-UTC timezone (e.g., IST = UTC+5:30): `2025-01-15T10:00:00+05:30` <br> 2. Import the CSV: `sporedb import csv tz_test.csv --batch "OQ-TZ-Test"` <br> 3. Query the imported data and inspect the timestamp column. <br> 4. Verify: `2025-01-15T10:00:00+05:30` is stored as `2025-01-15T04:30:00Z` (UTC). <br> 5. Verify all exported timestamps include timezone indicator (Z suffix or +00:00). |
| **Expected Result** | All timestamps converted to UTC. No naive (timezone-unaware) timestamps stored. Time values are mathematically correct after conversion. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-017: Unit Conversion Accuracy

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-017 |
| **Description** | Verify that unit conversions during data import are numerically accurate. |
| **Procedure** | 1. Prepare a CSV with known unit values: biomass = 5.0 g/L, dissolved_oxygen = 40 % sat. <br> 2. Import with a mapping that converts g/L to mg/mL: `sporedb import csv units_test.csv --batch "OQ-Units-Test" --mapping units_mapping.yml` <br> 3. Query the imported value for biomass. <br> 4. Verify: 5.0 g/L = 5.0 mg/mL (1:1 conversion). <br> 5. Test a non-trivial conversion if configured (e.g., temperature Fahrenheit to Celsius): 98.6F = 37.0C. |
| **Expected Result** | Converted values match expected results to full float64 precision. No off-by-one or scaling errors. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-018: Batch Metadata Persistence Across Sessions

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-018 |
| **Description** | Verify that batch metadata persists correctly across application restarts. |
| **Procedure** | 1. Create a batch with full metadata: `sporedb batch create "OQ-Persist-Test" --organism "S. cerevisiae" --reactor "BR-05" --volume 50 --notes "OQ persistence test"` <br> 2. Record all metadata fields. <br> 3. Restart the SporeDB container: `docker compose restart sporedb` <br> 4. Wait for health check to pass. <br> 5. Retrieve the batch: `sporedb batch get "OQ-Persist-Test"` <br> 6. Compare all metadata fields with values from step 2. |
| **Expected Result** | All metadata fields match exactly after container restart. No data loss or truncation. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

### 4.5 Batch Management Tests

#### OQ-019: Create Batch with Full Metadata

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-019 |
| **Description** | Verify that a batch can be created with all supported metadata fields. |
| **Procedure** | 1. Create a batch with all fields: name, organism, reactor, volume, media, temperature setpoint, pH setpoint, inoculation time, notes. <br> 2. Retrieve the batch and verify all fields are stored correctly. <br> 3. Verify an audit trail entry was created for the batch creation. |
| **Expected Result** | Batch is created with all metadata fields populated. All values retrievable and matching input. Audit entry records the creation. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-020: Search and Filter Batches

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-020 |
| **Description** | Verify that batches can be searched and filtered by date range, organism, and other metadata fields. |
| **Procedure** | 1. Ensure at least 5 batches exist with varying organisms and creation dates. <br> 2. Filter by organism: `sporedb batch list --organism "E. coli"` -- expect only E. coli batches. <br> 3. Filter by date range: `sporedb batch list --after 2025-01-01 --before 2025-12-31` <br> 4. Filter by reactor: `sporedb batch list --reactor "BR-01"` <br> 5. Combine filters: `sporedb batch list --organism "E. coli" --reactor "BR-01"` |
| **Expected Result** | Each filter returns only matching batches. Combined filters apply AND logic. Empty result sets return cleanly (no errors). |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-021: Delete Batch Cascades

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-021 |
| **Description** | Verify that deleting a batch also removes associated telemetry data, and that the deletion is recorded in the audit trail. |
| **Procedure** | 1. Create a test batch and import telemetry data. <br> 2. Record the batch ID and telemetry row count. <br> 3. Delete the batch: `sporedb batch delete "OQ-Delete-Test" --confirm` <br> 4. Verify batch is no longer listed: `sporedb batch list` <br> 5. Verify telemetry data is removed (query returns empty or error). <br> 6. Verify audit trail contains a "delete" entry for the batch. <br> 7. Verify the audit trail entries for the deleted batch's creation and data imports are NOT deleted (audit trail is immutable). |
| **Expected Result** | Batch and telemetry data are removed. Audit trail records the deletion. Historical audit entries (creation, imports) for the batch remain intact. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

## 5. 21 CFR Part 11 Specific Tests

These test cases map directly to specific sections of FDA 21 CFR Part 11.

#### OQ-CFR-001: 11.10(a) -- System Validation

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-001 |
| **Regulation** | 21 CFR Part 11, Section 11.10(a) |
| **Requirement** | Validation of systems to ensure accuracy, reliability, consistent intended performance, and the ability to discern invalid or altered records. |
| **Description** | Verify that the IQ/OQ/PQ execution itself constitutes system validation evidence. |
| **Procedure** | 1. Confirm IQ protocol (IQ-SPOREDB-001) has been executed and approved. <br> 2. Confirm this OQ protocol is being executed per procedure. <br> 3. Confirm PQ protocol (PQ-SPOREDB-001) is planned for execution after OQ. <br> 4. Verify all test results are documented with tester identity, date, and pass/fail. <br> 5. Verify the RTM (RTM-SPOREDB-001) links this requirement to validation evidence. |
| **Expected Result** | IQ/OQ/PQ execution provides documented validation evidence. All results are traceable via RTM. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-002: 11.10(b) -- Accurate and Complete Copies

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-002 |
| **Regulation** | 21 CFR Part 11, Section 11.10(b) |
| **Requirement** | The ability to generate accurate and complete copies of records in both human-readable and electronic form suitable for inspection. |
| **Description** | Verify that batch data and audit trail can be exported in human-readable (CSV, JSON) and electronic (Parquet) formats with full fidelity. |
| **Procedure** | 1. Export a batch to CSV: `sporedb export csv "OQ-Test-Batch-001" --output oq_cfr002.csv` <br> 2. Export the same batch to Parquet: `sporedb export parquet "OQ-Test-Batch-001" --output oq_cfr002.parquet` <br> 3. Export the audit trail to JSON: `sporedb audit export --format json --output oq_cfr002_audit.json` <br> 4. Verify CSV is human-readable (open in text editor). <br> 5. Verify Parquet contains identical data to CSV (load both, compare). <br> 6. Verify JSON audit trail is human-readable and contains all entries. |
| **Expected Result** | All export formats contain complete, accurate data. CSV and JSON are human-readable. Parquet contains bit-identical numerical data. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-003: 11.10(c) -- Record Protection

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-003 |
| **Regulation** | 21 CFR Part 11, Section 11.10(c) |
| **Requirement** | Protection of records to enable their accurate and ready retrieval throughout the records retention period. |
| **Description** | Verify that data survives container restarts and that Parquet files on MinIO remain accessible. |
| **Procedure** | 1. Create a batch and import data. Record batch ID and row count. <br> 2. Restart all containers: `docker compose restart` <br> 3. Wait for all health checks to pass. <br> 4. Retrieve the batch and verify data is intact. <br> 5. Verify audit trail entries from before restart are still present. <br> 6. Verify MinIO objects are present: `mc ls local/sporedb-data/` |
| **Expected Result** | All data survives restart. Batch data, metadata, and audit trail are fully retrievable. MinIO objects are intact. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-004: 11.10(d) -- Limiting System Access

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-004 |
| **Regulation** | 21 CFR Part 11, Section 11.10(d) |
| **Requirement** | Limiting system access to authorized individuals. |
| **Description** | Verify RBAC enforcement restricts access by role. Cross-references OQ-006 through OQ-010. |
| **Procedure** | 1. Verify test results of OQ-006 (admin operations). <br> 2. Verify test results of OQ-007 (editor restrictions). <br> 3. Verify test results of OQ-008 (viewer read-only). <br> 4. Verify test results of OQ-009 (unauthenticated denial). <br> 5. Verify test results of OQ-010 (immediate role change enforcement). |
| **Expected Result** | All referenced RBAC test cases (OQ-006 through OQ-010) passed. System access is limited to authorized individuals based on assigned roles. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-005: 11.10(e) -- Audit Trails

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-005 |
| **Regulation** | 21 CFR Part 11, Section 11.10(e) |
| **Requirement** | Use of secure, computer-generated, time-stamped audit trails to independently record the date and time of operator entries and actions. Audit trail documentation must be retained for a period at least as long as required for the subject electronic records. |
| **Description** | Verify tamper-evident audit trail with cryptographic integrity. Cross-references OQ-001 through OQ-005. |
| **Procedure** | 1. Verify test results of OQ-001 (signed audit entries). <br> 2. Verify test results of OQ-002 (hash chain integrity). <br> 3. Verify test results of OQ-003 (Merkle tree checkpoints). <br> 4. Verify test results of OQ-004 (audit trail export completeness). <br> 5. Verify test results of OQ-005 (tamper detection). |
| **Expected Result** | All referenced audit trail test cases (OQ-001 through OQ-005) passed. Audit trail is secure, computer-generated, time-stamped, and tamper-evident. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-006: 11.10(k)(1) -- Authority Checks

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-006 |
| **Regulation** | 21 CFR Part 11, Section 11.10(k)(1) |
| **Requirement** | Use of authority checks to ensure that only authorized individuals can use the system, electronically sign a record, access the operation or computer system input device, alter a record, or perform the operation at hand. |
| **Description** | Verify that only authorized users can perform signing operations. |
| **Procedure** | 1. Authenticate as oq-viewer (lowest privilege). <br> 2. Attempt to sign a record: `sporedb sign --batch "OQ-Test-Batch-001" --meaning "approved" --password <password>` -- expect rejection (viewer cannot sign). <br> 3. Authenticate as oq-editor. <br> 4. Sign the record -- expect success (editor has signing authority). <br> 5. Verify audit trail records who signed and that the viewer's attempt was logged as denied. |
| **Expected Result** | Viewer signing attempt is rejected. Editor signing succeeds. Both events are audit-logged. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-007: 11.10(k)(2) -- Device Checks

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-007 |
| **Regulation** | 21 CFR Part 11, Section 11.10(k)(2) |
| **Requirement** | Use of device (e.g., terminal) checks to determine the validity and integrity of data input and operational instructions. |
| **Description** | Verify that the system clock is NTP-synchronized (cross-reference IQ-010) and that input validation rejects malformed data. |
| **Procedure** | 1. Verify IQ-010 (NTP sync) test result from IQ protocol. <br> 2. Submit an API request with an invalid timestamp format: `{"timestamp": "not-a-date"}` -- expect validation error. <br> 3. Submit an API request with an out-of-range value: `{"dissolved_oxygen": -999}` -- expect validation warning or acceptance with flag. <br> 4. Verify that all validation errors are logged. |
| **Expected Result** | NTP sync confirmed (IQ-010). Invalid data inputs are rejected with descriptive error messages. Validation failures are audit-logged. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-008: 11.50 -- Signature Manifestations

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-008 |
| **Regulation** | 21 CFR Part 11, Section 11.50 |
| **Requirement** | Signed electronic records shall contain information associated with the signing that clearly indicates: (a) the printed name of the signer; (b) the date and time when the signature was executed; (c) the meaning associated with the signature. |
| **Description** | Cross-references OQ-012. Verify signed records display all three manifestation components. |
| **Procedure** | 1. Verify test results of OQ-012 (signature manifestations). <br> 2. Additionally, retrieve a signed record via API and verify JSON response includes: `signer_name`, `signed_at` (ISO 8601 UTC), `meaning` (approved/reviewed/verified/released/rejected). |
| **Expected Result** | All three signature manifestation components are present in every signed record. Values are human-readable. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-009: 11.70 -- Signature/Record Linking

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-009 |
| **Regulation** | 21 CFR Part 11, Section 11.70 |
| **Requirement** | Electronic signatures and handwritten signatures executed to electronic records shall be linked to their respective electronic records to ensure that the signatures cannot be excised, copied, or otherwise transferred to falsify an electronic record. |
| **Description** | Cross-references OQ-013. Verify cryptographic binding prevents signature excision or transfer. |
| **Procedure** | 1. Verify test results of OQ-013 (permanent signature-record linking). <br> 2. Additionally, attempt to copy a signature from one record to another via direct database manipulation and verify the compliance validator detects the invalid binding. |
| **Expected Result** | Signatures are cryptographically bound to records. Transfer or excision is detectable. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-010: 11.100 -- General E-Signature Requirements

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-010 |
| **Regulation** | 21 CFR Part 11, Section 11.100 |
| **Requirement** | Each electronic signature shall be unique to one individual and shall not be reused by, or reassigned to, anyone else. |
| **Description** | Verify that user accounts are unique and cannot be shared or reassigned. |
| **Procedure** | 1. Attempt to create a user with a duplicate username: `sporedb admin create-user --username oq-editor --role viewer --password <password>` -- expect rejection (username already exists). <br> 2. Verify user_id is a unique identifier in the database. <br> 3. Verify that deleting and re-creating a user with the same username produces a different internal user_id (no ID reuse). |
| **Expected Result** | Duplicate usernames are rejected. User IDs are unique and not reused. Each signature is attributable to exactly one individual. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-CFR-011: 11.200 -- E-Signature Components and Controls

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-CFR-011 |
| **Regulation** | 21 CFR Part 11, Section 11.200 |
| **Requirement** | Electronic signatures that are not based upon biometrics shall employ at least two distinct identification components such as an identification code and a password. |
| **Description** | Cross-references OQ-014. Verify two-component authentication for signing. |
| **Procedure** | 1. Verify test results of OQ-014 (two-component e-signature). <br> 2. Verify the system documentation states the two components: user ID (identification code) and password. <br> 3. Verify there is no bypass mechanism that allows single-factor signing. |
| **Expected Result** | Two distinct identification components are required for every electronic signature execution. No bypass exists. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

## 6. EU Annex 11 Specific Tests

These test cases address EU Annex 11 requirements for computerised systems in GMP environments.

#### OQ-AX-001: Data Storage and Backup

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-AX-001 |
| **Regulation** | EU Annex 11, Clause 7 (Data Storage) |
| **Requirement** | Data should be secured by both physical and electronic means against damage. Stored data should be checked for accessibility, readability, and accuracy. Access to data should be ensured throughout the retention period. |
| **Description** | Verify that stored data is persistent, accessible, and protected against corruption. |
| **Procedure** | 1. Verify data persists across container restarts (cross-reference OQ-CFR-003). <br> 2. Verify Parquet files on MinIO are readable: `sporedb query "SELECT count(*) FROM 'OQ-Test-Batch-001'"` <br> 3. Verify PostgreSQL metadata is accessible after restart. <br> 4. Verify backup procedures are documented (reference PQ-006 for backup/restore validation). |
| **Expected Result** | Data persists, is readable, and is accessible after restart. Backup procedures are documented and validated. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-AX-002: Audit Trail Completeness

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-AX-002 |
| **Regulation** | EU Annex 11, Clause 9 (Audit Trail) |
| **Requirement** | Consideration should be given to building into computerised systems the creation of a record of all GMP-relevant changes and deletions (a system-generated "audit trail"). For change to GMP-relevant data, the reason should be documented. |
| **Description** | Verify that every create, update, and delete operation on GMP-relevant data produces an audit trail entry. |
| **Procedure** | 1. Count audit entries before operations. <br> 2. Perform one create (batch create), one update (metadata change), and one delete (batch delete). <br> 3. Count audit entries after operations. <br> 4. Verify the count increased by exactly 3. <br> 5. Verify each new entry has: action type (create/update/delete), entity_type, entity_id, user_id, timestamp, and reason (for update/delete). |
| **Expected Result** | Every GMP-relevant operation produces exactly one audit entry. Update and delete entries include a reason field. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-AX-003: Electronic Signature Equivalence

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-AX-003 |
| **Regulation** | EU Annex 11, Clause 14 (Electronic Signatures) |
| **Requirement** | Electronic records may be signed electronically. Electronic signatures are expected to have the same impact as hand-written signatures within the boundaries of the company. |
| **Description** | Verify that electronic signatures include all elements necessary for regulatory equivalence with handwritten signatures. |
| **Procedure** | 1. Sign a record and retrieve the signature details. <br> 2. Verify the signature contains: full name (equivalent to printed name on paper), date/time (equivalent to handwritten date), meaning/purpose (equivalent to signing context), cryptographic proof of authenticity (equivalent to unique handwriting). <br> 3. Verify the signature is immutable (cannot be altered after creation). |
| **Expected Result** | Electronic signature contains all elements equivalent to a handwritten signature. Signature is immutable and cryptographically verifiable. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-AX-004: Access Control Effectiveness

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-AX-004 |
| **Regulation** | EU Annex 11, Clause 12.1 (Security) |
| **Requirement** | Physical and/or logical controls should be in place to restrict access to computerised systems to authorised persons. Suitable methods of preventing unauthorised entry to the system include the use of keys, pass cards, personal codes with passwords, biometrics, and restricted access to computer equipment and data storage areas. |
| **Description** | Verify that RBAC prevents unauthorized access at all API endpoints. Cross-references OQ-006 through OQ-010. |
| **Procedure** | 1. Verify all RBAC test cases passed (OQ-006 through OQ-010). <br> 2. Verify password complexity requirements are enforced (minimum length, character requirements). <br> 3. Verify failed login attempts are logged in the audit trail. <br> 4. Verify account lockout or rate limiting after repeated failed attempts (if implemented). |
| **Expected Result** | RBAC enforced at all endpoints. Password requirements are enforced. Failed login attempts are logged. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-AX-005: Data Integrity During Transfer

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-AX-005 |
| **Regulation** | EU Annex 11, Clause 7 (Data Storage) and Clause 12.1 (Security) |
| **Requirement** | Data should be secured against damage during transfer. Data integrity checks should be built in during data transfer. |
| **Description** | Verify that data import and export operations include integrity verification (checksum comparison). |
| **Procedure** | 1. Import a CSV file and record the import checksum reported by SporeDB. <br> 2. Compute the SHA-256 checksum of the source CSV independently. <br> 3. Verify checksums match. <br> 4. Export the data and compute checksum of exported file. <br> 5. Re-import the exported file and verify data integrity is maintained. |
| **Expected Result** | Import and export checksums match source data. No data corruption during transfer. Integrity is verifiable at every stage. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

## 7. Boundary and Negative Tests

#### OQ-NEG-001: Invalid Credentials Rejected

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-NEG-001 |
| **Description** | Verify that login attempts with invalid credentials are rejected and logged. |
| **Procedure** | 1. Attempt login with valid username, wrong password. <br> 2. Attempt login with nonexistent username. <br> 3. Attempt login with empty credentials. <br> 4. Verify all attempts return 401 Unauthorized. <br> 5. Verify all failed attempts are recorded in the audit trail (or security log). |
| **Expected Result** | All invalid credential attempts rejected with 401. No information leakage (same error message for all failure types). Failed attempts logged. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-NEG-002: Malformed CSV Import Fails Gracefully

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-NEG-002 |
| **Description** | Verify that importing a malformed CSV file produces a clear error message without crashing the system or corrupting existing data. |
| **Procedure** | 1. Prepare a malformed CSV: missing headers, inconsistent column counts, binary data in text fields. <br> 2. Attempt import: `sporedb import csv malformed.csv --batch "OQ-Bad-Import"` <br> 3. Verify the command returns a descriptive error (not a stack trace). <br> 4. Verify no partial batch was created. <br> 5. Verify existing data is unaffected: `sporedb batch list` still shows previous batches. <br> 6. Verify the system remains responsive: `curl http://localhost:8000/health` returns 200. |
| **Expected Result** | Import fails with a user-friendly error message. No partial data created. Existing data intact. System remains healthy. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-NEG-003: Empty Batch Name Rejected

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-NEG-003 |
| **Description** | Verify that creating a batch with an empty or whitespace-only name is rejected with a validation error. |
| **Procedure** | 1. Attempt: `sporedb batch create ""` -- expect validation error. <br> 2. Attempt: `sporedb batch create "   "` (whitespace only) -- expect validation error. <br> 3. Attempt via API: `POST /api/batches {"name": ""}` -- expect 422 Unprocessable Entity. <br> 4. Verify no batch is created in any case. |
| **Expected Result** | All attempts rejected with validation error (422 or similar). Error message indicates that batch name is required and cannot be empty. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

#### OQ-NEG-004: Concurrent Writes to Same Batch Handled Safely

| Field | Value |
|-------|-------|
| **Test Case ID** | OQ-NEG-004 |
| **Description** | Verify that concurrent write operations to the same batch do not cause data corruption, deadlocks, or lost updates. |
| **Procedure** | 1. Create a test batch. <br> 2. From two concurrent sessions (different terminals or API clients), simultaneously: <br> &nbsp;&nbsp;&nbsp;a. Session A: import a CSV file into the batch. <br> &nbsp;&nbsp;&nbsp;b. Session B: update the batch metadata. <br> 3. Wait for both operations to complete. <br> 4. Verify no deadlock occurred (both operations completed within timeout). <br> 5. Verify data integrity: query the batch and confirm both the imported data and updated metadata are present. <br> 6. Verify audit trail has entries for both operations with correct timestamps and user IDs. |
| **Expected Result** | Both operations complete without deadlock. Data integrity is maintained. Audit trail captures both operations. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

---

## 8. Deviations

Record any deviations from expected results during OQ execution. All deviations must be documented, assessed for impact, and resolved before proceeding to PQ.

| Deviation # | Test Case | Description | Impact Assessment | Resolution | Resolved By | Date |
|-------------|-----------|-------------|-------------------|------------|-------------|------|
| | | | | | | |
| | | | | | | |
| | | | | | | |

## 9. Summary of Results

### By Feature Area

| Feature Area | Test Cases | Passed | Failed |
|-------------|-----------|--------|--------|
| Audit Trail (OQ-001 to OQ-005) | 5 | _____ | _____ |
| RBAC (OQ-006 to OQ-010) | 5 | _____ | _____ |
| Electronic Signatures (OQ-011 to OQ-014) | 4 | _____ | _____ |
| Data Integrity (OQ-015 to OQ-018) | 4 | _____ | _____ |
| Batch Management (OQ-019 to OQ-021) | 3 | _____ | _____ |
| 21 CFR Part 11 (OQ-CFR-001 to OQ-CFR-011) | 11 | _____ | _____ |
| EU Annex 11 (OQ-AX-001 to OQ-AX-005) | 5 | _____ | _____ |
| Boundary/Negative (OQ-NEG-001 to OQ-NEG-004) | 4 | _____ | _____ |
| **TOTAL** | **41** | _____ | _____ |

### Overall

| Category | Count |
|----------|-------|
| Total Test Cases | 41 |
| Passed | _____ |
| Failed | _____ |
| Deviations Recorded | _____ |
| Deviations Resolved | _____ |

## 10. Conclusion

Based on the results documented in this protocol:

- [ ] All OQ tests PASSED -- the system is qualified for Performance Qualification (PQ).
- [ ] One or more tests FAILED -- deviations have been recorded and resolved. The system is qualified for PQ upon deviation closure.
- [ ] One or more tests FAILED -- unresolved deviations prevent progression to PQ. Corrective actions and re-execution of failed tests are required.

**Comments:**

_________________________________________________________________________________

_________________________________________________________________________________

## 11. Approval Signatures

By signing below, I confirm that I have reviewed the results of this Operational Qualification protocol and that the conclusions are accurate and supported by the documented evidence.

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
| PQ Protocol | PQ-SPOREDB-001 | Performance Qualification protocol for SporeDB |
| Traceability Matrix | RTM-SPOREDB-001 | Requirements Traceability Matrix |
| 21 CFR Part 11 | FDA | Electronic Records; Electronic Signatures |
| EU Annex 11 | EMA | Computerised Systems (2011, with 2025 draft provisions) |
| GAMP 5 | ISPE | A Risk-Based Approach to Compliant GxP Computerized Systems |

## Appendix B: Test User Accounts

| Username | Full Name | Role | Purpose |
|----------|-----------|------|---------|
| oq-admin | OQ Admin User | Admin | Administrative operations and user management |
| oq-editor | OQ Editor User | Editor | Data entry, batch management, signing |
| oq-viewer | OQ Viewer User | Viewer | Read-only access verification |
| oq-role-test | OQ Role Test User | Variable | Role change testing (OQ-010) |

## Appendix C: Version History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | _________________ | _________________ | Initial OQ protocol |
