"""
enhance_tools_git.py
Enhances core/data.json by:
- Normalizing categories
- Fetching GitHub/GitLab metadata (stars, forks, license, version, archive status)
- Handling rate limits, transient errors, and missing repositories gracefully
"""

import json
import os
import time
import requests
from urllib.parse import urlparse

# === CONFIG ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core"))
INPUT_FILE = os.path.join(BASE_DIR, "data.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "data_enhanced.json")

GITHUB_API = "https://api.github.com/repos"
GITLAB_API = "https://gitlab.com/api/v4/projects"
HEADERS = {"Accept": "application/vnd.github.v3+json"}
RATE_LIMIT_WAIT = 60  # seconds
MAX_RETRIES = 3

CATEGORY_MAP = {
    "termux os": "termux",
    "termux_os": "termux",
    "wireless_tools": "wireless",
    "wireless_testing": "wireless",
    "information gathering": "information_gathering",
    "password attacks": "password_attack",
    "ddos attacks": "ddos",
    "maintaining access": "maintaining_access",
    "forensics tools": "forensics",
    "web server": "web_server",
    "web server's": "web_server",
    "exploitation tools": "exploitation",
    "vulnerability scanner": "vulnerability_scanner",
    "ip-tracking tools": "ip_tracking"
}

def normalize_category(cat):
    """Normalize category values into consistent lowercase format."""
    if not cat:
        return ["uncategorized"]
    if isinstance(cat, str):
        cat = [cat]
    normalized = []
    for c in cat:
        c = c.strip().lower()
        c = CATEGORY_MAP.get(c, c)
        normalized.append(c)
    return list(set(normalized))

def parse_repo_info(url):
    """Identify platform and repo path from a URL."""
    if not url:
        return None, None
    parsed = urlparse(url)
    if "github.com" in parsed.netloc:
        path = parsed.path.strip("/").replace(".git", "")
        return "github", path
    elif "gitlab.com" in parsed.netloc:
        path = parsed.path.strip("/").replace(".git", "")
        return "gitlab", path.replace("/", "%2F")
    return None, None

def safe_get_json(response, path):
    """Safely parse JSON, logging errors if invalid."""
    try:
        return response.json()
    except ValueError:
        print(f"[ERROR] Invalid JSON for {path}")
        return None

def retry_request(url, headers=None, timeout=15, retries=MAX_RETRIES, wait=2):
    """Retry a request with exponential backoff on failure."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code in (200, 404, 403, 429):
                return r
            print(f"[WARN] Unexpected status {r.status_code} for {url}, retrying...")
        except requests.RequestException as e:
            print(f"[WARN] Request error: {e}, retrying...")
        time.sleep(wait * (2 ** attempt))
    print(f"[ERROR] Max retries exceeded for {url}")
    return None

def fetch_github_meta(path):
    """Fetch metadata for a GitHub repository with robust error handling."""
    meta = {"stars": None, "forks": None, "license": None, "latest_version": None, "archived": 
False}
    repo_url = f"{GITHUB_API}/{path}"

    r = retry_request(repo_url, headers=HEADERS)
    if not r:
        return meta

    if r.status_code == 404:
        print(f"[WARN] Repository not found: {path}")
        return meta
    if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
        print("[WARN] GitHub rate limit reached. Waiting...")
        time.sleep(RATE_LIMIT_WAIT)
        return fetch_github_meta(path)

    if r.status_code != 200:
        print(f"[ERROR] GitHub API error {r.status_code} for {path}")
        return meta

    data = safe_get_json(r, path)
    if not isinstance(data, dict):
        return meta

    meta["stars"] = data.get("stargazers_count")
    meta["forks"] = data.get("forks_count")
    meta["license"] = (data.get("license") or {}).get("spdx_id")
    meta["archived"] = data.get("archived", False)

    # Latest release
    rel = retry_request(f"{repo_url}/releases/latest", headers=HEADERS)
    if rel and rel.status_code == 200:
        rel_data = safe_get_json(rel, path)
        if isinstance(rel_data, dict):
            meta["latest_version"] = rel_data.get("tag_name")
    return meta

def fetch_gitlab_meta(path):
    """Fetch metadata for a GitLab repository."""
    meta = {"stars": None, "forks": None, "license": None, "latest_version": None, "archived": 
False}
    url = f"{GITLAB_API}/{path}"

    r = retry_request(url)
    if not r:
        return meta
    if r.status_code == 404:
        print(f"[WARN] GitLab repo not found: {path}")
        return meta
    if r.status_code == 429:
        print("[WARN] GitLab rate limit reached. Waiting...")
        time.sleep(RATE_LIMIT_WAIT)
        return fetch_gitlab_meta(path)
    if r.status_code != 200:
        print(f"[ERROR] GitLab API error {r.status_code} for {path}")
        return meta

    data = safe_get_json(r, path)
    if not isinstance(data, dict):
        return meta

    meta["stars"] = data.get("star_count")
    meta["forks"] = data.get("forks_count")
    meta["license"] = (data.get("license") or {}).get("name")
    meta["archived"] = data.get("archived", False)
    return meta

def enhance_data():
    """Main enhancement routine."""
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    enhanced = {}
    skipped = []

    for key, item in data.items():
        # Normalize categories
        item["category"] = normalize_category(item.get("category"))
        # Replace "latest" placeholders
        if item.get("version", "").lower() == "latest":
            item["version"] = "unknown"

        platform, path = parse_repo_info(item.get("url"))
        if platform == "github":
            meta = fetch_github_meta(path)
        elif platform == "gitlab":
            meta = fetch_gitlab_meta(path)
        else:
            skipped.append(key)
            enhanced[key] = item
            continue

        if meta.get("latest_version"):
            item["version"] = meta["latest_version"]
        item["stars"] = meta.get("stars")
        item["forks"] = meta.get("forks")
        item["license"] = meta.get("license")
        item["archived"] = meta.get("archived")

        enhanced[key] = item

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        json.dump(enhanced, out, indent=2)

    print(f"[INFO] Enhanced data written to {OUTPUT_FILE}")
    if skipped:
        print(f"[WARN] Skipped {len(skipped)} entries without valid URLs: {skipped}")

if __name__ == "__main__":
    enhance_data()

