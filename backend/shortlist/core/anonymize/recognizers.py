# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Custom Presidio PatternRecognizers for Moroccan and international CV PII."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


def build_moroccan_phone_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize Moroccan (+212, 06, 07, 05) and international phone numbers."""
    patterns = [
        Pattern(
            name="ma_intl_phone",
            regex=r"(?:\+212|00212)[ .-]?(?:5|6|7)(?:[ .-]?\d){8}\b",
            score=0.95,
        ),
        Pattern(
            name="ma_local_phone",
            regex=r"\b0(?:5|6|7)(?:[ .-]?\d{2}){4}\b",
            score=0.90,
        ),
        Pattern(
            name="generic_intl_phone",
            regex=r"\+\d{1,3}[ .-]?\(?\d{1,4}\)?(?:[ .-]?\d{2,4}){2,4}\b",
            score=0.80,
        ),
    ]
    return PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        patterns=patterns,
        supported_language=language,
        name="MoroccanPhoneRecognizer",
    )


def build_moroccan_cin_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize Moroccan National ID (CIN) numbers such as AB123456 or K123456."""
    patterns = [
        Pattern(
            name="ma_cin_labeled",
            regex=r"\b(?:CIN|C\.I\.N\.?|CNI)\s*:?\s*[A-Z]{1,2}\s?\d{5,6}\b",
            score=0.95,
        ),
        Pattern(
            name="ma_cin_standalone",
            regex=r"\b[A-Z]{1,2}\d{5,6}\b",
            score=0.75,
        ),
    ]
    return PatternRecognizer(
        supported_entity="MA_CIN",
        patterns=patterns,
        supported_language=language,
        context=["cin", "cni", "carte nationale", "identité", "identite"],
        name="MoroccanCINRecognizer",
    )


def build_email_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize email addresses."""
    return PatternRecognizer(
        supported_entity="EMAIL_ADDRESS",
        patterns=[
            Pattern(
                name="email",
                regex=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                score=0.95,
            )
        ],
        supported_language=language,
        name="CustomEmailRecognizer",
    )


def build_profile_url_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize LinkedIn and GitHub profile URLs."""
    return PatternRecognizer(
        supported_entity="PROFILE_URL",
        patterns=[
            Pattern(
                name="linkedin_github_url",
                regex=(
                    r"(?:https?://)?(?:www\.)?"
                    r"(?:linkedin\.com/in|github\.com)/[A-Za-z0-9._-]+/?"
                ),
                score=0.95,
            )
        ],
        supported_language=language,
        name="ProfileURLRecognizer",
    )


def build_address_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize street addresses and postal-code + city lines."""
    patterns = [
        Pattern(
            name="street_address",
            regex=(
                r"\b\d{1,4}[, ]+(?:rue|avenue|av\.?|boulevard|bd\.?|lotissement|lot|"
                r"quartier|résidence|residence|impasse|allée|street|st\.?|road|rd\.?|ave\.?)"
                r"\s+[^\n,;]{3,60}"
            ),
            score=0.85,
        ),
        Pattern(
            name="postal_city",
            regex=(
                r"\b\d{5}\s+(?:Casablanca|Rabat|Marrakech|Tanger|Fès|Fes|Agadir|"
                r"Meknès|Meknes|Oujda|Kénitra|Kenitra|Tétouan|Tetouan|Salé|Sale|"
                r"Mohammedia|Paris|Lyon|Marseille|Toulouse|Lille)\b"
            ),
            score=0.85,
        ),
        Pattern(
            name="labeled_address",
            regex=r"\b(?:Adresse|Address)\s*:?\s*[^\n]{5,80}",
            score=0.85,
        ),
    ]
    return PatternRecognizer(
        supported_entity="STREET_ADDRESS",
        patterns=patterns,
        supported_language=language,
        name="AddressRecognizer",
    )


def build_age_dob_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize birth dates and explicit ages."""
    patterns = [
        Pattern(
            name="dob_labeled",
            regex=(
                r"\b(?:né(?:\(e\))?\s*le|née\s*le|date de naissance|birth\s*date|dob)"
                r"\s*:?\s*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"
            ),
            score=0.95,
        ),
        Pattern(
            name="age_years",
            regex=r"\b(?:âge|age)\s*:?\s*\d{2}(?:\s*(?:ans|years?\s*old))?\b",
            score=0.90,
        ),
        Pattern(
            name="explicit_years_old",
            regex=r"\b(?:1[89]|[2-6]\d)\s*(?:ans|years?\s*old)\b",
            score=0.80,
        ),
    ]
    return PatternRecognizer(
        supported_entity="AGE_OR_DOB",
        patterns=patterns,
        supported_language=language,
        name="AgeDOBRecognizer",
    )


