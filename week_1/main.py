import sys
from pathlib import Path
from src.ingestor import ingest_all_mhtml
from src.processor import process_all_html 
from src.loader import load_all_jsons      
from src.profiler import run_data_profile   

SOURCE_DIR = Path("data/0_source")
BRONZE_DIR = Path("data/1_bronze")
SILVER_DIR = Path("data/2_silver")
GOLD_DIR = Path("data/3_gold")
DB_NAME = "jobs.db"


def run_bronze():
    """Extract MHTML to HTML (Bronze layer)."""
    print("\n" + "=" * 60)
    print("🥉 BRONZE LAYER: Extracting MHTML to HTML")
    print("=" * 60)
    ingest_all_mhtml(str(SOURCE_DIR), str(BRONZE_DIR))


def run_silver():
    """Process HTML to JSON (Silver layer)."""
    print("\n" + "=" * 60)
    print("🥈 SILVER LAYER: Processing HTML to JSON")
    print("=" * 60)
    process_all_html(str(BRONZE_DIR), str(SILVER_DIR))


def run_gold():
    """Load JSON to SQLite (Gold layer)."""
    print("\n" + "=" * 60)
    print("🥇 GOLD LAYER: Loading JSON to Database")
    print("=" * 60)
    load_all_jsons(str(SILVER_DIR), str(GOLD_DIR))


def run_profile():
    """Run data quality profile."""
    run_data_profile(str(GOLD_DIR / DB_NAME))


def run_all():
    """Run the complete ETL pipeline in order."""
    print("\n" + "🚀" * 30)
    print("STARTING ALL ETL PIPELINE")
    print("🚀" * 30)
    
    run_bronze()
    run_silver()
    run_gold()
    run_profile()
    
    print("\n" + "✅" * 30)
    print("ALL ETL PIPELINE COMPLETED SUCCESSFULLY")
    print("✅" * 30 + "\n")


def print_usage():
    """Print usage instructions."""
    print("\n" + "=" * 50)
    print("📋 ETL PIPELINE - AVAILABLE COMMANDS")
    print("=" * 50)
    print("  python main.py ingest   - Extract MHTML to HTML (Bronze layer)")
    print("  python main.py process  - Process HTML to JSON (Silver layer)")
    print("  python main.py load     - Load JSON to SQLite (Gold layer)")
    print("  python main.py profile  - Run data quality report")
    print("  python main.py all      - Run the complete ETL pipeline in order")
    print("=" * 50 + "\n")


def main():
    # Check command line arguments
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    # Route to appropriate function
    if command == "ingest":
        run_bronze()
    elif command == "process":
        run_silver()
    elif command == "load":
        run_gold()
    elif command == "profile":
        run_profile()
    elif command == "all":
        run_all()
    else:
        print(f"\n❌ Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()