#!/usr/bin/env python3
"""
Data Tagging Module for Job Descriptions
Uses Google Gemini for intelligent tech stack extraction with batch processing
Combines best practices from both Ollama and Gemini implementations
"""

import sqlite3
import time
import json
import os
import re
from typing import List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from datetime import datetime, timedelta
from collections import defaultdict

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

# Gemini Configuration
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"  # Using lite version for better rate limits

# Batch processing settings
BATCH_SIZE = 10  # Process 5 jobs per batch (conservative for rate limits)
RETRY_DELAY_SECONDS = 30  # Wait 30 seconds before retrying failed batches


# Token estimation (1 token ≈ 4 chars for Gemini)
def estimate_tokens(text: str) -> int:
    return len(text) // 4


# ============================================================================
# GEMINI RATE LIMITER (Persistent)
# ============================================================================


class GeminiRateLimiter:
    """Tracks Gemini API usage across multiple batch runs."""

    def __init__(self, storage_file="gemini_usage.json"):
        self.max_rpm = 10  # Gemini-2.5-flash-lite: 10 RPM
        self.max_tpm = 250000  # 250K TPM
        self.max_rpd = 50  # 50 RPD for lite version
        self.storage_file = storage_file
        self.usage = defaultdict(
            lambda: {
                "requests": [],
                "tokens": [],
                "daily_requests": [],
            }
        )
        self.load_persistent_usage()

    def load_persistent_usage(self):
        """Load saved usage data from disk."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    saved_data = json.load(f)
                for model, data in saved_data.items():
                    self.usage[model]["daily_requests"] = [
                        datetime.fromisoformat(ts)
                        for ts in data.get("daily_requests", [])
                    ]
                print(f"✓ Loaded persistent usage from {self.storage_file}")
            except Exception as e:
                print(f"⚠️ Could not load usage data: {e}")

    def save_persistent_usage(self):
        """Save usage data to disk."""
        try:
            save_data = {}
            for model, data in self.usage.items():
                save_data[model] = {
                    "daily_requests": [ts.isoformat() for ts in data["daily_requests"]],
                }
            with open(self.storage_file, "w") as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save usage: {e}")

    def _clean_old_records(self, model):
        """Remove records outside tracking windows."""
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

    def can_make_request(self, model: str, estimated_tokens: int) -> Tuple[bool, str]:
        """Check if request is within rate limits."""
        self._clean_old_records(model)

        rpm_used = len(self.usage[model]["requests"])
        if rpm_used >= self.max_rpm:
            return False, f"RPM limit ({self.max_rpm}) exceeded"

        tpm_used = sum(c for _, c in self.usage[model]["tokens"])
        if tpm_used + estimated_tokens > self.max_tpm:
            return False, f"TPM limit ({self.max_tpm}) exceeded"

        rpd_used = len(self.usage[model]["daily_requests"])
        if rpd_used >= self.max_rpd:
            return False, f"RPD limit ({self.max_rpd}) exceeded for today"

        return True, "OK"

    def record_request(self, model: str, tokens_used: int):
        """Record a successful request."""
        now = datetime.now()
        self.usage[model]["requests"].append(now)
        self.usage[model]["tokens"].append((now, tokens_used))
        self.usage[model]["daily_requests"].append(now)
        self.save_persistent_usage()


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================


def validate_database(db_url: str) -> Tuple[bool, str]:
    """Validate database connection and schema."""
    try:
        conn = sqlite3.connect(db_url)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        if not cursor.fetchone():
            conn.close()
            return False, "Table 'jobs' does not exist"

        cursor.execute("PRAGMA table_info(jobs)")
        columns = [col[1] for col in cursor.fetchall()]

        required = ["source_id", "job_title", "description", "tech_stack"]
        missing = [col for col in required if col not in columns]

        if missing:
            conn.close()
            return False, f"Missing columns: {', '.join(missing)}"

        conn.close()
        return True, "OK"
    except Exception as e:
        return False, str(e)


def get_jobs_to_tag(db_url: str) -> List[dict]:
    """Get all jobs that need tech_stack tagging (NULL or empty, but NOT 'N/A')."""
    conn = sqlite3.connect(db_url)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Only get jobs that are truly empty (not already marked as N/A)
    cursor.execute("""
        SELECT source_id, job_title, description 
        FROM jobs 
        WHERE (tech_stack IS NULL OR TRIM(tech_stack) = '')
    """)

    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs


def update_tech_stack(db_url: str, job_id: int, tech_stack: str):
    """Update a single job's tech_stack."""
    conn = sqlite3.connect(db_url)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE jobs SET tech_stack = ? WHERE source_id = ?", (tech_stack, job_id)
    )
    conn.commit()
    conn.close()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def has_valid_description(description: str, job_id: int) -> bool:
    """Check if the description has meaningful content for extraction."""
    if not description:
        return False

    if len(description.strip()) < 100:
        return False

    description_lower = description.lower().strip()
    placeholder_patterns = [
        r"^key responsibilities:?\s*qualifications:?\s*$",
        r"^job description\s*$",
        r"^to be announced\s*$",
        r"^tbd\s*$",
        r"^coming soon\s*$",
    ]

    description_clean = " ".join(description_lower.split())
    for pattern in placeholder_patterns:
        if re.match(pattern, description_clean):
            return False

    tech_keywords = [
        "python",
        "java",
        "sql",
        "javascript",
        "developer",
        "engineering",
        "software",
        "programming",
        "framework",
        "database",
        "api",
        "cloud",
        "aws",
        "docker",
        "kubernetes",
        "react",
        "node",
        "git",
    ]

    has_tech_content = any(keyword in description_lower for keyword in tech_keywords)
    return has_tech_content


