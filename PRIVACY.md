# Privacy & Data Protection

Shortlist processes CVs and candidate records, which constitute personal data under regulations such as **GDPR** (EU) and **Law 09-08 / CNDP** (Morocco).

> **Important:** Self-hosting Shortlist does **not** automatically make your organization legally compliant. As the deploying organization, you remain the data controller and are responsible for lawful basis, candidate notices, retention policies, and access controls.

## Privacy by Design

### 1. Local PII Anonymization
Before any CV text is sent to an external LLM provider, Shortlist runs a local anonymization pipeline (Microsoft Presidio + spaCy + custom rules) that replaces:
- Names, email addresses, phone numbers (including Moroccan formats `+212`, `06`, `07`), and national IDs (CIN)
- Physical addresses, LinkedIn and GitHub URLs
- Age, date of birth, marital status, and nationality

These are replaced with placeholders (`[NOM]`, `[EMAIL]`, etc.). The mapping table is stored encrypted in the local database and is never transmitted to external providers. Recruiters can preview the exact anonymized text before launching an analysis.

### 2. 100% Local Mode (Ollama)
If you want zero data to leave your infrastructure, enable the `ollama` profile in `deploy/docker-compose.yml` and configure an Ollama model profile. No CV data is sent to third-party servers.

### 3. External Providers & Free Tiers
Each job clearly displays whether data is processed locally or sent anonymized to an external provider. When configuring a free-tier API key, Shortlist displays an explicit warning: some providers may use free-tier requests to train or improve their models.

### 4. Data Retention, Erasure, and Audit
- **Configurable retention:** Default retention is 6 months after a job is closed, with automatic purge.
- **Right to erasure:** Individual candidates or entire jobs (including all uploaded files and evaluations) can be permanently deleted on demand.
- **Audit log:** Consultations, exports, and deletions are recorded in `audit_log`.

## Candidate Information Notice (Template)

Organizations using Shortlist should inform candidates in their job postings or application forms. Below is a suggested starting point (adapt to your legal requirements):

**English:**
> Your application and CV may be analyzed with the assistance of an automated AI screening tool to help our recruiting team review qualifications against the job criteria. No automated rejection decision is made—a human reviewer makes every hiring decision. You may request human review or exercise your data access/deletion rights by contacting [contact email].

**Français :**
> Votre candidature et votre CV peuvent être analysés à l'aide d'un outil d'assistance par intelligence artificielle afin d'aider notre équipe de recrutement à évaluer l'adéquation avec les critères du poste. Aucun rejet automatique n'est effectué : une personne prend chaque décision finale. Vous pouvez demander une révision humaine ou exercer vos droits d'accès et de suppression en contactant [email de contact].
