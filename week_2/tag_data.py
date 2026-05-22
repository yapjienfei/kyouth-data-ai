#!/usr/bin/env python3
"""
Data Tagging Module for Job Descriptions
Supports both Ollama (local) and Gemini (cloud) models
"""

import sqlite3
import time
import requests
import subprocess
from typing import List, Optional
from pathlib import Path
import re
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION - ADJUST BASED ON YOUR SYSTEM
# ============================================================================

# Rate limits for Ollama (adjust based on your system's capabilities)
MAX_TOKENS_PER_MINUTE = 10000  # Conservative estimate for local models
MAX_REQUESTS_PER_MINUTE = 10

# Gemini Configuration
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# Model selection - change this to switch between Ollama and Gemini
USE_GEMINI = False  # Set to True for Gemini, False for Ollama
GEMINI_MODEL = "gemini-3-flash-preview"  # or "gemini-2.5-flash", "gemini-2.5-flash-lite"
OLLAMA_MODEL = "phi3:latest"  # Fallback for Ollama

# ============================================================================
# RATE LIMITER FOR OLLAMA
# ============================================================================

class RateLimiter:
    """Simple rate limiter for Ollama requests."""
    
    def __init__(self, max_tokens_per_minute=MAX_TOKENS_PER_MINUTE, 
                 max_requests_per_minute=MAX_REQUESTS_PER_MINUTE):
        self.max_tokens_per_minute = max_tokens_per_minute
        self.max_requests_per_minute = max_requests_per_minute
        self.tokens_used_this_minute = 0
        self.requests_this_minute = 0
        self.minute_start = time.time()
    
    def wait_if_needed(self, estimated_tokens):
        """Wait if rate limits would be exceeded."""
        now = time.time()
        
        if now - self.minute_start >= 60:
            self.tokens_used_this_minute = 0
            self.requests_this_minute = 0
            self.minute_start = now
        
        if self.tokens_used_this_minute + estimated_tokens > self.max_tokens_per_minute:
            wait_time = 60 - (now - self.minute_start)
            if wait_time > 0:
                time.sleep(wait_time)
                self.tokens_used_this_minute = 0
                self.requests_this_minute = 0
                self.minute_start = time.time()
        
        if self.requests_this_minute >= self.max_requests_per_minute:
            wait_time = 60 - (now - self.minute_start)
            if wait_time > 0:
                time.sleep(wait_time)
                self.tokens_used_this_minute = 0
                self.requests_this_minute = 0
                self.minute_start = time.time()
    
    def record_usage(self, tokens_used):
        """Record actual usage."""
        self.tokens_used_this_minute += tokens_used
        self.requests_this_minute += 1


def calculate_batch_size(avg_tokens_per_job=500, max_tokens_per_minute=MAX_TOKENS_PER_MINUTE):
    """Calculate optimal batch size based on rate limits."""
    theoretical_batch = max_tokens_per_minute / avg_tokens_per_job
    batch_size = max(1, int(theoretical_batch * 0.5))
    return min(batch_size, 10)


# ============================================================================
# DATABASE VALIDATION
# ============================================================================

