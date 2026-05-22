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

# Define which models are Gemini vs Ollama
GEMINI_MODELS = {
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite', 
    'gemini-3.5-flash'
}

def prompt_model(model: str, prompt: str) -> str:
    """
    Prompt a model and return the response.
    
    Args:
        model: Model name (e.g., 'llama3.1', 'llama3.2:1b', 'phi3', 'deepseek-r1:1.5b',
               'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-3.5-flash')
        prompt: The prompt text to send to the model
    
    Returns:
        The response text from the model
    """
    
    try:
        # Smartly select which backend to use
        if model in GEMINI_MODELS:
            return _prompt_gemini(model, prompt)
        else:
            # Assume any other model is Ollama
            return _prompt_ollama(model, prompt)
        
    except Exception as e:
        # Function should not crash - return error message
        return f"[{model} Error] {str(e)}"


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
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "No response generated")
        
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure Ollama is running"
    except requests.exceptions.Timeout:
        return "Error: Request timed out after 240 seconds"
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"
    except json.JSONDecodeError:
        return "Error: Invalid response from Ollama"


def _prompt_gemini(model: str, prompt: str) -> str:
    """Prompt a Google Gemini model."""
    
    if not GOOGLE_API_KEY:
        return "Error: GOOGLE_API_KEY environment variable not set"
    
    try:
        gemini_model = genai.GenerativeModel(model)
        
        response = gemini_model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 1000,
            }
        )
        
        return response.text
        
    except Exception as e:
        return f"[Gemini Error] {str(e)}"


def prompt_model_with_timing(model: str, prompt: str) -> tuple[str, float]:
    """
    Wrapper function that returns both response and timing.
    Useful for performance testing.
    
    Args:
        model: Model name
        prompt: The prompt text
    
    Returns:
        A tuple of (response text, time taken in seconds)
    """
    start_time = time.time()
    response = prompt_model(model, prompt)
    elapsed_time = time.time() - start_time
    return response, elapsed_time


def main():
    """Test function to demonstrate prompt_model usage with timing."""
    
    print("=" * 80)
    print("Testing LLM Models with Performance Timing")
    print("=" * 80)
    
    # Define test cases: (model, prompt, description)
    test_cases = [
        # Ollama models
        ("phi3", "What is Python? Answer in one sentence.", "Ollama - phi3"),
        ("deepseek-r1:1.5b", "What is machine learning? Answer in one sentence.", "Ollama - DeepSeek R1 1.5B"),
        ("llama3.2:1b", "What is artificial intelligence? Answer in one sentence.", "Ollama - Llama 3.2 1B"),
        #("llama3.1", "What is artificial intelligence? Answer in one sentence.", "Ollama - Llama 3.1"),
    ]
    
    # Add Gemini test cases only if API key is available
    if GOOGLE_API_KEY:
        gemini_cases = [
            ("gemini-2.5-flash", "What is the capital of France? Answer in one sentence.", "Gemini 2.5 Flash"),
            ("gemini-2.5-flash-lite", "Explain quantum computing in one sentence.", "Gemini 2.5 Flash Lite"),
            ("gemini-3.5-flash", "What is the meaning of life? Answer in one sentence.", "Gemini 3.5 Flash"),
        ]
        test_cases.extend(gemini_cases)
    else:
        print("\n⚠️  GOOGLE_API_KEY not set. Skipping Gemini model tests.\n")
    
    # Store results for summary
    results = []
    
    # Run each test case
    for model, prompt, description in test_cases:
        print(f"\n{'─' * 80}")
        print(f"📝 Test: {description}")
        print(f"🔧 Model: {model}")
        print(f"💬 Prompt: {prompt}")
        print(f"⏳ Processing... ", end="", flush=True)
        
        # Get response with timing
        response, elapsed_time = prompt_model_with_timing(model, prompt)
        
        # Format time nicely
        if elapsed_time < 1:
            time_str = f"{elapsed_time*1000:.0f} ms"
        else:
            time_str = f"{elapsed_time:.2f} seconds"
        
        # Print response (truncate if too long)
        print(f"\r⏳ Processing... ✅ Done in {time_str}")
        print(f"\n📄 Response: {response[:200]}{'...' if len(response) > 200 else ''}")
        
        # Show full response for short ones
        if len(response) <= 200:
            print(f"\n💬 Full response: {response}")
        
        # Add to results for summary
        status = "✅ SUCCESS" if not ("Error" in response or "timed out" in response) else "❌ FAILED"
        results.append({
            "model": description,
            "time": elapsed_time,
            "time_str": time_str,
            "status": status,
            "response_length": len(response)
        })
        
        print(f"📊 Status: {status}")
        print(f"📏 Response length: {len(response)} characters")
        print(f"{'─' * 80}")
        
        # Small delay between requests to avoid overwhelming services
        time.sleep(1)
    
    # Print summary table
    print("\n" + "=" * 80)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"{'Model':<30} {'Time':<15} {'Status':<12} {'Length':<10}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['model']:<30} {result['time_str']:<15} {result['status']:<12} {result['response_length']:<10}")
    
    # Calculate statistics
    successful_tests = [r for r in results if "✅" in r['status']]
    if successful_tests:
        avg_time = sum(r['time'] for r in successful_tests) / len(successful_tests)
        fastest = min(successful_tests, key=lambda x: x['time'])
        slowest = max(successful_tests, key=lambda x: x['time'])
        
        print("-" * 80)
        print(f"📈 Statistics:")
        print(f"   • Average response time: {avg_time:.2f} seconds")
        print(f"   • Fastest model: {fastest['model']} ({fastest['time_str']})")
        print(f"   • Slowest model: {slowest['model']} ({slowest['time_str']})")
    
    print("=" * 80)


if __name__ == "__main__":
    main()