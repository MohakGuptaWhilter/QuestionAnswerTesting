"""
Sample API endpoint implementation.
Use this as a reference for creating your own validation API.
"""

from flask import Flask, request, jsonify
from functools import wraps


app = Flask(__name__)

# Sample database of questions and correct answers
QUESTIONS_DB = {
    1: {"question": "What is the capital of France?", "answer": "A"},
    2: {"question": "What is 2+2?", "answer": "B"},
    3: {"question": "Which planet is closest to the Sun?", "answer": "B"},
    4: {"question": "What is the chemical symbol for Gold?", "answer": "D"},
    5: {"question": "Who wrote Romeo and Juliet?", "answer": "C"},
}


def validate_request(f):
    """Decorator to validate incoming requests."""
    @wraps(f)
    def decorated(*args, **kwargs):
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        if 'question_id' not in data or 'user_answer' not in data:
            return jsonify({"error": "Missing required fields"}), 400
        
        return f(*args, **kwargs)
    
    return decorated


@app.route('/api/validate', methods=['POST'])
@validate_request
def validate_answer():
    """
    Validate a user's answer for a question.
    
    Expected request body:
    {
        "question_id": 1,
        "user_answer": "A"
    }
    
    Response:
    {
        "correct": true,
        "correct_answer": "A",
        "message": "Answer is correct!"
    }
    """
    data = request.get_json()
    question_id = data.get('question_id')
    user_answer = data.get('user_answer', '').upper()
    
    # Check if question exists
    if question_id not in QUESTIONS_DB:
        return jsonify({
            "correct": False,
            "correct_answer": None,
            "error": f"Question {question_id} not found"
        }), 404
    
    question_data = QUESTIONS_DB[question_id]
    correct_answer = question_data['answer']
    is_correct = user_answer == correct_answer
    
    return jsonify({
        "correct": is_correct,
        "correct_answer": correct_answer,
        "question": question_data['question'],
        "message": "Answer is correct!" if is_correct else "Answer is incorrect"
    }), 200


@app.route('/api/questions', methods=['GET'])
def get_all_questions():
    """Get all available questions (API metadata)."""
    questions = []
    for q_id, q_data in QUESTIONS_DB.items():
        questions.append({
            "id": q_id,
            "question": q_data['question'],
            "hint": f"Answer is one of: A, B, C, D"
        })
    
    return jsonify({
        "total": len(questions),
        "questions": questions
    }), 200


@app.route('/api/question/<int:question_id>', methods=['GET'])
def get_question(question_id):
    """Get a specific question details."""
    if question_id not in QUESTIONS_DB:
        return jsonify({"error": "Question not found"}), 404
    
    question_data = QUESTIONS_DB[question_id]
    return jsonify({
        "id": question_id,
        "question": question_data['question']
    }), 200


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "QA-Validation-API"
    }), 200


if __name__ == '__main__':
    print("\n" + "="*60)
    print("QA Validation API Server")
    print("="*60)
    print("\nEndpoints:")
    print("  POST /api/validate       - Validate user answer")
    print("  GET  /api/questions      - Get all questions")
    print("  GET  /api/question/<id>  - Get specific question")
    print("  GET  /health             - Health check")
    print("\nServer running on http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, host='localhost', port=5000)
