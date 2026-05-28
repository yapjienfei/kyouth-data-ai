# Week 2: LLM-Powered Job Description Tagging & Skill Gap Analysis

## Project Overview

This project implements an automated system for processing job descriptions and analyzing skill gaps using local LLMs (Ollama with phi3) or cloud APIs (Google Gemini). The system consists of two main components:

1. **Data Tagging (tag_data.py)** - Extracts technical skills from job descriptions and populates a SQLite database with structured tech stack information.

2. **Skill Gap Analysis (find_skill_gaps.py)** - Compares skills from a resume against aggregated job requirements to identify missing skills needed for career development.

The project balances cloud-powered performance (Gemini) with local control, privacy, and offline experimentation (Ollama), demonstrating practical LLM integration for HR tech applications.

## Setup Instructions

### Prerequisites

- Python: 3.14.5
- RAM: 8 GB minimum (16 GB recommended)
- Storage: 10 GB free space
- Operating System: Linux, macOS, or Windows (with WSL2)
- Tools: uv (fast Python package manager), ollama (local LLM runtime), sqlite3 (database)

### Installation

1. Clone the repository
   git clone <your-repo-url>
   cd week_2

2. Install uv package manager
   curl -LsSf https://astral.sh/uv/install.sh | sh
   or on Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

3. Install dependencies
   uv sync

4. Install and setup Ollama
   Install Ollama (macOS/Linux)
   curl -fsSL https://ollama.com/install.sh | sh
   
   or download from https://ollama.com/download (Windows)
   
    Pull required models
   ollama pull phi3:latest
   ollama pull deepseek-r1:1.5b
   ollama pull llama3.2:1b
   
   Verify installation
   ollama serve  # Start the service
   curl http://localhost:11434  # Should return "Ollama is running"

5. Configure Environment Variables (for Gemini API, optional)
   Create .env file
   echo 'GOOGLE_API_KEY=your-actual-api-key-here' > .env
   
   NEVER commit .env to version control!

6. Prepare Database
   mkdir -p data
   Place your jobs db in the data/ directory
   Place your resume.txt in the data/ directory

## Usage

### Data Tagging (tag_data.py)

This script extracts technical skills from job descriptions and updates the database.

Run the tagging script:
   uv run tag_data.py

Expected output:
   
   🔖 JOB DESCRIPTION TAGGING SYSTEM
   
   
   ✅ Found database: /path/to/data/jobs_d1.db
   🖥️  Using Ollama model: phi3:latest
   
   📊 Database Statistics:
      Total jobs in database: 8
      Already tagged: 0
      Jobs to tag: 8
   
   ⚙️  Configuration:
      Batch size: 5 jobs/batch
      Token limit: 5000 tokens/minute
   
   [Batch 1] Processing jobs 1-5 of 8
     ✅ Job 91397216: SQL, Python, Tableau, PowerBI, Java, Docker, Kubernetes, AWS
     ✅ Job 91347112: Java, Spring Boot, Python, PyTorch, TensorFlow, PostgreSQL, Git
   
   Total tokens used: 3464, took 56312ms
   Successfully tagged: 8, Failed: 0, Skipped: 0

Skill Gap Analysis (find_skill_gaps.py)

This script compares resume skills against job requirements to identify gaps.

Run with default paths (data/resume.txt and data/jobs_d1.db):
   uv run find_skill_gaps.py

Run with custom paths:
   uv run find_skill_gaps.py --resume /path/to/resume.txt --db /path/to/jobs.db

Expected output:
   
   🔍 SKILL GAP FINDER
   
   
   ✅ Resume: data/resume.txt
   ✅ Database: data/jobs_d1.db
   ⚙️  Batch size: 5 jobs/batch
   
   📄 Parsing resume...
      Found 6 skills: azure, c, c++, mysql, powershell, python
   
   📊 Analyzing job database...
      Found 47 unique skills across 8 jobs
   
   
   SKILL GAP ANALYSIS RESULTS
   
   ⏱️  Time taken: 79.98 seconds
   
   📋 Resume skills (6):
      azure, c, c++, mysql, powershell, python
   
   🔴 SKILL GAPS (29):
      alibaba cloud, aws, docker, kubernetes, jenkins, kafka, mongodb, nginx, php, redis
   
   
   FINAL RESULT (SkillGapResult)
   
   gaps=['alibaba cloud', 'aws', 'docker', 'kubernetes', ...]

## API / Function Reference

### tag_data.py

**tag_data(db_url: str, model: str = "phi3")**
- Purpose: Main function to tag job descriptions with technical stack information
- Inputs: 
  - db_url: Path to SQLite database file
  - model: Ollama model to use (default: "phi3")
- Outputs: None (updates database directly, prints progress to stdout)

**extract_with_ollama(title: str, description: str, job_id: int, model: str) -> Optional[str]**
- Purpose: Extract technical skills from a single job using Ollama
- Inputs: Job title, description, job ID, model name
- Outputs: Comma-separated string of technical skills or None

