#!/usr/bin/env python3
"""
Skill Gap Analysis Module - Clean Version
"""

import os
import re
import sqlite3
import time
from typing import List, Set, Tuple
from pathlib import Path
from pydantic import BaseModel, Field
from collections import Counter

# ============ Pydantic Models ============

class SkillGapResult(BaseModel):
    """Result model for skill gap analysis."""
    gaps: List[str] = Field(description="List of missing skills (lowercase, sorted)")
    resume_skills: List[str] = Field(default=[], description="Skills found in resume")
    job_skills: List[str] = Field(default=[], description="Skills required by jobs")
    time_taken: float = Field(default=0.0, description="Time taken in seconds")


# ============ Configuration ============

# Skills to ignore
IGNORED_SKILLS = {
    "leadership", "management", "communication", "teamwork", "problem solving",
    "critical thinking", "agile", "scrum", "mentoring", "cooking", "english",
    "mandarin", "bahasa", "japanese", "korean", "french", "german", "spanish",
    "interpersonal", "organizational", "presentation", "documentation", "reporting",
    "time management", "problem solving abilities", "communication skills",
    "leadership potential", "collaboration", "adaptability",
    "skills", "technical", "summary", "education", "experience", "certifications",
    "additional", "languages", "core", "programme", "note", "posting",
    "description", "explicitly", "mention", "programming", "languages",
    "methodologies", "principles", "strategies", "protocols", "life cycle",
}

# Skill normalization
SKILL_NORMALIZATION = {
    "c/c++": "c++",
    "c plus plus": "c++",
    "cpp": "c++",
    "c#": "csharp",
    "javascript": "js",
    "typescript": "ts",
    "postgresql": "postgres",
    "kubernetes": "k8s",
    "powershell": "powershell",
    "azure devops": "azure",
    "google cloud": "gcp",
    "amazon web services": "aws",
    "spring frameworkspring boot": "spring boot",
    "fastapiflask": "fastapi",
    "pytorch or tensorflow": "pytorch",
    "llm  rag in production": "llm",
    "git branching and prs": "git",
    "cloud deployment on aws": "aws",
    "monitoring with prometheus + grafana": "prometheus",
    "payment processing automation workflow": "",
    "opportunity identification for value addition": "",
    "selfadvancement techniques": "",
}


def normalize_skill(skill: str) -> str:
    """Normalize a skill name."""
    skill = skill.strip().lower()
    skill = re.sub(r'[^\w\s\+\#]', '', skill)
    skill = skill.strip()
    skill = re.sub(r'\s+(framework|language|tool|platform)$', '', skill)
    
    # Apply mapping
    if skill in SKILL_NORMALIZATION:
        return SKILL_NORMALIZATION[skill]
    
    # Remove common suffixes
    skill = re.sub(r'\s+and\s+.*$', '', skill)
    skill = re.sub(r'\s+or\s+.*$', '', skill)
    
    return skill


def is_valid_skill(skill: str) -> bool:
    """Check if a string is a valid technical skill."""
    if not skill or len(skill) < 2 or len(skill) > 25:
        return False
    
    # Reject obvious non-skills
    invalid_patterns = [
        r'technical', r'skill', r'^c$', r'^c\+$', r'^c#?$',
        r'\s+and\s+', r'\s+with\s+', r'using\s+',
        r'^note\s', r'posting\s', r'description',
        r'development', r'maintenance', r'testing$', r'analysis',
    ]
    
    for pattern in invalid_patterns:
        if re.search(pattern, skill, re.IGNORECASE):
            return False
    
    if skill in IGNORED_SKILLS:
        return False
    
    if not re.search(r'[a-z]', skill):
        return False
    
    if len(skill) == 1:
        return False
    
    return True


# ============ Resume Parsing ============

