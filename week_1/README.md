# Week 1: ETL Pipeline for Job Listings

## Project Description

This project implements a complete ETL (Extract, Transform, Load) pipeline that processes job listing data from MHTML web archive files into a structured SQLite database. The pipeline follows the **Medallion Architecture** with three layers:

- **Bronze Layer (Raw Data)**: Extracts HTML content from MHTML files
- **Silver Layer (Cleaned Data)**: Parses HTML, extracts job details (title, company, description, source_id), and validates data quality
- **Gold Layer (Curated Data)**: Loads validated data into a SQLite database with duplicate prevention

The pipeline processes 100 job listings and outputs a data quality report with metrics like record counts, missing values, and description length statistics.

## Setup Instructions

### Prerequisites

- **Python Version**: Exactly 3.14.0
- **UV Version**: Exactly 0.8.0
- **Operating System**: Linux, macOS, or Windows (platform-independent)

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd week_1
   ```

2. **Install UV package manager** (version 0.8.0)
   ```bash
   # For Linux/macOS
   curl -LsSf https://astral.sh/uv/0.8.0/install.sh | sh

   # For Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/0.8.0/install.ps1 | iex"
   ```

3. **Install Python 3.14.0**
   ```bash
   uv python install 3.14.0
   ```

4. **Create virtual environment and install dependencies**
   ```bash
   uv venv --python 3.14.0
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv sync
   ```

5. **Verify installation**
   ```bash
   uv run python --version  # Should show Python 3.14.0
   uv --version             # Should show uv 0.8.0
   uv run ruff --version    # Should show ruff 0.15.0
   ```

### Project Structure

```
week_1/
├── data/
│   ├── 0_source/          # Place MHTML files here
│   ├── 1_bronze/          # Extracted HTML files
│   ├── 2_silver/          # Cleaned JSON files
│   └── 3_gold/            # SQLite database
├── src/
│   ├── ingestor.py        # Bronze layer: MHTML -> HTML
│   ├── processor.py       # Silver layer: HTML -> JSON
│   ├── loader.py          # Gold layer: JSON -> SQLite
│   └── profiler.py        # Data quality reporting
├── main.py                # CLI orchestrator
├── pyproject.toml         # Dependencies
├── uv.lock                # Locked dependencies
└── README.md              # This file
```

## Usage

### Prepare Input Data

Place your MHTML files in `data/0_source/`:
```bash
mkdir -p data/0_source
# Copy your .mhtml files to data/0_source/
```

### Run Individual Pipeline Stages

```bash
# Bronze layer: Extract HTML from MHTML files
uv run python main.py ingest

# Silver layer: Process HTML to JSON with validation
uv run python main.py process

# Gold layer: Load JSON into SQLite database
uv run python main.py load

# Data quality report
uv run python main.py profile
```

### Run Complete Pipeline

```bash
# Run all stages in sequence
uv run python main.py all
```

### Expected Output

**Bronze Layer (100 files):**
```
🥉 Bronze: Processing 100 files...
✅ Extracted: job_001.mhtml
✅ Extracted: job_002.mhtml
...
📊 Bronze Summary:
Total: 100 | Extracted: 100 | Failed: 0
```

**Silver Layer (84 valid, 16 skipped):**
```
🥈 Silver: Processing 100 files...
✅ Processed: valid_job.html
⚠️ Skipped: invalid_job.html - missing required fields
...
📊 Silver Summary:
Total: 100 | Processed: 84 | Skipped: 16
```

**Gold Layer (84 inserted):**
```
🥇 Gold: Loading 84 JSON files...
✅ Inserted: job_001.json
...
📊 Gold Summary:
Total: 84 | Inserted: 84 | Skipped: 0
```

**Data Quality Report:**
```
--- 🔍 DATA QUALITY REPORT ---
📈 Total Records: 84
❓ Missing Values -> job_title: 0, company: 0, description: 0
📝 Avg Description Length: 2654 chars
⚠️ Shortest Description: 140 chars
   ↳ source_id: 88882387 | job_title: Senior Back-End Developer
🚨 Longest Description: 5003 chars
   ↳ source_id: 91460017 | job_title: Trading Platform Engineer
```

## Technical Reflections

### Module 1: The Extractor (Medallion & Lakehouses)

**Why keep raw HTML files instead of directly inserting into the database?**

Keeping raw HTML files in the Bronze layer provides an immutable source of truth. If a bug is discovered in the cleaning logic, you can re-process the original files without re-downloading data. This also enables debugging (compare raw vs cleaned data to identify transformation issues), recovery (re-run failed transformations without data loss), and audit trails (track exactly what data was received versus what was processed).

### Module 2: Treatment Plant (ETL vs ELT & Scale)

**Why do cloud systems prefer ELT (loading raw data first)?**

Cloud platforms like Snowflake and BigQuery separate storage from compute, making it cost-effective to store raw data and transform it on-demand. ELT allows flexibility (raw data can be transformed multiple ways for different use cases), speed (loading is fast, transformations happen in parallel), and reprocessing (new business rules can be applied to historical raw data).

**Sequential processing limitations vs distributed processing:**

Sequential processing creates bottlenecks where a single slow file blocks the entire pipeline. If one file takes 10 seconds, 1 million files would take approximately 115 days. Distributed processing (using tools like Apache Spark) splits data across hundreds of machines, processing in parallel for minutes instead of days, and provides fault tolerance if individual workers fail.

### Module 3: The Blueprint & The Vault (Storage & Contracts)

**What should happen if job_title is missing? Fail early vs insert NULL?**

Fail early with validation errors. Inserting NULLs causes "garbage in, garbage out" - downstream dashboards, reports, and ML models will produce misleading results. By rejecting incomplete records, data quality issues are caught immediately (not propagated), stakeholders trust the data because nulls are explicitly handled, and engineering teams fix root causes instead of compensating for bad data.

**How INSERT OR IGNORE prevents duplicates:**

The source_id field serves as the primary key (unique identifier from the job posting URL). When INSERT OR IGNORE is used, if a record with the same source_id already exists in the database, the insert is silently skipped. This makes the pipeline idempotent - running it multiple times produces the same result and prevents duplicate records that would cause incorrect counts or duplicate processing.

### Module 4: The QA Inspector & Orchestrator (Orchestration & DAGs)

**What happens if processor.py crashes halfway? How are orchestration tools more reliable?**

Manual handling requires operator intervention to figure out where the failure occurred, clean up partial outputs, re-run from the correct point, and risk re-processing already-completed files (creating duplicates).

Automated orchestration tools (like Apache Airflow or Dagster) provide checkpoints to track which tasks succeeded before failure, automatic retries with exponential backoff, dependency management to only re-run failed tasks (not the entire pipeline), alerts to notify operators when manual intervention is needed, and centralized observability for logging, metrics, and lineage tracking. For example, if processor.py fails after processing 50 files, Airflow can restart only the failed task while skipping the 50 already-completed files.

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| No interpreter found for Python 3.14.0 | Run `uv python install 3.14.0` |
| Module not found | Run `uv sync` to install dependencies |
| Database locked | Close any SQLite browsers and re-run |
| Permission denied | Ensure `data/` directory has write permissions |

## License

This project is for educational purposes as part of a data engineering course.