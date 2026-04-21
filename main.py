"""
Main entry point for the QA Testing System.
Demonstrates usage of PDF processor and quiz evaluator.
"""

from src.pdf_processor import PDFProcessor
from src.quiz_evaluator import QuizEvaluator


def example_pdf_processing():
    """
    Example: Extract questions and answers from PDFs and export to Excel.
    """
    print("\n" + "="*60)
    print("EXAMPLE 1: PDF Processing - Extract Q&A to Excel")
    print("="*60)
    
    # Initialize PDF processor
    processor = PDFProcessor(
        questions_pdf_path="data/input/questions.pdf",
        answers_pdf_path="data/input/answers.pdf"
    )
    
    # Process PDFs and export to Excel
    try:
        output_file = processor.process_and_export("data/output/extracted_qa.xlsx")
        summary = processor.get_summary()
        
        print(f"\nSummary:")
        print(f"  Total Questions: {summary['total_questions']}")
        print(f"  Total Answers: {summary['total_answers']}")
        print(f"  Matched Pairs: {summary['matched_pairs']}")
        
    except Exception as e:
        print(f"Error: {e}")


def example_quiz_evaluation():
    """
    Example: Test answers via API and generate results report.
    """
    print("\n" + "="*60)
    print("EXAMPLE 2: Quiz Evaluation - Test Answers via API")
    print("="*60)
    
    # Initialize quiz evaluator
    evaluator = QuizEvaluator(
        excel_file_path="data/output/extracted_qa.xlsx",
        api_endpoint="http://localhost:5000/api/validate",  # Replace with your API endpoint
        api_timeout=10
    )
    
    # Load questions from Excel
    try:
        questions = evaluator.load_questions_from_excel()
        print(f"Loaded {len(questions)} questions from Excel")
        
        # Example user answers (replace with actual answers)
        user_answers = ["A", "B", "C", "D", "A"]  # Example answers
        
        # Test answers via API
        results = evaluator.test_answers(user_answers)
        
        # Export results to Excel
        output_file = evaluator.export_results_to_excel("data/output/test_results.xlsx")
        
        # Get summary
        summary = evaluator.get_summary()
        print(f"\nAccuracy: {summary['accuracy']:.1f}%")
        
    except Exception as e:
        print(f"Error: {e}")


def main():
    """
    Main function - uncomment examples to run.
    """
    print("\nQA Testing System - Main Entry Point\n")
    
    # Uncomment the example you want to run:
    
    # Example 1: PDF Processing
    # example_pdf_processing()
    
    # Example 2: Quiz Evaluation
    # example_quiz_evaluation()
    
    print("\nTo use this system:")
    print("1. PDF Processing: Place PDF files in data/input/ and call PDFProcessor")
    print("2. Quiz Evaluation: Load Excel file and call QuizEvaluator with API endpoint")
    print("\nSee README.md for detailed usage instructions.")


if __name__ == "__main__":
    main()