def validate_database(db_url: str) -> tuple[bool, str]:
    """Validate database connection, table existence, and schema."""
    try:
        conn = sqlite3.connect(db_url)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='jobs'
        """)
        if not cursor.fetchone():
            conn.close()
            return False, "Table 'jobs' does not exist in database"
        
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [col[1] for col in cursor.fetchall()]
        
        required_columns = ['source_id', 'job_title', 'description', 'tech_stack']
        missing_columns = [col for col in required_columns if col not in columns]
        
        if missing_columns:
            conn.close()
            return False, f"Missing columns: {', '.join(missing_columns)}"
        
        conn.close()
        return True, "Database validation passed"
        
    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


# ============================================================================
# OLLAMA CHECKS
# ============================================================================

def is_ollama_running() -> bool:
    """Check if Ollama service is running."""
    try:
        response = requests.get("http://localhost:11434", timeout=3)
        return response.status_code == 200
    except:
        return False


def is_model_available(model: str) -> bool:
    """Check if the specified model is available in Ollama."""
    try:
        result = subprocess.run(
            ["ollama", "list"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        return model in result.stdout
    except:
        return False


def get_token_count(text: str) -> int:
    """Rough estimate of token count (4 chars ≈ 1 token)."""
    return len(text) // 4


def has_valid_description(description: str, job_id: int) -> bool:
    """Check if the description has meaningful content for extraction."""
    if not description:
        print(f"      ⏭️  Job {job_id}: Empty description - skipping")
        return False
    
    if len(description.strip()) < 100:
        print(f"      ⏭️  Job {job_id}: Description too short ({len(description)} chars) - skipping")
        return False
    
    description_lower = description.lower().strip()
    placeholder_patterns = [
        r'^key responsibilities:?\s*qualifications:?\s*$',
        r'^job description\s*$',
        r'^to be announced\s*$',
        r'^tbd\s*$',
        r'^coming soon\s*$',
    ]
    
    description_clean = ' '.join(description_lower.split())
    for pattern in placeholder_patterns:
        if re.match(pattern, description_clean):
            print(f"      ⏭️  Job {job_id}: Placeholder description - skipping")
            return False
    
    tech_keywords = [
        'python', 'java', 'sql', 'javascript', 'developer', 'engineering',
        'software', 'programming', 'framework', 'database', 'api', 'cloud',
        'aws', 'docker', 'kubernetes', 'react', 'node', 'git'
    ]
    
    has_tech_content = any(keyword in description_lower for keyword in tech_keywords)
    
    if not has_tech_content:
        print(f"      ⏭️  Job {job_id}: No technical keywords found - skipping")
        return False
    
    return True


# ============================================================================
# GEMINI API FUNCTIONS
# ============================================================================

def is_gemini_available() -> bool:
    """Check if Gemini API is available."""
    return GOOGLE_API_KEY is not None


def extract_with_gemini(title: str, description: str, job_id: int) -> Optional[str]:
    """Extract technical skills using Gemini."""
    
    prompt = f"""Extract ALL technical skills from this job posting.

Include these categories:
- Programming Languages (Python, Java, Go, C++, etc.)
- Frameworks (Spring Boot, FastAPI, React, etc.)
- Databases (PostgreSQL, MongoDB, Redis, etc.)
- Cloud Platforms (AWS, Azure, GCP, Alibaba Cloud)
- DevOps Tools (Docker, Kubernetes, Jenkins, Git, CI/CD)
- Monitoring Tools (Prometheus, Grafana)
- ML/AI Tools (PyTorch, TensorFlow, scikit-learn)
- Message Queues (Kafka, RabbitMQ)
- Caching (Redis)

Exclude (DO NOT include):
- Soft skills (leadership, communication, teamwork, problem solving)
- Languages (Mandarin, Chinese, English)
- Vague terms (logical thinking, coding standards)

Return ONLY a comma-separated list of technical skills. No explanations.

Job Title: {title}

Job Description:
{description[:4000]}

Technical skills (comma-separated only):"""
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 500,
            }
        )
        
        tags = response.text.strip()
        
        # Clean up
        tags = tags.replace("Technical skills:", "")
        tags = tags.replace("comma-separated", "")
        tags = tags.strip()
        
        if tags and len(tags) > 5 and tags.upper() != "NONE":
            return tags
        return None
        
    except Exception as e:
        print(f"      ⚠️  Gemini error for job {job_id}: {str(e)[:50]}")
        return None


# ============================================================================
# OLLAMA EXTRACTION FUNCTIONS - IMPROVED VERSION
# ============================================================================

def extract_with_ollama(title: str, description: str, job_id: int, model: str) -> Optional[str]:
    """Extract technical skills using Ollama - improved for better extraction."""
    
    # Enhanced prompt for better technical skill extraction
    prompt = f"""Extract ALL technical skills, programming languages, frameworks, databases, and tools from this job posting.

Rules:
- Return ONLY a comma-separated list
- Include ALL technical skills you can find (be comprehensive)
- Include programming languages, frameworks, databases, cloud platforms, DevOps tools, ML/AI tools, message queues, caching
- Do NOT include soft skills (leadership, communication, teamwork, problem solving)
- Do NOT include language skills (Mandarin, Chinese, English)
- Extract as many relevant technical skills as you can find
- If you cannot find any technical skills, return "NONE"

Examples of GOOD comprehensive technical skills:
"Python, Java, SQL, Docker, Kubernetes, AWS, Azure, GCP, React, PostgreSQL, Git, Jenkins, Kafka, Redis, PyTorch, TensorFlow"

