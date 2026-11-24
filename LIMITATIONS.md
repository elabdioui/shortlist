# Known Limitations

Shortlist is designed to be transparent about what it can and cannot do.

## 1. Decision Support, Not Automated Decision-Making
- Shortlist helps recruiters prioritize which CVs to read first. It **never** makes hiring or rejection decisions.
- Every candidate marked "Not shortlisted, to confirm" still requires human confirmation.

## 2. Evaluation Accuracy & Benchmarks
- Accuracy and ranking correlation metrics are measured only on Shortlist's synthetic evaluation dataset (`eval/`). Real-world performance varies based on CV formatting, domain terminology, language, and the chosen LLM.
- **Scores are not comparable across different models or prompt versions.** If a fallback model is used during a run, it is flagged in the ranking table.

## 3. Anonymization Limits
- Local anonymization (Presidio + spaCy + regex rules) removes explicit PII such as names, emails, phone numbers, CINs, and addresses.
- However, **indirect identifying cues** may remain in the text (e.g., specific employer names, niche schools, project titles, or writing style). For maximum privacy, use the local **Ollama** profile.

## 4. Document Extraction & OCR
- In the MVP, OCR (Tesseract) supports **French and English** only.
- Low-resolution scans, handwritten annotations, or heavily stylized graphic CVs may yield incomplete or noisy text extraction.
- Extremely long CVs are truncated to approximately **6,000 tokens**, with a warning shown in the UI.

## 5. Prompt Injection & Adversarial Inputs
- Shortlist detects hidden text (e.g., white-on-white or `< 2pt` fonts), wraps CV text in delimiters, computes scores deterministically in code, and verifies every quoted evidence snippet against the extracted CV text.
- While these measures mitigate prompt injection, no LLM-based system is 100% immune to novel adversarial phrasing. CVs with suspicious formatting are routed to manual review.
