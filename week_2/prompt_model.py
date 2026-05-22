#!/usr/bin/env python3
"""
Module for prompting LLM models (Ollama local models and Google Gemini)
with automatic rate limit tracking.
"""

import os
import time
import requests
import json
import google.generativeai as genai
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================================
# PART 1: GEMINI API CONFIGURATION
# ============================================================================
# This section configures the Google Gemini API using your API key.
# The API key should be stored in an environment variable for security.
# NEVER hardcode API keys in your source code!

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# Define which models are Gemini vs Ollama
# This allows the code to intelligently route requests to the correct backend
GEMINI_MODELS = {
    'gemini-2.5-flash',      # Fast, efficient model
    'gemini-2.5-flash-lite', # Lighter version for simpler tasks
    'gemini-3.5-flash'       # Newer version with better capabilities
}

# ============================================================================
# PART 2: RATE LIMITER CLASS
# ============================================================================
# This class tracks API usage in real-time and prevents exceeding quotas.
# It reads the MAXIMUM limits from rate_limits.txt and tracks CURRENT usage.
# The rate_limits.txt file is NEVER modified - only read once at startup.

class RateLimiter:
    """
    Automatically track and enforce rate limits for Gemini API.
    
    How it works:
    1. Reads max limits from rate_limits.txt at startup (e.g., 5 requests per minute)
    2. Tracks every request made during script execution in memory
    3. Before each request, checks if we're within limits
    4. Automatically resets counters after time windows expire (1 minute for RPM, 24 hours for RPD)
    5. Never modifies the rate_limits.txt file
    """
    
    def __init__(self, rate_limits_file="rate_limits.txt"):
        # Store maximum allowed limits (these NEVER change during execution)
        self.max_limits = {}
        
        # Track current usage in memory
        # Structure: usage[model] = {
        #     'requests': [timestamps of recent requests],
        #     'tokens': [(timestamp, token_count)],
        #     'daily_requests': [timestamps from today]
        # }
        self.usage = defaultdict(lambda: {
            'requests': [],      # For RPM (Requests Per Minute)
            'tokens': [],        # For TPM (Tokens Per Minute)
            'daily_requests': [] # For RPD (Requests Per Day)
        })
        
        # Load the maximum limits from the file
        self.load_max_limits(rate_limits_file)
    
    def load_max_limits(self, filename):
        """
        Read maximum rate limits from rate_limits.txt.
        This file contains the QUOTAS, not current usage.
        Example line: gemini-2.5-flash 5 250K 20
        Means: 5 requests per minute, 250,000 tokens per minute, 20 requests per day
        """
        try:
            with open(filename, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        parts = line.split()
                        if len(parts) >= 4:
                            model = parts[0]
                            rpm = self._parse_limit_value(parts[1])  # Requests Per Minute
                            tpm = self._parse_limit_value(parts[2])  # Tokens Per Minute
                            rpd = self._parse_limit_value(parts[3])  # Requests Per Day
                            
                            self.max_limits[model] = {
                                'rpm': rpm,
                                'tpm': tpm,
                                'rpd': rpd
                            }
                            print(f"✓ Loaded rate limits for {model}: {rpm} RPM, {tpm} TPM, {rpd} RPD")
                        else:
                            print(f"⚠️  Line {line_num}: Invalid format (expected 4 fields): {line}")
        except FileNotFoundError:
            print("⚠️  rate_limits.txt not found. Rate limiting disabled.")
            print("   Create this file with format: model RPM TPM RPD")
        except Exception as e:
            print(f"⚠️  Error loading rate limits: {e}")
    
    def _parse_limit_value(self, value):
        """
        Convert limit values with K/M/B suffixes to integers.
        
        Examples:
        - "5" -> 5
        - "250K" -> 250,000
        - "10M" -> 10,000,000
        - "2B" -> 2,000,000,000
        """
        value = str(value).upper()
        if 'K' in value:
            # K = Thousand (multiply by 1000)
            return int(float(value.replace('K', '')) * 1000)
        elif 'M' in value:
            # M = Million (multiply by 1,000,000)
            return int(float(value.replace('M', '')) * 1000000)
        elif 'B' in value:
            # B = Billion (multiply by 1,000,000,000)
            return int(float(value.replace('B', '')) * 1000000000)
        else:
            # Plain number
            return int(float(value))
    
    def _clean_old_records(self, model):
        """
        Remove usage records that are outside the tracking windows.
        This implements the "rolling window" for rate limits.
        
        For RPM/TPM: Keep only requests from the last 60 seconds
        For RPD: Keep only requests from the last 24 hours
        """
        now = datetime.now()
        
        # Clean RPM/TPM records (keep last 60 seconds)
        minute_ago = now - timedelta(minutes=1)
        self.usage[model]['requests'] = [
            t for t in self.usage[model]['requests'] 
            if t > minute_ago
        ]
        self.usage[model]['tokens'] = [
            (t, count) for t, count in self.usage[model]['tokens']
            if t > minute_ago
        ]
        
        # Clean RPD records (keep last 24 hours)
        day_ago = now - timedelta(days=1)
        self.usage[model]['daily_requests'] = [
            t for t in self.usage[model]['daily_requests']
            if t > day_ago
        ]
    
    def can_make_request(self, model, estimated_tokens=100):
        """
        Check if a request can be made without exceeding rate limits.
        
        Returns:
            (can_proceed: bool, message: str)
            
        This is called BEFORE making an API request to prevent quota violations.
        """
        # If no limits defined for this model, allow unlimited requests
        if model not in self.max_limits:
            return True, "No rate limits defined (unlimited)"
        
        # Clean old records to get current usage
        self._clean_old_records(model)
        limits = self.max_limits[model]
        
        # Check 1: Requests Per Minute (RPM)
        rpm_used = len(self.usage[model]['requests'])
        if rpm_used >= limits['rpm']:
            # Calculate how long to wait until next request is allowed
            oldest_request = self.usage[model]['requests'][0]
            seconds_to_wait = 60 - (datetime.now() - oldest_request).seconds
            return False, f"RPM limit ({limits['rpm']}) exceeded. Wait {seconds_to_wait}s"
        
        # Check 2: Tokens Per Minute (TPM)
        tpm_used = sum(count for _, count in self.usage[model]['tokens'])
        if tpm_used + estimated_tokens > limits['tpm']:
            return False, f"TPM limit ({limits['tpm']}) exceeded. Used {tpm_used} tokens"
        
        # Check 3: Requests Per Day (RPD)
        rpd_used = len(self.usage[model]['daily_requests'])
        if rpd_used >= limits['rpd']:
            return False, f"RPD limit ({limits['rpd']}) exceeded. Used {rpd_used} requests today"
        
        # All checks passed - request is allowed
        return True, f"OK ({rpm_used}/{limits['rpm']} RPM, {tpm_used}/{limits['tpm']} TPM)"
    
    def record_request(self, model, tokens_used=0):
        """
        Record that a request was made and how many tokens were used.
        
        This is called AFTER a successful API request to update usage counters.
        The counters are stored in memory and reset automatically after time windows expire.
        """
        now = datetime.now()
        self.usage[model]['requests'].append(now)           # For RPM tracking
        self.usage[model]['daily_requests'].append(now)     # For RPD tracking
        if tokens_used > 0:
            self.usage[model]['tokens'].append((now, tokens_used))  # For TPM tracking
    
    def get_usage_stats(self, model):
        """
        Get current usage statistics for display.
        Shows how much of the quota has been used in the current windows.
        """
        if model not in self.max_limits:
            return None
        
        self._clean_old_records(model)
        limits = self.max_limits[model]
        
        rpm_used = len(self.usage[model]['requests'])
        tpm_used = sum(count for _, count in self.usage[model]['tokens'])
        rpd_used = len(self.usage[model]['daily_requests'])
        
        return {
            'rpm_used': rpm_used,
            'rpm_limit': limits['rpm'],
            'rpm_remaining': limits['rpm'] - rpm_used,
            'tpm_used': tpm_used,
            'tpm_limit': limits['tpm'],
            'tpm_remaining': limits['tpm'] - tpm_used,
            'rpd_used': rpd_used,
            'rpd_limit': limits['rpd'],
            'rpd_remaining': limits['rpd'] - rpd_used,
        }

# Create a global instance of the rate limiter
# This loads rate_limits.txt once at startup and tracks usage throughout the script
rate_limiter = RateLimiter("rate_limits.txt")

# ============================================================================
# PART 3: MAIN PROMPT FUNCTION (WITH RATE LIMIT INTEGRATION)
# ============================================================================

def prompt_model(model: str, prompt: str) -> str:
    """
    Prompt a model and return the response with automatic rate limit tracking.
    
    The flow:
    1. Check if it's a Gemini model or Ollama model
    2. For Gemini: Check rate limits BEFORE making request
    3. Make the request if limits allow
    4. Record the usage AFTER successful request
    5. Return response or error message
    
    Args:
        model: Model name (e.g., 'llama3.2:1b', 'gemini-2.5-flash', etc.)
        prompt: The prompt text to send to the model
    
    Returns:
        The response text from the model or an error message
    """
    
    try:
        # Smart routing: Gemini models vs Ollama models
        if model in GEMINI_MODELS:
            # STEP 1: Estimate token usage for this request
            # Rough estimate: 1.3 tokens per word (typical for English)
            estimated_tokens = len(prompt.split()) * 1.3
            
            # STEP 2: Check if we're within rate limits
            can_proceed, message = rate_limiter.can_make_request(model, estimated_tokens)
            
            # STEP 3: If rate limit would be exceeded, return error instead of making request
            if not can_proceed:
                return f"[Rate Limit] {model}: {message}"
            
            # STEP 4: Make the actual API request
            response = _prompt_gemini(model, prompt)
            
            # STEP 5: Calculate actual tokens used (estimate)
            # This helps track TPM (Tokens Per Minute) accurately
            tokens_used = len(response.split()) * 1.3 + len(prompt.split()) * 1.3
            
            # STEP 6: Record this request for future rate limit checks
            rate_limiter.record_request(model, int(tokens_used))
            
            return response
        else:
            # Ollama models run locally with no rate limits
            return _prompt_ollama(model, prompt)
        
    except Exception as e:
        # Catch any unexpected errors to prevent crashing
        # This satisfies the requirement: "The function should not crash due to unexpected errors"
        return f"[{model} Error] {str(e)}"


def _prompt_ollama(model: str, prompt: str) -> str:
    """
    Prompt an Ollama model running locally.
    
    Ollama runs on localhost:11434 and provides a REST API.
    No rate limits apply since it's running on your own machine.
    """
    
    url = "http://localhost:11434/api/generate"
    
    # Configure the request payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,  # Don't stream - get complete response at once
        "options": {
            "temperature": 0.7,  # Controls randomness (0=deterministic, 1=creative)
            "num_predict": 1000  # Max tokens to generate
        }
    }
    
    try:
        # Send POST request with 240 second timeout (4 minutes)
        # Some models like llama3.1 are large and need more time
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        result = response.json()
        return result.get("response", "No response generated")
        
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)"
    except requests.exceptions.Timeout:
        return "Error: Request timed out after 240 seconds. Model might be too slow"
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"
    except json.JSONDecodeError:
        return "Error: Invalid response from Ollama"


