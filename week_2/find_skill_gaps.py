#!/usr/bin/env python3
"""
Skill Gap Analysis Module - Deterministic LLM Approach
Uses the same successful prompt logic as tag_data.py for consistent extraction.
"""

import os
import re
import sqlite3
import time
import requests
from typing import List, Set, Tuple, Optional
from pathlib import Path
from pydantic import BaseModel, Field
import argparse

# ============ Pydantic Models ============


class SkillGapResult(BaseModel):
    """Result model for skill gap analysis."""

    gaps: List[str] = Field(description="List of missing skills (lowercase, sorted)")
    resume_skills: List[str] = Field(default=[], description="Skills found in resume")
    job_skills: List[str] = Field(default=[], description="Skills required by jobs")
    time_taken: float = Field(default=0.0, description="Time taken in seconds")
    method_used: str = Field(default="", description="Method used")


# ============ Configuration ============

# Ollama Configuration (same as tag_data.py)
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "phi3:latest"

# Rate limits for Ollama (based on 8GB RAM testing)
MAX_TOKENS_PER_MINUTE = 5000
AVG_TOKENS_PER_REQUEST = 500


def calculate_batch_size():
    """Calculate batch size based on rate limits (same as tag_data.py)."""
    theoretical_batch = MAX_TOKENS_PER_MINUTE / AVG_TOKENS_PER_REQUEST
    batch_size = max(1, int(theoretical_batch * 0.5))
    return min(batch_size, 10)


BATCH_SIZE = calculate_batch_size()
RETRY_DELAY = 2
MAX_RETRIES = 3

# Skills to ignore (non-technical)
IGNORED_SKILLS = {
    # Soft skills
    "leadership",
    "management",
    "communication",
    "teamwork",
    "problem solving",
    "critical thinking",
    "agile",
    "scrum",
    "mentoring",
    "interpersonal",
    "organizational",
    "presentation",
    "documentation",
    "reporting",
    "time management",
    "collaboration",
    "adaptability",
    "analytical",
    "team player",
    "self-starter",
    "fast learner",
    "detail-oriented",
    "problem-solving",
    "logical thinking",
    "coding standards",
    # Languages (non-technical)
    "english",
    "mandarin",
    "bahasa",
    "japanese",
    "korean",
    "french",
    "german",
    "spanish",
    "chinese",
    # Certifications (to ignore)
    "certified",
    "certification",
    "certificate",
    "diploma",
    "degree",
    "bachelor",
    "master",
    "phd",
    "ccna",
    "cisco",
    "comptia",
    # Vague/process terms
    "skills",
    "technical",
    "summary",
    "education",
    "experience",
    "certifications",
    "additional",
    "core",
    "programme",
    "description",
    "methodologies",
    "principles",
    "strategies",
    "protocols",
    "life cycle",
    "best practices",
    "cooking",
    "code reviews",
    "data processing",
    "labeling",
    "testing",
}

# Skill normalization (same as tag_data.py)
SKILL_NORMALIZATION = {
    # C/C++ family
    "c": "c",
    "c++": "c++",
    "cpp": "c++",
    "c plus plus": "c++",
    "c#": "csharp",
    "c sharp": "csharp",
    # Languages
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "python": "python",
    "java": "java",
    "go": "go",
    "rust": "rust",
    "php": "php",
    "ruby": "ruby",
    # Databases
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "redis": "redis",
    # Cloud
    "aws": "aws",
    "amazon web services": "aws",
    "azure": "azure",
    "gcp": "gcp",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "alibaba cloud": "alibaba cloud",
    # DevOps
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "docker": "docker",
    "jenkins": "jenkins",
    "gitlab": "gitlab",
    "github actions": "github actions",
    "terraform": "terraform",
    "ansible": "ansible",
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    # Monitoring
    "prometheus": "prometheus",
    "grafana": "grafana",
    # ML/AI
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "keras": "keras",
    "pandas": "pandas",
    "numpy": "numpy",
    # Frameworks
    "spring framework/spring boot": "spring boot",
    "spring framework": "spring boot",
    "spring boot": "spring boot",
    "fastapi/flask": "fastapi",
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "react": "react",
    "angular": "angular",
    "vue": "vue",
    "node.js": "node.js",
    "nodejs": "node.js",
    "express": "express",
    # Big Data
    "apache spark": "spark",
    "spark": "spark",
    "hadoop": "hadoop",
    "kafka": "kafka",
    "rabbitmq": "rabbitmq",
    # Other
    "llm": "llm",
    "rag": "rag",
    "etl": "etl",
    "power bi": "powerbi",
    "powerbi": "powerbi",
    "tableau": "tableau",
    "excel": "excel",
    "git": "git",
    "shell": "shell",
    "bash": "bash",
    "powershell": "powershell",
    "linux": "linux",
    "restful api": "rest api",
    "api": "api",
    "testing": "testing",
    "cicd": "ci/cd",
    "cicd pipelines": "ci/cd",
    "ci/cd pipelines": "ci/cd",
    "linux": "linux",
    "linux development": "linux",
    "linux development environments": "linux",
    # R language (important - single character)
    "r": "r",
    "r language": "r",
    "r programming": "r",
    "r statistical": "r",
    "r analytics": "r",
}


