# Installation Qualification Protocol

## SporeDB Self-Hosted Deployment

| Field | Value |
|-------|-------|
| **Document ID** | IQ-SPOREDB-001 |
| **Version** | 1.0 |
| **System** | SporeDB v0.1.0 |
| **Effective Date** | _________________ |
| **Prepared By** | _________________ |
| **Reviewed By** | _________________ |
| **Approved By** | _________________ |

---

## 1. Purpose

This Installation Qualification (IQ) protocol verifies that all SporeDB self-hosted components are installed correctly per approved specifications. Successful execution of this protocol confirms that the system hardware, software, and supporting infrastructure meet the documented requirements and are ready for Operational Qualification (OQ) testing.

This protocol is designed to satisfy the requirements of:

- FDA 21 CFR Part 11, Section 11.10(a) -- Validation of systems to ensure accuracy, reliability, consistent intended performance, and the ability to discern invalid or altered records
- EU Annex 11, Clause 4 -- Validation documentation should cover system life cycle steps including the installation phase
- GAMP 5 guidelines for computerized system validation

## 2. Scope

This IQ protocol covers the installation verification of the following SporeDB self-hosted deployment components:

- **SporeDB application container** -- Docker image containing the FastAPI server, storage engine, compliance modules, and CLI tools
- **PostgreSQL database** -- Metadata store for user accounts, batch metadata, access controls, and audit log index
- **MinIO object storage** -- S3-compatible object storage for Parquet data files
- **Network configuration** -- Inter-service connectivity, port availability, and DNS resolution
- **SSL/TLS certificates** -- Transport encryption configuration (if applicable)
- **Ed25519 signing keys** -- Cryptographic key pair for audit trail entry signing
- **RBAC configuration** -- Default user accounts and role assignments
- **NTP/time synchronization** -- System clock accuracy for audit trail timestamps

### Out of Scope

- Functional verification of SporeDB features (covered in OQ protocol OQ-SPOREDB-001)
- Performance testing under production conditions (covered in PQ protocol PQ-SPOREDB-001)
- Network security assessments and penetration testing
- Operating system hardening and patch management

## 3. Prerequisites Checklist

Before executing this IQ protocol, verify that the following prerequisites are met:

| # | Prerequisite | Verified | Initials | Date |
|---|-------------|----------|----------|------|
| 1 | Docker Engine >= 24.0 installed on host server | [ ] | _____ | _____ |
| 2 | Docker Compose >= 2.20 installed on host server | [ ] | _____ | _____ |
| 3 | Host server meets minimum hardware requirements (Section 4) | [ ] | _____ | _____ |
| 4 | Network ports 8000, 5432, 9000, 9001 are available | [ ] | _____ | _____ |
| 5 | Ed25519 signing key pair generated per key generation SOP | [ ] | _____ | _____ |
| 6 | `sporedb.yml` configuration file prepared per deployment SOP | [ ] | _____ | _____ |
| 7 | DNS or /etc/hosts entries configured for service discovery | [ ] | _____ | _____ |
| 8 | Docker images obtained (via registry pull or air-gap bundle) | [ ] | _____ | _____ |
| 9 | Approved change control ticket for this installation | [ ] | _____ | _____ |

## 4. Hardware and Software Requirements

### 4.1 Hardware Requirements

| Component | Minimum Requirement | Recommended | Actual (Record) |
|-----------|-------------------|-------------|-----------------|
| CPU | 4 cores | 8 cores | _________________ |
| RAM | 8 GB | 16 GB | _________________ |
| Storage | 100 GB SSD | 500 GB SSD | _________________ |
| Network | 100 Mbps | 1 Gbps | _________________ |

### 4.2 Software Requirements

| Component | Required Version | Actual Version | Pass/Fail |
|-----------|-----------------|----------------|-----------|
| Operating System | Linux (kernel >= 5.10) | _________________ | _____ |
| Docker Engine | >= 24.0 | _________________ | _____ |
| Docker Compose | >= 2.20 | _________________ | _____ |
| SporeDB Image | v0.1.0 | _________________ | _____ |
| PostgreSQL Image | 16-alpine | _________________ | _____ |
| MinIO Image | latest (RELEASE.2025-*) | _________________ | _____ |

## 5. Installation Verification Tests

