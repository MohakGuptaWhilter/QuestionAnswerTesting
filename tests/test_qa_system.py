import unittest
import tempfile
import os
from src.pdf_processor import PDFProcessor
from openpyxl import Workbook


class TestPDFProcessor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_parse_questions(self):
        processor = PDFProcessor("dummy1.pdf", "dummy2.pdf")
        text = """
        1. What is the capital of France?
        2. What is 2+2?
        3. What is Python?
        """
        questions = processor.parse_questions(text)
        self.assertGreater(len(questions), 0)

    def test_parse_answers(self):
        processor = PDFProcessor("dummy1.pdf", "dummy2.pdf")
        text = """
        Answer: A
        Answer: B
        Answer: C
        """
        answers = processor.parse_answers(text)
        self.assertGreater(len(answers), 0)

    def test_get_summary(self):
        processor = PDFProcessor("dummy1.pdf", "dummy2.pdf")
        processor.questions = ["Q1", "Q2", "Q3"]
        processor.answers = ["A", "B"]
        summary = processor.get_summary()
        self.assertEqual(summary['total_questions'], 3)
        self.assertEqual(summary['total_answers'], 2)
        self.assertEqual(summary['matched_pairs'], 2)
        self.assertIn('timestamp', summary)


if __name__ == "__main__":
    unittest.main()
