import os
import json
from datetime import datetime
from dataclasses import asdict

import pandas as pd


# =========================================================
# EXPORTER
# =========================================================

class Exporter:
    """
    Exports extracted academic pipeline results into
    production-ready artifacts.

    Responsibilities:
    - export Excel datasets
    - export canonical JSON
    - export graph JSON
    - preserve metadata/confidence
    - preserve provenance

    IMPORTANT:
    Exporter should NEVER modify extraction data.
    It only serializes pipeline outputs.
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, config):

        self.config = config

    # =====================================================
    # MAIN EXPORT API
    # =====================================================

    def export(
        self,
        result,
        output_dir
    ):
        """
        Main export entry point.

        Parameters
        ----------
        result : dict
            Pipeline result object.

        output_dir : str
            Output directory.

        Returns
        -------
        dict
            Paths to exported files.
        """

        os.makedirs(
            output_dir,
            exist_ok=True
        )

        # =================================================
        # EXTRACT COMPONENTS
        # =================================================

        from arihant_pipeline.document_graph_builder import DocumentGraph

        if isinstance(result, DocumentGraph):
            graph = result
            metadata = result.metadata
            questions = self._questions_from_graph(result)
        else:
            questions = result.get("questions", [])
            graph = result.get("graph", None)
            metadata = result.get("metadata", {})

        # =================================================
        # BUILD EXPORT ROWS
        # =================================================

        rows = self._build_question_rows(
            questions
        )

        # =================================================
        # TIMESTAMP
        # =================================================

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        # =================================================
        # FILE PATHS
        # =================================================

        excel_path = os.path.join(
            output_dir,
            f"jee_extraction_{timestamp}.xlsx"
        )

        json_path = os.path.join(
            output_dir,
            f"jee_extraction_{timestamp}.json"
        )

        graph_path = os.path.join(
            output_dir,
            f"jee_graph_{timestamp}.json"
        )

        metadata_path = os.path.join(
            output_dir,
            f"jee_metadata_{timestamp}.json"
        )

        # =================================================
        # EXPORT EXCEL
        # =================================================

        self._export_excel(
            rows,
            excel_path
        )

        # =================================================
        # EXPORT JSON
        # =================================================

        self._export_json(
            rows,
            json_path
        )

        # =================================================
        # EXPORT GRAPH
        # =================================================

        if graph is not None:

            self._export_graph(
                graph,
                graph_path
            )

        # =================================================
        # EXPORT METADATA
        # =================================================

        self._export_metadata(
            metadata,
            metadata_path
        )

        # =================================================
        # RETURN PATHS
        # =================================================

        return {

            "excel_path":
                excel_path,

            "json_path":
                json_path,

            "graph_path":
                graph_path,

            "metadata_path":
                metadata_path,
        }

    # =====================================================
    # RECONSTRUCT QUESTIONS FROM GRAPH
    # =====================================================

    def _questions_from_graph(self, graph):
        import types
        from arihant_pipeline.extraction_verification import VerificationIssue

        solution_by_qid = {}
        answer_by_qid = {}

        for node in graph.nodes:
            qid = node.metadata.get("qid")
            if not qid:
                continue
            if node.node_type == "solution":
                solution_by_qid[qid] = node.metadata.get("solution_text", "")
            elif node.node_type == "answer":
                answer_by_qid[qid] = node.metadata.get("answer", "")

        questions = []
        for node in graph.nodes:
            if node.node_type != "question":
                continue
            m = node.metadata
            qid = m.get("qid")
            questions.append(types.SimpleNamespace(
                qid=qid,
                question_text=m.get("question_text", ""),
                options=m.get("options", {}),
                answer=answer_by_qid.get(qid),
                solution_text=solution_by_qid.get(qid),
                question_type=m.get("question_type", ""),
                confidence=m.get("confidence", 0.0),
                verified=m.get("verified", False),
                verification_score=m.get("verification_score"),
                retry_recommended=m.get("retry_recommended", False),
                verification_issues=[
                    VerificationIssue(**issue)
                    for issue in m.get("verification_issues", [])
                ],
                metadata={},
            ))
        return questions

    # =====================================================
    # BUILD QUESTION ROWS
    # =====================================================

    def _build_question_rows(
        self,
        questions
    ):

        rows = []

        for q in questions:

            rows.append({

                # -------------------------------------
                # Identity
                # -------------------------------------
                "qid":
                    q.qid,

                # -------------------------------------
                # Core content
                # -------------------------------------
                "question":
                    q.question_text,

                "options":
                    json.dumps(
                        q.options,
                        ensure_ascii=False
                    ),

                "answer":
                    q.answer,

                "solution":
                    q.solution_text,

                # -------------------------------------
                # Structure
                # -------------------------------------
                "question_type":
                    q.question_type,

                # -------------------------------------
                # Confidence
                # -------------------------------------
                "confidence":
                    q.confidence,

                "verification_score":
                    getattr(
                        q,
                        "verification_score",
                        None
                    ),

                "verified":
                    getattr(
                        q,
                        "verified",
                        False
                    ),

                # -------------------------------------
                # Retry recommendations
                # -------------------------------------
                "retry_recommended":
                    getattr(
                        q,
                        "retry_recommended",
                        False
                    ),

                # -------------------------------------
                # Verification issues
                # -------------------------------------
                "verification_issues":
                    json.dumps(
                        [
                            asdict(issue)
                            for issue in getattr(
                                q,
                                "verification_issues",
                                []
                            )
                        ],
                        ensure_ascii=False
                    ),

                # -------------------------------------
                # Metadata
                # -------------------------------------
                "metadata":
                    json.dumps(
                        getattr(
                            q,
                            "metadata",
                            {}
                        ),
                        ensure_ascii=False
                    ),
            })

        return rows

    # =====================================================
    # EXPORT EXCEL
    # =====================================================

    def _export_excel(
        self,
        rows,
        output_path
    ):

        df = pd.DataFrame(rows)

        with pd.ExcelWriter(
            output_path,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                index=False,
                sheet_name="Questions"
            )

            # -----------------------------------------
            # Auto column width
            # -----------------------------------------
            worksheet = writer.sheets[
                "Questions"
            ]

            for column_cells in worksheet.columns:

                max_length = 0

                column = (
                    column_cells[0].column_letter
                )

                for cell in column_cells:

                    try:

                        value = str(cell.value)

                        if len(value) > max_length:

                            max_length = len(value)

                    except Exception:
                        pass

                adjusted_width = min(
                    max_length + 2,
                    80
                )

                worksheet.column_dimensions[
                    column
                ].width = adjusted_width

    # =====================================================
    # EXPORT JSON
    # =====================================================

    def _export_json(
        self,
        rows,
        output_path
    ):

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(

                rows,

                f,

                ensure_ascii=False,

                indent=2
            )

    # =====================================================
    # EXPORT GRAPH
    # =====================================================

    def _export_graph(
        self,
        graph,
        output_path
    ):

        graph_dict = {

            "nodes": [

                {

                    "node_id":
                        node.node_id,

                    "node_type":
                        node.node_type,

                    "label":
                        node.label,

                    "metadata":
                        node.metadata,
                }

                for node in graph.nodes
            ],

            "edges": [

                {

                    "edge_id":
                        edge.edge_id,

                    "source_id":
                        edge.source_id,

                    "target_id":
                        edge.target_id,

                    "relation":
                        edge.relation,

                    "weight":
                        edge.weight,

                    "metadata":
                        edge.metadata,
                }

                for edge in graph.edges
            ],

            "metadata":
                graph.metadata,
        }

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(

                graph_dict,

                f,

                ensure_ascii=False,

                indent=2
            )

    # =====================================================
    # EXPORT METADATA
    # =====================================================

    def _export_metadata(
        self,
        metadata,
        output_path
    ):

        with open(
            output_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(

                metadata,

                f,

                ensure_ascii=False,

                indent=2
            )

    # =====================================================
    # DEBUG UTILITIES
    # =====================================================

    def print_export_summary(
        self,
        export_result
    ):

        print(
            "\n========== EXPORT SUMMARY ==========\n"
        )

        for key, value in export_result.items():

            print(
                f"{key}: {value}"
            )

        print("\nExport completed successfully.")