def _prompt_gemini(model: str, prompt: str) -> str:
    """
    Prompt a Google Gemini model via the official SDK.
    
    This function makes the actual API call to Google's servers.
    Rate limiting is handled BEFORE calling this function.
    """
    
    if not GOOGLE_API_KEY:
        return "Error: GOOGLE_API_KEY environment variable not set"
    
    try:
        # Create a model instance
        gemini_model = genai.GenerativeModel(model)
        
        # Generate content with configuration
        response = gemini_model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 1000,
            }
        )
        
        return response.text
        
    except Exception as e:
        # Return user-friendly error message
        return f"[Gemini Error] {str(e)}"


def prompt_model_with_timing(model: str, prompt: str) -> tuple[str, float]:
    """
    Wrapper function that returns both response and timing.
    Useful for performance testing and comparison.
    
    Returns:
        A tuple of (response text, time taken in seconds)
    """
    start_time = time.time()
    response = prompt_model(model, prompt)
    elapsed_time = time.time() - start_time
    return response, elapsed_time


def display_rate_limit_status():
    """
    Show current rate limit usage for all Gemini models.
    This helps users understand how close they are to hitting quotas.
    """
    print("\n" + "=" * 80)
    print("📊 CURRENT RATE LIMIT USAGE (Auto-tracked in memory)")
    print("=" * 80)
    print("Note: These counters reset automatically after time windows expire")
    print("-" * 80)
    
    for model in GEMINI_MODELS:
        stats = rate_limiter.get_usage_stats(model)
        if stats:
            print(f"\n🔹 {model}")
            print(f"   📈 RPM: {stats['rpm_used']}/{stats['rpm_limit']} ( {stats['rpm_remaining']} remaining)")
            print(f"   🔤 TPM: {stats['tpm_used']:,}/{stats['tpm_limit']:,} ( {stats['tpm_remaining']:,} remaining)")
            print(f"   📅 RPD: {stats['rpd_used']}/{stats['rpd_limit']} ( {stats['rpd_remaining']} remaining)")
            
            # Show reset information
            if stats['rpm_used'] > 0:
                print(f"   ⏰ RPM resets in: ~{60 - (datetime.now().second)} seconds")
            if stats['rpd_used'] > 0:
                hours_left = 24 - datetime.now().hour
                print(f"   ⏰ RPD resets in: ~{hours_left} hours")


