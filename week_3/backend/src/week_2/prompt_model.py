#!/usr/bin/env python3
"""
Module for prompting LLM models (Ollama local models and Google Gemini)
with automatic rate limit tracking.
"""

import os
import time
import requests
import json
from google import genai
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

# ============================================================================
# PART 1: GEMINI API CONFIGURATION
# ============================================================================

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai_client = genai.Client(api_key=GOOGLE_API_KEY)
else:
    genai_client = None

# Define which models are Gemini vs Ollama
GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
}

# ============================================================================
# PART 2: RATE LIMITER CLASS
# ============================================================================


class RateLimiter:
    """
    Automatically track and enforce rate limits for Gemini API.
    Now with PERSISTENT storage for RPD (Requests Per Day) across script runs.
    """

    def __init__(
        self, rate_limits_file="rate_limits.txt", storage_file="rate_usage.json"
    ):
        # Store maximum allowed limits (these NEVER change during execution)
        self.max_limits = {}

        # Track current usage in memory
        self.usage = defaultdict(
            lambda: {
                "requests": [],  # For RPM (Requests Per Minute)
                "tokens": [],  # For TPM (Tokens Per Minute)
                "daily_requests": [],  # For RPD (Requests Per Day) - PERSISTENT
            }
        )

        self.storage_file = storage_file

        # Load the maximum limits from the file
        self.load_max_limits(rate_limits_file)

        # Load previously saved usage data (for RPD persistence)
        self.load_persistent_usage()

    def load_max_limits(self, filename):
        """Read maximum rate limits from rate_limits.txt."""
        try:
            with open(filename, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 4:
                            model = parts[0]
                            rpm = self._parse_limit_value(parts[1])
                            tpm = self._parse_limit_value(parts[2])
                            rpd = self._parse_limit_value(parts[3])

                            self.max_limits[model] = {
                                "rpm": rpm,
                                "tpm": tpm,
                                "rpd": rpd,
                            }
                            print(
                                f"✓ Loaded rate limits for {model}: {rpm} RPM, {tpm} TPM, {rpd} RPD"
                            )
                        else:
                            print(
                                f"⚠️  Line {line_num}: Invalid format (expected 4 fields): {line}"
                            )
        except FileNotFoundError:
            print("⚠️  rate_limits.txt not found. Rate limiting disabled.")
            print("   Create this file with format: model RPM TPM RPD")
        except Exception as e:
            print(f"⚠️  Error loading rate limits: {e}")

    def load_persistent_usage(self):
        """Load previously saved usage data from disk (for RPD persistence)."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    saved_data = json.load(f)

                # Convert string timestamps back to datetime objects
                for model, data in saved_data.items():
                    # Only load daily_requests (RPM/TPM don't need persistence)
                    if "daily_requests" in data:
                        self.usage[model]["daily_requests"] = [
                            datetime.fromisoformat(ts)
                            for ts in data.get("daily_requests", [])
                        ]
                    # Optionally load requests/tokens if you want them persistent too
                    if "requests" in data:
                        self.usage[model]["requests"] = [
                            datetime.fromisoformat(ts)
                            for ts in data.get("requests", [])
                        ]
                    if "tokens" in data:
                        self.usage[model]["tokens"] = [
                            (datetime.fromisoformat(ts), count)
                            for ts, count in data.get("tokens", [])
                        ]
                print(f"✓ Loaded persistent usage data from {self.storage_file}")
            except Exception as e:
                print(f"⚠️ Could not load saved usage: {e}")
        else:
            print(f"ℹ️ No existing usage data found. Starting fresh.")

    def save_persistent_usage(self):
        """Save current usage data to disk for future runs."""
        try:
            # Convert datetime objects to strings for JSON serialization
            save_data = {}
            for model, data in self.usage.items():
                save_data[model] = {
                    "requests": [ts.isoformat() for ts in data["requests"]],
                    "tokens": [(ts.isoformat(), count) for ts, count in data["tokens"]],
                    "daily_requests": [ts.isoformat() for ts in data["daily_requests"]],
                }

            with open(self.storage_file, "w") as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save usage data: {e}")

    def _parse_limit_value(self, value):
        """Convert limit values with K/M/B suffixes to integers."""
        value = str(value).upper()
        if "K" in value:
            return int(float(value.replace("K", "")) * 1000)
        elif "M" in value:
            return int(float(value.replace("M", "")) * 1000000)
        elif "B" in value:
            return int(float(value.replace("B", "")) * 1000000000)
        else:
            return int(float(value))

    def _clean_old_records(self, model):
        """Remove usage records that are outside the tracking windows."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)

        self.usage[model]["requests"] = [
            t for t in self.usage[model]["requests"] if t > minute_ago
        ]
        self.usage[model]["tokens"] = [
            (t, count) for t, count in self.usage[model]["tokens"] if t > minute_ago
        ]
        self.usage[model]["daily_requests"] = [
            t for t in self.usage[model]["daily_requests"] if t > day_ago
        ]

    def can_make_request(self, model, estimated_tokens=100):
        """Check if a request can be made without exceeding rate limits."""
        if model not in self.max_limits:
            return True, "No rate limits defined (unlimited)"

        self._clean_old_records(model)
        limits = self.max_limits[model]

        # Check 1: Requests Per Minute (RPM)
        rpm_used = len(self.usage[model]["requests"])
        if rpm_used >= limits["rpm"]:
            oldest_request = self.usage[model]["requests"][0]
            seconds_to_wait = 60 - (datetime.now() - oldest_request).seconds
            return (
                False,
                f"RPM limit ({limits['rpm']}) exceeded. Wait {seconds_to_wait}s",
            )

        # Check 2: Tokens Per Minute (TPM)
        tpm_used = sum(count for _, count in self.usage[model]["tokens"])
        if tpm_used + estimated_tokens > limits["tpm"]:
            return (
                False,
                f"TPM limit ({limits['tpm']}) exceeded. Used {tpm_used} tokens",
            )

        # Check 3: Requests Per Day (RPD)
        rpd_used = len(self.usage[model]["daily_requests"])
        if rpd_used >= limits["rpd"]:
            return (
                False,
                f"RPD limit ({limits['rpd']}) exceeded. Used {rpd_used} requests today",
            )

        return (
            True,
            f"OK ({rpm_used}/{limits['rpm']} RPM, {tpm_used}/{limits['tpm']} TPM)",
        )

    def record_request(self, model, tokens_used=0):
        """Record that a request was made and SAVE to disk for persistence."""
        now = datetime.now()
        self.usage[model]["requests"].append(now)  # For RPM tracking
        self.usage[model]["daily_requests"].append(now)  # For RPD tracking
        if tokens_used > 0:
            self.usage[model]["tokens"].append((now, tokens_used))  # For TPM tracking

        # Save to disk after every request to persist across script runs
        self.save_persistent_usage()

    def get_usage_stats(self, model):
        """Get current usage statistics for display."""
        if model not in self.max_limits:
            return None

        self._clean_old_records(model)
        limits = self.max_limits[model]

        rpm_used = len(self.usage[model]["requests"])
        tpm_used = sum(count for _, count in self.usage[model]["tokens"])
        rpd_used = len(self.usage[model]["daily_requests"])

        return {
            "rpm_used": rpm_used,
            "rpm_limit": limits["rpm"],
            "rpm_remaining": limits["rpm"] - rpm_used,
            "tpm_used": tpm_used,
            "tpm_limit": limits["tpm"],
            "tpm_remaining": limits["tpm"] - tpm_used,
            "rpd_used": rpd_used,
            "rpd_limit": limits["rpd"],
            "rpd_remaining": limits["rpd"] - rpd_used,
        }


rate_limiter = None


def get_rate_limiter():
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = RateLimiter("rate_limits.txt")
    return rate_limiter


# ============================================================================
# PART 3: MAIN PROMPT FUNCTION (THE REQUIRED FUNCTION)
# ============================================================================


def prompt_model(model: str, prompt: str) -> str:
    """
    Prompt a model and return the response with automatic rate limit tracking.

    Args:
        model: Model name (e.g., 'llama3.2:1b', 'gemini-2.5-flash', etc.)
        prompt: The prompt text to send to the model

    Returns:
        The response text from the model or an error message
    """
    try:
        if model in GEMINI_MODELS:
            limiter = get_rate_limiter()
            estimated_tokens = len(prompt.split()) * 1.3

            can_proceed, message = limiter.can_make_request(model, estimated_tokens)

            if not can_proceed:
                return f"[Rate Limit] {model}: {message}"

            response = _prompt_gemini(model, prompt)
            tokens_used = len(response.split()) * 1.3 + len(prompt.split()) * 1.3
            limiter.record_request(model, int(tokens_used))

            return response
        else:
            return _prompt_ollama(model, prompt)

    except Exception as e:
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
            "num_predict": 1000,
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "No response generated")
    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to Ollama. Make sure Ollama is running (ollama serve)"
    except requests.exceptions.Timeout:
        return "Error: Request timed out after 240 seconds"
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"
    except json.JSONDecodeError:
        return "Error: Invalid response from Ollama"


