# 🎉 QA PDF Extractor - Complete Application

Your complete React + Flask application is ready!

## 📁 What Was Created

### Backend (Flask API)
```
qa_test/
├── api.py                    ← Flask API Server (Main entry point)
├── api_client.py            ← Python API client for testing
├── sample_api.py            ← Reference API implementation
├── requirements.txt         ← Python dependencies
├── API_DOCS.md             ← Complete API documentation
├── QUICKSTART.md           ← Quick start guide
├── SETUP.md                ← Full setup instructions
└── src/
    ├── pdf_processor.py     ← PDF extraction logic
    ├── quiz_evaluator.py    ← Answer validation
    ├── utils.py             ← Utilities
    └── __init__.py
```

### Frontend (React)
```
qa_test/frontend/
├── src/
│   ├── components/
│   │   ├── PDFUploader.jsx     ← Main upload component
│   │   └── PDFUploader.css     ← Component styles
│   ├── App.jsx                 ← Main app component
│   ├── App.css                 ← Global styles
│   ├── main.jsx                ← React entry point
├── index.html                  ← HTML template
├── vite.config.js             ← Build configuration
├── package.json               ← Dependencies
├── README.md                  ← Frontend docs
└── .gitignore
```

---

## 🚀 Quick Start (5 minutes)

### Step 1: Backend Setup (Terminal 1)

```bash
# Navigate to project
cd /Users/rajanpunchouty/Desktop/test_question_answers/qa_test

# Activate Python environment
source venv/bin/activate

# Start API server
python api.py
```

**Expected output:**
```
======================================================================
QA PDF Extractor API
======================================================================

Server running on http://localhost:5000
```

### Step 2: Frontend Setup (Terminal 2)

```bash
# Navigate to project
cd /Users/rajanpunchouty/Desktop/test_question_answers/qa_test/frontend

# Install dependencies (one-time)
npm install

# Start React dev server
npm run dev
```

**Expected output:**
```
  > http://localhost:3000/
```

### Step 3: Use the Application

1. **Open Browser**
   - Go to: http://localhost:3000

2. **Upload Files**
   - Click "Questions PDF" → Select a PDF with questions
   - Click "Answers PDF" → Select a PDF with answers

3. **Extract**
   - Click "Extract & Download Excel"
   - Wait for processing (~5-10 seconds)

4. **Download**
   - Excel file downloads automatically
   - Preview shows extracted questions

---

## 📋 Features

### React Frontend
✅ Modern, responsive UI  
✅ Real-time API status indicator  
✅ File upload with validation  
✅ Live preview of extracted data  
✅ Automatic Excel file download  
✅ Error handling and messages  
✅ Mobile-friendly design  

### Flask Backend API
✅ PDF upload and processing  
✅ Text extraction with regex parsing  
✅ Excel generation with formatting  
✅ JSON response option  
✅ Error handling  
✅ Auto file cleanup  
✅ Health check endpoint  

---

## 🔗 API Endpoints

The React app calls these API endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Check if API is running |
| `/api/extract` | POST | Upload PDFs → Get Excel file |
| `/api/extract-json` | POST | Upload PDFs → Get JSON |
| `/api/info` | GET | View API documentation |

---

## 📚 Documentation

### For Backend
- [API_DOCS.md](API_DOCS.md) - Complete API reference
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [README.md](README.md) - Full project documentation

### For Frontend
- [frontend/README.md](frontend/README.md) - Frontend setup & development
- [frontend/src/components/PDFUploader.jsx](frontend/src/components/PDFUploader.jsx) - Main component

### Full Setup
- [SETUP.md](SETUP.md) - Complete installation & troubleshooting guide

---

## 🛠️ Development

### Making Changes to Backend

Edit `api.py` or `src/` files:
- API auto-reloads in debug mode
- No action needed, changes take effect immediately

### Making Changes to Frontend

Edit `frontend/src/` files:
- Frontend hot-reloads automatically
- Save file → Changes appear in browser

### Adding Dependencies

**Python:**
```bash
source venv/bin/activate
pip install package_name
pip freeze > requirements.txt
```

**JavaScript:**
```bash
cd frontend
npm install package_name
```

---

## 🧪 Testing

### Test API Health
```bash
curl http://localhost:5000/health
```

### Test API with cURL
```bash
curl -F "questions_pdf=@questions.pdf" \
     -F "answers_pdf=@answers.pdf" \
     http://localhost:5000/api/extract \
     -o output.xlsx
```

### Test with Python
```python
from api_client import APIClient

client = APIClient('http://localhost:5000')
client.extract_to_excel('questions.pdf', 'answers.pdf', 'output.xlsx')
```