def main():
    """
    Test function to demonstrate prompt_model usage with timing and rate limits.
    """
    
    print("=" * 80)
    print("Testing LLM Models with Performance Timing & Rate Limits")
    print("=" * 80)
    
    # Display loaded rate limits
    if rate_limiter.max_limits:
        print("\n✅ Rate limits loaded from rate_limits.txt")
    else:
        print("\n⚠️  No rate limits loaded. Create rate_limits.txt to enable tracking")
    
    # Define test cases for Ollama models
    test_cases = [
        ("phi3", "What is Python? Answer in one sentence.", "Ollama - phi3"),
        ("deepseek-r1:1.5b", "What is machine learning? Answer in one sentence.", "Ollama - DeepSeek R1 1.5B"),
        ("llama3.2:1b", "What is artificial intelligence? Answer in one sentence.", "Ollama - Llama 3.2 1B"),
    ]
    
    # Add Gemini test cases if API key is available
    if GOOGLE_API_KEY:
        gemini_cases = [
            ("gemini-2.5-flash", "What is the capital of France? Answer in one sentence.", "Gemini 2.5 Flash"),
            ("gemini-2.5-flash-lite", "Explain quantum computing in one sentence.", "Gemini 2.5 Flash Lite"),
            ("gemini-3.5-flash", "What is the meaning of life? Answer in one sentence.", "Gemini 3.5 Flash"),
        ]
        test_cases.extend(gemini_cases)
    else:
        print("\n⚠️  GOOGLE_API_KEY not set. Skipping Gemini model tests.\n")
        print("   To test Gemini models, set your API key:")
        print("   export GOOGLE_API_KEY='your-api-key-here'")
    
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
        
        # Determine status
        is_error = "Error" in response or "timed out" in response or "Rate Limit" in response
        status = "✅ SUCCESS" if not is_error else "❌ FAILED"
        
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
    
    # Display rate limit usage after Gemini tests
    if GOOGLE_API_KEY and rate_limiter.max_limits:
        display_rate_limit_status()
    
    # Print summary table
    print("\n" + "=" * 80)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 80)
    print(f"{'Model':<30} {'Time':<15} {'Status':<12} {'Length':<10}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['model']:<30} {result['time_str']:<15} {result['status']:<12} {result['response_length']:<10}")
    
    # Calculate statistics for successful tests
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
    print("   All usage tracking is done in memory and resets automatically")


if __name__ == "__main__":
    main()