def _prompt_gemini(model: str, prompt: str) -> str:
    """Prompt a Google Gemini model via the official SDK."""
    if not GOOGLE_API_KEY or not genai_client:
        return "Error: GOOGLE_API_KEY environment variable not set"

    try:
        response = genai_client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "temperature": 0.7,
                "max_output_tokens": 1000,
            },
        )
        return response.text
    except Exception as e:
        return f"[Gemini Error] {str(e)}"


def prompt_model_with_timing(model: str, prompt: str) -> tuple[str, float]:
    """Wrapper function that returns both response and timing."""
    start_time = time.time()
    response = prompt_model(model, prompt)
    elapsed_time = time.time() - start_time
    return response, elapsed_time


def display_rate_limit_status():
    """Show current rate limit usage for all Gemini models."""
    limiter = get_rate_limiter()

    print("\n" + "=" * 80)
    print("📊 CURRENT RATE LIMIT USAGE (Auto-tracked in memory)")
    print("=" * 80)
    print("Note: These counters reset automatically after time windows expire")
    print("-" * 80)

    for model in GEMINI_MODELS:
        stats = limiter.get_usage_stats(model)
        if stats:
            print(f"\n🔹 {model}")
            print(
                f"   📈 RPM: {stats['rpm_used']}/{stats['rpm_limit']} ({stats['rpm_remaining']} remaining)"
            )
            print(
                f"   🔤 TPM: {stats['tpm_used']:,}/{stats['tpm_limit']:,} ({stats['tpm_remaining']:,} remaining)"
            )
            print(
                f"   📅 RPD: {stats['rpd_used']}/{stats['rpd_limit']} ({stats['rpd_remaining']} remaining)"
            )