def build_marital_status_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize marital / family status mentions."""
    patterns = [
        Pattern(
            name="marital_labeled",
            regex=(
                r"\b(?:situation\s+familiale|état\s+civil|etat\s+civil|marital\s+status)"
                r"\s*:?\s*[A-Za-zÀ-ÿ -]{3,25}"
            ),
            score=0.90,
        ),
        Pattern(
            name="marital_keywords",
            regex=(
                r"\b(?:célibataire|celibataire|marié\(e\)?|marie\(e\)?|"
                r"divorcé\(e\)?|veuf|veuve|single|married|divorced|widowed)\b"
            ),
            score=0.80,
        ),
    ]
    return PatternRecognizer(
        supported_entity="MARITAL_STATUS",
        patterns=patterns,
        supported_language=language,
        name="MaritalStatusRecognizer",
    )


def build_nationality_recognizer(language: str = "fr") -> PatternRecognizer:
    """Recognize nationality mentions."""
    patterns = [
        Pattern(
            name="nationality_labeled",
            regex=r"\b(?:nationalité|nationalite|nationality)\s*:?\s*[A-Za-zÀ-ÿ -]{3,30}",
            score=0.90,
        ),
        Pattern(
            name="nationality_keywords",
            regex=(
                r"\b(?:marocain(?:e)?|français(?:e)?|moroccan|french|"
                r"tunisien(?:ne)?|algérien(?:ne)?|algerien(?:ne)?)\b"
            ),
            score=0.75,
        ),
    ]
    return PatternRecognizer(
        supported_entity="NATIONALITY",
        patterns=patterns,
        supported_language=language,
        name="NationalityRecognizer",
    )


def build_person_name_heuristic_recognizer(language: str = "fr") -> PatternRecognizer:
    """Fallback heuristic recognizer for person names when spaCy NER models are absent."""
    patterns = [
        Pattern(
            name="labeled_person_name",
            regex=(
                r"(?:Nom\s*(?:&|et)?\s*Prénom|Nom\s+complet|Full\s*Name|Candidat|Name|Nom)"
                r"\s*:\s*([A-ZÀ-Ÿ][a-zà-ÿ'-]+(?:\s+[A-ZÀ-Ÿ][A-Za-zÀ-ÿ'-]+){1,2})"
            ),
            score=0.85,
        ),
    ]
    return PatternRecognizer(
        supported_entity="PERSON",
        patterns=patterns,
        supported_language=language,
        name="PersonNameHeuristicRecognizer",
    )


def build_custom_recognizers(language: str = "fr") -> list[PatternRecognizer]:
    """Return all custom PII recognizers for a given language."""
    return [
        build_moroccan_phone_recognizer(language),
        build_moroccan_cin_recognizer(language),
        build_email_recognizer(language),
        build_profile_url_recognizer(language),
        build_address_recognizer(language),
        build_age_dob_recognizer(language),
        build_marital_status_recognizer(language),
        build_nationality_recognizer(language),
        build_person_name_heuristic_recognizer(language),
    ]
