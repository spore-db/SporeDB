# Requirements Traceability Matrix

## SporeDB Regulatory Compliance

| Field | Value |
|-------|-------|
| **Document ID** | RTM-SPOREDB-001 |
| **Version** | 1.0 |
| **System** | SporeDB v0.1.0 |
| **Effective Date** | _________________ |
| **Prepared By** | _________________ |
| **Reviewed By** | _________________ |
| **Approved By** | _________________ |

---

## 1. Purpose

This Requirements Traceability Matrix (RTM) provides bidirectional traceability between regulatory requirements and validation test evidence for SporeDB. It maps every applicable requirement from FDA 21 CFR Part 11 and EU Annex 11 to specific test cases in the IQ, OQ, and PQ protocols, along with the evidence artifacts that demonstrate compliance.

This matrix enables:

- **Forward traceability:** From each regulatory requirement to the test(s) that verify it.
- **Backward traceability:** From each test case to the regulatory requirement(s) it satisfies.
- **Gap analysis:** Identification of any unaddressed regulatory requirements.
- **Audit readiness:** Rapid lookup for inspectors asking "show me which test verifies requirement X."

---

## 2. FDA 21 CFR Part 11 Requirements

| Req ID | Source | Section | Description | Test Case ID(s) | Test Type | Evidence Reference | Status |
|--------|--------|---------|-------------|-----------------|-----------|-------------------|--------|
| CFR-11.10a | 21 CFR Part 11 | 11.10(a) | Validation of systems to ensure accuracy, reliability, consistent intended performance, and the ability to discern invalid or altered records | OQ-CFR-001 | OQ | IQ/OQ/PQ execution reports, RTM-SPOREDB-001 | |
| CFR-11.10b | 21 CFR Part 11 | 11.10(b) | Ability to generate accurate and complete copies of records in both human-readable and electronic form | OQ-CFR-002, OQ-015 | OQ | CSV, Parquet, and JSON export files with checksum verification | |
| CFR-11.10c | 21 CFR Part 11 | 11.10(c) | Protection of records to enable accurate and ready retrieval throughout the records retention period | OQ-CFR-003, PQ-006 | OQ, PQ | Container restart test results, backup/restore verification report | |
| CFR-11.10d | 21 CFR Part 11 | 11.10(d) | Limiting system access to authorized individuals | OQ-CFR-004, OQ-006, OQ-007, OQ-008, OQ-009, OQ-010 | OQ | RBAC test logs showing role-based enforcement | |
| CFR-11.10e | 21 CFR Part 11 | 11.10(e) | Use of secure, computer-generated, time-stamped audit trails to independently record the date and time of operator entries and actions | OQ-CFR-005, OQ-001, OQ-002, OQ-003, OQ-004, OQ-005, PQ-004 | OQ, PQ | Audit trail export, hash chain verification report, Merkle checkpoint log | |
| CFR-11.10f | 21 CFR Part 11 | 11.10(f) | Use of operational system checks to enforce permitted sequencing of steps and events | OQ-002 | OQ | SHA-256 hash chain verification showing sequential ordering | |
| CFR-11.10g | 21 CFR Part 11 | 11.10(g) | Use of authority checks to ensure only authorized individuals can use the system, electronically sign, access, alter records, or perform operations | OQ-CFR-006, OQ-006, OQ-007, OQ-008 | OQ | RBAC test logs, signing authorization verification | |
| CFR-11.10k1 | 21 CFR Part 11 | 11.10(k)(1) | Use of appropriate controls over systems documentation including adequate controls over the distribution of, access to, and use of documentation for system operation and maintenance | OQ-CFR-006 | OQ | Authority check test results, signing access verification | |
| CFR-11.10k2 | 21 CFR Part 11 | 11.10(k)(2) | Use of revision and change control procedures to maintain an audit trail that documents time-sequenced development and modification of systems documentation | OQ-CFR-007, IQ-010 | OQ, IQ | NTP sync verification, input validation test results | |
| CFR-11.50 | 21 CFR Part 11 | 11.50 | Signed electronic records shall contain: (a) printed name of signer, (b) date and time of signing, (c) meaning of signature | OQ-CFR-008, OQ-012 | OQ | Signed record display showing name, date/time (UTC), and meaning | |
| CFR-11.70 | 21 CFR Part 11 | 11.70 | Electronic signatures linked to records such that signatures cannot be excised, copied, or transferred to falsify | OQ-CFR-009, OQ-013 | OQ | Cryptographic binding verification, record modification invalidation test | |
| CFR-11.100 | 21 CFR Part 11 | 11.100 | Each electronic signature unique to one individual, not reused or reassigned | OQ-CFR-010 | OQ | Duplicate username rejection test, unique user_id verification | |
| CFR-11.200 | 21 CFR Part 11 | 11.200 | Electronic signatures employ at least two distinct identification components (ID code + password) | OQ-CFR-011, OQ-014, OQ-011 | OQ | Two-component signing verification, re-authentication test results | |

