# Security Specification

This document describes the security measures implemented in this Proof of Concept (POC) and identifies the components that must be hardened before any production deployment.

---

## 1. Implemented Security Controls

### Column-Level Encryption at Rest
- Direct child identifiers (name, date of birth, school, grade, parent contact) and specialist clinical notes are encrypted with **Fernet symmetric cryptography** before being written to the database, and decrypted dynamically via model property getters.
- Encryption keys are loaded from an environment variable (`PHI_ENCRYPTION_KEY`) — never hardcoded in source.

### PHI Minimization & Redaction Layer
Every prompt sent to the external OpenRouter API passes through automatic sanitization (`redact_phi`):
- Strips telephone numbers (Arabic and Western numerals).
- Strips email addresses and calendar date strings.
- Scans for and replaces common Arabic first names with a placeholder token.
- Maps child database UUIDs to shortened internal references (e.g. `CHILD_a8d3e2f1`) instead of exposing raw identifiers.

### Authentication & Authorization
- Password hashing uses the computationally hard **Argon2id** algorithm via `passlib`.
- Endpoint security uses short-lived JSON Web Tokens (JWT) for session authentication.
- Server-side Role-Based Access Control (RBAC) restricts endpoint access via decorators (e.g. AI report generation and clinical observations are locked to `specialist` and `admin` scopes).

### Sanitized Audit Trails
Security audit logs are captured in a dedicated `audit_logs` table, tracking system events (logins, registrations, AI generations, report approvals) without referencing any raw patient information (PHI).

### Secret Management
All credentials — the OpenRouter API key, JWT signing secret, Fernet encryption key, and database password — are loaded exclusively from environment variables (`.env`, gitignored). No secret has a hardcoded fallback value in source control: in production the app refuses to start without `JWT_SECRET` and `PHI_ENCRYPTION_KEY`. See [`.env.example`](.env.example) and [`backend/.env.example`](backend/.env.example) for the required variables.

---

## 2. Deferred Production Hardening

| Security Aspect | POC Implementation | Required for Production |
|---|---|---|
| **Compliance certification** | None (POC only) | Full HIPAA, GDPR, and relevant national health authority certification. |
| **LLM provider agreement** | OpenRouter (public endpoint) | Business-level BAA / DPA with a private VPC LLM deployment. |
| **Key management** | Environment variables (`.env`) | Managed key vault — HashiCorp Vault, AWS KMS, or Google Cloud KMS. |
| **File upload scanning** | Not implemented | Active virus scanning (e.g. ClamAV) and MIME-type signature checks. |
| **Database encryption** | Column-level Fernet | Full Transparent Data Encryption (TDE) at the storage engine layer. |
| **PHI redaction robustness** | Regex + a fixed Arabic name list | NLP-based named-entity recognition (NER) for reliable PHI detection. |
| **Vector store scaling** | Qdrant with in-memory fallback | Dedicated, persistent, horizontally-scalable Qdrant cluster. |

---

## Reporting a vulnerability

This is a proof-of-concept project. If you find a security issue, please open an issue on the repository rather than disclosing it publicly.

---

## 3. Current Security Posture

- **Authentication:** every protected endpoint requires a valid, short-lived access token. Passwords are verified with Argon2id, failed logins are rate-limited, and error messages are generic.
- **Authorization:** roles are enforced server-side from the database. Self-registration is limited to non-clinical roles, and parents can only access the records they created.
- **Secrets:** no secret exists in the repository. In production the app refuses to start unless `JWT_SECRET` and `PHI_ENCRYPTION_KEY` are provided through the environment.
- **Demo data:** demo accounts are disabled by default and can only be enabled locally with a password you choose.
- **Transport/browser hardening:** explicit CORS allow-list, API documentation disabled in production, and standard security response headers.
- **Testing:** `backend/test_security.py` is a regression suite covering authentication, role enforcement, record ownership and lockout.

### Deployment requirements
Configure the variables listed in [DEPLOYMENT.md](DEPLOYMENT.md) (database URL, JWT secret, PHI key, LLM API key) and use your own freshly generated values. Never commit `.env` files, database files or backups; the `.gitignore` already excludes them.

### Known POC limitations
Login rate limiting is per instance (use a shared store in production), there is no token revocation, and this project is a proof of concept without formal compliance certification.

### Reporting a vulnerability
Please contact the maintainer privately rather than opening a public issue.