# ============================================================================
# GEMINI EXTRACTION (COMBINED PROMPT FROM OLLAMA)
# ============================================================================


def is_gemini_available() -> bool:
    """Check if Gemini API is configured."""
    return GOOGLE_API_KEY is not None


def extract_tech_stack_with_gemini(
    title: str, description: str, job_id: int
) -> Optional[str]:
    """
    Extract technical stack using Gemini with improved prompt from Ollama testing.
    Returns comma-separated string of technologies, or "N/A" if none found.
    """
    if not GOOGLE_API_KEY:
        return None

    # Enhanced prompt combining best practices from Ollama and Gemini
    prompt = f"""Extract ALL technical skills, programming languages, frameworks, databases, and tools from this job posting.

Rules:
- Return ONLY a comma-separated list
- Include ALL technical skills you can find (be comprehensive)
- Include programming languages, frameworks, databases, cloud platforms, DevOps tools, ML/AI tools, message queues, caching
- Do NOT include soft skills (leadership, communication, teamwork, problem solving)
- Do NOT include language skills (Mandarin, Chinese, English)
- Extract as many relevant technical skills as you can find
- If you cannot find ANY technical skills, return exactly "N/A" (without quotes)

Examples of GOOD comprehensive technical skills:
"Python, Java, SQL, Docker, Kubernetes, AWS, Azure, GCP, React, PostgreSQL, Git, Jenkins, Kafka, Redis, PyTorch, TensorFlow"

Examples of BAD skills (DO NOT include):
"leadership, teamwork, problem solving, communication, agile, mandarin, logical thinking"

Job Title: {title}

Job Description:
{description[:4000]}

Technical skills (comma-separated only, be comprehensive, or "N/A" if none found):"""

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.2,  # Low temperature for consistent extraction
                "max_output_tokens": 600,  # Increased for comprehensive output
            },
        )

        tags = response.text.strip()

        # Clean up common prefixes
        tags = re.sub(
            r"^(Technical skills:|comma-separated only:|be comprehensive:)",
            "",
            tags,
            flags=re.IGNORECASE,
        )
        tags = tags.strip(" \"'")

        # Check if it's explicitly N/A
        if tags.upper() == "N/A":
            return "N/A"

        # Check if we got something reasonable
        if tags and len(tags) > 5 and tags.upper() != "NONE":
            # Clean and format
            cleaned = clean_tech_stack(tags)
            # If after cleaning we have at least 2 tags, return them
            if len(cleaned.split(",")) >= 2 and cleaned != "N/A":
                return cleaned

        # Default: no valid tags found
        return "N/A"

    except Exception as e:
        print(f"      ⚠️  Gemini error for job {job_id}: {str(e)[:100]}")
        return "N/A"  # On error, mark as N/A to avoid retrying


