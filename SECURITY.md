# Security & Dependency Management Policy

## 1. Overview & Scope
This policy defines the dependency vulnerability scanning and remediation standards for the E-Signature Platform in accordance with **OWASP A06 (Vulnerable and Outdated Components)**.

The security scanning pipeline encompasses:
- **Backend (Python)**: Production dependencies declared in sign-backend/requirements.txt scanned via pip-audit.
- **Frontend (Node.js)**: Client-side and build dependencies in sign-frontend/package.json and package-lock.json scanned via 
pm audit.

---

## 2. Dependency Classification & Enforcement Policy

### A. Production Dependencies (Runtime)
Production dependencies are deployed to the live application environment or compiled directly into the client-facing distribution bundle.

| Severity | CI/CD Action | Remediation SLA |
| :--- | :--- | :--- |
| **CRITICAL** | **FAIL CI** (Blocks Merge & Deployment) | Immediate (< 24 hours) |
| **HIGH** | **FAIL CI** (Blocks Merge & Deployment) | Within 7 days |
| **MEDIUM** | **FAIL CI** (If applicable to runtime code) | Next planned sprint |
| **LOW** | **REPORT** (Informational log) | Periodic review |

### B. Development / Tooling Dependencies (Build-Time Only)
Development dependencies (e.g. test runners, linters, local dev servers) do not execute in production runtime or expose customer data.

- **CI Action**: **REPORT & AUDIT**
- Development vulnerabilities do not automatically fail production deployment pipelines unless they introduce build artifact compromise (supply chain risk).
- Automated 
pm audit --omit=dev is enforced as the gating gate for production builds.

---

## 3. Tooling & Execution

### Backend Scanning (pip-audit)
- **Engine**: pip-audit querying PyPI and OSV databases.
- **CI Invocation**:
  `ash
  pip-audit -r esign-backend/requirements.txt --desc
  `

### Frontend Scanning (
pm audit)
- **Production Gate**:
  `ash
  npm audit --omit=dev --audit-level=high
  `
- **Development Advisory Report**:
  `ash
  npm audit || true
  `

---

## 4. Exception & Waiver Process
If a false positive or unexploitable vulnerability is detected:
1. Document the CVE/GHSA identifier.
2. Document the technical rationale demonstrating why the vulnerability is not exploitable in the application architecture.
3. Define an expiration date for the exception (maximum 90 days).
4. Require engineering lead and security reviewer sign-off before committing an exception filter.

---

## 5. Automated CI/CD Triggers
Security scans execute automatically:
- On every pull request to main.
- On every push to main.
- On any modification to dependency manifests (
equirements.txt, package.json, package-lock.json).
- On a scheduled recurring cron basis (weekly) to detect newly published CVEs against static dependencies.
