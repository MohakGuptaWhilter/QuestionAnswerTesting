"""
Test suite for the QA Testing System.
Tests PDF processing and quiz evaluation functionality.
"""

import unittest
import os
from pathlib import Path
import tempfile
import json
from src.pdf_processor import PDFProcessor
from src.quiz_evaluator import QuizEvaluator, ResultStatus
from openpyxl import Workbook, load_workbook


class TestPDFProcessor(unittest.TestCase):
    """Test cases for PDFProcessor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, "test_output.xlsx")
    
    def tearDown(self):
        """Clean up test files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_test_excel(self, file_path):
        """Helper to create test Excel file."""
        wb = Workbook()
        ws = wb.active
        ws.append(["Question #", "Question", "Correct Answer"])
        ws.append([1, "Test Question?", "A"])
        wb.save(file_path)
        return file_path
    
    def test_parse_questions(self):
        """Test question parsing from text."""
        processor = PDFProcessor("dummy1.pdf", "dummy2.pdf")
        
        text = """
        1. What is the capital of France?
        2. What is 2+2?
        3. What is Python?
        """
        
        questions = processor.parse_questions(text)
        self.assertGreater(len(questions), 0)
    
    def test_parse_answers(self):
        """Test answer parsing from text."""
        processor = PDFProcessor("dummy1.pdf", "dummy2.pdf")
        
        text = """
        Answer: A
        Answer: B
        Answer: C
        """
        
        answers = processor.parse_answers(text)
        self.assertGreater(len(answers), 0)
    
    def test_get_summary(self):
        """Test summary generation."""
        processor = PDFProcessor("dummy1.pdf", "dummy2.pdf")
        processor.questions = ["Q1", "Q2", "Q3"]
        processor.answers = ["A", "B"]
        
        summary = processor.get_summary()
        
        self.assertEqual(summary['total_questions'], 3)
        self.assertEqual(summary['total_answers'], 2)
        self.assertEqual(summary['matched_pairs'], 2)
        self.assertIn('timestamp', summary)


class TestQuizEvaluator(unittest.TestCase):
    """Test cases for QuizEvaluator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_excel = os.path.join(self.temp_dir, "test_questions.xlsx")
        self.output_file = os.path.join(self.temp_dir, "test_results.xlsx")
        self.create_sample_excel()
    
    def tearDown(self):
        """Clean up test files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_sample_excel(self):
        """Create sample Excel file for testing."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Q&A"
        
        ws.append(["Question #", "Question", "Correct Answer"])
        ws.append([1, "What is the capital of France?", "A"])
        ws.append([2, "What is 2+2?", "B"])
        ws.append([3, "What color is the sky?", "C"])
        
        wb.save(self.test_excel)
    
    def test_load_questions_from_excel(self):
        """Test loading questions from Excel file."""
        evaluator = QuizEvaluator(
            self.test_excel,
            "http://localhost:5000/api/validate"
        )
        
        questions = evaluator.load_questions_from_excel()
        
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]['id'], 1)
        self.assertEqual(questions[0]['correct_answer'], 'A')
    
    def test_get_summary_empty(self):
        """Test summary for empty results."""
        evaluator = QuizEvaluator(
            self.test_excel,
            "http://localhost:5000/api/validate"
        )
        
        summary = evaluator.get_summary()
        
        self.assertEqual(summary['total_questions'], 0)
        self.assertEqual(summary['correct_answers'], 0)
    
    def test_result_status_enum(self):
        """Test ResultStatus enum values."""
        self.assertEqual(ResultStatus.CORRECT.value, "Correct")
        self.assertEqual(ResultStatus.INCORRECT.value, "Incorrect")
        self.assertEqual(ResultStatus.ERROR.value, "Error")
        self.assertEqual(ResultStatus.SKIPPED.value, "Skipped")


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_end_to_end_workflow(self):
        """Test complete workflow from Excel creation to export."""
        from openpyxl.styles import Font, PatternFill, Alignment
        
        # Create test Excel
        test_file = os.path.join(self.temp_dir, "questions.xlsx")
        output_file = os.path.join(self.temp_dir, "results.xlsx")
        
        wb = Workbook()
        ws = wb.active
        ws.append(["Question #", "Question", "Correct Answer"])
        ws.append([1, "Test Q1?", "A"])
        ws.append([2, "Test Q2?", "B"])
        wb.save(test_file)
        
        # Test loading
        evaluator = QuizEvaluator(test_file, "http://localhost:5000/api/validate")
        questions = evaluator.load_questions_from_excel()
        
        self.assertEqual(len(questions), 2)
        
        # Verify file was created
        self.assertTrue(os.path.exists(test_file))


def run_tests():
    """Run all tests."""
    unittest.main(argv=[''], verbosity=2, exit=False)


if __name__ == "__main__":
    run_tests()
