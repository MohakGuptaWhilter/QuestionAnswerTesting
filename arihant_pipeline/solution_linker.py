from dataclasses import dataclass
from typing import List, Dict, Optional
import re


# =========================================================
# DATA MODEL
# =========================================================

@dataclass
class LinkedQuestion:
    """
    Final linked educational QA object.
    """

    qid: Optional[str]

    question_text: str

    options: dict

    answer: Optional[str]

    solution_text: Optional[str]

    question_type: str

    confidence: float

    metadata: dict


# =========================================================
# SOLUTION LINKER
# =========================================================

class SolutionLinker:
    """
    Links questions with corresponding solutions
    and answer keys.

    Responsibilities:
    - attach solutions to questions
    - attach answer keys
    - resolve orphan solutions
    - preserve linkage metadata

    IMPORTANT:
    This stage performs semantic alignment.
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

    # =====================================================
    # PUBLIC API
    # =====================================================

    def link(
        self,
        questions
    ) -> List[LinkedQuestion]:

        linked_questions = []

        question_map = {}

        solution_pool = []

        answer_key_pool = []

        # ---------------------------------------------
        # Separate objects
        # ---------------------------------------------
        for q in questions:

            region_type = q.metadata.get(
                "region_type",
                "question"
            )

            # -----------------------------------------
            # Questions
            # -----------------------------------------
            if region_type == "question":

                question_map[q.qid] = q

            # -----------------------------------------
            # Solutions
            # -----------------------------------------
            elif region_type == "solution":

                solution_pool.append(q)

            # -----------------------------------------
            # Answer keys
            # -----------------------------------------
            elif region_type == "answer_key":

                answer_key_pool.append(q)

        # =================================================
        # LINK SOLUTIONS
        # =================================================

        for solution in solution_pool:

            qid = solution.qid

            if qid in question_map:

                target = question_map[qid]

                solution_text = (
                    solution.solution_text
                    or solution.question_text
                )

                target.solution_text = solution_text

                # Confidence boost
                target.confidence = min(
                    1.0,
                    target.confidence + 0.05
                )

            else:

                # -------------------------------------
                # Attempt fallback linkage
                # -------------------------------------
                fallback_qid = (
                    self._fallback_match_solution(
                        solution,
                        question_map
                    )
                )

                if fallback_qid:

                    target = question_map[
                        fallback_qid
                    ]

                    target.solution_text = (
                        solution.solution_text
                        or solution.question_text
                    )

                    target.metadata[
                        "fallback_solution_match"
                    ] = True

        # =================================================
        # LINK ANSWER KEYS
        # =================================================

        answer_map = self._build_answer_key_map(
            answer_key_pool
        )

        for qid, question in question_map.items():

            if qid in answer_map:

                question.answer = answer_map[qid]

        # =================================================
        # BUILD FINAL LINKED OBJECTS
        # =================================================

        for qid, question in question_map.items():

            linked_questions.append(

                LinkedQuestion(

                    qid=question.qid,

                    question_text=
                        question.question_text,

                    options=question.options,

                    answer=question.answer,

                    solution_text=
                        question.solution_text,

                    question_type=
                        question.question_type,

                    confidence=
                        question.confidence,

                    metadata=question.metadata
                )
            )

        return linked_questions

    # =====================================================
    # FALLBACK MATCHING
    # =====================================================

    def _fallback_match_solution(
        self,
        solution,
        question_map
    ) -> Optional[str]:
        """
        Attempt fuzzy linkage when exact
        qid matching fails.
        """

        solution_qid = solution.qid

        if not solution_qid:
            return None

        # ---------------------------------------------
        # Normalize numeric IDs
        # ---------------------------------------------
        digits = re.findall(
            r"\d+",
            str(solution_qid)
        )

        if not digits:
            return None

        normalized = digits[0]

        for qid in question_map.keys():

            q_digits = re.findall(
                r"\d+",
                str(qid)
            )

            if not q_digits:
                continue

            if q_digits[0] == normalized:

                return qid

        return None

    # =====================================================
    # ANSWER KEY PARSING
    # =====================================================

    def _build_answer_key_map(
        self,
        answer_key_pool
    ) -> Dict[str, str]:
        """
        Build:
            {
                "1": "A",
                "2": "C"
            }
        """

        answer_map = {}

        pattern = re.compile(
            r"(\d+)\.\(?([A-D])\)?",
            re.I
        )

        for answer_key in answer_key_pool:

            text = answer_key.question_text

            matches = pattern.findall(text)

            for qid, ans in matches:

                answer_map[qid] = ans.upper()

        return answer_map

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_link_summary(
        self,
        linked_questions
    ):

        print(
            "\n========== LINKED QUESTIONS ==========\n"
        )

        for q in linked_questions:

            print(
                f"QID={q.qid} | "
                f"Type={q.question_type} | "
                f"Confidence={q.confidence:.2f}"
            )

            print("\nQUESTION:")
            print(q.question_text[:300])

            if q.options:

                print("\nOPTIONS:")

                for k, v in q.options.items():

                    print(f"{k}: {v}")

            if q.answer:

                print(f"\nANSWER: {q.answer}")

            if q.solution_text:

                print("\nSOLUTION:")
                print(q.solution_text[:300])

            print("-" * 80)