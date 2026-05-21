"""HTML processing module - cleans HTML and extracts structured JSON data."""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError


class JobListing(BaseModel):
    """Pydantic model for job listing data."""
    source_id: str
    job_title: str
    company: str
    description: str
    
    class Config:
        min_anystr_length = 1
        anystr_strip_whitespace = True


def extract_source_id(soup: BeautifulSoup) -> Optional[str]:
    """Extract source_id from og:url meta tag."""
    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        match = re.search(r'/job/(\d+)', og_url["content"])
        if match:
            return match.group(1)
    return None


def extract_job_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract job title from data-automation attribute."""
    title_elem = soup.find(attrs={"data-automation": "job-detail-title"})
    if title_elem:
        return title_elem.get_text(strip=True)
    return None


def extract_company(soup: BeautifulSoup) -> Optional[str]:
    """Extract company name from advertiser-name."""
    company_elem = soup.find("span", attrs={"data-automation": "advertiser-name"})
    if company_elem:
        company = company_elem.get_text(strip=True)
        company = re.sub(r'✓$', '', company).strip()
        return company
    
    company_btn = soup.find("button", attrs={"data-automation": "advertiser-name"})
    if company_btn:
        company = company_btn.get_text(strip=True)
        company = re.sub(r'✓$', '', company).strip()
        return company    
    return None

def extract_description(soup: BeautifulSoup) -> Optional[str]:
    """Extract job description from jobAdDetails."""
    desc_elem = soup.find("div", attrs={"data-automation": "jobAdDetails"})
    if desc_elem:
        description = desc_elem.get_text(separator="\n", strip=True)
        description = re.sub(r'\n{3,}', '\n\n', description)
        return description
    return None

def process_all_html(input_dir: str, output_dir: str) -> None:
    """Process all HTML files from input_dir to JSON files in output_dir."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    if not input_path.exists():
        print(f"🥈 Silver: Directory {input_dir} does not exist")
        print(f"\n📊 Silver Summary:\nTotal: 0 | Processed: 0 | Skipped: 0")
        return
    
    html_files = list(input_path.glob("*.html"))
    
    if not html_files:
        print(f"🥈 Silver: No HTML files found in {input_dir}")
        print(f"\n📊 Silver Summary:\nTotal: 0 | Processed: 0 | Skipped: 0")
        return
    
    total = len(html_files)
    processed = 0
    skipped = 0
    
    print(f"🥈 Silver: Processing {total} files...")
    
    for html_file in html_files:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            source_id = extract_source_id(soup)
            job_title = extract_job_title(soup)
            company = extract_company(soup)
            description = extract_description(soup)
            
            # Track missing fields for warning messages
            missing_fields = []
            if not source_id:
                missing_fields.append("source_id")
            if not job_title:
                missing_fields.append("job_title")
            if not company:
                missing_fields.append("company")
            if not description or len(description) < 10:
                missing_fields.append("description")
            
            # Print missing field warnings
            if missing_fields:
                for field in missing_fields:
                    print(f"⚠️ Missing {field} in: {html_file.name}")
            
            # Check required fields
            if not source_id or not job_title or not company or not description or len(description) < 10:
                skipped += 1
                continue
            
            # Create a dictionary for the data
            raw_data = {
                "source_id": source_id,
                "job_title": job_title,
                "company": company,
                "description": description,
            }
            
            # Validate with Pydantic
            try:
                JobListing(**raw_data)
                
                output_file = output_path / f"{html_file.stem}.json"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(raw_data, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Processed: {html_file.name}")
                processed += 1
                
            except ValidationError as e:
                print(f"❌ Validation error in {html_file.name}: {e}")
                skipped += 1
                
        except Exception as e:
            print(f"❌ Error processing {html_file.name}: {type(e).__name__}: {e}")
            skipped += 1
    
    print(f"\n📊 Silver Summary:")
    print(f"Total: {total} | Processed: {processed} | Skipped: {skipped}")
