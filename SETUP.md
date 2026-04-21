# Complete Setup Guide: Backend + Frontend

## System Requirements

- Python 3.8+ (for backend)
- Node.js 16+ (for frontend)
- npm or yarn (for frontend dependencies)

---

## Setup Steps

### 1. Backend Setup (Python API)

```bash
# Navigate to project root
cd qa_test

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate     # Windows

# Install Python dependencies
pip install -r requirements.txt
pip install flask
```

### 2. Frontend Setup (React)

```bash
# Navigate to frontend folder (from project root)
cd frontend

# Install Node dependencies
npm install

# You're ready to run!
```

---

## Running the Application

### Terminal 1: Start Backend API

```bash
# From project root
source venv/bin/activate
python api.py
```

Expected output:
```
======================================================================
QA PDF Extractor API
======================================================================

Endpoints:
  GET  /health                    - Health check
  GET  /api/info                  - API documentation
  POST /api/extract               - Extract Q&A, returns Excel
  POST /api/extract-json          - Extract Q&A, returns JSON

Server running on http://localhost:5000
```

### Terminal 2: Start Frontend

```bash
# From project root, in frontend directory
cd frontend
npm run dev
```

Expected output:
```
Port 3000 is in use.

  > http://localhost:3000/
```

---

## Using the Application

1. **Open Browser**
   - Visit: http://localhost:3000

2. **Upload PDFs**
   - Select Questions PDF
   - Select Answers PDF

3. **Extract**
   - Click "Extract & Download Excel"
   - Excel file downloads automatically

4. **Done!**
   - File is ready to use

---

## Folder Structure

```
qa_test/
├── venv/                       # Python virtual environment
│
├── Backend (Python):
├── api.py                      # Flask API server
├── api_client.py              # API test client
├── sample_api.py              # Sample API reference
├── requirements.txt           # Python dependencies
├── README.md                  # Backend docs
├── API_DOCS.md               # API documentation
├── QUICKSTART.md             # Quick start guide
│
├── src/                       # Python source code
│   ├── pdf_processor.py       # PDF extraction
│   ├── quiz_evaluator.py      # Answer validation
│   ├── utils.py              # Utilities
│   └── __init__.py
│
├── Frontend (React):
├── frontend/
│   ├── node_modules/         # NPM dependencies
│   ├── src/
│   │   ├── components/
│   │   │   ├── PDFUploader.jsx    # Upload component
│   │   │   └── PDFUploader.css    # Component styles
│   │   ├── App.jsx               # Main app
│   │   ├── App.css               # App styles
│   │   └── main.jsx              # Entry point
│   ├── index.html            # HTML template
│   ├── vite.config.js        # Build config
│   ├── package.json          # NPM packages
│   └── README.md             # Frontend docs
│
├── data/                      # Data folder
│   ├── input/               # Put PDF files here
│   └── output/              # Excel output here
│
└── tests/                     # Unit tests
```

---

## API Endpoints

### Frontend calls these endpoints:

| Endpoint | Method | Body | Returns |
|----------|--------|------|---------|
| `/health` | GET | - | Status |
| `/api/extract` | POST | 2 PDFs | Excel file |
| `/api/extract-json` | POST | 2 PDFs | JSON data |

---

## Common Tasks

### Task 1: Check API Health

```bash
curl http://localhost:5000/health
```

### Task 2: View API Documentation

```bash
curl http://localhost:5000/api/info
```

Or open in browser:
```
http://localhost:5000/api/info
```

### Task 3: Test API with cURL

```bash
curl -F "questions_pdf=@questions.pdf" \
     -F "answers_pdf=@answers.pdf" \
     http://localhost:5000/api/extract \
     -o output.xlsx
```

### Task 4: Stop Backend API

```bash
# In the terminal running api.py:
Press CTRL+C
```

### Task 5: Stop Frontend Server

```bash
# In the terminal running npm run dev:
Press CTRL+C
```

---

## Troubleshooting

### Port Already in Use

**Port 3000 (Frontend) is in use:**
```bash
# Change in frontend/vite.config.js
server: {
  port: 3001,  // Use 3001 instead
  ...
}
```

**Port 5000 (Backend) is in use:**
```bash
# Change in api.py
app.run(debug=True, host='localhost', port=5001)
```

### Cannot Connect to API

Make sure:
1. Backend is running: `python api.py`
2. Port 5000 is available
3. API returns 200 on `http://localhost:5000/health`

### npm install fails

```bash
# Clear cache and try again
npm cache clean --force
npm install
```

### ModuleNotFoundError in Python

```bash
# Activate virtual environment and reinstall
source venv/bin/activate
pip install -r requirements.txt
pip install flask
```

### React won't start

```bash
# Make sure you're in frontend directory
cd frontend
npm run dev
```

---

## Development Workflow

1. **Make changes to backend** (api.py, src/*.py)
   - API auto-reloads in debug mode
   - No action needed

2. **Make changes to frontend** (src/*.jsx, src/*.css)
   - Frontend hot-reloads automatically
   - Just save the file

3. **Test changes**
   - Refresh browser (http://localhost:3000)
   - Check console for errors (F12)

---

## Production Deployment

### Build Frontend for Production

```bash
cd frontend
npm run build
```

Creates optimized `dist/` folder with minified files.

### Deploy Backend

For production, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app
```

### Serve Frontend from Backend (Optional)

To serve React from Flask:

1. Build React: `npm run build`
2. Copy `frontend/dist/` contents to `backend/static/`
3. Configure Flask to serve static files

---

## Performance Tips

- Both servers run on localhost (same machine)
- API responses are typically <5 seconds per PDF
- Tested with PDFs up to 50MB
- Handles multiple concurrent requests

---

## Getting Help

1. **Check logs**
   - API logs: Terminal running `api.py`
   - Frontend logs: Browser console (F12)

2. **Check docs**
   - Backend: [API_DOCS.md](API_DOCS.md)
   - Frontend: [frontend/README.md](frontend/README.md)

3. **Verify setup**
   - Test API health: `curl http://localhost:5000/health`
   - Test frontend: Visit http://localhost:3000

---

## Next Steps

1. ✅ Start both servers
2. ✅ Open http://localhost:3000
3. ✅ Upload your PDFs
4. ✅ Download Excel file
5. 🎉 Done!
