#!/usr/bin/env python3
"""
Skill Gap Analysis Module - Deterministic Gemini Approach
Uses the same successful prompt logic as tag_data.py for consistent extraction.
Ensures deterministic results through temperature=0 and normalization.
"""

import os
import re
import sqlite3
import time
import json
from typing import List, Set, Tuple, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from datetime import datetime, timedelta
from collections import defaultdict

# Load environment variables
load_dotenv()

# ============ Pydantic Models ============

class SkillGapResult(BaseModel):
    """Result model for skill gap analysis."""
    gaps: List[str] = Field(description="List of missing skills (lowercase, sorted)")
    resume_skills: List[str] = Field(default=[], description="Skills found in resume")
    job_skills: List[str] = Field(default=[], description="Skills required by jobs")
    time_taken: float = Field(default=0.0, description="Time taken in seconds")
    method_used: str = Field(default="", description="Method used")

# ============ Gemini Configuration ============

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"  # Using lite version for consistent results

# Gemini Rate Limits
MAX_RPM = 10  # Requests per minute
MAX_TPM = 250000  # Tokens per minute
AVG_TOKENS_PER_REQUEST = 500

def calculate_batch_size():
    """Calculate batch size based on rate limits (same as tag_data.py)."""
    theoretical_batch = MAX_TPM / AVG_TOKENS_PER_REQUEST
    batch_size = max(1, int(theoretical_batch * 0.5))
    return min(batch_size, 10)

BATCH_SIZE = calculate_batch_size()
RETRY_DELAY = 30  # Wait 30 seconds on rate limit errors
MAX_RETRIES = 3

# ============ Gemini Rate Limiter ============