**RateLimiter class**
- Purpose: Enforces token-based rate limiting for Ollama requests
- Methods: wait_if_needed(estimated_tokens), record_usage(tokens_used)

**light_filter(tags: str) -> str**
- Purpose: Removes obvious non-technical phrases from extracted tags
- Inputs: Raw comma-separated tags string
- Outputs: Cleaned tags string

**filter_technical_skills(tags: str) -> str**
- Purpose: Filters out soft skills and non-technical terms
- Inputs: Tags string
- Outputs: Filtered technical skills only

**clean_tags(tags: str) -> str**
- Purpose: Standardizes and capitalizes skill names
- Inputs: Tags string
- Outputs: Cleaned and formatted tags

### find_skill_gaps.py

**find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult**
- Purpose: Find skill gaps between resume and job requirements
- Inputs: 
  - input_file_path: Path to resume text file
  - db_url: Path to SQLite database
- Outputs: SkillGapResult object with gaps, resume_skills, job_skills, time_taken

**extract_skills_from_resume(file_path: str) -> Set[str]**
- Purpose: Extract technical skills from resume using LLM
- Inputs: Path to resume text file
- Outputs: Set of normalized technical skills

**get_job_skills_from_db(db_url: str) -> Tuple[Set[str], int]**
- Purpose: Extract unique skills from job database tech_stack column
- Inputs: Path to SQLite database
- Outputs: Tuple of (set of skills, total jobs processed)

**normalize_skill(skill: str) -> str**
- Purpose: Normalize skill names for consistent matching
- Inputs: Raw skill string
- Outputs: Normalized skill string

**is_valid_skill(skill: str) -> bool**
- Purpose: Validate if a string is a legitimate technical skill
- Inputs: Skill string
- Outputs: Boolean indicating validity

### Pydantic Models

**SkillGapResult**
- Fields:
  - gaps: List[str] - Missing skills (lowercase, sorted)
  - resume_skills: List[str] - Skills found in resume
  - job_skills: List[str] - Skills required by jobs
  - time_taken: float - Processing time in seconds
  - method_used: str - Extraction method (llm or regex)

## Data / Assumptions

### Data Structure

**Database Schema (jobs table)**
- source_id (INTEGER PRIMARY KEY) - Unique job identifier
- job_title (TEXT) - Position title
- description (TEXT) - Full job description
- tech_stack (TEXT) - Comma-separated technical skills (populated by tag_data.py)

**Input Files**
- resume.txt: Plain text file with resume content
  - Expected format: Contains a "Technical Skills:" section with comma-separated skills
  - Example: "Technical Skills: Python, SQL, Java, Docker"

### Assumptions

1. **Technical Skills Format**: Skills in tech_stack are comma-separated (e.g., "Python, Java, SQL")

2. **Resume Structure**: Contains a "Technical Skills:" section or similar identifiable section

3. **Local LLM Availability**: Ollama is running with phi3 model pulled

4. **Token Limits**: 5,000 tokens per minute is safe for 8GB RAM with phi3 model

5. **Skill Normalization**: Similar skills (e.g., "k8s" and "kubernetes") are normalized to standard form

6. **Determinism**: With temperature=0, LLM outputs are consistent for same inputs

7. **Ignored Skills**: Certifications, soft skills, and languages are filtered out

### Data Flow

1. Raw job descriptions → tag_data.py → LLM extraction → tech_stack column
2. tech_stack column + resume.txt → find_skill_gaps.py → SkillGapResult
3. SkillGapResult → Gap analysis → Actionable insights

## Testing

### Test Cases

1. **Data Tagging Tests**
   - Empty description: Script correctly skips jobs with <100 characters
   - Placeholder text: "Key Responsibilities: Qualifications:" - skipped
   - Valid job: Extracts 15-25 technical skills
   - Partial tech_stack: Only processes NULL or empty columns

