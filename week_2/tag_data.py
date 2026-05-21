#!/usr/bin/env python3
"""
Data Tagging Module for Job Descriptions

This module reads job descriptions from a SQLite database,
uses local Ollama models to extract technical stack information,
and updates the tech_stack column.
"""

import os
import sqlite3
import time
import requests
import subprocess
from typing import List, Dict, Any, Optional
from pathlib import Path

# Configuration
BATCH_SIZE = 3  # Number of jobs to process in each batch
RETRY_DELAY = 2  # Seconds to wait before retrying
MAX_RETRIES = 2  # Maximum retries per batch
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "phi3"  # or "deepseek-r1:1.5b"


def is_ollama_running() -> bool:
    """Check if Ollama service is running."""
    try:
        response = requests.get("http://localhost:11434", timeout=3)
        return response.status_code == 200
    except:
        return False


def is_model_available(model: str) -> bool:
    """Check if the specified model is available in Ollama."""
    # Check via ollama list command (fastest)
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
    if model in result.stdout:
        return True
    return False


def tag_data(db_url: str, model: str = DEFAULT_MODEL):
    """
    Main function to tag job descriptions with technical stack information.
    
    Args:
        db_url: Path to the SQLite database file
        model: Ollama model to use ("phi3" or "deepseek-r1:1.5b")
    """
    
    # Check Ollama
    if not is_ollama_running():
        print("Error: Ollama is not running. Start with: ollama serve")
        return
    
    if not is_model_available(model):
        print(f"Error: Model '{model}' not found. Pull with: ollama pull {model}")
        return
    
    # Connect to database
    conn = sqlite3.connect(db_url)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get jobs without tech_stack (NULL or empty string)
        cursor.execute("""
            SELECT source_id, job_title, description 
            FROM jobs 
            WHERE tech_stack IS NULL OR tech_stack = ''
        """)
        
        jobs = cursor.fetchall()
        total_jobs = len(jobs)
        print(f"\n📊 Found {total_jobs} jobs that need tagging")
        
        if total_jobs == 0:
            print("No jobs to tag. Exiting.")
            return
        
        successful = 0
        failed = 0
        
        # Process in batches
        for batch_start in range(0, total_jobs, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_jobs)
            batch = jobs[batch_start:batch_end]
            
            print(f"\n[Batch {batch_start // BATCH_SIZE + 1}] "
                  f"Processing jobs {batch_start + 1}-{batch_end} of {total_jobs}")
            
            # Process batch with retries
            for attempt in range(MAX_RETRIES):
                try:
                    for job in batch:
                        tags = extract_tech_stack(job, model)
                        
                        if tags:
                            # Update the database
                            cursor.execute("""
                                UPDATE jobs 
                                SET tech_stack = ? 
                                WHERE source_id = ?
                            """, (tags, job['source_id']))
                            conn.commit()
                            
                            # Log as required
                            print(f"  ✅ Job {job['source_id']}: {tags}")
                            successful += 1
                        else:
                            print(f"  ⚠️  Job {job['source_id']}: No tags extracted")
                            failed += 1
                    
                    break  # Batch successful, exit retry loop
                    
                except Exception as e:
                    print(f"  Attempt {attempt + 1} failed: {str(e)[:100]}")
                    if attempt < MAX_RETRIES - 1:
                        print(f"  Retrying in {RETRY_DELAY} seconds...")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"  ❌ Batch failed after {MAX_RETRIES} attempts")
                        failed += len(batch)
            
            # Delay between batches to let the model breathe
            time.sleep(1)
        
        # Final summary
        print("\n" + "=" * 60)
        print("📊 TAGGING COMPLETED")
        print(f"  ✅ Successfully tagged: {successful} jobs")
        print(f"  ❌ Failed: {failed} jobs")
        print(f"  📈 Total processed: {successful + failed} jobs")
        print("=" * 60)
        
    finally:
        conn.close()