Examples of BAD skills (DO NOT include):
"leadership, teamwork, problem solving, communication, agile, mandarin, logical thinking"

Job Title: {title}

Job Description:
{description[:4000]}

Technical skills (comma-separated only, be comprehensive):"""
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,  # Slightly higher for better extraction
            "num_predict": 600,  # Increased for more comprehensive output
            "top_p": 0.95,
        }
    }
    
    try:
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        tags = result.get("response", "").strip()
        
        if tags.upper() == "NONE":
            return None
        
        # Clean up
        tags = tags.replace("Technical skills:", "")
        tags = tags.replace("comma-separated", "")
        tags = tags.replace("only", "")
        tags = tags.replace("be comprehensive", "")
        tags = tags.strip()
        tags = tags.strip('"').strip("'")
        tags = tags.split('\n')[0]
        
        # Don't filter too aggressively here - let post-processing handle it
        return tags if len(tags) > 10 else None
        
    except requests.exceptions.Timeout:
        print(f"      ⏱️  Timeout for job {job_id}")
        return None
    except Exception as e:
        print(f"      ⚠️  Ollama error: {str(e)[:50]}")
        return None


# ============================================================================
# MAIN TAGGING FUNCTION
# ============================================================================

def tag_data(db_url: str, model: str = None):
    """
    Main function to tag job descriptions with technical stack information.
    
    Args:
        db_url: Path to the SQLite database file
        model: Deprecated - now uses USE_GEMINI flag
    """
    
    total_tokens_used = 0
    start_time = time.time()
    
    # Determine which backend to use
    use_gemini = USE_GEMINI and is_gemini_available()
    
    if use_gemini:
        print(f"\n🤖 Using Gemini model: {GEMINI_MODEL}")
        if not is_gemini_available():
            print("Error: GOOGLE_API_KEY not set. Falling back to Ollama.")
            use_gemini = False
    
    if not use_gemini:
        # Check Ollama
        if not is_ollama_running():
            print("Error: Ollama is not running. Start with: ollama serve")
            print("Total tokens used: 0, took 0ms")
            return
        
        if not is_model_available(OLLAMA_MODEL):
            print(f"Error: Model '{OLLAMA_MODEL}' not found. Pull with: ollama pull {OLLAMA_MODEL}")
            print("Total tokens used: 0, took 0ms")
            return
        print(f"\n🖥️  Using Ollama model: {OLLAMA_MODEL}")
    
    # Validate database
    is_valid, error_msg = validate_database(db_url)
    if not is_valid:
        print(f"Error: {error_msg}")
        print("Total tokens used: 0, took 0ms")
        return
    
    # Database connection
    try:
        conn = sqlite3.connect(db_url)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error: Cannot connect to database - {str(e)}")
        print("Total tokens used: 0, took 0ms")
        return
    
    try:
        cursor.execute("SELECT COUNT(*) as count FROM jobs")
        total_all_jobs = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT source_id, job_title, description 
            FROM jobs 
            WHERE tech_stack IS NULL OR TRIM(tech_stack) = ''
        """)
        
        jobs = cursor.fetchall()
        jobs_to_tag = len(jobs)
        already_tagged = total_all_jobs - jobs_to_tag
        
        print(f"\n📊 Database Statistics:")
        print(f"   Total jobs in database: {total_all_jobs}")
        print(f"   Already tagged: {already_tagged}")
        print(f"   Jobs to tag: {jobs_to_tag}")
        
        if jobs_to_tag == 0:
            print("\nNo data to tag")
            print(f"Total tokens used: 0, took {0}ms")
            return
        
        BATCH_SIZE = calculate_batch_size()
        print(f"\n⚙️  Configuration:")
        print(f"   Batch size: {BATCH_SIZE} jobs/batch")
        print(f"   Token limit: {MAX_TOKENS_PER_MINUTE} tokens/minute")
        
        rate_limiter = RateLimiter() if not use_gemini else None
        
        successful = 0
        failed = 0
        skipped = 0
        batch_num = 0
        
        for batch_start in range(0, jobs_to_tag, BATCH_SIZE):
            batch_num += 1
            batch_end = min(batch_start + BATCH_SIZE, jobs_to_tag)
            batch = jobs[batch_start:batch_end]
            
            print(f"\n[Batch {batch_num}] Processing jobs {batch_start + 1}-{batch_end} of {jobs_to_tag}")
            
            for job in batch:
                if not has_valid_description(job['description'], job['source_id']):
                    skipped += 1
                    failed += 1
                    continue
                
                try:
                    title = job['job_title'] if job['job_title'] else "Unknown Position"
                    description = job['description'] if job['description'] else ""
                    
                    # Extract tags using selected backend
                    if use_gemini:
                        tags = extract_with_gemini(title, description, job['source_id'])
                        tokens_used = get_token_count(description)
                    else:
                        if rate_limiter:
                            estimated_tokens = get_token_count(description) if description else 100
                            rate_limiter.wait_if_needed(estimated_tokens)
                        
                        tags = extract_with_ollama(title, description, job['source_id'], OLLAMA_MODEL)
                        tokens_used = get_token_count(description) if description else 100
                        
                        if rate_limiter:
                            rate_limiter.record_usage(tokens_used)
                    
                    if tags:
                        # Apply filters
                        tags = light_filter(tags)
                        tags = filter_technical_skills(tags)
                        tags = clean_tags(tags)
                        
                        if tags and len(tags) > 5:
                            cursor.execute("""
                                UPDATE jobs 
                                SET tech_stack = ? 
                                WHERE source_id = ?
                            """, (tags, job['source_id']))
                            conn.commit()
                            
                            total_tokens_used += tokens_used
                            print(f"  ✅ Job {job['source_id']}: {tags}")
                            successful += 1
                        else:
                            print(f"  ⚠️  Job {job['source_id']}: No valid tags extracted")
                            failed += 1
                    else:
                        print(f"  ⚠️  Job {job['source_id']}: No tags extracted")
                        failed += 1
                        
                except Exception as e:
                    print(f"  ❌ Job {job['source_id']}: Error - {str(e)[:80]}")
                    failed += 1
            
            time.sleep(0.5)
        
        elapsed_ms = (time.time() - start_time) * 1000
        print(f"\nTotal tokens used: {total_tokens_used}, took {elapsed_ms:.0f}ms")
        print(f"Successfully tagged: {successful}, Failed: {failed}, Skipped: {skipped}")
        
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        print(f"Total tokens used: {total_tokens_used}, took {(time.time() - start_time) * 1000:.0f}ms")
    finally:
        conn.close()


