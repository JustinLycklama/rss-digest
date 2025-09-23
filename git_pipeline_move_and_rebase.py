#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# Path to your feed file
OUTPUT_FILE = "feed.xml"

def run(cmd, check=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, capture_output=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        if check:
            sys.exit(result.returncode)

# Switch to gh-pages branch
run(["git", "checkout", "gh-pages"])

# Rebase onto main to get latest
run(["git", "rebase", "main"])
