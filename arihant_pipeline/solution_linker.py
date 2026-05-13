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

        question_list = []

        solution_pool = []

        answer_key_pool = []

        # ---------------------------------------------
        # Separate objects, preserving order
        # ---------------------------------------------
        for q in questions:

            region_type = q.metadata.get(
                "region_type",
                "question"
            )

            if region_type == "question":

                question_list.append(q)

            elif region_type == "solution":

                solution_pool.append(q)

            elif region_type == "answer_key":

                answer_key_pool.append(q)

        # =================================================
        # LINK SOLUTIONS — positional: nth question ↔ nth solution
        # =================================================

        for i, solution in enumerate(solution_pool):

            if i >= len(question_list):
                break

            target = question_list[i]

            target.solution_text = (
                solution.solution_text
                or solution.question_text
            )

        # =================================================
        # LINK ANSWER KEYS
        # =================================================

        answer_map = self._build_answer_key_map(
            answer_key_pool
        )

        for question in question_list:

            if question.qid in answer_map:

                question.answer = answer_map[
                    question.qid
                ]

        # =================================================
        # BUILD FINAL LINKED OBJECTS
        # =================================================

        return [
            LinkedQuestion(
                qid=q.qid,
                question_text=q.question_text,
                options=q.options,
                answer=q.answer,
                solution_text=q.solution_text,
                question_type=q.question_type,
                confidence=q.confidence,
                metadata=q.metadata
            )
            for q in question_list
        ]

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