def clean_tech_stack(tags: str) -> str:
    """Clean and standardize tech stack tags."""
    # Handle N/A case
    if tags.upper() == "N/A":
        return "N/A"

    # Split by commas
    if ", " in tags:
        parts = [p.strip() for p in tags.split(", ")]
    elif "," in tags:
        parts = [p.strip() for p in tags.split(",")]
    else:
        parts = [tags.strip()]

    # Remove duplicates while preserving order
    seen = set()
    cleaned = []

    non_technical = {
        "soft skills",
        "communication",
        "teamwork",
        "leadership",
        "problem solving",
        "critical thinking",
        "agile",
        "scrum",
        "mandarin",
        "chinese",
        "english",
        "documentation",
        "n/a",
        "agile methodologies",
        "logical thinking",
        "coding standards",
        "mlops concepts",
        "problem-solving",
        "interpersonal",
        "organizational",
        "presentation",
        "reporting",
        "time management",
        "collaboration",
        "adaptability",
        "analytical",
        "team player",
        "self-starter",
        "fast learner",
        "detail-oriented",
    }

    for part in parts:
        part_lower = part.lower().strip()

        # Skip non-technical
        if part_lower in non_technical:
            continue

        # Skip if contains certain phrases
        skip_phrases = [
            "for communication",
            "project management",
            "soft skill",
            "life cycle",
            "version control documentation",
            "script troubleshooting",
            "collaboration frameworks",
            "finance reporting",
        ]
        if any(phrase in part_lower for phrase in skip_phrases):
            continue

        # Skip very short
        if len(part) < 2:
            continue

        # Remove duplicates
        if part_lower not in seen:
            seen.add(part_lower)
            # Capitalize common terms nicely
            if part_lower in ["sql", "api", "git", "ci/cd", "etl", "ai", "llm"]:
                cleaned.append(part_lower.upper())
            elif part_lower in [
                "kubernetes",
                "docker",
                "postgresql",
                "mongodb",
                "redis",
            ]:
                cleaned.append(part_lower.capitalize())
            elif part_lower in [
                "pytorch",
                "tensorflow",
                "scikit-learn",
                "fastapi",
                "flask",
            ]:
                cleaned.append(part_lower.title())
            else:
                # Capitalize first letter of each word
                cleaned.append(
                    " ".join(word.capitalize() for word in part_lower.split())
                )

    # If no valid tags found, return N/A
    if not cleaned:
        return "N/A"

    # Limit to 20 tags per job
    return ", ".join(cleaned[:20])


# ============================================================================
# MAIN FUNCTION
# ============================================================================


