# React Frontend for QA PDF Extractor

A modern React frontend for uploading PDFs and downloading extracted Q&A as an Excel file.

## Features

✅ Clean, modern UI with responsive design  
✅ Drag-and-drop file upload support  
✅ Live API status checking  
✅ Preview of extracted questions  
✅ Download Excel file directly  
✅ Error handling and validation  
✅ Mobile-friendly interface  

## Setup

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Start Development Server

```bash
npm run dev
```

Opens at: **http://localhost:3000**

### 3. Make Sure Backend API is Running

In another terminal:

```bash
cd ..  # Go back to project root
source venv/bin/activate
python api.py
```

API runs at: **http://localhost:5000**

## Usage

1. **Upload Files**
   - Click on "Questions PDF" and select your questions PDF
   - Click on "Answers PDF" and select your answers PDF

2. **Extract**
   - Click "Extract & Download Excel"
   - Wait for processing to complete

3. **Download**
   - Excel file downloads automatically
   - Preview shows sample questions extracted

## How It Works

```
Browser (React)
    ↓
    ├─→ POST /api/extract-json  (Get JSON preview)
    │   └─→ Display preview
    │
    └─→ POST /api/extract       (Get Excel file)
        └─→ Download Excel
```

## Development

### Start Development Server

```bash
npm run dev
```

### Build for Production

```bash
npm run build
```

Outputs to `dist/` folder

### Preview Production Build

```bash
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── PDFUploader.jsx     # Main upload component
│   │   └── PDFUploader.css     # Component styles
│   ├── App.jsx                 # Main app component
│   ├── App.css                 # App styles
│   └── main.jsx                # Entry point
├── index.html                  # HTML template
├── vite.config.js             # Vite configuration
└── package.json               # Dependencies
```

## Configuration

Edit `vite.config.js` to change the API proxy URL:

```javascript
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:5000',  // ← Change here
      changeOrigin: true,
    }
  }
}
```

## Troubleshooting

### Port 3000 already in use

Change in `vite.config.js`:
```javascript
server: {
  port: 3001,  // Change to different port
  ...
}
```

### Cannot connect to API

Make sure:
1. API server is running: `python api.py`
2. API is at `http://localhost:5000`
3. Both servers are running on your machine

### File upload fails

Check:
- File is PDF format
- File size is under 50MB
- API server is running and healthy

## Dependencies

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- Built-in Fetch API for HTTP requests (no additional HTTP library needed)

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## API Endpoints Used

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `POST /api/extract` | Extract and get Excel | Excel file (.xlsx) |
| `POST /api/extract-json` | Extract and get JSON | JSON data |
| `GET /health` | Check API status | Health status |

## Environment Variables

Currently no env variables needed. All configuration is in `vite.config.js`.

To add environment variables:

1. Create `.env` file in `frontend/` folder
2. Add variables with `VITE_` prefix:
   ```
   VITE_API_URL=http://localhost:5000
   ```
3. Use in code:
   ```javascript
   const apiUrl = import.meta.env.VITE_API_URL
   ```

## License

MIT - Use freely

## Support

For issues or questions:
- Check API is running: `python api.py`
- Check frontend is running: `npm run dev`
- Check browser console for errors (F12)
