"""Database loader module - loads JSON data into SQLite database."""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


def create_database_schema(conn: sqlite3.Connection) -> None:
    """
    Create the jobs table if it doesn't exist.

    This function defines the structure of our database table.
    We use CREATE TABLE IF NOT EXISTS to ensure idempotency -
    running this multiple times won't cause errors.

    Args:
        conn: SQLite database connection object
    """
    cursor = conn.cursor()

    # SQL statement to create the jobs table
    # IF NOT EXISTS means: if the table already exists, don't do anything
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            source_id TEXT PRIMARY KEY,
            job_title TEXT NOT NULL,
            company TEXT NOT NULL,
            description TEXT NOT NULL,
            tech_stack TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Commit the change to the database
    conn.commit()

    print("   ✓ Database schema created/verified")


def insert_job_record(
    conn: sqlite3.Connection, job_data: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Insert a single job record into the database.

    Uses INSERT OR IGNORE to prevent duplicates based on source_id.
    If a record with the same source_id already exists, the insert is skipped.

    Args:
        conn: SQLite database connection object
        job_data: Dictionary containing job fields

    Returns:
        Tuple of (success boolean, message string)
    """
    cursor = conn.cursor()

    try:
        # INSERT OR IGNORE: Only insert if source_id doesn't already exist
        # The ? placeholders are safe against SQL injection
        cursor.execute(
            """
            INSERT OR IGNORE INTO jobs (source_id, job_title, company, description)
            VALUES (?, ?, ?, ?)
        """,
            (
                job_data.get("source_id"),
                job_data.get("job_title"),
                job_data.get("company"),
                job_data.get("description"),
            ),
        )

        # Commit the change
        conn.commit()

        # Check if a row was actually inserted
        # cursor.rowcount tells us how many rows were affected
        if cursor.rowcount > 0:
            return True, "Inserted"
        else:
            return False, "Skipped (duplicate)"

    except sqlite3.Error as e:
        # Catch any database errors (corruption, constraints, etc.)
        return False, f"Failed: {str(e)}"


def load_all_jsons(input_dir: str, output_dir: str) -> None:
    """
    Load all JSON files from input_dir into SQLite database in output_dir.

    Args:
        input_dir: Directory containing JSON files (Silver layer)
        output_dir: Directory where SQLite database will be created (Gold layer)
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Create output directory if it doesn't exist (idempotency)
    output_path.mkdir(parents=True, exist_ok=True)

    # Database path - using Path for platform independence
    db_path = output_path / "jobs.db"

    # Check if input directory exists
    if not input_path.exists():
        print(f"🥇 Gold: Directory {input_dir} does not exist")
        print(f"\n📊 Gold Summary:\nTotal: 0 | Inserted: 0 | Skipped: 0")
        return

    # Find all JSON files
    json_files = list(input_path.glob("*.json"))

    if not json_files:
        print(f"🥇 Gold: No JSON files found in {input_dir}")
        print(f"\n📊 Gold Summary:\nTotal: 0 | Inserted: 0 | Skipped: 0")
        return

    print(f"🥇 Gold: Loading {len(json_files)} JSON files into database...")

    # Connect to SQLite database (creates it if it doesn't exist)
    # This works the same on Windows, Linux, and macOS
    conn = sqlite3.connect(str(db_path))

    try:
        # Create the database schema
        create_database_schema(conn)

        total = len(json_files)
        inserted = 0
        skipped = 0

        for json_file in json_files:
            try:
                # Read the JSON file
                with open(json_file, "r", encoding="utf-8") as f:
                    job_data = json.load(f)

                # Insert into database
                success, message = insert_job_record(conn, job_data)

                if success:
                    print(f"✅ Inserted: {json_file.name}")
                    inserted += 1
                else:
                    print(f"⏭️ {message}: {json_file.name}")
                    skipped += 1

            except json.JSONDecodeError as e:
                # JSON file is corrupted or invalid
                print(f"⚠️ Failed to parse JSON: {json_file.name} - {e}")
                skipped += 1
            except Exception as e:
                # Other unexpected errors
                print(f"⚠️ Error processing {json_file.name}: {str(e)[:100]}")
                skipped += 1

        # Print summary
        print(f"\n📊 Gold Summary:")
        print(f"Total: {total} | Inserted: {inserted} | Skipped: {skipped}")

    finally:
        # Always close the database connection, even if errors occur
        conn.close()
