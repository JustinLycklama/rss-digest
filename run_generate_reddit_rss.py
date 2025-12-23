#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

subreddit_file = Path(__file__).parent / "subreddit_list.txt"

def run_generate_reddit_rss():
    results = []
    if not subreddit_file.exists():
        print(f"{subreddit_file} not found!")
        return results

    with open(subreddit_file) as f:
        subreddits = [line.strip() for line in f if line.strip()]


    for subreddit in subreddits:
        try:
            print(f"Generating RSS feed for r/{subreddit}...")
            subprocess.run([sys.executable, "generate_subreddit_rss.py", subreddit], check=True)
            results.append(f"{subreddit}.xml")
        except subprocess.CalledProcessError as e:
            print(f"Failed for r/{subreddit} with error code {e.returncode}")

    return results

if __name__ == "__main__":
    outputs = run_generate_reddit_rss()
    print("\nFinished running reddit rss gen")
    print("Generated files:")
    for f in outputs:
        print(f" - {f}")