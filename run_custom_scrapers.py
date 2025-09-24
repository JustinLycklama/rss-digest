#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

scraper_dir = Path(__file__).parent / "custom_scrapers"

def run_custom_scrapers():
    results = []
    for scraper in scraper_dir.glob("*.py"):
        try:
            print(f"Running {scraper.name}...")
            subprocess.run([sys.executable, str(scraper)], check=True)
            output_file = scraper.with_suffix(".xml").name
            results.append(output_file)
        except subprocess.CalledProcessError as e:
            print(f"{scraper.name} failed with error code {e.returncode}")
    return results

if __name__ == "__main__":
    outputs = run_custom_scrapers()
    print("\nFinished running custom scrapers")
    print("Generated files:")
    for f in outputs:
        print(f" - {f}")

