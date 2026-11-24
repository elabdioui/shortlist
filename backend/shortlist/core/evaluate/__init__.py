# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""CV evaluation and criteria generation package."""

from shortlist.core.evaluate.criteria_generator import (
    CriteriaGenerationResult,
    detect_discriminatory_reason,
    generate_criteria,
)
from shortlist.core.evaluate.evaluator import (
    CV_END_DELIMITER,
    CV_START_DELIMITER,
    EvaluationCallResult,
    build_evaluation_messages,
    evaluate_cv,
    load_prompt,
)

__all__ = [
    "CV_END_DELIMITER",
    "CV_START_DELIMITER",
    "CriteriaGenerationResult",
    "EvaluationCallResult",
    "build_evaluation_messages",
    "detect_discriminatory_reason",
    "evaluate_cv",
    "generate_criteria",
    "load_prompt",
]