2. **Skill Gap Tests**
   - Resume with C/C++: Correctly identifies C and C++ (not C#)
   - Resume with Python: Python excluded from gaps
   - Empty resume: Returns all job skills as gaps
   - Corrupted database: Graceful error handling, no crashes

3. **Rate Limiting Tests**
   - 6 requests within 1 minute: 5 succeed, 1 blocked
   - Token tracking: Accurately counts tokens used
   - Batch processing: Processes in configurable batch sizes

4. **Determinism Tests**
   - Run same input twice: Identical output
   - Temperature=0: Consistent LLM responses
   - Regex fallback: Same results when LLM fails

### How to Reproduce Tests

1. Test empty description:
   - Insert job with description = "Key Responsibilities: Qualifications:"
   - Run uv run tag_data.py
   - Expected: Job skipped with "Description too short" message

2. Test determinism:
   - uv run find_skill_gaps.py > output1.txt
   - uv run find_skill_gaps.py > output2.txt
   - diff output1.txt output2.txt  # Should show no differences

3. Test rate limiting:
   - Run test_rate_limit.py (included in project)
   - uv run test_rate_limit.py
   - Expected: First 5 requests succeed, 6th rate limited

4. Test database validation:
   - Run with non-existent database: uv run tag_data.py fake.db
   - Expected: Error message, no crash

### Validation Methods

- **Manual Verification**: Sample outputs checked against source descriptions
- **Cross-validation**: Compare Ollama vs Gemini results for consistency
- **Token counting**: Track tokens to ensure within rate limits
- **Error injection**: Test with malformed inputs to verify error handling

## Limitations

### Performance Limitations

- **Processing Speed**: ~5-10 seconds per job on 8GB RAM with phi3
- **Concurrent Jobs**: Batch size limited to 5-10 due to memory constraints
- **Long Descriptions**: Truncated to 4000 characters to manage token usage
- **Token Processing**: ~5000 tokens/minute maximum on reference hardware

### Accuracy Trade-offs

- **Temperature=0**: More deterministic but may miss some valid extractions
- **Skill Normalization**: Some rare technology names may be incorrectly normalized
- **C/C++ Detection**: Single character 'c' can be ambiguous in some contexts
- **Certification Filtering**: May occasionally filter legitimate technical certifications

### Missing Features

- **Multi-language Support**: Only English language processing tested
- **Real-time Updates**: Requires manual re-running for database updates
- **Batch Resume Processing**: Only processes one resume at a time
- **Export Formats**: Results only available as Python objects or console output
- **Web Interface**: No GUI or API endpoint for external integration

### Edge Cases

- **Empty Database**: Script exits gracefully with "No data to tag"
- **Missing Ollama**: Falls back to regex extraction with warning
- **Invalid API Key**: Falls back to Ollama with clear error message
- **Corrupted Database**: Validation checks prevent crashes
- **Very Long Resumes**: Truncated to 3000-4000 characters

## Architecture Reflection

### Design Choices

**Modular Separation**
- Separated tag_data.py and find_skill_gaps.py for single responsibility
- Independent rate limiter class reusable across modules
- Shared utility functions (normalize_skill, is_valid_skill) for consistency

**Hybrid LLM Approach**
- Primary: Ollama with phi3 for free, offline, private processing
- Secondary: Gemini cloud API for comparison and fallback
- Third: Regex extraction as deterministic fallback

**Determinism by Design**
- Temperature = 0 for all LLM calls
- Top_k = 1, Top_p = 0.1 to constrain token selection
- Post-processing normalization for consistent output
- Set operations (job_skills - resume_skills) for gap calculation

**Rate Limit Awareness**
- Batch size calculated from token processing capacity (5000 TPM)
- 50% safety margin to prevent resource exhaustion
- Configurable retry logic with exponential backoff

### Trade-offs

**Speed vs Accuracy**
- Chose phi3 (2.2GB) over larger models for faster inference on 8GB RAM
- Accept 5-10 seconds per job for comprehensive skill extraction
- Regex fallback trades some accuracy for reliability

**Determinism vs Flexibility**
- Temperature=0 sacrifices creative extraction for consistency
- Accept that some valid extractions may be missed
- Critical for skill gap analysis where reproducibility matters

**Local vs Cloud**
- Prioritized local Ollama for privacy and zero cost
- Added Gemini support for users with API access
- Regex provides offline capability when no LLM available

**Memory vs Batch Size**
- Batch size limited to 5-10 jobs to prevent OOM errors
- Larger batches would improve throughput but risk crashes
- Conservative memory management for 8GB environment

### Improvements with More Time

**Architecture Improvements**
- Implement async processing for concurrent job tagging
- Add result caching to avoid re-processing unchanged jobs
- Create FastAPI web service with REST endpoints
- Add support for multiple resume formats (PDF, DOCX)

**Performance Optimizations**
- Implement streaming responses for real-time progress
- Add GPU acceleration for Ollama (if available)
- Optimize prompt lengths to reduce token usage
- Pre-compile regex patterns for faster matching

**Feature Enhancements**
- Add resume parsing for section detection (Experience, Education, Projects)
- Implement weighted skill importance (required vs nice-to-have)
- Generate personalized learning path recommendations
- Add time-series tracking of skill development
- Create visualization dashboard for gap analysis

**Quality Improvements**
- Build skill taxonomy database for hierarchical classification
- Implement ensemble extraction (multiple models with voting)
- Add confidence scoring for extracted skills
- Create extensive unit test suite (>90% coverage)
- Add continuous integration pipeline

**User Experience**
- Develop CLI with rich progress bars and colored output
- Add JSON/CSV export options for results
- Create configuration file for custom skill mappings
- Implement interactive resume editing mode

---

## License

This project is for educational purposes as part of the K-Youth Data AI program.

## Authors

- K-Youth Data AI Program Participant

## Acknowledgments

- Ollama for local LLM runtime
- Google AI Studio for Gemini API access
- SQLite for lightweight database