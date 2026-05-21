import os
import quopri
from pathlib import Path
from email import policy
from email.parser import BytesParser


def extract_html_from_mhtml(mhtml_path):
    """
    Extract and decode HTML content from an MHTML file.
    Returns decoded HTML string or None if not found.
    """
    try:
        # rb opens file in read binary mode(raw bytes, not text)
        with open(mhtml_path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        # Handle multipart messages
        if msg.is_multipart():
            for part in msg.walk():  # Loops through each section
                content_type = part.get_content_type()  # html, css, image, etc.

                if content_type == "text/html":
                    # Get raw data and decodes it
                    payload = part.get_payload(decode=True)

                    if payload:
                        # Check if it's quoted-printable encoded
                        content_transfer_encoding = part.get(
                            "Content-Transfer-Encoding", ""
                        ).lower()

                        if content_transfer_encoding == "quoted-printable":
                            # Decode quoted-printable
                            decoded = quopri.decodestring(payload)
                            return decoded.decode("utf-8", errors="ignore")
                        # errors='ignore' will skip any characters that can't be decoded, preventing crashes
                        else:
                            return payload.decode("utf-8", errors="ignore")
        else:
            # Single part message
            if msg.get_content_type() == "text/html":
                payload = msg.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")

        return None
    except Exception as e:
        print(f"⚠️ Error processing {mhtml_path}: {e}")
        return None


def ingest_all_mhtml(input_dir, output_dir):
    """
    Extract all MHTML files from input_dir to HTML files in output_dir.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Create output directory if it doesn't exist
    # create parent folders too if they don't exist
    # exist_ok=True means it won't raise an error if the directory already exists
    output_path.mkdir(parents=True, exist_ok=True)

    # Check if input directory exists
    if not input_path.exists():
        print(f"🥉 Bronze: Directory {input_dir} does not exist")
        print(f"\n📊 Bronze Summary:\nTotal: 0 | Extracted: 0 | Failed: 0")
        return

    # Find all MHTML files
    # glob pattern means any file that ends with .mhtml or .mht (case-sensitive) in the input directory. It returns a list of Path objects for those files.
    mhtml_files = list(input_path.glob("*.mhtml")) + list(input_path.glob("*.mht"))

    if not mhtml_files:
        print(f"🥉 Bronze: No MHTML files found in {input_dir}")
        print(f"\n📊 Bronze Summary:\nTotal: 0 | Extracted: 0 | Failed: 0")
        return

    total = len(mhtml_files)
    extracted = 0
    failed = 0

    print(f"🥉 Bronze: Processing {total} files...")

    for mhtml_file in mhtml_files:
        html_content = extract_html_from_mhtml(str(mhtml_file))

        if html_content:
            # Save to bronze layer
            # mhtml_file.stem gives the filename without the extension
            # joins folder and filename to create the full path for the output file
            output_file = output_path / f"{mhtml_file.stem}.html"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"✅ Extracted: {mhtml_file.name}")
            extracted += 1
        else:
            print(f"⚠️ No HTML content found in: {mhtml_file.name}")
            failed += 1

    # Print summary
    print(f"\n📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")
