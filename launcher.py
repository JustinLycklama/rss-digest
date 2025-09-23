#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# Get the directory of this script (so paths are relative to the repo)
repo_dir = Path(__file__).parent

# Path to the script you want to run
digest_script = repo_dir / "digest.py"

# Run the digest.py script
try:
    result = subprocess.run(
        [sys.executable, str(digest_script)],
        check=True,
        capture_output=True,
        text=True
    )
    print("digest.py output:\n", result.stdout)
except subprocess.CalledProcessError as e:
    print("digest.py failed with error:\n", e.stderr)