class GeminiRateLimiter:
    """Tracks Gemini API usage across calls."""
    
    def __init__(self, storage_file="gemini_skill_gap_usage.json"):
        self.max_rpm = MAX_RPM
        self.max_tpm = MAX_TPM
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
                with open(self.storage_file, 'r') as f:
                    saved_data = json.load(f)
                for model, data in saved_data.items():
                    self.usage[model]["daily_requests"] = [
                        datetime.fromisoformat(ts) for ts in data.get("daily_requests", [])
                    ]
            except Exception:
                pass
    
    def save_persistent_usage(self):
        """Save usage data to disk."""
        try:
            save_data = {}
            for model, data in self.usage.items():
                save_data[model] = {
                    "daily_requests": [ts.isoformat() for ts in data["daily_requests"]],
                }
            with open(self.storage_file, 'w') as f:
                json.dump(save_data, f, indent=2)
        except Exception:
            pass
    
    def _clean_old_records(self, model):
        """Remove records outside tracking windows."""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)
        self.usage[model]["requests"] = [t for t in self.usage[model]["requests"] if t > minute_ago]
        self.usage[model]["tokens"] = [(t, c) for t, c in self.usage[model]["tokens"] if t > minute_ago]
        self.usage[model]["daily_requests"] = [t for t in self.usage[model]["daily_requests"] if t > day_ago]
    
    def can_make_request(self, model: str, estimated_tokens: int) -> Tuple[bool, str]:
        """Check if request is within rate limits."""
        self._clean_old_records(model)
        
        rpm_used = len(self.usage[model]["requests"])
        if rpm_used >= self.max_rpm:
            return False, f"RPM limit ({self.max_rpm}) exceeded"
        
        tpm_used = sum(c for _, c in self.usage[model]["tokens"])
        if tpm_used + estimated_tokens > self.max_tpm:
            return False, f"TPM limit ({self.max_tpm}) exceeded"
        
        return True, "OK"
    
    def record_request(self, model: str, tokens_used: int):
        """Record a successful request."""
        now = datetime.now()
        self.usage[model]["requests"].append(now)
        self.usage[model]["tokens"].append((now, tokens_used))
        self.usage[model]["daily_requests"].append(now)
        self.save_persistent_usage()
    
    def wait_if_needed(self, estimated_tokens: int):
        """Wait if rate limits would be exceeded."""
        can_proceed, msg = self.can_make_request(GEMINI_MODEL, estimated_tokens)
        if not can_proceed:
            print(f"   ⏸️  Rate limit reached: {msg}")
            print(f"   ⏰ Waiting {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

# ============ Skills to Ignore (Non-Technical) ============

IGNORED_SKILLS = {
    # Soft skills
    "leadership", "management", "communication", "teamwork", "problem solving",
    "critical thinking", "agile", "scrum", "mentoring", "interpersonal",
    "organizational", "presentation", "documentation", "reporting",
    "time management", "collaboration", "adaptability", "analytical",
    "team player", "self-starter", "fast learner", "detail-oriented",
    "problem-solving", "logical thinking", "coding standards",
    # Languages (non-technical)
    "english", "mandarin", "bahasa", "japanese", "korean", "french",
    "german", "spanish", "chinese",
    # Certifications (to ignore)
    "certified", "certification", "certificate", "diploma", "degree",
    "bachelor", "master", "phd", "ccna", "cisco", "comptia",
    # Vague/process terms
    "skills", "technical", "summary", "education", "experience",
    "certifications", "additional", "core", "programme", "description",
    "methodologies", "principles", "strategies", "protocols", "life cycle",
    "best practices", "cooking", "code reviews", "data processing", "labeling",
}

# ============ Skill Normalization (For Deterministic Matching) ============

SKILL_NORMALIZATION = {
    # C/C++ family
    "c": "c", "c++": "c++", "cpp": "c++", "c plus plus": "c++",
    "c#": "csharp", "c sharp": "csharp",
    # Languages
    "javascript": "javascript", "js": "javascript",
    "typescript": "typescript", "ts": "typescript",
    "python": "python", "java": "java", "go": "go", "rust": "rust",
    "php": "php", "ruby": "ruby", "r": "r", "r language": "r",
    # Databases
    "postgresql": "postgresql", "postgres": "postgresql",
    "mysql": "mysql", "mongodb": "mongodb", "redis": "redis",
    # Cloud
    "aws": "aws", "amazon web services": "aws", "azure": "azure",
    "gcp": "gcp", "google cloud": "gcp", "google cloud platform": "gcp",
    # DevOps
    "kubernetes": "kubernetes", "k8s": "kubernetes", "docker": "docker",
    "jenkins": "jenkins", "gitlab": "gitlab", "github actions": "github actions",
    "terraform": "terraform", "ansible": "ansible", "ci/cd": "ci/cd", "cicd": "ci/cd",
    # Monitoring
    "prometheus": "prometheus", "grafana": "grafana",
    # ML/AI
    "pytorch": "pytorch", "tensorflow": "tensorflow",
    "scikit-learn": "scikit-learn", "sklearn": "scikit-learn",
    "keras": "keras", "pandas": "pandas", "numpy": "numpy",
    # Frameworks
    "spring boot": "spring boot", "fastapi": "fastapi", "flask": "flask",
    "django": "django", "react": "react", "angular": "angular",
    "vue": "vue", "node.js": "node.js", "nodejs": "node.js", "express": "express",
    # Big Data
    "spark": "spark", "hadoop": "hadoop", "kafka": "kafka", "rabbitmq": "rabbitmq",
    # Other
    "llm": "llm", "rag": "rag", "etl": "etl", "power bi": "powerbi",
    "powerbi": "powerbi", "tableau": "tableau", "excel": "excel",
    "git": "git", "shell": "shell", "bash": "bash", "powershell": "powershell",
    "linux": "linux", "rest api": "rest api", "api": "api", "testing": "testing",
}

def normalize_skill(skill: str) -> str:
    """Normalize a skill name for deterministic matching."""
    skill = skill.strip().lower()
    skill = re.sub(r"[^\w\s\+\#\.]", "", skill)
    skill = skill.strip()
    skill = re.sub(r"\s+(framework|language|tool|platform)$", "", skill)
    
    if skill in SKILL_NORMALIZATION:
        return SKILL_NORMALIZATION[skill]
    
    skill = re.sub(r"\s+and\s+.*$", "", skill)
    skill = re.sub(r"\s+or\s+.*$", "", skill)
    
    return skill

def is_valid_skill(skill: str) -> bool:
    """Check if a string is a valid technical skill."""
    if not skill:
        return False
    
    single_char_languages = {"c", "r"}
    if skill in single_char_languages:
        return True
    
    if len(skill) < 2:
        return False
    
    invalid_patterns = [
        r"technical", r"skill", r"^\+\+$", r"^c#?$",
        r"\s+and\s+", r"\s+with\s+", r"using\s+",
        r"^note\s", r"description", r"development", r"maintenance",
    ]
    
    for pattern in invalid_patterns:
        if re.search(pattern, skill, re.IGNORECASE):
            return False
    
    if skill in IGNORED_SKILLS:
        return False
    
    if not re.search(r"[a-z0-9]", skill):
        return False
    
    return True

# ============ Gemini API Functions ============

def is_gemini_available() -> bool:
    """Check if Gemini API is configured."""
    return GOOGLE_API_KEY is not None

def call_gemini(prompt: str, rate_limiter: GeminiRateLimiter = None) -> Optional[str]:
    """Call Gemini with deterministic settings (temperature=0)."""
    if not GOOGLE_API_KEY:
        return None
    
    estimated_tokens = len(prompt) // 4
    
    if rate_limiter:
        rate_limiter.wait_if_needed(estimated_tokens)
    
    for attempt in range(MAX_RETRIES):
        try:
            client = genai.Client(api_key=GOOGLE_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "temperature": 0.0,  # Deterministic output
                    "max_output_tokens": 500,
                }
            )
            
            if rate_limiter:
                rate_limiter.record_request(GEMINI_MODEL, estimated_tokens)
            
            return response.text.strip()
        
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate" in error_msg.lower():
                print(f"   Attempt {attempt + 1} rate limited, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY * (attempt + 1))
            elif attempt < MAX_RETRIES - 1:
                print(f"   Attempt {attempt + 1} failed: {error_msg[:50]}, retrying...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"   ❌ Gemini error: {error_msg[:100]}")
                return None
    
    return None

# ============ Resume Extraction (Deterministic Gemini) ============

def extract_skills_from_resume(file_path: str, rate_limiter: GeminiRateLimiter = None) -> Set[str]:
    """Extract technical skills from resume using Gemini (temperature=0 for consistency)."""
    if not os.path.exists(file_path):
        print(f"⚠️  Resume file not found: {file_path}")
        return set()
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"⚠️  Error reading resume: {e}")
        return set()
    
    if len(content) > 4000:
        content = content[:4000]
    
    # Same prompt pattern as tag_data.py, adapted for resume
    prompt = f"""Extract ONLY technical skills, programming languages, frameworks, databases, and tools from this resume.

Rules:
- Return ONLY a comma-separated list
- Include ONLY technical skills (not soft skills like "leadership" or "communication")
- Do NOT include any explanations or additional text
- Keep skills concise and standardized
- For C language, return "c"
- For C++, return "c++"
- For C#, return "csharp"
- For R language, return "r"
- Do NOT include certifications (CCNA, etc.)
- Do NOT include languages (English, Mandarin, etc.)

Examples of GOOD technical skills:
"Python, Java, SQL, Docker, Kubernetes, AWS, React, PostgreSQL, Git, C++"

Examples of BAD skills (DO NOT include):
"leadership, teamwork, problem solving, communication, agile, CCNA, English"

Resume Content:
{content}

Technical skills (comma-separated only):"""
    
    response = call_gemini(prompt, rate_limiter)
    
    skills = set()
    if response and response.upper() != "NONE" and response.upper() != "N/A":
        parts = [s.strip() for s in response.split(",")]
        
        for part in parts:
            clean = part.strip()
            clean = re.sub(r"[,;:]$", "", clean)
            clean = " ".join(clean.split())
            clean = normalize_skill(clean)
            
            if is_valid_skill(clean) and clean not in IGNORED_SKILLS:
                skills.add(clean)
    
    # If Gemini extraction failed, use regex fallback for determinism
    if not skills:
        print("   ⚠️  Gemini extraction failed, falling back to regex...")
        skills = extract_skills_from_resume_regex(content)
    
    return skills

def extract_skills_from_resume_regex(content: str) -> Set[str]:
    """Regex-based fallback extraction (deterministic)."""
    skills = set()
    
    # Find Technical Skills section
    pattern = r"Technical Skills:\s*(.+?)(?=\n\n|\n[A-Z]|\Z)"
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    
    if match:
        tech_content = match.group(1)
        tech_content = tech_content.replace("\n", " ")
        skill_parts = re.split(r",\s*", tech_content)
        
        for part in skill_parts:
            clean = part.strip()
            clean = re.sub(r"[,;:]$", "", clean)
            clean = " ".join(clean.split())
            clean = normalize_skill(clean)
            
            if is_valid_skill(clean):
                skills.add(clean)
    
    # Also check for common tech keywords
    common_tech = {
        "python", "java", "c++", "c", "r", "sql", "mysql", "postgresql",
        "docker", "kubernetes", "git", "aws", "azure", "powershell",
        "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn"
    }
    
    content_lower = content.lower()
    for tech in common_tech:
        if re.search(r"\b" + re.escape(tech) + r"\b", content_lower):
            norm = normalize_skill(tech)
            if is_valid_skill(norm):
                skills.add(norm)
    
    return skills

# ============ Job Skills Extraction ============

def get_job_skills_from_db(db_url: str) -> Tuple[Set[str], int]:
    """Extract unique skills from the tech_stack column."""
    try:
        conn = sqlite3.connect(db_url)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    except Exception as e:
        print(f"⚠️  Cannot connect to database: {e}")
        return set(), 0
    
    all_skills = set()
    total_jobs = 0
    
    try:
        cursor.execute("SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != '' AND tech_stack != 'N/A'")
        rows = cursor.fetchall()
        total_jobs = len(rows)
        
        for row in rows:
            tech_stack = row["tech_stack"]
            if tech_stack:
                skills = [s.strip() for s in tech_stack.split(",")]
                for skill in skills:
                    if not skill:
                        continue
                    
                    skill = re.sub(r"\([^)]*\)", "", skill)
                    skill = skill.split("(")[0].strip()
                    skill = skill.split("-")[0].strip()
                    
                    normalized = normalize_skill(skill)
                    if is_valid_skill(normalized) and normalized:
                        all_skills.add(normalized)
    except Exception as e:
        print(f"⚠️  Error querying database: {e}")
    finally:
        conn.close()
    
    return all_skills, total_jobs

# ============ Main Function ============

def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    """
    Find skill gaps between resume and job requirements.
    Deterministic - uses temperature=0 Gemini calls with regex fallback.
    """
    start_time = time.time()
    method_used = "gemini"
    
    # Initialize rate limiter
    rate_limiter = GeminiRateLimiter()
    
    # Check Gemini availability
    if not is_gemini_available():
        print("⚠️  GOOGLE_API_KEY not set, using regex mode")
        method_used = "regex"
    
    try:
        print("📄 Parsing resume...")
        resume_skills = extract_skills_from_resume(input_file_path, rate_limiter if method_used == "gemini" else None)
        print(f"   Found {len(resume_skills)} skills: {', '.join(sorted(resume_skills))}")
        
        print("📊 Analyzing job database...")
        job_skills, total_jobs = get_job_skills_from_db(db_url)
        print(f"   Found {len(job_skills)} unique skills across {total_jobs} jobs")
        
        # Calculate gaps (skills in jobs but not in resume)
        gaps = job_skills - resume_skills
        gaps_list = sorted(gaps)
        
        elapsed_time = time.time() - start_time
        
        print(f"\n{'=' * 60}")
        print(f"SKILL GAP ANALYSIS RESULTS")
        print(f"{'=' * 60}")
        print(f"⏱️  Time taken: {elapsed_time:.2f} seconds")
        print(f"🔧 Method: {method_used}")
        print(f"\n📋 Resume skills ({len(resume_skills)}):")
        if resume_skills:
            print(f"   {', '.join(sorted(resume_skills))}")
        print(f"\n📋 Job skills ({len(job_skills)}):")
        if job_skills:
            print(f"   {', '.join(sorted(job_skills))}")
        print(f"\n🔴 SKILL GAPS ({len(gaps_list)}):")
        if gaps_list:
            print(f"   {', '.join(gaps_list)}")
        else:
            print("   ✅ No gaps found!")
        
        return SkillGapResult(
            gaps=gaps_list,
            resume_skills=sorted(resume_skills),
            job_skills=sorted(job_skills),
            time_taken=elapsed_time,
            method_used=method_used,
        )
    
    except Exception as e:
        print(f"❌ Error in find_skill_gaps: {e}")
        return SkillGapResult(gaps=[], time_taken=time.time() - start_time)

def main():
    """Main entry point."""
    print("=" * 60)
    print("🔍 SKILL GAP FINDER (Gemini)")
    print("=" * 60)
    
    # Check Gemini availability
    if not is_gemini_available():
        print("\n⚠️  GOOGLE_API_KEY not set!")
        print("   Please set your API key:")
        print("   export GOOGLE_API_KEY='your-key-here'")
        print("\n   Falling back to regex mode...")
    
    # Find files
    project_root = Path(__file__).parent
    data_dir = project_root / "data"
    
    resume_path = data_dir / "resume.txt"
    db_path = data_dir / "jobs_d3_eval.db"
    
    if not resume_path.exists():
        # Try other common names
        alternatives = ["resume_d3_eval.txt", "resume.txt"]
        for alt in alternatives:
            test_path = data_dir / alt
            if test_path.exists():
                resume_path = test_path
                break
    
    if not resume_path.exists():
        print(f"\n❌ Resume not found in {data_dir}")
        print(f"   Expected: resume.txt or resume_d3_eval.txt")
        return
    
    if not db_path.exists():
        print(f"\n❌ Database not found: {db_path}")
        print(f"   Please ensure jobs_d3_eval.db is in the data/ directory")
        return
    
    print(f"\n✅ Resume: {resume_path}")
    print(f"✅ Database: {db_path}")
    print(f"⚙️  Batch size: {BATCH_SIZE} jobs/batch (calculated from rate limits: {MAX_TPM} TPM / {AVG_TOKENS_PER_REQUEST} tokens)")
    print(f"🔄 Retry delay: {RETRY_DELAY}s, Max retries: {MAX_RETRIES}")
    print(f"🎯 Temperature: 0.0 (deterministic)")
    print("\n" + "-" * 60)
    
    result = find_skill_gaps(str(resume_path), str(db_path))
    
    print(f"\n{'=' * 60}")
    print("FINAL RESULT (SkillGapResult)")
    print(f"{'=' * 60}")
    print(f"gaps={result.gaps}")

if __name__ == "__main__":
    main()