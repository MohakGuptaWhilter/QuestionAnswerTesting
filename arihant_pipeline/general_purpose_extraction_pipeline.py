import os
from pathlib import Path
from PIL import Image
import numpy as np

from arihant_pipeline.pdf_loader import PDFLoader
from arihant_pipeline.page_render import PageRenderer
from arihant_pipeline.layout_analysis import LayoutAnalyzer
from arihant_pipeline.reading_order_resolver import ReadingOrderResolver
from arihant_pipeline.block_classifier import BlockClassifier
from arihant_pipeline.question_anchor_detector import QuestionAnchorDetector
from arihant_pipeline.semantic_region_builder import SemanticRegionBuilder
from arihant_pipeline.figure_linker import FigureLinker
from arihant_pipeline.region_validator import RegionValidator
from arihant_pipeline.crop_generator import CropGenerator
from arihant_pipeline.vlm_transcribe import VLMTranscriber
from arihant_pipeline.question_parser import QuestionParser
from arihant_pipeline.solution_linker import SolutionLinker
from arihant_pipeline.extraction_verification import ExtractionVerifier
from arihant_pipeline.document_graph_builder import DocumentGraphBuilder


class GeneralPurposeExtractionPipeline:

    def __init__(self, config):
        self.config = config

        self.pdf_loader = PDFLoader(config)
        self.renderer = PageRenderer(config)
        self.layout_analyzer = LayoutAnalyzer(config)
        self.reading_order = ReadingOrderResolver(config)
        self.block_classifier = BlockClassifier(config)
        self.anchor_detector = QuestionAnchorDetector(config)
        self.region_builder = SemanticRegionBuilder(config)
        self.figure_linker = FigureLinker(config)
        self.region_validator = RegionValidator(config)
        self.crop_generator = CropGenerator(config)
        self.transcriber = VLMTranscriber(config)
        self.question_parser = QuestionParser(config)
        self.solution_linker = SolutionLinker(config)
        self.verifier = ExtractionVerifier(config)
        self.graph_builder = DocumentGraphBuilder(config)
    
    def _save_crops(self, crops, pdf_path):
        project_root = Path(__file__).resolve().parent.parent
        out_root = project_root / "crops" / Path(pdf_path).stem
        for crop in crops:
            folder = out_root / crop.region_type
            folder.mkdir(parents=True, exist_ok=True)
            fname = f"qid_{crop.qid}_p{crop.page_number}_{crop.crop_id[:8]}.png"
            img = crop.image
            if isinstance(img, np.ndarray):
                img = Image.fromarray(img)
            img.save(folder / fname)
        print(f"[Pipeline] Saved {len(crops)} crops → {out_root}")

    def run(self, pdf_path):

        # -----------------------------------
        # Stage 1: Load PDF
        # -----------------------------------
        document = self.pdf_loader.load(pdf_path)

        # -----------------------------------
        # Stage 2: Render pages
        # -----------------------------------
        rendered_pages = self.renderer.render(document)

        # -----------------------------------
        # Stage 3: Layout analysis
        # -----------------------------------
        layout_blocks = self.layout_analyzer.analyze(
            document,
            rendered_pages
        )

        # -----------------------------------
        # Stage 4: Reading order
        # -----------------------------------
        ordered_blocks = self.reading_order.resolve(
            layout_blocks
        )

        # -----------------------------------
        # Stage 5: Block classification
        # -----------------------------------
        classified_blocks = self.block_classifier.classify(
            ordered_blocks
        )

        # -----------------------------------
        # Stage 6: Detect anchors
        # -----------------------------------
        anchors = self.anchor_detector.detect(
            classified_blocks
        )

        # -----------------------------------
        # Stage 7: Build semantic regions
        # -----------------------------------
        semantic_regions = self.region_builder.build(
            anchors,
            classified_blocks
        )

        # -----------------------------------
        # Stage 8: Link figures
        # -----------------------------------
        semantic_regions = self.figure_linker.link(
            semantic_regions,
            classified_blocks
        )

        # -----------------------------------
        # Stage 9: Validate regions
        # -----------------------------------
        validated_regions = self.region_validator.validate(
            semantic_regions
        )

        # -----------------------------------
        # Stage 10: Generate crops
        # -----------------------------------
        crops = self.crop_generator.generate(
            validated_regions,
            rendered_pages
        )

        # -----------------------------------
        # Stage 11: OCR/VLM
        # -----------------------------------
        _TRANSCRIBE_TYPES = {"examples","question", "solution", "answer_key"}
        crops = [c for c in crops if c.region_type in _TRANSCRIBE_TYPES]

        self._save_crops(crops, pdf_path)

        transcriptions = self.transcriber.transcribe(
            crops
        )

        # -----------------------------------
        # Stage 12: Parse structure
        # -----------------------------------
        questions = self.question_parser.parse(
            transcriptions
        )

        # -----------------------------------
        # Stage 13: Link solutions
        # -----------------------------------
        linked_questions = self.solution_linker.link(
            questions
        )

        # -----------------------------------
        # Stage 14: Verification
        # -----------------------------------
        verified_questions = self.verifier.verify(
            linked_questions
        )

        # -----------------------------------
        # Stage 15: Build graph
        # -----------------------------------
        graph = self.graph_builder.build(
            verified_questions
        )

        return graph