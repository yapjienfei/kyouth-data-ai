"""
FastAPI server for chat interface
Serves HTML page and handles chat requests
"""

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI()

# Get backend URL from environment
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8001")

# Set up templates
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

# Create directories if they don't exist
TEMPLATES_DIR.mkdir(exist_ok=True)

# Set up templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/")
async def chat_page(request: Request):
    """
    Serve the chat interface HTML page
    Pass the backend URL to the template
    """
    return templates.TemplateResponse(
        "chat_page.html", {"request": request, "backend_url": BACKEND_API_URL}
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "frontend-chat"}
