# Labl IQ Rate Analyzer - Hybrid Integration Guide

## 🎯 Purpose
This cleaned-up FastAPI backend is ready for integration with a React/TypeScript frontend. It contains only the essential files needed for the hybrid approach.

## 📦 What's Included

### Core Files (Essential)
- ✅ `app/services/calc_engine.py` - Advanced rate calculation engine
- ✅ `app/services/processor.py` - File processing and data handling
- ✅ `app/services/utils_processing.py` - Utility functions
- ✅ `app/services/profiles.py` - User profile management
- ✅ `app/api/routes.py` - API endpoints
- ✅ `app/core/config.py` - Configuration settings
- ✅ `app/schemas/schemas.py` - Pydantic data models
- ✅ `app/main.py` - FastAPI application (API-only)
- ✅ `requirements.txt` - Essential dependencies only
- ✅ `run.py` - Simple startup script

### Reference Data
- ✅ `app/services/reference_data/2025 Labl IQ Rate Analyzer Template.xlsx` - Rate table template

### Documentation
- ✅ `README.md` - Comprehensive setup and usage guide
- ✅ `INTEGRATION_GUIDE.md` - This file

## 🚀 Quick Start for Integration

1. **Extract this folder** to your development environment
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Start the API:**
   ```bash
   python run.py
   ```
4. **Test the API:**
   - Visit http://localhost:8000/docs for interactive documentation
   - Visit http://localhost:8000/health for health check

## 🔗 Frontend Integration Points

### API Base URL
- Development: `http://localhost:8000/api`
- All endpoints are prefixed with `/api`

### Key Endpoints for Frontend
1. **File Upload**: `POST /api/upload`
2. **Column Mapping**: `POST /api/map-columns`
3. **Rate Processing**: `POST /api/process`
4. **Results**: `GET /api/results/{id}`

### CORS Configuration
The backend is pre-configured with CORS for frontend communication:
```python
allow_origins=["*"]  # Configure for production
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

## 🧮 Rate Calculation Features

The backend includes the most advanced rate calculation engine from the Streamlit project:

### Core Features
- Amazon rate table processing
- Zone-based calculations
- Surcharge calculations (DAS, EDAS, Remote)
- Dimensional weight calculations
- Fuel surcharge adjustments
- Service level markups
- Advanced error handling

### Data Processing
- CSV/Excel file parsing
- Smart column mapping
- Data validation and cleaning
- Comprehensive error reporting

## 📊 File Size Breakdown

- **Total Size**: ~13MB
- **Largest File**: `2025 Labl IQ Rate Analyzer Template.xlsx` (~13MB)
- **Code Files**: ~200KB
- **Dependencies**: Minimal, essential only

## 🔧 Technical Specifications

### Python Version
- **Recommended**: Python 3.11+
- **Minimum**: Python 3.8+
- **Note**: numpy 1.26.0+ for best compatibility

### Dependencies
- FastAPI 0.104.1
- pandas >= 2.2.0
- numpy >= 1.26.0
- openpyxl >= 3.1.0
- pydantic 2.5.0

### Architecture
- **Framework**: FastAPI
- **API Style**: RESTful
- **Data Validation**: Pydantic
- **File Processing**: pandas + openpyxl
- **CORS**: Pre-configured for frontend

## 🎨 Integration with Figma Design

This backend is designed to work seamlessly with a React frontend implementing Figma designs:

### Expected Frontend Features
1. **File Upload Interface**: Drag & drop or file browser
2. **Column Mapping UI**: Interactive column selection
3. **Results Dashboard**: Data visualization and tables
4. **Export Options**: Download results in various formats
5. **Settings Panel**: Configure rate calculation parameters

### API Response Format
All endpoints return structured JSON responses:
```json
{
  "success": true,
  "data": {...},
  "message": "Operation completed successfully"
}
```

## 🚨 Important Notes

1. **Template File**: The Excel template is required for rate calculations
2. **Python Version**: Use Python 3.11+ to avoid numpy compatibility issues
3. **CORS**: Configure properly for production deployment
4. **File Upload**: Currently supports local file storage
5. **Authentication**: Not included - add as needed for production

## 📈 Next Steps for Full Integration

1. **Frontend Development**: Build React components based on Figma designs
2. **API Integration**: Connect frontend to these backend endpoints
3. **Database**: Add user management and data persistence
4. **Authentication**: Implement JWT-based auth
5. **File Storage**: Add S3 or similar for production
6. **Deployment**: Containerize with Docker

## 🆘 Support

- **API Documentation**: Available at `/docs` when server is running
- **Health Check**: Available at `/health`
- **Error Handling**: All endpoints include structured error responses
- **Logging**: Check console output for debugging

---

**Ready for Integration!** 🚀

This backend contains all the essential components needed to power a modern React frontend with advanced rate calculation capabilities. 