def normalize_skill(skill: str) -> str:
    """Normalize a skill name (same logic as tag_data.py)."""
    skill = skill.strip().lower()
    skill = re.sub(r"[^\w\s\+\#]", "", skill)
    skill = skill.strip()
    skill = re.sub(r"\s+(framework|language|tool|platform)$", "", skill)

    # Apply mapping
    if skill in SKILL_NORMALIZATION:
        return SKILL_NORMALIZATION[skill]

    # Remove common suffixes
    skill = re.sub(r"\s+and\s+.*$", "", skill)
    skill = re.sub(r"\s+or\s+.*$", "", skill)

    return skill


def is_valid_skill(skill: str) -> bool:
    """Check if a string is a valid technical skill."""
    if not skill:
        return False

    # Allow single characters for languages: c, r
    single_char_languages = {"c", "r"}
    if skill in single_char_languages:
        return True

    if len(skill) < 2:
        return False

    # Reject obvious non-skills
    invalid_patterns = [
        r"technical",
        r"skill",
        r"^c$",
        r"^c\+$",
        r"^c#?$",
        r"\s+and\s+",
        r"\s+with\s+",
        r"using\s+",
        r"^note\s",
        r"description",
        r"development",
        r"maintenance",
    ]

    for pattern in invalid_patterns:
        if re.search(pattern, skill, re.IGNORECASE):
            return False

    if skill in IGNORED_SKILLS:
        return False

    if not re.search(r"[a-z]", skill):
        return False

    return True


# ============ Ollama Functions (Same as tag_data.py) ============


def is_ollama_running() -> bool:
    """Check if Ollama service is running."""
    try:
        response = requests.get("http://localhost:11434", timeout=3)
        return response.status_code == 200
    except:
        return False


def call_ollama(prompt: str, temperature: float = 0.0) -> Optional[str]:
    """
    Call Ollama with deterministic settings.
    Temperature=0 ensures consistent output.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 300,
        },
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.Timeout:
            print(f"   Attempt {attempt + 1} timed out...")
            time.sleep(RETRY_DELAY * (attempt + 1))
        except Exception as e:
            print(f"   Attempt {attempt + 1} failed: {str(e)[:50]}")
            time.sleep(RETRY_DELAY)

    return None


# ============ Resume Extraction (Using tag_data.py prompt pattern) ============


def extract_skills_from_resume(file_path: str) -> Set[str]:
    """
    Extract technical skills from a resume text file.
    Uses the same successful prompt pattern as tag_data.py.
    """
    if not os.path.exists(file_path):
        print(f"⚠️  Resume file not found: {file_path}")
        return set()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"⚠️  Error reading resume: {e}")
        return set()

    # Truncate if too long (same as tag_data.py)
    if len(content) > 3000:
        content = content[:3000]

    # Same prompt pattern as tag_data.py, adapted for resume
    prompt = f"""Extract ONLY technical skills, programming languages, frameworks, databases, and tools from this resume.

Rules:
- Return ONLY a comma-separated list
- Include ONLY technical skills (not soft skills like "leadership" or "communication")
- Do NOT include any explanations or additional text
- Keep skills concise and standardized
- For C language, return "c"
- For C++, return "c++"
- Do NOT include certifications (CCNA, etc.)
- Do NOT include languages (English, Mandarin, etc.)

