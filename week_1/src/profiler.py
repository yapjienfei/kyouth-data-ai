"""Data profiling module - checks data quality metrics in the database."""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


def get_database_stats(db_path: Path) -> Optional[Dict[str, Any]]:
    """
    Calculate data quality metrics from the database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Dictionary with statistics or None if database doesn't exist
    """
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    stats = {}

    # 1. Total records
    cursor.execute("SELECT COUNT(*) FROM jobs")
    stats["total_records"] = cursor.fetchone()[0]

    # 2. Missing values count for each field
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN job_title IS NULL OR job_title = '' THEN 1 ELSE 0 END) as missing_job_title,
            SUM(CASE WHEN company IS NULL OR company = '' THEN 1 ELSE 0 END) as missing_company,
            SUM(CASE WHEN description IS NULL OR description = '' THEN 1 ELSE 0 END) as missing_description
        FROM jobs
    """)
    missing = cursor.fetchone()
    stats["missing_job_title"] = missing[0]
    stats["missing_company"] = missing[1]
    stats["missing_description"] = missing[2]

    # 3. Average description length
    cursor.execute("""
        SELECT AVG(LENGTH(description)) 
        FROM jobs 
        WHERE description IS NOT NULL
    """)
    stats["avg_desc_length"] = round(cursor.fetchone()[0] or 0)

    # 4. Shortest description with details
    cursor.execute("""
        SELECT source_id, job_title, LENGTH(description) as desc_len
        FROM jobs 
        WHERE description IS NOT NULL
        ORDER BY LENGTH(description) ASC
        LIMIT 1
    """)
    shortest = cursor.fetchone()
    if shortest:
        stats["shortest_desc"] = {
            "length": shortest[2],
            "source_id": shortest[0],
            "job_title": shortest[1],
        }
    else:
        stats["shortest_desc"] = None

    # 5. Longest description with details
    cursor.execute("""
        SELECT source_id, job_title, LENGTH(description) as desc_len
        FROM jobs 
        WHERE description IS NOT NULL
        ORDER BY LENGTH(description) DESC
        LIMIT 1
    """)
    longest = cursor.fetchone()
    if longest:
        stats["longest_desc"] = {
            "length": longest[2],
            "source_id": longest[0],
            "job_title": longest[1],
        }
    else:
        stats["longest_desc"] = None

    conn.close()
    return stats


def run_data_profile(db_path: str) -> None:
    """
    Run data quality profile on the gold layer database.

    Args:
        db_path: Path to the SQLite database file
    """
    db_file = Path(db_path)

    # Check if database exists (idempotency)
    if not db_file.exists():
        print(f"❌ Database not found at {db_path}")
        return

    # Get statistics
    stats = get_database_stats(db_file)

    if not stats:
        print("❌ Could not read database")
        return

    # Print formatted report
    print("\n--- 🔍 DATA QUALITY REPORT ---")

    # Total records
    print(f"📈 Total Records: {stats['total_records']}")

    # Missing values
    print(
        f"❓ Missing Values -> job_title: {stats['missing_job_title']}, "
        f"company: {stats['missing_company']}, "
        f"description: {stats['missing_description']}"
    )

    # Average description length
    print(f"📝 Avg Description Length: {stats['avg_desc_length']} chars")

    # Shortest description
    if stats["shortest_desc"]:
        print(f"⚠️  Shortest Description: {stats['shortest_desc']['length']} chars")
        print(
            f"   ↳ source_id: {stats['shortest_desc']['source_id']} | "
            f"job_title: {stats['shortest_desc']['job_title']}"
        )
    else:
        print("⚠️  Shortest Description: No descriptions found")

    # Longest description
    if stats["longest_desc"]:
        print(f"🚨 Longest Description: {stats['longest_desc']['length']} chars")
        print(
            f"   ↳ source_id: {stats['longest_desc']['source_id']} | "
            f"job_title: {stats['longest_desc']['job_title']}"
        )
    else:
        print("🚨 Longest Description: No descriptions found")

    print("=" * 50 + "\n")