### IQ-001: Docker Images Present

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-001 |
| **Description** | Verify that all required Docker images are present on the host with correct version tags. |
| **Procedure** | 1. Run: `docker images \| grep sporedb` <br> 2. Run: `docker images \| grep postgres` <br> 3. Run: `docker images \| grep minio` |
| **Expected Result** | SporeDB image shows tag `v0.1.0` or configured version. PostgreSQL image shows tag `16-alpine`. MinIO image is present with expected release tag. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-002: Container Health Checks

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-002 |
| **Description** | Verify that all Docker Compose services start and report healthy status. |
| **Procedure** | 1. Run: `docker compose -f docker-compose.yml -f docker-compose.selfhosted.yml up -d` <br> 2. Wait 60 seconds for health checks to complete. <br> 3. Run: `docker compose ps` |
| **Expected Result** | All services (sporedb, postgres, minio) show status "healthy" or "running (healthy)". No services show "unhealthy" or "restarting". |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-003: Ed25519 Signing Key Configuration

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-003 |
| **Description** | Verify that the Ed25519 signing key pair is correctly configured and has appropriate file permissions. |
| **Procedure** | 1. Verify key files exist: `ls -la keys/cloud_private.pem keys/cloud_public.pem` <br> 2. Verify private key permissions: `stat -c '%a' keys/cloud_private.pem` (expect 600) <br> 3. Verify public key permissions: `stat -c '%a' keys/cloud_public.pem` (expect 644) <br> 4. Verify key type: `openssl pkey -in keys/cloud_private.pem -noout -text 2>&1 \| head -1` (expect "ED25519 Private-Key") |
| **Expected Result** | Both key files exist. Private key has permissions 600 (owner read/write only). Public key has permissions 644. Key type is Ed25519. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-004: PostgreSQL Connectivity

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-004 |
| **Description** | Verify that the PostgreSQL database is running and accepting connections. |
| **Procedure** | 1. Run: `docker compose exec postgres pg_isready -U sporedb` <br> 2. Run: `docker compose exec postgres psql -U sporedb -d sporedb -c "SELECT version();"` |
| **Expected Result** | `pg_isready` returns "accepting connections". `psql` returns PostgreSQL version 16.x. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-005: MinIO Object Storage Connectivity

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-005 |
| **Description** | Verify that MinIO object storage is running and accessible. |
| **Procedure** | 1. Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live` <br> 2. Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/cluster` |
| **Expected Result** | Both health endpoints return HTTP status code 200. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-006: SporeDB API Health

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-006 |
| **Description** | Verify that the SporeDB API server is running and returns correct version information. |
| **Procedure** | 1. Run: `curl -s http://localhost:8000/health` <br> 2. Parse JSON response and verify `version` field. |
| **Expected Result** | HTTP 200 response with JSON body containing `"version": "0.1.0"` and `"status": "healthy"`. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-007: SPOREDB_MODE Environment Variable

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-007 |
| **Description** | Verify that the SporeDB container is running in self-hosted mode. |
| **Procedure** | 1. Run: `docker compose exec sporedb env \| grep SPOREDB_MODE` <br> 2. Verify the value is `selfhosted`. |
| **Expected Result** | Output shows `SPOREDB_MODE=selfhosted`. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-008: Audit Trail Enabled at Startup

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-008 |
| **Description** | Verify that the audit trail subsystem is active and writing entries at application startup. |
| **Procedure** | 1. Check container logs for audit trail initialization: `docker compose logs sporedb \| grep -i "audit"` <br> 2. Verify audit trail Parquet file exists: `docker compose exec sporedb ls -la data/audit/` <br> 3. Alternatively, query the health endpoint: `curl -s http://localhost:8000/health` and verify `audit_trail_active` is `true`. |
| **Expected Result** | Startup logs confirm audit trail initialization. Audit trail data directory exists. Health endpoint confirms audit trail is active. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-009: RBAC Configuration Verified

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-009 |
| **Description** | Verify that RBAC is configured with at least a default admin user and that role enforcement is active. |
| **Procedure** | 1. Check for default admin user: `docker compose exec sporedb sporedb admin list-users` or query the users endpoint: `curl -s -H "Authorization: Bearer <admin-token>" http://localhost:8000/api/users` <br> 2. Verify at least one user with admin role exists. <br> 3. Verify unauthenticated access is denied: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/batches` (expect 401 or 403). |
| **Expected Result** | Default admin user exists with role "admin". Unauthenticated API requests are rejected with 401 or 403 status. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-010: NTP/Time Synchronization Verification

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-010 |
| **Description** | Verify that the host server clock is synchronized via NTP. Accurate timestamps are critical for audit trail compliance per 21 CFR Part 11, Section 11.10(e). |
| **Procedure** | 1. Check NTP synchronization status on host: `timedatectl status \| grep "synchronized"` <br> 2. Verify clock offset is within acceptable tolerance: `chronyc tracking \| grep "System time"` (or `ntpq -p` for ntpd) <br> 3. Verify container time matches host: `docker compose exec sporedb date -u` and compare with `date -u` on host. |
| **Expected Result** | NTP synchronization is active ("System clock synchronized: yes"). Clock offset is less than 1 second. Container time matches host time within 1 second. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-011: Database Schema Migration Status

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-011 |
| **Description** | Verify that all Alembic database migrations have been applied to PostgreSQL. |
| **Procedure** | 1. Run: `docker compose exec sporedb alembic current` <br> 2. Run: `docker compose exec sporedb alembic check` (returns 0 if up to date) |
| **Expected Result** | Alembic reports the latest migration revision as current. No pending migrations. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-012: MinIO Bucket Configuration

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-012 |
| **Description** | Verify that the required MinIO storage buckets are created and accessible. |
| **Procedure** | 1. Run: `docker compose exec minio mc alias set local http://localhost:9000 <access-key> <secret-key>` <br> 2. Run: `docker compose exec minio mc ls local/` <br> 3. Verify the `sporedb-data` bucket (or configured bucket name) exists. |
| **Expected Result** | The SporeDB data bucket exists and is accessible. Bucket policy allows the SporeDB service account to read and write. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

