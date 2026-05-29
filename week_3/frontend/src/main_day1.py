"""
Simple FastAPI web server with Jinja2 templates
Serves a "Hello World" HTML page at the root endpoint
"""

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Create the FastAPI application instance
app = FastAPI()

# FIX: Correct way to set up templates
# Get the directory where this file is located
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

# Create templates directory if it doesn't exist
TEMPLATES_DIR.mkdir(exist_ok=True)

# FIX: Pass directory as a string, NOT as a Path object
# Some versions of FastAPI/Starlette have issues with Path objects
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Define a GET endpoint at the root URL ("/")
@app.get("/")
async def home(request: Request):
    """
    Handle GET requests to the root URL.
    Returns the index.html template
    """
    # The request parameter is required for templates
    return templates.TemplateResponse("index.html", {"request": request})


# Optional health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "frontend-server"}
