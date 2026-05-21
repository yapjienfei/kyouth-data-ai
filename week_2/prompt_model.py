#!/usr/bin/env python3
"""
Module for prompting LLM models (Ollama local models and Google Gemini)
"""

import os
import time
import requests
import json
import google.generativeai as genai

# Configure Gemini if API key is available
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


def prompt_model(model: str, prompt: str) -> tuple[str, float]:
    """
    Prompt a model and return the response and time taken.
    
    Args:
        model: Model name (e.g., 'llama3.1', 'phi3', 'deepseek-r1:1.5b',
               'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-3-flash')
        prompt: The prompt text to send to the model
    
    Returns:
        A tuple of (response text, time taken in seconds)
    """
    
    # Check if it's a Gemini model
    gemini_models = [
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-3-flash'
    ]
    
    start_time = time.time()
    
    try:
        if model in gemini_models:
            response = _prompt_gemini(model, prompt)
        else:
            response = _prompt_ollama(model, prompt)
        
        elapsed_time = time.time() - start_time
        return response, elapsed_time
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        return f"Error prompting {model}: {str(e)}", elapsed_time


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
        # Increased timeout to 120 seconds (2 minutes) for slower models
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "No response generated")
        
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)"
    except requests.exceptions.Timeout:
        return "Error: Request timed out after 120 seconds. Model might be too slow or not loaded properly"
    except requests.exceptions.RequestException as e:
        return f"Error making request to Ollama: {str(e)}"
    except json.JSONDecodeError:
        return "Error: Invalid response from Ollama"


def _prompt_gemini(model: str, prompt: str) -> str:
    """Prompt a Google Gemini model via the old (but working) SDK."""
    
    if not GOOGLE_API_KEY:
        return "Error: GOOGLE_API_KEY environment variable not set"
    
    try:
        # Initialize the model
        gemini_model = genai.GenerativeModel(model)
        
        # Generate response
        response = gemini_model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 1000,
            }
        )
        
        return response.text
        
    except Exception as e:
        return f"Error with Gemini API: {str(e)}"


def main():
    """Test function to demonstrate prompt_model usage."""
    
    print("=" * 70)
    print("Testing prompt_model function with timing")
    print("=" * 70)
    
    # Test Ollama models
    test_prompts = [
        ("phi3", "What is Python? Answer in one sentence."),
        ("deepseek-r1:1.5b", "What is machine learning? One sentence only."),
    ]
    
    # Test Gemini models if API key is available
    # if GOOGLE_API_KEY:
    #     gemini_prompts = [
    #         ("gemini-2.5-flash", "What is artificial intelligence? One sentence."),
    #         ("gemini-2.5-flash-lite", "What is cloud computing? One sentence."),
    #     ]
    #     test_prompts.extend(gemini_prompts)
    
    for model, prompt in test_prompts:
        print(f"\n{'─' * 70}")
        print(f"Model: {model}")
        print(f"Prompt: {prompt}")
        print(f"Processing... ", end="", flush=True)
        
        response, elapsed_time = prompt_model(model, prompt)
        
        # Format time nicely
        if elapsed_time < 1:
            time_str = f"{elapsed_time*1000:.0f} ms"
        else:
            time_str = f"{elapsed_time:.2f} seconds"
        
        print(f"\nResponse: {response}")
        print(f"⏱️  Time taken: {time_str}")
        
        # Add performance indicator
        if "Error" in response or "timed out" in response:
            print(f"⚠️  Status: FAILED")
        else:
            print(f"✅ Status: SUCCESS")
        print(f"{'─' * 70}")


if __name__ == "__main__":
    main()