from dataclasses import dataclass
from typing import List
import re


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class VerificationIssue:
    """
    Represents a verification issue found in the
    final extracted academic object.
    """

    severity: str

    message: str


# =========================================================
# EXTRACTION VERIFIER
# =========================================================

class ExtractionVerifier:
    """
    Final quality-assurance stage for extracted
    educational QA objects.

    Responsibilities:
    - verify structural integrity
    - verify MCQ completeness
    - verify answer consistency
    - detect OCR corruption
    - detect truncation
    - compute verification confidence

    IMPORTANT:
    This stage SHOULD NOT silently repair data.
    It should:
    - detect
    - flag
    - score
    - recommend retries
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        self.minimum_question_words = getattr(
            config,
            "minimum_question_words",
            3
        )

        self.minimum_solution_words = getattr(
            config,
            "minimum_solution_words",
            5
        )

        self.minimum_verification_score = getattr(
            config,
            "minimum_verification_score",
            0.50
        )

    # =====================================================
    # PUBLIC API
    # =====================================================

    def verify(
        self,
        linked_questions
    ):

        verified_questions = []

        for question in linked_questions:

            issues = []

            # -----------------------------------------
            # Question validation
            # -----------------------------------------
            issues.extend(
                self._verify_question_structure(
                    question
                )
            )

            # -----------------------------------------
            # MCQ validation
            # -----------------------------------------
            if question.question_type == "mcq":

                issues.extend(
                    self._verify_mcq(
                        question
                    )
                )

            # -----------------------------------------
            # Answer validation
            # -----------------------------------------
            issues.extend(
                self._verify_answer(
                    question
                )
            )

            # -----------------------------------------
            # Solution validation
            # -----------------------------------------
            issues.extend(
                self._verify_solution(
                    question
                )
            )

            # -----------------------------------------
            # OCR sanity checks
            # -----------------------------------------
            issues.extend(
                self._verify_ocr_quality(
                    question
                )
            )

            # -----------------------------------------
            # Equation sanity
            # -----------------------------------------
            issues.extend(
                self._verify_equations(
                    question
                )
            )

            # -----------------------------------------
            # Compute verification score
            # -----------------------------------------
            verification_score = (
                self._compute_score(
                    issues
                )
            )

            # -----------------------------------------
            # Attach metadata
            # -----------------------------------------
            question.verification_issues = issues

            question.verification_score = (
                verification_score
            )

            question.verified = (
                verification_score
                >= self.minimum_verification_score
            )

            question.retry_recommended = (
                verification_score < 0.70
            )

            verified_questions.append(
                question
            )

        return verified_questions

    # =====================================================
    # QUESTION STRUCTURE VERIFICATION
    # =====================================================

    def _verify_question_structure(
        self,
        question
    ) -> List[VerificationIssue]:

        issues = []

        text = (
            question.question_text or ""
        ).strip()

        # ---------------------------------------------
        # Empty question
        # ---------------------------------------------
        if not text:

            issues.append(
                VerificationIssue(
                    severity="high",
                    message="Empty question text"
                )
            )

            return issues

        # ---------------------------------------------
        # Tiny question
        # ---------------------------------------------
        if (
            len(text.split())
            < self.minimum_question_words
        ):

            issues.append(
                VerificationIssue(
                    severity="medium",
                    message="Very short question"
                )
            )

        # ---------------------------------------------
        # Truncation indicators
        # ---------------------------------------------
        if text.endswith("="):

            issues.append(
                VerificationIssue(
                    severity="high",
                    message="Possible equation truncation"
                )
            )

        if text.endswith("("):

            issues.append(
                VerificationIssue(
                    severity="high",
                    message="Unclosed expression"
                )
            )

        return issues

    # =====================================================
    # MCQ VERIFICATION
    # =====================================================

    def _verify_mcq(
        self,
        question
    ) -> List[VerificationIssue]:

        issues = []

        options = question.options or {}

        expected = {"A", "B", "C", "D"}

        actual = set(options.keys())

        # ---------------------------------------------
        # Missing options
        # ---------------------------------------------
        missing = expected - actual

        if missing:

            issues.append(
                VerificationIssue(
                    severity="high",
                    message=(
                        f"Missing MCQ options: "
                        f"{sorted(missing)}"
                    )
                )
            )

        # ---------------------------------------------
        # Duplicate option text
        # ---------------------------------------------
        values = list(options.values())

        if len(values) != len(set(values)):

            issues.append(
                VerificationIssue(
                    severity="medium",
                    message="Duplicate MCQ options"
                )
            )

        return issues

    # =====================================================
    # ANSWER VERIFICATION
    # =====================================================

    def _verify_answer(
        self,
        question
    ) -> List[VerificationIssue]:

        issues = []

        answer = question.answer

        if not answer:
            return issues

        # ---------------------------------------------
        # MCQ answer mismatch
        # ---------------------------------------------
        if question.question_type == "mcq":

            if answer not in question.options:

                issues.append(
                    VerificationIssue(
                        severity="high",
                        message=(
                            f"Answer '{answer}' "
                            f"not present in options"
                        )
                    )
                )

        return issues

    # =====================================================
    # SOLUTION VERIFICATION
    # =====================================================

    def _verify_solution(
        self,
        question
    ) -> List[VerificationIssue]:

        issues = []

        solution = (
            question.solution_text or ""
        ).strip()

        if not solution:
            return issues

        # ---------------------------------------------
        # Tiny solution
        # ---------------------------------------------
        if (
            len(solution.split())
            < self.minimum_solution_words
        ):

            issues.append(
                VerificationIssue(
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

            "thus",

            "given",

            "solution",
        ]

        hits = sum(
            word in solution.lower()
            for word in derivation_words
        )

        if hits == 0:

            issues.append(
                VerificationIssue(
                    severity="low",
                    message="Weak derivation structure"
                )
            )

        return issues

    # =====================================================
    # OCR QUALITY VERIFICATION
    # =====================================================

    def _verify_ocr_quality(
        self,
        question
    ) -> List[VerificationIssue]:

        issues = []

        text = (
            question.question_text
            + " "
            + (question.solution_text or "")
        )

        # ---------------------------------------------
        # Weird character ratio
        # ---------------------------------------------
        weird_chars = len(
            re.findall(
                r"[�□◊]",
                text
            )
        )

        ratio = weird_chars / max(
            len(text),
            1
        )

        if ratio > 0.05:

            issues.append(
                VerificationIssue(
                    severity="high",
                    message="Heavy OCR corruption"
                )
            )

        # ---------------------------------------------
        # Excessive repeated chars
        # ---------------------------------------------
        repeated = re.findall(
            r"(.)\1{5,}",
            text
        )

        if repeated:

            issues.append(
                VerificationIssue(
                    severity="medium",
                    message="Suspicious repeated characters"
                )
            )

        return issues

    # =====================================================
    # EQUATION VERIFICATION
    # =====================================================

    def _verify_equations(
        self,
        question
    ) -> List[VerificationIssue]:

        issues = []

        text = (
            question.question_text
            + " "
            + (question.solution_text or "")
        )

        # ---------------------------------------------
        # Unbalanced parentheses
        # ---------------------------------------------
        if text.count("(") != text.count(")"):

            issues.append(
                VerificationIssue(
                    severity="medium",
                    message="Unbalanced parentheses"
                )
            )

        # ---------------------------------------------
        # Unbalanced brackets
        # ---------------------------------------------
        if text.count("[") != text.count("]"):

            issues.append(
                VerificationIssue(
                    severity="medium",
                    message="Unbalanced brackets"
                )
            )

        return issues

    # =====================================================
    # SCORE COMPUTATION
    # =====================================================

    def _compute_score(
        self,
        issues
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

    def print_verification_summary(
        self,
        verified_questions
    ):

        print(
            "\n========== VERIFICATION SUMMARY ==========\n"
        )

        for q in verified_questions:

            print(
                f"QID={q.qid} | "
                f"Verified={q.verified} | "
                f"Score={q.verification_score:.2f}"
            )

            if q.verification_issues:

                for issue in q.verification_issues:

                    print(
                        f"   [{issue.severity.upper()}] "
                        f"{issue.message}"
                    )

            else:

                print(
                    "   No verification issues."
                )

            print("-" * 80)