---

## ⚙️ Configuration

### Change Frontend Port
Edit `frontend/vite.config.js`:
```javascript
server: {
  port: 3001,  // Change here
  ...
}
```

### Change Backend Port
Edit `api.py`:
```python
app.run(debug=True, host='localhost', port=5001)  # Change here
```

### Change API Proxy (if needed)
Edit `frontend/vite.config.js`:
```javascript
proxy: {
  '/api': {
    target: 'http://your-api-server.com',  // Change here
    changeOrigin: true,
  }
}
```

---

## 📦 Project Layout

```
qa_test/
│
├─ Backend (Python):
│  ├─ api.py                 ← START HERE for API
│  ├─ src/
│  │  ├─ pdf_processor.py
│  │  ├─ quiz_evaluator.py
│  │  └─ utils.py
│  ├─ requirements.txt
│  └─ API_DOCS.md            ← Read for API details
│
├─ Frontend (React):
│  └─ frontend/
│     ├─ src/
│     │  ├─ components/
│     │  │  └─ PDFUploader.jsx  ← Main upload component
│     │  ├─ App.jsx             ← Main app page
│     │  └─ main.jsx
│     ├─ package.json
│     └─ README.md              ← Read for frontend details
│
├─ Documentation:
│  ├─ SETUP.md                ← Full setup guide
│  ├─ QUICKSTART.md           ← Quick reference
│  ├─ API_DOCS.md            ← API details
│  └─ README.md              ← Project overview
│
└─ venv/                       ← Python virtual environment
```

---

## 🐛 Troubleshooting

### Port Already in Use

**For port 3000:**
```bash
# Change port in frontend/vite.config.js
# Or kill process:
lsof -ti:3000 | xargs kill -9
```

**For port 5000:**
```bash
# Change port in api.py
# Or kill process:
lsof -ti:5000 | xargs kill -9
```

### Cannot Connect to API

1. **Check API is running:**
   ```bash
   curl http://localhost:5000/health
   ```

2. **Check both servers are running:**
   - Backend: Terminal with `python api.py` running
   - Frontend: Terminal with `npm run dev` running

3. **Check ports are correct:**
   - Frontend: http://localhost:3000
   - Backend: http://localhost:5000

### Dependencies Not Installing

```bash
# For Python:
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# For npm:
rm -rf frontend/node_modules package-lock.json
cd frontend
npm install
```

### Files Not Downloading

- Check browser console (F12) for errors
- Check API is running and healthy
- Try uploading smaller PDF files first
- Check available disk space

---

## 🚀 Production Deployment

### Build Frontend for Production

```bash
cd frontend
npm run build
# Creates optimized 'dist/' folder
```

### Deploy Backend

Use a production WSGI server:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app
```

### Serve Frontend from Backend (Optional)

```bash
# Copy React build to Flask static folder
cp -r frontend/dist/* static/
```

Then configure Flask to serve static/index.html for all non-API routes.

---

## ✨ Features Breakdown

### PDF Extraction (`PDFProcessor`)
- ✅ Reads PDF files
- ✅ Extracts questions (numbered format)
- ✅ Extracts answers (A/B/C/D format)
- ✅ Handles large PDFs (50MB+)
- ✅ Error handling and logging

### Excel Export
- ✅ Formatted headers
- ✅ Color-coded cells
- ✅ Optimal column widths
- ✅ Professional appearance
- ✅ Downloadable from browser

### React UI
- ✅ Drag-and-drop file input
- ✅ Live validation
- ✅ Loading states
- ✅ Error messages
- ✅ Preview of results
- ✅ Responsive design
- ✅ API status indicator

---

## 📞 Support

### Check Documentation
- API: [API_DOCS.md](API_DOCS.md)
- Frontend: [frontend/README.md](frontend/README.md)
- Setup: [SETUP.md](SETUP.md)

### View Logs
- **API:** Check terminal running `python api.py`
- **Frontend:** Check browser console (F12)
- **Network:** Check browser Network tab (F12)

### Test API Manually
```bash
# View all endpoints
curl http://localhost:5000/api/info | python -m json.tool

# Check health
curl http://localhost:5000/health
```

---

## 🎯 Next Steps

1. ✅ **Start Backend:** `python api.py`
2. ✅ **Start Frontend:** `npm run dev`
3. ✅ **Open Browser:** http://localhost:3000
4. ✅ **Upload PDFs:** Select your question and answer files
5. ✅ **Extract:** Click the extract button
6. ✅ **Download:** Excel file downloads automatically
7. 🎉 **Done!**

---

## 📝 License

Open source - modify and use freely.

---

**Enjoy your QA PDF Extractor! 🚀**