### IQ-013: Configuration File Validation

| Field | Value |
|-------|-------|
| **Test Case ID** | IQ-013 |
| **Description** | Verify that `sporedb.yml` configuration file is syntactically valid and contains all required settings. |
| **Procedure** | 1. Run: `docker compose exec sporedb sporedb config validate` (or `python -c "import yaml; yaml.safe_load(open('/home/sporedb/app/sporedb.yml'))"`) <br> 2. Verify key settings are present: database URL, S3 endpoint, signing key path, RBAC enabled flag. |
| **Expected Result** | Configuration file parses without errors. All required fields are present and non-empty. |
| **Actual Result** | _________________ |
| **Pass/Fail** | _____ |
| **Tester** | _________________ |
| **Date** | _________________ |

## 6. Deviations

Record any deviations from expected results during IQ execution. All deviations must be documented, assessed for impact, and resolved before proceeding to OQ.

| Deviation # | Test Case | Description | Impact Assessment | Resolution | Resolved By | Date |
|-------------|-----------|-------------|-------------------|------------|-------------|------|
| | | | | | | |
| | | | | | | |
| | | | | | | |

## 7. Summary of Results

| Category | Count |
|----------|-------|
| Total Test Cases | 13 |
| Passed | _____ |
| Failed | _____ |
| Deviations Recorded | _____ |
| Deviations Resolved | _____ |

## 8. Conclusion

Based on the results documented in this protocol:

- [ ] All installation verification tests PASSED -- the system is qualified for Operational Qualification (OQ).
- [ ] One or more tests FAILED -- deviations have been recorded and resolved. The system is qualified for OQ upon deviation closure.
- [ ] One or more tests FAILED -- unresolved deviations prevent progression to OQ. Re-installation and re-execution of IQ required.

**Comments:**

_________________________________________________________________________________

_________________________________________________________________________________

## 9. Approval Signatures

By signing below, I confirm that I have reviewed the results of this Installation Qualification protocol and that the conclusions are accurate and supported by the documented evidence.

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **QA Reviewer** | _________________ | _________________ | _________________ |
| **System Administrator** | _________________ | _________________ | _________________ |
| **Quality Head** | _________________ | _________________ | _________________ |

---

## Appendix A: Reference Documents

| Document | ID | Description |
|----------|-----|-------------|
| OQ Protocol | OQ-SPOREDB-001 | Operational Qualification protocol for SporeDB |
| PQ Protocol | PQ-SPOREDB-001 | Performance Qualification protocol for SporeDB |
| Traceability Matrix | RTM-SPOREDB-001 | Requirements Traceability Matrix |
| Deployment SOP | _(site-specific)_ | Standard operating procedure for SporeDB deployment |
| Key Generation SOP | _(site-specific)_ | Standard operating procedure for Ed25519 key generation |

## Appendix B: Version History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | _________________ | _________________ | Initial IQ protocol |