def main():
    """Test function to demonstrate prompt_model usage."""
    print("=" * 80)
    print("Testing LLM Models with prompt_model()")
    print("=" * 80)

    # Check if rate limiter loaded limits
    limiter = get_rate_limiter()
    if limiter.max_limits:
        print("\n✅ Rate limits loaded from rate_limits.txt")
    else:
        print("\n⚠️  No rate limits loaded. Create rate_limits.txt to enable tracking")

    # Test cases
    test_cases = [
        # Uncomment to test Ollama models:
        # ("phi3", "What is Python? Answer in one sentence.", "Ollama - phi3"),
        # ("deepseek-r1:1.5b", "What is machine learning? Answer in one sentence.", "Ollama - DeepSeek R1"),
        # ("llama3.2:1b", "What is AI? Answer in one sentence.", "Ollama - Llama 3.2"),
    ]

    # Add Gemini test cases if API key is available
    if GOOGLE_API_KEY:
        gemini_cases = [
            (
                "gemini-2.5-flash",
                "What is the capital of France? Answer in one sentence.",
                "Gemini 2.5 Flash",
            ),
            (
                "gemini-2.5-flash-lite",
                "Explain quantum computing in one sentence.",
                "Gemini 2.5 Flash Lite",
            ),
            (
                "gemini-3-flash-preview",
                "What is the meaning of life? Answer in one sentence.",
                "Gemini 3 Flash Preview",
            ),
        ]
        test_cases.extend(gemini_cases)
    else:
        print("\n⚠️  GOOGLE_API_KEY not set. Skipping Gemini model tests.")
        print("   To test Gemini models, set your API key:")
        print("   export GOOGLE_API_KEY='your-api-key-here'")

    # Run tests
    results = []
    for model, prompt, description in test_cases:
        print(f"\n{'─' * 80}")
        print(f"📝 Test: {description}")
        print(f"🔧 Model: {model}")
        print(f"💬 Prompt: {prompt}")
        print(f"⏳ Processing... ", end="", flush=True)

        response, elapsed_time = prompt_model_with_timing(model, prompt)

        if elapsed_time < 1:
            time_str = f"{elapsed_time * 1000:.0f} ms"
        else:
            time_str = f"{elapsed_time:.2f} seconds"

        print(f"\r⏳ Processing... ✅ Done in {time_str}")
        print(f"\n📄 Response: {response[:200]}{'...' if len(response) > 200 else ''}")

        is_error = (
            "Error" in response or "timed out" in response or "Rate Limit" in response
        )
        status = "✅ SUCCESS" if not is_error else "❌ FAILED"

        results.append(
            {
                "model": description,
                "time": elapsed_time,
                "time_str": time_str,
                "status": status,
            }
        )

        print(f"📊 Status: {status}")
        print(f"{'─' * 80}")
        time.sleep(1)

    # Display rate limit status after tests
    if GOOGLE_API_KEY and limiter.max_limits:
        display_rate_limit_status()

    # Print summary
    print("\n" + "=" * 80)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 80)
    for result in results:
        print(f"{result['model']:<30} {result['time_str']:<15} {result['status']:<12}")


if __name__ == "__main__":
    main()