def extract_tech_stack(job: sqlite3.Row, model: str) -> Optional[str]:
    """
    Extract technical stack from a single job using Ollama.
    
    Args:
        job: Row containing job_title and description
        model: Ollama model name
    
    Returns:
        Comma-separated string of tech skills, or None if failed
    """
    
    title = job['job_title'] if job['job_title'] else "Unknown Position"
    description = job['description'] if job['description'] else ""
    
    if not description:
        return None
    
    # Truncate description to save memory and speed up processing
    max_length = 2000
    if len(description) > max_length:
        description = description[:max_length] + "..."
    
    # Create prompt for the LLM
    prompt = f"""Extract ONLY the technical skills, programming languages, frameworks, databases, and tools from this job posting.

Return ONLY a comma-separated list. Do NOT include any other text or explanations.

Examples:
- "Python, Django, PostgreSQL, AWS, Docker"
- "Java, Spring Boot, MongoDB, Kubernetes"
- "JavaScript, React, Node.js, TypeScript"

Job Title: {title}

Job Description:
{description}

Technical skills (comma-separated only):"""
    
    # Call Ollama API
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 150,
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        tags = result.get("response", "").strip()
        
        # Clean up common issues
        tags = tags.replace("Technical skills:", "")
        tags = tags.replace("comma-separated", "")
        tags = tags.strip()
        
        # Remove quotes if present
        tags = tags.strip('"').strip("'")
        
        if tags and len(tags) > 2:
            return clean_tags(tags)
        return None
        
    except requests.exceptions.Timeout:
        print(f"      ⏱️  Timeout for job {job['source_id']}")
        return None
    except Exception as e:
        print(f"      ⚠️  Error: {str(e)[:50]}")
        return None


def clean_tags(tags: str) -> str:
    """
    Clean and standardize the extracted tags.
    
    Args:
        tags: Raw comma-separated tags from LLM
    
    Returns:
        Cleaned and formatted tags
    """
    
    if not tags:
        return ""
    
    # Handle different separators
    if ", " in tags:
        tag_list = [t.strip() for t in tags.split(", ")]
    elif "," in tags:
        tag_list = [t.strip() for t in tags.split(",")]
    else:
        # Single tag or space-separated
        tag_list = [tags.strip()]
    
    # Remove empty and very short tags (likely errors)
    tag_list = [t for t in tag_list if t and len(t) > 1]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in tag_list:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique_tags.append(tag)
    
    # Limit to 15 tags per job
    if len(unique_tags) > 15:
        unique_tags = unique_tags[:15]
    
    return ", ".join(unique_tags)


def get_available_models() -> List[str]:
    """Get list of available models from Ollama."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        models = []
        for line in result.stdout.split('\n')[1:]:  # Skip header
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
    
    # Find the database
    project_root = Path(__file__).parent
    db_path = project_root / "data" / "jobs_d1.db"
    
    if not db_path.exists():
        print(f"\n❌ Database not found at: {db_path}")
        print("Expected structure: week_2/data/jobs_d1.db")
        return
    
    print(f"\n✅ Found database: {db_path}")
    
    # Check Ollama
    print("\n🔍 Checking Ollama...")
    if not is_ollama_running():
        print("❌ Ollama is not running!")
        print("Start with: ollama serve")
        return
    print("✅ Ollama is running")
    
    # Get available models
    print("\n📋 Available models:")
    available_models = get_available_models()
    
    if not available_models:
        print("  No models found!")
        return
    
    for model in available_models:
        print(f"  ✅ {model}")
    
    # Find models we can use (phi3 or deepseek, with or without :latest)
    usable_models = []
    for model in available_models:
        # Check base name (remove :latest if present)
        base = model.replace(":latest", "")
        if base in ["phi3", "deepseek-r1:1.5b"]:
            usable_models.append(model)
    
    if not usable_models:
        print("\n⚠️  No preferred models found. Using first available.")
        selected_model = available_models[0]
    else:
        print("\n🎯 Choose a model:")
        for i, model in enumerate(usable_models, 1):
            base = model.replace(":latest", "")
            if base == "phi3":
                print(f"   {i}. {model} (more accurate, slower)")
            else:
                print(f"   {i}. {model} (faster, lighter)")
        
        choice = input(f"\nEnter choice (1-{len(usable_models)}, default 1): ").strip()
        try:
            idx = int(choice) - 1 if choice else 0
            selected_model = usable_models[idx]
        except:
            selected_model = usable_models[0]
    
    print(f"\n🚀 Starting tagging with model: {selected_model}")
    print("-" * 60)
    
    # Run tagging
    tag_data(str(db_path), selected_model)

if __name__ == "__main__":
    main()