---

## 3. EU Annex 11 Requirements

| Req ID | Source | Section | Description | Test Case ID(s) | Test Type | Evidence Reference | Status |
|--------|--------|---------|-------------|-----------------|-----------|-------------------|--------|
| AX11-1 | EU Annex 11 | Clause 1 (Risk Management) | Risk management should be applied throughout the lifecycle of the computerised system taking into account patient safety, data integrity, and product quality | OQ-CFR-001 | OQ | IQ/OQ/PQ execution as lifecycle validation evidence | |
| AX11-7 | EU Annex 11 | Clause 7 (Data Storage) | Data should be secured by both physical and electronic means against damage. Stored data should be checked for accessibility, readability, and accuracy | OQ-AX-001, OQ-CFR-003, PQ-006 | OQ, PQ | Data persistence test, backup/restore verification, MinIO storage check | |
| AX11-9 | EU Annex 11 | Clause 9 (Audit Trail) | Consideration should be given to building into computerised systems the creation of a record of all GMP-relevant changes and deletions | OQ-AX-002, OQ-001, OQ-002, OQ-003, OQ-004, OQ-005, PQ-004 | OQ, PQ | Audit trail completeness test, hash chain verification, tamper detection | |
| AX11-12.1 | EU Annex 11 | Clause 12.1 (Security) | Physical and/or logical controls should restrict access to computerised systems to authorised persons | OQ-AX-004, OQ-006, OQ-007, OQ-008, OQ-009, OQ-010, OQ-NEG-001 | OQ | RBAC enforcement test suite, password validation, failed login logging | |
| AX11-12.4 | EU Annex 11 | Clause 12.4 (Electronic Signatures - Management) | Management systems for data and documents should be designed so that identities of operators entering, changing, confirming, or deleting data are recorded | OQ-001, OQ-AX-002 | OQ | Audit trail entries with user_id for every operation | |
| AX11-14 | EU Annex 11 | Clause 14 (Electronic Signatures) | Electronic records may be signed electronically. Electronic signatures are expected to have the same impact as hand-written signatures | OQ-AX-003, OQ-012, OQ-013, OQ-014 | OQ | Signature manifestation test, cryptographic binding verification | |

---

## 4. Cross-Cutting Requirements

| Req ID | Source | Description | Test Case ID(s) | Test Type | Evidence Reference | Status |
|--------|--------|-------------|-----------------|-----------|-------------------|--------|
| CROSS-01 | Best Practice | System installation meets documented specifications | IQ-001 through IQ-013 | IQ | IQ execution report with all test results | |
| CROSS-02 | Best Practice | System functions correctly under production-like conditions | PQ-001 through PQ-007 | PQ | PQ execution report with timing and acceptance criteria | |
| CROSS-03 | GAMP 5 | Input validation prevents data integrity issues | OQ-CFR-007, OQ-NEG-002, OQ-NEG-003 | OQ | Malformed input rejection tests, validation error logs | |
| CROSS-04 | GAMP 5 | Error handling is graceful and informative | OQ-NEG-001, OQ-NEG-002, OQ-NEG-003, OQ-NEG-004 | OQ | Negative test results showing error messages without crashes | |
| CROSS-05 | Best Practice | Concurrent operations do not cause data corruption | OQ-NEG-004, PQ-002 | OQ, PQ | Concurrent access test results, deadlock verification | |

---

## 5. Backward Traceability: Test Case to Requirements

This section allows auditors to trace from any test case back to the regulatory requirement(s) it satisfies.

### IQ Test Cases

