from dataclasses import dataclass
from typing import List
import re


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class ValidationIssue:
    """
    Represents a validation issue inside a semantic region.
    """

    severity: str

    message: str


# =========================================================
# REGION VALIDATOR
# =========================================================

class RegionValidator:
    """
    Validates semantic regions before crop generation.

    Responsibilities:
    - validate question completeness
    - validate MCQ integrity
    - validate solution structure
    - detect truncation
    - detect figure mismatches
    - compute validation confidence

    IMPORTANT:
    This stage SHOULD NOT silently modify regions.
    It should:
    - detect
    - flag
    - score
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        self.minimum_question_words = getattr(
            config,
            "minimum_question_words",
            5
        )

        self.minimum_valid_score = getattr(
            config,
            "minimum_valid_score",
            0.50
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def validate(
        self,
        semantic_regions
    ):

        validated_regions = []

        for region in semantic_regions:

            issues = []

            # -----------------------------------------
            # Question validation
            # -----------------------------------------
            if region.region_type == "question":

                issues.extend(
                    self._validate_question(region)
                )

            # -----------------------------------------
            # Solution validation
            # -----------------------------------------
            elif region.region_type == "solution":

                issues.extend(
                    self._validate_solution(region)
                )

            # -----------------------------------------
            # Example validation
            # -----------------------------------------
            elif region.region_type == "example":

                issues.extend(
                    self._validate_example(region)
                )

            # -----------------------------------------
            # Answer key validation
            # -----------------------------------------
            elif region.region_type == "answer_key":

                issues.extend(
                    self._validate_answer_key(region)
                )

            # -----------------------------------------
            # Compute validation score
            # -----------------------------------------
            validation_score = self._compute_score(
                issues
            )

            # -----------------------------------------
            # Attach validation metadata
            # -----------------------------------------
            region.validation_issues = issues

            region.validation_score = validation_score

            region.is_valid = (
                validation_score
                >= self.minimum_valid_score
            )

            region.retry_recommended = (
                validation_score < 0.70
            )

            validated_regions.append(region)

        return validated_regions

    # =====================================================
    # QUESTION VALIDATION
    # =====================================================

    def _validate_question(
        self,
        region
    ) -> List[ValidationIssue]:

        issues = []

        text = region.text.strip()

        # ---------------------------------------------
        # Empty / tiny question
        # ---------------------------------------------
        if (
            len(text.split())
            < self.minimum_question_words
        ):

            issues.append(
                ValidationIssue(
                    severity="high",
                    message="Question too short"
                )
            )

        # ---------------------------------------------
        # Incomplete MCQ options
        # ---------------------------------------------
        option_hits = sum(
            option in text
            for option in [
                "(A)",
                "(B)",
                "(C)",
                "(D)"
            ]
        )

        if 0 < option_hits < 4:

            issues.append(
                ValidationIssue(
                    severity="medium",
                    message="Incomplete MCQ options"
                )
            )

        # ---------------------------------------------
        # Truncated equation
        # ---------------------------------------------
        if text.endswith("="):

            issues.append(
                ValidationIssue(
                    severity="high",
                    message="Possible equation truncation"
                )
            )

        # ---------------------------------------------
        # Figure referenced but missing
        # ---------------------------------------------
        references_figure = any(
            keyword in text.lower()
            for keyword in [
                "figure",
                "fig.",
                "diagram",
                "shown below",
                "graph below",
            ]
        )

        figure_count = len(
            getattr(
                region,
                "figure_blocks",
                []
            )
        )

        if references_figure and figure_count == 0:

            issues.append(
                ValidationIssue(
                    severity="medium",
                    message="Figure referenced but not linked"
                )
            )

        # ---------------------------------------------
        # Multiple question anchors inside one region
        # ---------------------------------------------
        multiple_questions = len(
            re.findall(
                r"(Q\.?\s*\d+)|(^\d+\.)",
                text,
                re.M
            )
        )

        if multiple_questions >= 2:

            issues.append(
                ValidationIssue(
                    severity="high",
                    message="Possible multi-question merge"
                )
            )

        return issues

    # =====================================================
    # SOLUTION VALIDATION
    # =====================================================

    def _validate_solution(
        self,
        region
    ) -> List[ValidationIssue]:

        issues = []

        text = region.text.lower()

        # ---------------------------------------------
        # Tiny solution
        # ---------------------------------------------
        if len(text.split()) < 10:

            issues.append(
                ValidationIssue(
                    severity="medium",
                    message="Very short solution"
                )
            )

        # ---------------------------------------------
        # Weak derivation structure
        # ---------------------------------------------
        derivation_words = [
            "therefore",
            "hence",
            "given",
            "solution",
            "thus",
        ]

        derivation_hits = sum(
            word in text
            for word in derivation_words
        )

        if derivation_hits == 0:

            issues.append(
                ValidationIssue(
                    severity="medium",
                    message="Weak derivation structure"
                )
            )

        return issues

    # =====================================================
    # EXAMPLE VALIDATION
    # =====================================================

    def _validate_example(
        self,
        region
    ) -> List[ValidationIssue]:

        issues = []

        # ---------------------------------------------
        # Tiny example
        # ---------------------------------------------
        if len(region.blocks) < 2:

            issues.append(
                ValidationIssue(
                    severity="low",
                    message="Tiny example region"
                )
            )

        # ---------------------------------------------
        # Weak explanatory structure
        # ---------------------------------------------
        explanatory_words = [
            "therefore",
            "hence",
            "solution",
            "step",
        ]

        text = region.text.lower()

        hits = sum(
            word in text
            for word in explanatory_words
        )

        if hits == 0:

            issues.append(
                ValidationIssue(
                    severity="low",
                    message="Weak example explanation"
                )
            )

        return issues

    # =====================================================
    # ANSWER KEY VALIDATION
    # =====================================================

    def _validate_answer_key(
        self,
        region
    ) -> List[ValidationIssue]:

        issues = []

        text = region.text

        matches = re.findall(
            r"\d+\.\([A-D]\)",
            text
        )

        if len(matches) < 3:

            issues.append(
                ValidationIssue(
                    severity="medium",
                    message="Sparse answer key pattern"
                )
            )

        return issues

    # =====================================================
    # SCORE COMPUTATION
    # =====================================================

    def _compute_score(
        self,
        issues: List[ValidationIssue]
    ) -> float:

        score = 1.0

        for issue in issues:

            if issue.severity == "high":
                score -= 0.40

            elif issue.severity == "medium":
                score -= 0.20

            elif issue.severity == "low":
                score -= 0.10

        return max(score, 0.0)

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_validation_summary(
        self,
        validated_regions
    ):

        print(
            "\n========== REGION VALIDATION ==========\n"
        )

        for region in validated_regions:

            print(
                f"[{region.region_type.upper()}] "
                f"QID={region.qid} | "
                f"Score={region.validation_score:.2f} | "
                f"Valid={region.is_valid}"
            )

            if region.validation_issues:

                for issue in region.validation_issues:

                    print(
                        f"   [{issue.severity.upper()}] "
                        f"{issue.message}"
                    )

            else:

                print("   No validation issues.")

            print("-" * 80)