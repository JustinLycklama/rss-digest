#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# Path to your feed file
OUTPUT_DIR = "output"

def run(cmd, check=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, capture_output=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        if check:
            sys.exit(result.returncode)

try:
    # Stage feed file
    run(["git", "stage", OUTPUT_DIR])

    # Commit (amend previous commit to keep history clean)
    run(["git", "commit", "-m", "Update daily feed", "--amend"])

    # Force push to overwrite remote
    run(["git", "push", "-f"])

finally:
    # Switch back to main branch
    run(["git", "checkout", "main"], check=False)
