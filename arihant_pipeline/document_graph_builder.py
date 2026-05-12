from dataclasses import dataclass, field
from typing import List, Dict, Optional
import uuid
import re


# =========================================================
# GRAPH DATA MODELS
# =========================================================

@dataclass
class GraphNode:
    """
    Represents a node in the academic document graph.
    """

    node_id: str

    node_type: str

    label: str

    metadata: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """
    Represents a relationship between two nodes.
    """

    edge_id: str

    source_id: str

    target_id: str

    relation: str

    weight: float = 1.0

    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentGraph:
    """
    Complete academic document graph.
    """

    nodes: List[GraphNode]

    edges: List[GraphEdge]

    metadata: dict = field(default_factory=dict)


# =========================================================
# DOCUMENT GRAPH BUILDER
# =========================================================

class DocumentGraphBuilder:
    """
    Builds a connected academic knowledge graph.

    Responsibilities:
    - create question nodes
    - create solution nodes
    - create concept nodes
    - create semantic relationships
    - preserve provenance metadata

    IMPORTANT:
    This stage converts extracted educational
    objects into connected knowledge.
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

        # ---------------------------------------------
        # Lightweight concept keywords
        # ---------------------------------------------
        self.concept_keywords = {

            "kinematics": [
                "velocity",
                "acceleration",
                "displacement",
                "motion",
            ],

            "calculus": [
                "integration",
                "differentiate",
                "derivative",
                "limit",
            ],

            "electrostatics": [
                "charge",
                "electric field",
                "potential",
            ],

            "thermodynamics": [
                "heat",
                "entropy",
                "temperature",
            ],
        }

    # =====================================================
    # PUBLIC API
    # =====================================================

    def build(
        self,
        verified_questions
    ) -> DocumentGraph:

        nodes = []

        edges = []

        question_node_map = {}

        concept_node_map = {}

        # =================================================
        # CREATE QUESTION/SOLUTION NODES
        # =================================================

        for question in verified_questions:

            # ---------------------------------------------
            # Question node
            # ---------------------------------------------
            q_node = self._build_question_node(
                question
            )

            nodes.append(q_node)

            question_node_map[
                question.qid
            ] = q_node

            # ---------------------------------------------
            # Solution node
            # ---------------------------------------------
            if question.solution_text:

                s_node = self._build_solution_node(
                    question
                )

                nodes.append(s_node)

                # Link solution -> question
                edges.append(

                    self._build_edge(

                        source_id=s_node.node_id,

                        target_id=q_node.node_id,

                        relation="solves",

                        weight=1.0
                    )
                )

            # ---------------------------------------------
            # Answer node
            # ---------------------------------------------
            if question.answer:

                a_node = self._build_answer_node(
                    question
                )

                nodes.append(a_node)

                edges.append(

                    self._build_edge(

                        source_id=q_node.node_id,

                        target_id=a_node.node_id,

                        relation="has_answer",

                        weight=1.0
                    )
                )

        # =================================================
        # CONCEPT EXTRACTION
        # =================================================

        for question in verified_questions:

            q_node = question_node_map.get(
                question.qid
            )

            concepts = self._extract_concepts(
                question
            )

            for concept in concepts:

                # -----------------------------------------
                # Reuse concept node if exists
                # -----------------------------------------
                if concept not in concept_node_map:

                    concept_node = GraphNode(

                        node_id=str(uuid.uuid4()),

                        node_type="concept",

                        label=concept,

                        metadata={}
                    )

                    concept_node_map[
                        concept
                    ] = concept_node

                    nodes.append(concept_node)

                else:

                    concept_node = concept_node_map[
                        concept
                    ]

                # -----------------------------------------
                # Question -> concept edge
                # -----------------------------------------
                edges.append(

                    self._build_edge(

                        source_id=q_node.node_id,

                        target_id=concept_node.node_id,

                        relation="belongs_to",

                        weight=0.8
                    )
                )

        # =================================================
        # QUESTION SIMILARITY LINKS
        # =================================================

        similarity_edges = (
            self._build_similarity_edges(
                verified_questions,
                question_node_map
            )
        )

        edges.extend(similarity_edges)

        # =================================================
        # FINAL GRAPH
        # =================================================

        return DocumentGraph(

            nodes=nodes,

            edges=edges,

            metadata={

                "node_count": len(nodes),

                "edge_count": len(edges),
            }
        )

    # =====================================================
    # NODE BUILDERS
    # =====================================================

    def _build_question_node(
        self,
        question
    ) -> GraphNode:

        return GraphNode(

            node_id=str(uuid.uuid4()),

            node_type="question",

            label=f"Question {question.qid}",

            metadata={

                "qid":
                    question.qid,

                "question_text":
                    question.question_text,

                "question_type":
                    question.question_type,

                "confidence":
                    question.confidence,

                "verified":
                    getattr(
                        question,
                        "verified",
                        False
                    ),
            }
        )

    def _build_solution_node(
        self,
        question
    ) -> GraphNode:

        return GraphNode(

            node_id=str(uuid.uuid4()),

            node_type="solution",

            label=f"Solution {question.qid}",

            metadata={

                "qid":
                    question.qid,

                "solution_text":
                    question.solution_text,
            }
        )

    def _build_answer_node(
        self,
        question
    ) -> GraphNode:

        return GraphNode(

            node_id=str(uuid.uuid4()),

            node_type="answer",

            label=f"Answer {question.answer}",

            metadata={

                "qid":
                    question.qid,

                "answer":
                    question.answer,
            }
        )

    # =====================================================
    # EDGE BUILDER
    # =====================================================

    def _build_edge(
        self,
        source_id,
        target_id,
        relation,
        weight=1.0
    ) -> GraphEdge:

        return GraphEdge(

            edge_id=str(uuid.uuid4()),

            source_id=source_id,

            target_id=target_id,

            relation=relation,

            weight=weight,

            metadata={}
        )

    # =====================================================
    # CONCEPT EXTRACTION
    # =====================================================

    def _extract_concepts(
        self,
        question
    ) -> List[str]:

        concepts = []

        text = (
            question.question_text
            + " "
            + (question.solution_text or "")
        ).lower()

        for concept, keywords in (
            self.concept_keywords.items()
        ):

            hits = sum(
                keyword in text
                for keyword in keywords
            )

            if hits >= 1:

                concepts.append(concept)

        return concepts

    # =====================================================
    # SIMILARITY LINKS
    # =====================================================

    def _build_similarity_edges(
        self,
        questions,
        question_node_map
    ) -> List[GraphEdge]:

        edges = []

        for i in range(len(questions)):

            for j in range(i + 1, len(questions)):

                q1 = questions[i]
                q2 = questions[j]

                similarity = (
                    self._question_similarity(
                        q1,
                        q2
                    )
                )

                if similarity >= 0.5:

                    n1 = question_node_map[
                        q1.qid
                    ]

                    n2 = question_node_map[
                        q2.qid
                    ]

                    edges.append(

                        self._build_edge(

                            source_id=n1.node_id,

                            target_id=n2.node_id,

                            relation="related_to",

                            weight=similarity
                        )
                    )

        return edges

    # =====================================================
    # LIGHTWEIGHT SIMILARITY
    # =====================================================

    def _question_similarity(
        self,
        q1,
        q2
    ) -> float:

        words1 = set(
            re.findall(
                r"\w+",
                q1.question_text.lower()
            )
        )

        words2 = set(
            re.findall(
                r"\w+",
                q2.question_text.lower()
            )
        )

        if not words1 or not words2:
            return 0.0

        overlap = len(
            words1.intersection(words2)
        )

        union = len(
            words1.union(words2)
        )

        return overlap / union

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_graph_summary(
        self,
        graph
    ):

        print(
            "\n========== DOCUMENT GRAPH ==========\n"
        )

        print(
            f"Nodes: {len(graph.nodes)}"
        )

        print(
            f"Edges: {len(graph.edges)}"
        )

        print("\n--- SAMPLE NODES ---\n")

        for node in graph.nodes[:10]:

            print(
                f"[{node.node_type.upper()}] "
                f"{node.label}"
            )

        print("\n--- SAMPLE EDGES ---\n")

        for edge in graph.edges[:10]:

            print(
                f"{edge.source_id[:8]} "
                f"--{edge.relation}--> "
                f"{edge.target_id[:8]}"
            )