# ============================================================================
# FILTER FUNCTIONS - IMPROVED VERSION
# ============================================================================

def light_filter(tags: str) -> str:
    """Only remove the most obvious non-technical phrases."""
    
    remove_phrases = [
        'agile methodologies',
        'logical thinking', 
        'coding standards',
        'mlops concepts',
        'problem solving',
        'critical thinking',
        'mandarin language',
        'mandarin chinese',
        'ability to speak chinese',
        'collaboration on finance reporting',
        'version control documentation maintenance',
        'script troubleshooting and enhancement',
        'collaboration frameworks',
        'problem analysis',  # Added
        'data gathering',    # Added
        'system troubleshooting',  # Added
        'project life cycle',  # Added
        'requirements elicitation',  # Added
        'test planning',  # Added
        'deployment strategies',  # Added
        'development standards',  # Added
        'script maintenance',  # Added
        'performance enhancement',  # Added
    ]
    
    result = tags
    for phrase in remove_phrases:
        result = re.sub(re.escape(phrase), '', result, flags=re.IGNORECASE)
    
    # Clean up double commas and extra spaces
    result = re.sub(r',\s*,', ',', result)
    result = re.sub(r'\s+', ' ', result)
    result = result.strip(', ')
    
    return result


def filter_technical_skills(tags: str) -> str:
    """Filter out non-technical skills from the extracted tags."""
    
    non_technical = {
        # Soft skills
        'leadership', 'management', 'communication', 'teamwork', 'problem solving',
        'critical thinking', 'agile', 'scrum', 'mentoring', 'interpersonal',
        'organizational', 'presentation', 'documentation', 'reporting',
        'time management', 'collaboration', 'adaptability', 'analytical',
        'team player', 'self-starter', 'fast learner', 'detail-oriented',
        'agile methodologies', 'logical thinking', 'coding standards',
        'mlops concepts', 'problem-solving',
        
        # Language skills
        'mandarin language', 'mandarin chinese', 'ability to speak chinese',
        'mandarin', 'chinese language', 'english',
        
        # Process-related (non-technical)
        'version control documentation maintenance', 'script troubleshooting',
        'collaboration frameworks', 'finance reporting', 'data reconciliation frameworks',
        'problem analysis', 'data gathering', 'system troubleshooting',
        'project life cycle management', 'requirements elicitation',
        'development standards improvement', 'script maintenance',
        'performance enhancement', 'test planning', 'deployment strategies',
        'project life cycle', 'requirements gathering', 'task tracking',
        'deadline management', 'self-advancement'
    }
    
    if not tags:
        return ""
    
    # Split tags
    if ", " in tags:
        tag_list = [t.strip().lower() for t in tags.split(", ")]
    elif "," in tags:
        tag_list = [t.strip().lower() for t in tags.split(",")]
    else:
        tag_list = [tags.strip().lower()]
    
    # Filter out non-technical skills
    filtered = []
    for t in tag_list:
        # Skip if in non_technical set
        if t in non_technical:
            continue
        
        # Skip if contains certain phrases
        skip_phrases = ['for communication', 'project management', 'soft skill', 'life cycle']
        if any(phrase in t for phrase in skip_phrases):
            continue
        
        # Skip very short tags (except 'c' for C language)
        if len(t) < 2 and t != 'c':
            continue
        
        filtered.append(t)
    
    return ", ".join(filtered) if filtered else ""


