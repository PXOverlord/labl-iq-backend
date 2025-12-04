# Labl IQ Rate Analyzer - Hybrid Backend

This is the cleaned-up FastAPI backend for the Labl IQ Rate Analyzer hybrid application. It provides the core rate calculation engine and API endpoints for integration with a React/TypeScript frontend.

## 🏗️ Architecture

This backend is designed to work with a React frontend and provides:
- **Rate Calculation Engine**: Advanced Amazon shipping rate analysis
- **File Processing**: CSV/Excel upload and processing
- **API Endpoints**: RESTful API for frontend integration
- **CORS Support**: Configured for React frontend communication

## 📁 Project Structure

```
labl_iq_hybrid_backend/
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py          # API endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py          # Configuration settings
│   ├── models/
│   │   └── __init__.py        # Database models (future)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py         # Pydantic schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── calc_engine.py     # Core rate calculation engine
│   │   ├── processor.py       # File processing logic
│   │   ├── profiles.py        # User profile management
│   │   ├── utils_processing.py # Utility functions
│   │   └── reference_data/
│   │       └── 2025 Labl IQ Rate Analyzer Template.xlsx
│   ├── __init__.py
│   └── main.py                # FastAPI application
├── requirements.txt           # Python dependencies
├── run.py                     # Startup script
└── README.md                  # This file
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ (recommended due to numpy compatibility)
- pip

### Installation

1. **Clone or download this backend folder**

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the API server:**
   ```bash
   python run.py
   ```

5. **Access the API:**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health
   - Root Endpoint: http://localhost:8000/

### AI Assistant Configuration
- Environment variables are defined in `app/core/config.py` and `.env`. The defaults use a local rule-based assistant so the feature works without external APIs.
- Set `AI_ASSISTANT_PROVIDER=openai` and `OPENAI_API_KEY=...` to proxy assistant replies through OpenAI (optional).
- Configure `OPENAI_MODEL` (default `gpt-4o-mini`) and `OPENAI_API_BASE` for Azure/OpenAI-compatible endpoints as needed.
- Session transcripts are stored under `app/data/assistant_sessions/`. Delete the folder to reset conversations during development.
- Run `python3 -m pytest app/test_assistant_service.py` to validate the assistant service.

## 🔧 API Endpoints

### Core Endpoints
- `GET /` - API information
- `GET /health` - Health check
- `GET /docs` - Interactive API documentation

### File Processing
- `POST /api/upload` - Upload CSV/Excel files
- `POST /api/map-columns` - Map file columns to required fields
- `POST /api/process` - Process mapped data and calculate rates

### Rate Analysis
- `GET /api/results/{analysis_id}` - Get analysis results
- `POST /api/export` - Export results in various formats

### Conversational Assistant
- `POST /api/assistant/sessions` - Create a new assistant session
- `GET /api/assistant/sessions/{session_id}` - Retrieve session history
- `POST /api/assistant/sessions/{session_id}/messages` - Send a chat message and receive the AI response

## 🔗 Frontend Integration

This backend is designed to work with a React/TypeScript frontend. Key integration points:

### CORS Configuration
The backend includes CORS middleware configured for frontend communication:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### API Base URL
- Development: `http://localhost:8000/api`
- Production: Configure as needed

### Key Features for Frontend
1. **File Upload**: Multipart form data support
2. **Column Mapping**: JSON-based column mapping
3. **Rate Calculation**: Advanced Amazon rate analysis
4. **Results Export**: Multiple format support
5. **Error Handling**: Structured error responses

## 🧮 Rate Calculation Engine

The core rate calculation engine (`calc_engine.py`) includes:
- Amazon rate table processing
- Zone-based calculations
- Surcharge calculations (DAS, EDAS, Remote)
- Dimensional weight calculations
- Fuel surcharge adjustments
- Service level markups

## 📊 Data Processing

The processor (`processor.py`) handles:
- CSV/Excel file parsing
- Data validation and cleaning
- Column mapping and transformation
- Error handling and reporting

## 🔒 Security Notes

For production deployment:
1. Configure CORS origins properly
2. Add authentication middleware
3. Implement rate limiting
4. Add input validation
5. Configure secure file upload limits

## 🐛 Troubleshooting

### Common Issues

1. **Port already in use:**
   ```bash
   # Kill process on port 8000
   lsof -ti:8000 | xargs kill -9
   ```

2. **Dependency issues:**
   ```bash
   # Upgrade pip and reinstall
   pip install --upgrade pip
   pip install -r requirements.txt --force-reinstall
   ```

3. **Python version issues:**
   - Use Python 3.11+ for best compatibility
   - numpy 1.26.0+ is recommended

### Logs
- Check console output for error messages
- API documentation available at `/docs`

## 📈 Next Steps

1. **Frontend Integration**: Connect with React/TypeScript frontend
2. **Database Integration**: Add user management and data persistence
3. **Authentication**: Implement JWT-based authentication
4. **File Storage**: Add S3 or similar for file storage
5. **Background Processing**: Add Celery for long-running tasks
6. **Monitoring**: Add logging and monitoring

## 🤝 Contributing

This backend is part of the Labl IQ Rate Analyzer hybrid application. For integration questions or issues, refer to the main project documentation.

## 📄 License

Part of the Labl IQ Rate Analyzer project.
