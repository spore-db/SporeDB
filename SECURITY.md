# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in SporeDB, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email: **security@sporedb.dev** (or use GitHub's private vulnerability reporting feature on this repository).

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgment:** within 48 hours
- **Initial assessment:** within 1 week
- **Fix timeline:** depends on severity, typically within 30 days for critical issues

### Scope

The following are in scope:
- SporeDB Python library (`sporedb` package)
- SporeDB Cloud tier (FastAPI server)
- Authentication and authorization (JWT, RBAC)
- Compliance module (audit trails, e-signatures, Merkle proofs)
- Data integrity and storage security

### Recognition

We appreciate responsible disclosure and will credit reporters in the changelog (unless they prefer to remain anonymous).
