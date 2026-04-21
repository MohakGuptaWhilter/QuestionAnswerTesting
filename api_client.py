"""
Test client for the QA PDF Extractor API
Demonstrates how to use the API endpoints
"""

import requests
import sys
from pathlib import Path


class APIClient:
    """Client for QA PDF Extractor API."""
    
    def __init__(self, base_url="http://localhost:5000"):
        """
        Initialize API client.
        
        Args:
            base_url: Base URL of the API server
        """
        self.base_url = base_url
    
    def check_health(self):
        """Check if API is running and healthy."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                print("✓ API is healthy")
                return True
            else:
                print(f"✗ API returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print(f"✗ Cannot connect to API at {self.base_url}")
            return False
        except Exception as e:
            print(f"✗ Error: {e}")
            return False
    
    def get_info(self):
        """Get API information and documentation."""
        try:
            response = requests.get(f"{self.base_url}/api/info")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def extract_to_excel(self, questions_pdf, answers_pdf, output_file=None):
        """
        Extract Q&A from PDFs and save as Excel file.
        
        Args:
            questions_pdf: Path to questions PDF
            answers_pdf: Path to answers PDF
            output_file: Output Excel file path (optional)
        
        Returns:
            Path to saved Excel file or None on error
        """
        try:
            if not Path(questions_pdf).exists():
                print(f"✗ Questions PDF not found: {questions_pdf}")
                return None
            
            if not Path(answers_pdf).exists():
                print(f"✗ Answers PDF not found: {answers_pdf}")
                return None
            
            print(f"Uploading PDFs...")
            with open(questions_pdf, 'rb') as qf, open(answers_pdf, 'rb') as af:
                files = {
                    'questions_pdf': qf,
                    'answers_pdf': af
                }
                response = requests.post(
                    f"{self.base_url}/api/extract",
                    files=files,
                    timeout=30
                )
            
            if response.status_code == 200:
                # Save the Excel file
                if output_file is None:
                    output_file = "extracted_qa.xlsx"
                
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                
                print(f"✓ Excel file saved: {output_file}")
                return output_file
            else:
                error = response.json()
                print(f"✗ Error: {error.get('error', 'Unknown error')}")
                return None
        
        except Exception as e:
            print(f"✗ Error: {e}")
            return None
    
    def extract_to_json(self, questions_pdf, answers_pdf):
        """
        Extract Q&A from PDFs and return as JSON.
        
        Args:
            questions_pdf: Path to questions PDF
            answers_pdf: Path to answers PDF
        
        Returns:
            JSON response dict or None on error
        """
        try:
            if not Path(questions_pdf).exists():
                print(f"✗ Questions PDF not found: {questions_pdf}")
                return None
            
            if not Path(answers_pdf).exists():
                print(f"✗ Answers PDF not found: {answers_pdf}")
                return None
            
            print(f"Uploading PDFs...")
            with open(questions_pdf, 'rb') as qf, open(answers_pdf, 'rb') as af:
                files = {
                    'questions_pdf': qf,
                    'answers_pdf': af
                }
                response = requests.post(
                    f"{self.base_url}/api/extract-json",
                    files=files,
                    timeout=30
                )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Extraction successful")
                print(f"  Total questions: {data['summary']['total_questions']}")
                print(f"  Total answers: {data['summary']['total_answers']}")
                return data
            else:
                error = response.json()
                print(f"✗ Error: {error.get('error', 'Unknown error')}")
                return None
        
        except Exception as e:
            print(f"✗ Error: {e}")
            return None


def test_api():
    """Test the API with example usage."""
    client = APIClient()
    
    print("\n" + "="*70)
    print("QA PDF Extractor API - Test Client")
    print("="*70 + "\n")
    
    # Check health
    print("1. Checking API health...")
    if not client.check_health():
        print("\n✗ API is not running. Start it with:")
        print("  python api.py")
        return
    
    print("\n2. Getting API information...")
    info = client.get_info()
    if info:
        print(f"  Service: {info['service']}")
        print(f"  Version: {info['version']}")
        print(f"  Endpoints: {len(info['endpoints'])}")
    
    print("\n3. To extract Q&A from your PDFs:")
    print("\n  Option A: Get Excel file")
    print("  " + "-" * 50)
    print("  client = APIClient('http://localhost:5000')")
    print("  client.extract_to_excel(")
    print('      "path/to/questions.pdf",')
    print('      "path/to/answers.pdf",')
    print('      "output.xlsx"')
    print("  )")
    
    print("\n  Option B: Get JSON response")
    print("  " + "-" * 50)
    print("  client = APIClient('http://localhost:5000')")
    print("  data = client.extract_to_json(")
    print('      "path/to/questions.pdf",')
    print('      "path/to/answers.pdf"')
    print("  )")
    
    print("\n  Option C: cURL command")
    print("  " + "-" * 50)
    print('  curl -F "questions_pdf=@questions.pdf" \\')
    print('       -F "answers_pdf=@answers.pdf" \\')
    print('       http://localhost:5000/api/extract -o output.xlsx')
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    test_api()