| Test Case | Description | Regulatory Requirements |
|-----------|-------------|----------------------|
| IQ-001 | Docker images present | CROSS-01 |
| IQ-002 | Container health checks | CROSS-01 |
| IQ-003 | Ed25519 signing key configuration | CROSS-01, CFR-11.10e (key infrastructure) |
| IQ-004 | PostgreSQL connectivity | CROSS-01, AX11-7 (data storage) |
| IQ-005 | MinIO connectivity | CROSS-01, AX11-7 (data storage) |
| IQ-006 | SporeDB API health | CROSS-01 |
| IQ-007 | SPOREDB_MODE=selfhosted | CROSS-01 |
| IQ-008 | Audit trail enabled at startup | CFR-11.10e, AX11-9 |
| IQ-009 | RBAC configured | CFR-11.10d, AX11-12.1 |
| IQ-010 | NTP/time synchronization | CFR-11.10k2, CFR-11.10e (timestamp accuracy) |
| IQ-011 | Database schema migration | CROSS-01 |
| IQ-012 | MinIO bucket configuration | CROSS-01, AX11-7 |
| IQ-013 | Configuration file validation | CROSS-01 |

### OQ Test Cases

| Test Case | Description | Regulatory Requirements |
|-----------|-------------|----------------------|
| OQ-001 | Signed audit entry | CFR-11.10e, AX11-9, AX11-12.4 |
| OQ-002 | SHA-256 hash chain | CFR-11.10e, CFR-11.10f, AX11-9 |
| OQ-003 | Merkle tree checkpoint | CFR-11.10e, AX11-9 |
| OQ-004 | Audit trail export | CFR-11.10e, CFR-11.10b, AX11-9 |
| OQ-005 | Tamper detection | CFR-11.10e, AX11-9, AX11-12.1 |
| OQ-006 | Admin user management | CFR-11.10d, CFR-11.10g, AX11-12.1 |
| OQ-007 | Editor batch permissions | CFR-11.10d, CFR-11.10g, AX11-12.1 |
| OQ-008 | Viewer read-only access | CFR-11.10d, CFR-11.10g, AX11-12.1 |
| OQ-009 | Unauthorized access denial | CFR-11.10d, AX11-12.1 |
| OQ-010 | Role changes immediate | CFR-11.10d, AX11-12.1 |
| OQ-011 | E-signature re-authentication | CFR-11.200, AX11-14 |
| OQ-012 | Signature manifestations | CFR-11.50, AX11-14 |
| OQ-013 | Signature-record linking | CFR-11.70, AX11-14 |
| OQ-014 | Two-component e-signature | CFR-11.200, AX11-14 |
| OQ-015 | Import data fidelity | CFR-11.10b, AX11-7 |
| OQ-016 | Timestamp normalization | CFR-11.10e (timestamp accuracy) |
| OQ-017 | Unit conversion accuracy | CROSS-03 (data integrity) |
| OQ-018 | Metadata persistence | CFR-11.10c, AX11-7 |
| OQ-019 | Create batch with metadata | CROSS-04 |
| OQ-020 | Search/filter batches | CFR-11.10b (record retrieval) |
| OQ-021 | Delete batch cascades | AX11-9 (deletion audit), CFR-11.10e |
| OQ-CFR-001 | 11.10(a) system validation | CFR-11.10a |
| OQ-CFR-002 | 11.10(b) accurate copies | CFR-11.10b |
| OQ-CFR-003 | 11.10(c) record protection | CFR-11.10c |
| OQ-CFR-004 | 11.10(d) access limiting | CFR-11.10d |
| OQ-CFR-005 | 11.10(e) audit trails | CFR-11.10e |
| OQ-CFR-006 | 11.10(k)(1) authority checks | CFR-11.10g, CFR-11.10k1 |
| OQ-CFR-007 | 11.10(k)(2) device checks | CFR-11.10k2 |
| OQ-CFR-008 | 11.50 signature manifestations | CFR-11.50 |
| OQ-CFR-009 | 11.70 signature/record linking | CFR-11.70 |
| OQ-CFR-010 | 11.100 unique e-signatures | CFR-11.100 |
| OQ-CFR-011 | 11.200 signature components | CFR-11.200 |
| OQ-AX-001 | Data storage and backup | AX11-7 |
| OQ-AX-002 | Audit trail completeness | AX11-9, AX11-12.4 |
| OQ-AX-003 | E-signature equivalence | AX11-14 |
| OQ-AX-004 | Access control effectiveness | AX11-12.1 |
| OQ-AX-005 | Data integrity during transfer | AX11-7, AX11-12.1 |
| OQ-NEG-001 | Invalid credentials rejected | AX11-12.1, CROSS-04 |
| OQ-NEG-002 | Malformed CSV import fails | CROSS-03, CROSS-04 |
| OQ-NEG-003 | Empty batch name rejected | CROSS-03, CROSS-04 |
| OQ-NEG-004 | Concurrent writes safe | CROSS-05 |

