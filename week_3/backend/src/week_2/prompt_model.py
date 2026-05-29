#!/usr/bin/env python3
"""
Module for prompting LLM models (Google Gemini)
with automatic rate limit tracking.
"""

import os
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

# Define which models are Gemini
GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash-preview",
}

# ============================================================================
# PART 2: RATE LIMITER CLASS
# ============================================================================


class RateLimiter:
    """Track and enforce rate limits for Gemini API."""

    def __init__(
        self, rate_limits_file="rate_limits.txt", storage_file="rate_usage.json"
    ):
        self.max_limits = {}
        self.usage = defaultdict(
            lambda: {
                "requests": [],
                "tokens": [],
                "daily_requests": [],
            }
        )
        self.storage_file = storage_file
        self.load_max_limits(rate_limits_file)
        self.load_persistent_usage()

    def load_max_limits(self, filename):
        """Read maximum rate limits from rate_limits.txt."""
        try:
            with open(filename, "r") as f:
                for line in f:
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
        except FileNotFoundError:
            pass  # Rate limiting disabled
        except Exception:
            pass

    def load_persistent_usage(self):
        """Load previously saved usage data from disk."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    saved_data = json.load(f)
                for model, data in saved_data.items():
                    if "daily_requests" in data:
                        self.usage[model]["daily_requests"] = [
                            datetime.fromisoformat(ts)
                            for ts in data.get("daily_requests", [])
                        ]
            except Exception:
                pass

    def save_persistent_usage(self):
        """Save current usage data to disk."""
        try:
            save_data = {}
            for model, data in self.usage.items():
                save_data[model] = {
                    "daily_requests": [ts.isoformat() for ts in data["daily_requests"]],
                }
            with open(self.storage_file, "w") as f:
                json.dump(save_data, f, indent=2)
        except Exception:
            pass

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
        """Remove usage records outside tracking windows."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)

        self.usage[model]["requests"] = [
            t for t in self.usage[model]["requests"] if t > minute_ago
        ]
        self.usage[model]["tokens"] = [
            (t, c) for t, c in self.usage[model]["tokens"] if t > minute_ago
        ]
        self.usage[model]["daily_requests"] = [
            t for t in self.usage[model]["daily_requests"] if t > day_ago
        ]

    def can_make_request(self, model, estimated_tokens=100):
        """Check if a request can be made without exceeding rate limits."""
        if model not in self.max_limits:
            return True, "OK"

        self._clean_old_records(model)
        limits = self.max_limits[model]

        rpm_used = len(self.usage[model]["requests"])
        if rpm_used >= limits["rpm"]:
            return False, "RPM limit exceeded"

        tpm_used = sum(c for _, c in self.usage[model]["tokens"])
        if tpm_used + estimated_tokens > limits["tpm"]:
            return False, "TPM limit exceeded"

        rpd_used = len(self.usage[model]["daily_requests"])
        if rpd_used >= limits["rpd"]:
            return False, "RPD limit exceeded"

        return True, "OK"

    def record_request(self, model, tokens_used=0):
        """Record a successful request."""
        now = datetime.now()
        self.usage[model]["requests"].append(now)
        self.usage[model]["daily_requests"].append(now)
        if tokens_used > 0:
            self.usage[model]["tokens"].append((now, tokens_used))
        self.save_persistent_usage()


rate_limiter = None


def get_rate_limiter():
    """Get or create the global rate limiter instance."""
    global rate_limiter
    if rate_limiter is None:
        rate_limiter = RateLimiter("rate_limits.txt")
    return rate_limiter


# ============================================================================
# PART 3: MAIN PROMPT FUNCTION
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

            can_proceed, _ = limiter.can_make_request(model, estimated_tokens)
            if not can_proceed:
                return f"[Rate Limit] {model} is currently rate limited. Please try again later."

            response = _prompt_gemini(model, prompt)
            tokens_used = len(response.split()) * 1.3 + len(prompt.split()) * 1.3
            limiter.record_request(model, int(tokens_used))

            return response
        else:
            return "Error: Model not supported"

    except Exception as e:
        return f"Error: {str(e)}"


def _prompt_gemini(model: str, prompt: str) -> str:
    """Prompt a Google Gemini model via the official SDK."""
    if not GOOGLE_API_KEY or not genai_client:
        return "Error: GOOGLE_API_KEY environment variable not set"

    try:
        response = genai_client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": 0.7, "max_output_tokens": 8000},
        )
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"