Examples of GOOD technical skills:
"Python, Java, SQL, Docker, Kubernetes, AWS, React, PostgreSQL, Git, C++"

Examples of BAD skills (DO NOT include):
"leadership, teamwork, problem solving, communication, agile, CCNA, English"

Resume Content:
{content}

Technical skills (comma-separated only):"""

    response = call_ollama(prompt, temperature=0.0)

    skills = set()
    if response and response.upper() != "NONE":
        # Parse the comma-separated list (same as tag_data.py)
        parts = [s.strip() for s in response.split(",")]

        for part in parts:
            # Clean each part
            clean = part.strip()
            clean = re.sub(r"[,;:]$", "", clean)
            clean = " ".join(clean.split())
            clean = normalize_skill(clean)

            if is_valid_skill(clean) and clean not in IGNORED_SKILLS:
                skills.add(clean)

    # If LLM extraction failed, try regex fallback
    if not skills:
        print("   ⚠️  LLM extraction failed, falling back to regex...")
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

        # Split by comma
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
        "python",
        "java",
        "c++",
        "c",
        "r",
        "sql",
        "mysql",
        "postgresql",
        "docker",
        "kubernetes",
        "git",
        "aws",
        "azure",
        "powershell",
        "tensorflow",
        "pytorch",
        "pandas",
        "numpy",
        "scikit-learn",
    }

    content_lower = content.lower()
    for tech in common_tech:
        if re.search(r"\b" + re.escape(tech) + r"\b", content_lower):
            norm = normalize_skill(tech)
            if is_valid_skill(norm):
                skills.add(norm)

    return skills


# ============ Job Skills Extraction (Same as tag_data.py logic) ============


def get_job_skills_from_db(db_url: str) -> Tuple[Set[str], int]:
    """Extract unique skills from the tech_stack column (same as tag_data.py)."""
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
        cursor.execute(
            "SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
        rows = cursor.fetchall()
        total_jobs = len(rows)

        for row in rows:
            tech_stack = row["tech_stack"]
            if tech_stack:
                skills = [s.strip() for s in tech_stack.split(",")]
                for skill in skills:
                    if not skill:
                        continue

                    # Clean the skill (same as tag_data.py)
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
    Deterministic - uses temperature=0 LLM calls with regex fallback.
    """
    start_time = time.time()
    method_used = "llm"

    try:
        # Check Ollama
        if not is_ollama_running():
            print("⚠️  Ollama not running, using regex mode")
            method_used = "regex"

        print("📄 Parsing resume...")
        resume_skills = extract_skills_from_resume(input_file_path)
        print(
            f"   Found {len(resume_skills)} skills: {', '.join(sorted(resume_skills))}"
        )

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
    parser = argparse.ArgumentParser(description="Skill Gap Analysis Tool")
    parser.add_argument("--resume", type=str, help="Path to resume text file")
    parser.add_argument("--db", type=str, help="Path to SQLite database")
    args = parser.parse_args()

    print("=" * 60)
    print("🔍 SKILL GAP FINDER")
    print("=" * 60)

    # Determine paths
    project_root = Path(__file__).parent
    data_dir = project_root / "data"

    resume_path = Path(args.resume) if args.resume else data_dir / "resume_d3_eval.txt"
    db_path = Path(args.db) if args.db else data_dir / "jobs_d3_eval.db"

    if not resume_path.exists():
        print(f"\n❌ Resume not found: {resume_path}")
        print(f"   Please place resume txt in the data/ directory")
        return

    if not db_path.exists():
        print(f"\n❌ Database not found: {db_path}")
        print(f"   Please ensure jobs db is in the data/ directory")
        return

    print(f"\n✅ Resume: {resume_path}")
    print(f"✅ Database: {db_path}")
    print(f"⚙️  Batch size: {BATCH_SIZE} jobs/batch (calculated from rate limits)")
    print(f"🔄 Retry delay: {RETRY_DELAY}s, Max retries: {MAX_RETRIES}")
    print("\n" + "-" * 60)

    result = find_skill_gaps(str(resume_path), str(db_path))

    print(f"\n{'=' * 60}")
    print("FINAL RESULT (SkillGapResult)")
    print(f"{'=' * 60}")
    print(f"gaps={result.gaps}")


if __name__ == "__main__":
    main()