def tag_data(db_url: str):
    """
    Tag job descriptions with tech stack using Gemini batch processing.

    Args:
        db_url: Path to SQLite database file
    """
    start_time = time.time()
    total_tokens_used = 0
    rate_limiter = GeminiRateLimiter()

    print(f"\n🤖 Using Gemini model: {GEMINI_MODEL}")

    # Validate database
    valid, msg = validate_database(db_url)
    if not valid:
        print(f"Error: {msg}")
        print(f"Total tokens used: 0, took {0}ms")
        return

    # Get jobs to tag (only NULL or empty, not already tagged)
    jobs = get_jobs_to_tag(db_url)
    total_jobs = len(jobs)

    if total_jobs == 0:
        print("\n✅ No jobs need tagging. All tech_stack fields are populated.")
        print(f"Total tokens used: 0, took {0}ms")
        return

    print(f"\n📊 Found {total_jobs} jobs to tag")
    print(f"⚙️  Batch size: {BATCH_SIZE} jobs/batch")
    print(f"⏱️  Retry delay: {RETRY_DELAY_SECONDS}s on failure")

    successful = 0
    no_tags = 0  # Track jobs with no technical content
    failed = 0
    skipped = 0
    batch_num = 0

    # Process in batches
    for batch_start in range(0, total_jobs, BATCH_SIZE):
        batch_num += 1
        batch_end = min(batch_start + BATCH_SIZE, total_jobs)
        batch = jobs[batch_start:batch_end]

        print(
            f"\n[Batch {batch_num}] Processing jobs {batch_start + 1}-{batch_end} of {total_jobs}"
        )

        # Process each job in the batch
        for job in batch:
            job_id = job["source_id"]
            title = job["job_title"] or "Unknown Position"
            description = job["description"] or ""

            # Check if description has valid content
            if not has_valid_description(description, job_id):
                print(
                    f"  ⏭️  Job {job_id}: Description too short or no technical content - marking as N/A"
                )
                update_tech_stack(db_url, job_id, "N/A")
                skipped += 1
                no_tags += 1
                continue

            # Estimate tokens for rate limiting
            estimated_tokens = estimate_tokens(description)

            # Check rate limits
            can_proceed, msg = rate_limiter.can_make_request(
                GEMINI_MODEL, estimated_tokens
            )

            if not can_proceed:
                print(f"  ⏸️  Rate limit reached: {msg}")
                print(f"  ⏰ Waiting {RETRY_DELAY_SECONDS}s before continuing...")
                time.sleep(RETRY_DELAY_SECONDS)
                # Retry the check
                can_proceed, msg = rate_limiter.can_make_request(
                    GEMINI_MODEL, estimated_tokens
                )
                if not can_proceed:
                    print(
                        f"  ❌ Still rate limited: {msg}. Skipping remaining jobs in this batch."
                    )
                    failed += len(batch) - (
                        successful + no_tags - (batch_start + (batch.index(job)))
                    )
                    break

            if can_proceed:
                # Extract tech stack
                tech_stack = extract_tech_stack_with_gemini(title, description, job_id)

                if tech_stack and tech_stack != "N/A":
                    # Update database with actual tags
                    update_tech_stack(db_url, job_id, tech_stack)
                    successful += 1
                    total_tokens_used += estimated_tokens
                    rate_limiter.record_request(GEMINI_MODEL, estimated_tokens)
                    # Output format required: "Analyzed Job {id}: {tech_stack}"
                    print(f"Analyzed Job {job_id}: {tech_stack}")
                else:
                    # No technical content found - mark as N/A to skip future runs
                    update_tech_stack(db_url, job_id, "N/A")
                    no_tags += 1
                    total_tokens_used += estimated_tokens
                    rate_limiter.record_request(GEMINI_MODEL, estimated_tokens)
                    print(
                        f"  📝 Job {job_id}: No technical content found - marked as N/A"
                    )

            # Small delay between requests to be gentle
            time.sleep(0.5)

    # Final summary
    elapsed_ms = (time.time() - start_time) * 1000
    print(f"\n{'=' * 60}")
    print(f"📊 SUMMARY")
    print(f"{'=' * 60}")
    print(f"✅ Successfully tagged: {successful}")
    print(f"📝 Marked as N/A (no tech content): {no_tags}")
    print(f"⏭️  Skipped (invalid description): {skipped}")
    print(f"❌ Failed (errors): {failed}")
    print(f"🔢 Total tokens used: {total_tokens_used}")
    print(f"⏱️  Time taken: {elapsed_ms:.0f}ms")
    print(f"{'=' * 60}")


def reset_na_jobs(db_url: str):
    """Utility function to reset jobs marked as N/A so they can be processed again."""
    conn = sqlite3.connect(db_url)
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET tech_stack = NULL WHERE tech_stack = 'N/A'")
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    print(f"Reset {affected} jobs from 'N/A' to NULL")


def main():
    """Main entry point."""
    print("=" * 60)
    print("🔖 JOB TECH STACK TAGGING WITH GEMINI")
    print("=" * 60)

    # Check Gemini availability
    if not is_gemini_available():
        print("\n❌ GOOGLE_API_KEY environment variable not set!")
        print("   Please set your API key:")
        print("   export GOOGLE_API_KEY='your-key-here'")
        return

    # Find database - try common locations
    possible_paths = [
        Path(__file__).parent / "data" / "jobs_d1.db",
        Path(__file__).parent / "jobs_d1.db",
        Path.cwd() / "data" / "jobs_d1.db",
        Path.cwd() / "jobs_d1.db",
    ]

    db_path = None
    for path in possible_paths:
        if path.exists():
            db_path = path
            break

    if not db_path:
        print(f"\n❌ Database not found!")
        print("   Tried locations:")
        for path in possible_paths:
            print(f"     - {path}")
        print("\n   Please ensure jobs_d1.db is in the data/ directory")
        return

    print(f"\n✅ Found database: {db_path}")

    # Ask if user wants to reset N/A jobs
    print("\nOptions:")
    print("  1. Run tagging (process only NULL/empty jobs)")
    print("  2. Reset N/A jobs and run tagging (process all jobs)")
    print("  3. Exit")

    choice = input("\nSelect option (1-3): ").strip()

    if choice == "2":
        reset_na_jobs(str(db_path))
        print("\n🔄 Running tagging on all jobs...")
        tag_data(str(db_path))
    elif choice == "1":
        tag_data(str(db_path))
    else:
        print("Exiting...")


if __name__ == "__main__":
    main()
