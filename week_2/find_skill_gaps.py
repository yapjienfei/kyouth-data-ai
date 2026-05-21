#!/usr/bin/env python3
"""
Module for prompting LLM models (Ollama local models and Google Gemini)
"""

import os
import requests
import json
from google import genai
from google.genai import types

# Configure Gemini if API key is available
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
gemini_client = None
if GOOGLE_API_KEY:
    gemini_client = genai.Client(api_key=GOOGLE_API_KEY)


def prompt_model(model: str, prompt: str) -> str:
    """
    Prompt a model and return the response.
    
    Args:
        model: Model name (e.g., 'llama3.1', 'phi3', 'deepseek-r1:1.5b',
               'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-3-flash')
        prompt: The prompt text to send to the model
    
    Returns:
        The model's response text, or error message if failed
    """
    
    # Check if it's a Gemini model
    gemini_models = [
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-3-flash'
    ]
    
    try:
        if model in gemini_models:
            return _prompt_gemini(model, prompt)
        else:
            return _prompt_ollama(model, prompt)
    except Exception as e:
        return f"Error prompting {model}: {str(e)}"


def _prompt_ollama(model: str, prompt: str) -> str:
    """Prompt an Ollama model running locally."""
    
    url = "http://localhost:11434/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1000
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "No response generated")
        
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)"
    except requests.exceptions.Timeout:
        return "Error: Request timed out. Model might be slow to respond"
    except requests.exceptions.RequestException as e:
        return f"Error making request to Ollama: {str(e)}"
    except json.JSONDecodeError:
        return "Error: Invalid response from Ollama"


def _prompt_gemini(model: str, prompt: str) -> str:
    """Prompt a Google Gemini model via the new genai SDK."""
    
    if not GOOGLE_API_KEY or not gemini_client:
        return "Error: GOOGLE_API_KEY environment variable not set"
    
    try:
        # Generate content using the new SDK
        response = gemini_client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1000,
            )
        )
        
        return response.text
        
    except Exception as e:
        return f"Error with Gemini API: {str(e)}"


def main():
    """Test function to demonstrate prompt_model usage."""
    
    print("=" * 60)
    print("Testing prompt_model function")
    print("=" * 60)
    
    # Test Ollama models
    test_prompts = [
        # ("llama3.1", "What is Python? Answer in one sentence."),
        ("phi3", "Explain what a function is in programming. Keep it brief."),
        ("deepseek-r1:1.5b", "What is machine learning? One sentence only."),
    ]
    
    # Test Gemini models if API key is available
    if GOOGLE_API_KEY and gemini_client:
        gemini_prompts = [
            ("gemini-2.5-flash", "What is artificial intelligence? One sentence."),
            ("gemini-2.5-flash-lite", "What is cloud computing? One sentence."),
        ]
        test_prompts.extend(gemini_prompts)
    
    for model, prompt in test_prompts:
        print(f"\n{'─' * 60}")
        print(f"Model: {model}")
        print(f"Prompt: {prompt}")
        print(f"Response: ", end="", flush=True)
        
        response = prompt_model(model, prompt)
        print(response)
        print(f"{'─' * 60}")


if __name__ == "__main__":
    main()