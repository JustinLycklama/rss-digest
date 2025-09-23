#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# Get the directory of this script (so paths are relative to the repo)
repo_dir = Path(__file__).parent

# List of scripts to run, in order
scripts = [
    "generate_digest.py",
    "update_git.py",
    # add more scripts here if needed
]

for script_name in scripts:
    script_path = repo_dir / script_name
    print(f"Running {script_name}...")

    try:
        # Run script and let stdout/stderr print directly to console
        result = subprocess.run([sys.executable, str(script_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"{script_name} failed with return code {e.returncode}")
        break  # stop on error