def clean_tags(tags: str) -> str:
    """Clean and standardize the extracted tags."""
    
    if not tags:
        return ""
    
    # Handle different separators
    if ", " in tags:
        tag_list = [t.strip() for t in tags.split(", ")]
    elif "," in tags:
        tag_list = [t.strip() for t in tags.split(",")]
    else:
        tag_list = [tags.strip()]
    
    cleaned = []
    seen = set()
    
    for tag in tag_list:
        # Remove common prefixes/suffixes
        tag = tag.lower()
        tag = tag.replace(" skills", "").replace(" experience", "")
        tag = tag.strip()
        
        # Remove duplicates while preserving order
        if tag and len(tag) > 1 and tag not in seen:
            seen.add(tag)
            # Capitalize properly for common terms
            if tag in ['sql', 'api', 'etl', 'ai', 'llm', 'git', 'ci/cd']:
                tag = tag.upper()
            elif tag in ['aws', 'gcp', 'azure']:
                tag = tag.upper()
            elif tag in ['kubernetes', 'docker', 'postgresql', 'mongodb', 'redis', 'kafka', 'rabbitmq']:
                tag = tag.capitalize()
            elif tag in ['pytorch', 'tensorflow', 'scikit-learn', 'fastapi', 'flask']:
                # Keep as is but capitalize properly
                tag = tag.title()
            else:
                tag = tag.title()
            cleaned.append(tag)
    
    # Limit to 25 tags per job
    if len(cleaned) > 25:
        cleaned = cleaned[:25]
    
    return ", ".join(cleaned)


def get_available_models() -> List[str]:
    """Get list of available models from Ollama."""
    try:
        result = subprocess.run(
            ["ollama", "list"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        models = []
        for line in result.stdout.split('\n')[1:]:
            if line.strip():
                model_name = line.split()[0]
                models.append(model_name)
        return models
    except:
        return []


def main():
    """Main entry point for the tagging script."""
    
    print("=" * 60)
    print("🔖 JOB DESCRIPTION TAGGING SYSTEM")
    print("=" * 60)
    
    # Show which backend is being used
    if USE_GEMINI and is_gemini_available():
        print(f"\n🤖 Backend: Google Gemini ({GEMINI_MODEL})")
    else:
        print(f"\n🖥️  Backend: Ollama Local ({OLLAMA_MODEL})")
    
    # Find the database
    project_root = Path(__file__).parent
    db_path = project_root / "data" / "jobs_d1.db"
    
    if not db_path.exists():
        print(f"\n❌ Database not found at: {db_path}")
        print("Total tokens used: 0, took 0ms")
        return
    
    print(f"\n✅ Found database: {db_path}")
    
    # Run tagging
    tag_data(str(db_path))


if __name__ == "__main__":
    main()