# Security Specification (المعايير الأمنية وحماية الخصوصية)

This document highlights the security measures incorporated into this Proof of Concept (POC) and identifies components that must be reinforced prior to a production deployment.

---

## 1. Implemented Security Controls (المعايير المطبقة حاليًا)

### Column-Level Encryption at Rest (تشفير البيانات الحساسة)
- Direct child identifiers (Name, Date of Birth, School, Grade, Parent Contact) and specialist clinical notes are encrypted using **Fernet Symmetric Cryptography** before database write, and decrypted dynamically via class property getters.
- Encryptions keys are loaded from system environment variables (`PHI_ENCRYPTION_KEY`), ensuring they are never hardcoded in repository sources.

### PHI Minimization & Redaction Layer (تجريد البيانات قبل إرسالها للذكاء الاصطناعي)
- All prompts sent to the external OpenRouter API undergo automatic sanitization (`redact_phi`):
  - Strips telephone numbers (Arabic & Western numerals).
  - Strips email addresses and calendar date strings.
  - Scans and replaces common Arabic name tokens with placeholders `[الطفل/الحالة]`.
  - Maps Child database UUIDs to shortened internal references (e.g. `CHILD_a8d3e2f1`).

### Authentication & Authorization (التحقق والترخيص)
- Password hashing is enforced using the computationally hard **Argon2id** algorithm via `passlib`.
- Endpoint security uses short-lived JSON Web Tokens (JWT) for session authentication.
- Server-side Role-Based Access Control (RBAC) regulates endpoint access via decorators (e.g., locking AI report generation and observations to `specialist` and `admin` scopes).

### Sanitized Audit Trails (سجل مراجعة أمان النظام)
- Security audit logs are captured in a dedicated table `audit_logs` tracking system events (logins, registrations, AI generations, report approvals) without referencing any raw patient information (PHI).

---

## 2. Deferred Production Hardening (الخطوات المؤجلة للإنتاج المستقبلي)

| Security Aspect | Implementation status in POC | Required for Production |
|---|---|---|
| **Compliance Certification** | None (POC Only) | Requires full HIPAA, GDPR, and regional national health commission certifications. |
| **LLM Provider Agreement** | OpenRouter (Public endpoint) | Requires business-level BAA (Business Associate Agreement) or DPA (Data Processing Agreement) with private VPC LLM deployments. |
| **KMS Key Management** | Environment variable (`.env`) | Must transition to key management vaults such as HashiCorp Vault, AWS KMS, or Google Cloud KMS. |
| **File Upload Scanner** | Mocked function hook | Needs active virus scan container integration (e.g. ClamAV) and mime-type signature checks. |
| **Database Encryption** | Column-level Fernet | Requires full Transparent Data Encryption (TDE) at the database storage engine layer. |
