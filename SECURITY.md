# Security Policy

## Reporting a Vulnerability

Because Shortlist processes sensitive personal data (CVs/resumes and API keys), we take security vulnerabilities seriously.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them privately using GitHub Security Advisories ("Report a vulnerability" under the repository's **Security** tab) or by contacting the maintainers directly.

When reporting, please include:
- A clear description of the vulnerability and its potential impact.
- Steps to reproduce or a proof-of-concept.
- Affected versions or components (`api`, `worker`, `web`, `core`).

We aim to acknowledge receipt within **72 hours** and provide a remediation timeline once the issue is confirmed.

## Security Architecture

Shortlist is designed with defense-in-depth for self-hosted deployments:

- **Secrets & API Keys:** Provider API keys are encrypted at rest using Fernet symmetric encryption (`SHORTLIST_SECRET_KEY`), masked in API responses (e.g., `AIza…x9F2`), and never written to logs.
- **Authentication & Access Control:** Local authentication uses Argon2 password hashing, `httpOnly` session cookies, CSRF protection, and login rate limiting. Uploaded CV files are never exposed directly and are served only through authenticated API endpoints with access control.
- **File Ingestion Hardening:** Uploads are capped at 10 MB, MIME-checked, stored under regenerated filenames, and protected against zip bombs. DOCX macros are never executed.
- **Prompt Injection Defenses:** Hidden text (e.g., white-on-white or `< 2pt` font) is detected and flagged for manual review. CV content is wrapped in explicit delimiters as untrusted data. Scores are computed deterministically in code, and every positive/partial verdict requires a verified quote from the CV.
- **Logging:** Application logs record only identifiers and operational metadata—never raw CV text or personal data.
- **CI Scanning:** Dependencies and container images are scanned in CI (`pip-audit`, `npm audit`, and Trivy).

## Deployment Recommendations

- Always set a strong, unique `SHORTLIST_SECRET_KEY` in production.
- Terminate TLS in front of Shortlist (e.g., via Caddy, Traefik, or Nginx) when exposing it on a network.
- Keep the `/data` volume on encrypted storage with regular backups.