### PQ Test Cases

| Test Case | Description | Regulatory Requirements |
|-----------|-------------|----------------------|
| PQ-001 | Full bioprocess workflow | CROSS-02 |
| PQ-002 | Multi-user concurrent access | CFR-11.10d, AX11-12.1, CROSS-05 |
| PQ-003 | Large dataset handling | CROSS-02 |
| PQ-004 | Audit trail under load | CFR-11.10e, AX11-9 |
| PQ-005 | Data export fidelity | CFR-11.10b, AX11-7 |
| PQ-006 | Backup and restore | CFR-11.10c, AX11-7 |
| PQ-007 | System stability (24h) | CROSS-02 |

---

## 6. Coverage Summary

### FDA 21 CFR Part 11 Coverage

| Section | Description | Covered | Test Cases |
|---------|-------------|---------|-----------|
| 11.10(a) | System validation | Yes | OQ-CFR-001 |
| 11.10(b) | Accurate copies | Yes | OQ-CFR-002, OQ-015, PQ-005 |
| 11.10(c) | Record protection | Yes | OQ-CFR-003, PQ-006 |
| 11.10(d) | Access limitation | Yes | OQ-CFR-004, OQ-006--OQ-010, PQ-002 |
| 11.10(e) | Audit trails | Yes | OQ-CFR-005, OQ-001--OQ-005, PQ-004 |
| 11.10(f) | Sequencing checks | Yes | OQ-002 |
| 11.10(g) | Authority checks | Yes | OQ-CFR-006, OQ-006--OQ-008 |
| 11.10(k)(1) | Authority checks (signing) | Yes | OQ-CFR-006 |
| 11.10(k)(2) | Device checks | Yes | OQ-CFR-007, IQ-010 |
| 11.50 | Signature manifestations | Yes | OQ-CFR-008, OQ-012 |
| 11.70 | Signature/record linking | Yes | OQ-CFR-009, OQ-013 |
| 11.100 | Unique e-signatures | Yes | OQ-CFR-010 |
| 11.200 | Signature components | Yes | OQ-CFR-011, OQ-014, OQ-011 |

**Coverage: 13/13 sections (100%)**

### EU Annex 11 Coverage

| Clause | Description | Covered | Test Cases |
|--------|-------------|---------|-----------|
| Clause 1 | Risk management | Yes | OQ-CFR-001 |
| Clause 7 | Data storage | Yes | OQ-AX-001, OQ-AX-005, PQ-006 |
| Clause 9 | Audit trail | Yes | OQ-AX-002, OQ-001--OQ-005, PQ-004 |
| Clause 12.1 | Security | Yes | OQ-AX-004, OQ-006--OQ-010, OQ-NEG-001 |
| Clause 12.4 | Electronic signatures (management) | Yes | OQ-AX-002, OQ-001 |
| Clause 14 | Electronic signatures | Yes | OQ-AX-003, OQ-011--OQ-014 |

**Coverage: 6/6 clauses (100%)**

---

## 7. Gap Analysis

| # | Description | Status |
|---|-------------|--------|
| 1 | All 21 CFR Part 11 sections covered | No gaps identified |
| 2 | All EU Annex 11 clauses covered | No gaps identified |
| 3 | All IQ test cases linked to requirements | Verified |
| 4 | All OQ test cases linked to requirements | Verified |
| 5 | All PQ test cases linked to requirements | Verified |

**Note:** EU Annex 11 (2025 draft) introduces additional requirements for cybersecurity, alarms, and lifecycle management. These are marked as provisional in this version and will be updated when the final regulation is published (expected mid-2026).

---

## 8. Approval Signatures

By signing below, I confirm that this Requirements Traceability Matrix is complete and accurately maps all applicable regulatory requirements to validation test evidence.

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **QA Reviewer** | _________________ | _________________ | _________________ |
| **System Administrator** | _________________ | _________________ | _________________ |
| **Quality Head** | _________________ | _________________ | _________________ |

---

## Appendix: Version History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | _________________ | _________________ | Initial RTM covering 21 CFR Part 11 and EU Annex 11 |