def extract_skills_from_resume(file_path: str) -> Set[str]:
    """Extract technical skills from a resume text file."""
    if not os.path.exists(file_path):
        return set()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    skills = set()
    
    # Find Technical Skills section
    pattern = r'Technical Skills:\s*(.+?)(?=\n\n|\n[A-Z]|\Z)'
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    
    if match:
        tech_content = match.group(1)
        # Replace newlines with spaces
        tech_content = tech_content.replace('\n', ' ')
        
        # Split by comma
        skill_parts = re.split(r',\s*', tech_content)
        
        for part in skill_parts:
            # Clean each part
            clean = part.strip()
            clean = re.sub(r'[,;:]$', '', clean)
            clean = ' '.join(clean.split())
            clean = normalize_skill(clean)
            
            if is_valid_skill(clean) and clean not in IGNORED_SKILLS:
                skills.add(clean)
    
    # Also check for common tech keywords
    common_tech = {
        'python', 'java', 'javascript', 'c++', 'csharp', 'go', 'rust', 'sql',
        'mysql', 'postgresql', 'mongodb', 'redis', 'aws', 'azure', 'gcp',
        'docker', 'kubernetes', 'git', 'linux', 'powershell', 'excel', 
        'tableau', 'powerbi', 'pandas', 'numpy', 'tensorflow', 'pytorch'
    }
    
    for tech in common_tech:
        if re.search(r'\b' + tech + r'\b', content, re.IGNORECASE):
            skills.add(tech)
    
    return skills


# ============ Database Query ============

def get_job_skills_from_db(db_url: str) -> Tuple[Set[str], Counter]:
    """Extract unique skills from the tech_stack column."""
    conn = sqlite3.connect(db_url)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    all_skills = set()
    skill_counter = Counter()
    
    try:
        cursor.execute("SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != ''")
        rows = cursor.fetchall()
        
        for row in rows:
            tech_stack = row['tech_stack']
            if tech_stack:
                skills = [s.strip() for s in tech_stack.split(',')]
                for skill in skills:
                    # Clean the skill
                    skill = re.sub(r'\([^)]*\)', '', skill)  # Remove parentheses content
                    skill = skill.split('(')[0].strip()  # Take only the part before '('
                    skill = skill.split('-')[0].strip()  # Take only before dash
                    
                    normalized = normalize_skill(skill)
                    if is_valid_skill(normalized) and normalized:
                        all_skills.add(normalized)
                        skill_counter[normalized] += 1
    finally:
        conn.close()
    
    return all_skills, skill_counter


# ============ Main Function ============

def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    """Find skill gaps between resume and job requirements."""
    start_time = time.time()
    
    try:
        print("📄 Parsing resume...")
        resume_skills = extract_skills_from_resume(input_file_path)
        print(f"   Found {len(resume_skills)} skills: {', '.join(sorted(resume_skills))}")
        
        print("📊 Analyzing job database...")
        job_skills, _ = get_job_skills_from_db(db_url)
        print(f"   Found {len(job_skills)} unique skills across all jobs")
        
        gaps = job_skills - resume_skills
        gaps_list = sorted(gaps)
        
        elapsed_time = time.time() - start_time
        
        print(f"\n{'='*60}")
        print(f"SKILL GAP ANALYSIS RESULTS")
        print(f"{'='*60}")
        print(f"⏱️  Time taken: {elapsed_time:.2f} seconds")
        print(f"\n📋 Resume skills ({len(resume_skills)}):")
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
            time_taken=elapsed_time
        )
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return SkillGapResult(gaps=[], time_taken=time.time() - start_time)


def main():
    """Main entry point."""
    print("=" * 60)
    print("🔍 SKILL GAP FINDER")
    print("=" * 60)
    
    project_root = Path(__file__).parent
    resume_path = project_root / "data" / "resume.txt"
    db_path = project_root / "data" / "jobs_d1.db"
    
    if not resume_path.exists():
        print(f"\n❌ Resume not found: {resume_path}")
        return
    
    if not db_path.exists():
        print(f"\n❌ Database not found: {db_path}")
        return
    
    print(f"\n✅ Resume: {resume_path}")
    print(f"✅ Database: {db_path}")
    print("\n" + "-" * 60)
    
    find_skill_gaps(str(resume_path), str(db_path))


if __name__ == "__main__":
    main()