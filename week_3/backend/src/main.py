"""
Backend Chat Server for Resume Helper Chatbot
Receives messages from frontend and responds using AI models
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import sys
from pathlib import Path

# Add week_2 to path so we can import prompt_model
sys.path.append(str(Path(__file__).parent / "week_2"))

# Import your prompt_model from week 2
from prompt_model import prompt_model

# Create FastAPI app
app = FastAPI(
    title="Resume Helper Chatbot API",
    description="Backend API for Resume Helper Chatbot using Gemini",
    version="1.0.0",
)

# Enable CORS (allows frontend to talk to backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Pydantic Models (Request/Response Shapes) ============


class ChatRequest(BaseModel):
    """
    Expected JSON body from frontend:
    {
        "message": "What skills are needed?",
        "pdf_content": "Extracted text from PDF...",
        "timestamp": "2024-01-15T10:30:00Z"
    }
    """

    message: str
    pdf_content: Optional[str] = None
    pdf_name: Optional[str] = None
    timestamp: Optional[str] = None


class ChatResponse(BaseModel):
    """
    Response sent back to frontend:
    {
        "response": "The AI's answer...",
        "model_used": "gemini-2.5-flash-lite",
        "status": "success"
    }
    """

    response: str
    model_used: str
    status: str


# ============ Helper Functions ============


def combine_prompt_with_pdf(user_message: str, pdf_content: Optional[str]) -> str:
    """
    Combine user message with PDF content into a single prompt for the AI.

    If a PDF was uploaded, it's added as context before the user's question.
    """
    if pdf_content:
        # Truncate PDF content if too long (Gemini has token limits)
        max_pdf_chars = 4000
        truncated_pdf = pdf_content[:max_pdf_chars]

        prompt = f"""Here is a document that the user wants you to analyze:

--- START OF DOCUMENT ---
{truncated_pdf}
--- END OF DOCUMENT ---

Based on the document above, please answer the following question:

{user_message}

If the answer isn't in the document, use your general knowledge to help."""

        return prompt
    else:
        # No PDF, just send the user's message
        return user_message


def call_ai_with_fallback(
    prompt: str, preferred_model: str = "gemini-2.5-flash-lite"
) -> tuple[str, str]:
    """
    Call AI with automatic fallback to other models if rate limited.

    Args:
        prompt: The prompt to send to the AI
        preferred_model: The preferred model to try first

    Returns:
        tuple of (response_text, model_used)
    """
    # Define fallback order (preferred first, then alternatives)
    fallback_models = [
        preferred_model,
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.5-flash-lite",  # Try lite again as last resort
    ]

    # Remove duplicates while preserving order
    seen = set()
    unique_models = []
    for model in fallback_models:
        if model not in seen:
            seen.add(model)
            unique_models.append(model)

    last_error = None

    for model in unique_models:
        print(f"🔄 Trying model: {model}")

        # Call the model
        response = prompt_model(model, prompt)

        # Check if successful (not an error message)
        if not _is_error_response(response):
            print(f"✅ Success with model: {model}")
            return response, model

        # Check if it's a rate limit error
        if _is_rate_limit_error(response):
            print(f"⚠️  Model {model} is rate limited: {response[:100]}...")
            last_error = response
            continue  # Try next model

        # If it's another error (API key, etc.), still try next model
        print(f"⚠️  Model {model} failed: {response[:100]}...")
        last_error = response
        continue

    # All models failed
    return f"Error: All models failed. Last error: {last_error}", "none"


def _is_error_response(response: str) -> bool:
    """Check if the response contains an error."""
    error_indicators = [
        "Error:",
        "[Rate Limit]",
        "rate limited",
        "API key",
        "GOOGLE_API_KEY",
    ]
    for indicator in error_indicators:
        if indicator.lower() in response.lower():
            return True
    return False


def _is_rate_limit_error(response: str) -> bool:
    """Check if the error is specifically a rate limit."""
    rate_limit_indicators = [
        "[Rate Limit]",
        "Rate limit",
        "RPM limit",
        "TPM limit",
        "RPD limit",
        "quota exceeded",
        "too many requests",
    ]
    for indicator in rate_limit_indicators:
        if indicator.lower() in response.lower():
            return True
    return False


# ============ API Endpoints ============


@app.get("/")
async def root():
    """Root endpoint - shows API is running"""
    return {
        "message": "Resume Helper Chatbot API is running!",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring"""
    return {"status": "healthy", "service": "backend-chat"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint - receives user message and returns AI response.
    Automatically handles model fallback if rate limited.
    """

    print(f"📨 Received message: {request.message[:100]}...")
    if request.pdf_content:
        print(f"📎 PDF attached: {request.pdf_name} ({len(request.pdf_content)} chars)")

    try:
        # Step 1: Combine user message with PDF content
        full_prompt = combine_prompt_with_pdf(request.message, request.pdf_content)

        # Step 2: Call AI with automatic fallback
        print(f"🤖 Calling AI model with fallback support...")
        response_text, model_used = call_ai_with_fallback(full_prompt)

        # Step 3: Determine status
        if _is_error_response(response_text):
            status = "error"
        else:
            status = "success"

        print(f"✅ Response generated ({len(response_text)} chars) using {model_used}")
        return ChatResponse(
            response=response_text, model_used=model_used, status=status
        )

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        # Return error but don't crash
        return ChatResponse(
            response=f"I encountered an error: {str(e)}. Please try again.",
            model_used="error",
            status="error",
        )


# Optional: Add a test endpoint to verify PDF processing
@app.post("/test-pdf")
async def test_pdf(request: ChatRequest):
    """Test endpoint to see what the backend receives"""
    return {
        "received_message": request.message,
        "pdf_received": request.pdf_content is not None,
        "pdf_length": len(request.pdf_content) if request.pdf_content else 0,
        "pdf_name": request.pdf_name,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
