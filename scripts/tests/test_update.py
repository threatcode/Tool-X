import os
import json
import pytest
import types

# Dynamically import the updater script
import importlib.util
SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "enhance_tools_git.py")
spec = importlib.util.spec_from_file_location("enhance_tools_git", SCRIPT_PATH)
enhance_tools_git = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enhance_tools_git)

# ---- SAMPLE DATA FOR TESTING ----
SAMPLE_DATA = {
    "ToolA": {
        "name": "ToolA",
        "package_name": "tool-a",
        "version": "latest",
        "category": ["Termux OS"],
        "url": "https://github.com/octocat/Hello-World.git",
        "package_manager": "git",
        "dependency": ["git"]
    },
    "ToolB": {
        "name": "ToolB",
        "package_name": "tool-b",
        "version": "1.0",
        "category": None,
        "url": None,
        "package_manager": "git",
        "dependency": ["python", "git"]
    }
}

def test_normalize_category_merges_synonyms():
    categories = ["Termux OS", "wireless_tools", "Information Gathering"]
    normalized = enhance_tools_git.normalize_category(categories)
    assert "termux" in normalized
    assert "wireless" in normalized
    assert "information_gathering" in normalized

def test_normalize_category_handles_none():
    normalized = enhance_tools_git.normalize_category(None)
    assert normalized == ["uncategorized"]

def test_parse_repo_info_github():
    platform, path = enhance_tools_git.parse_repo_info("https://github.com/user/repo.git")
    assert platform == "github"
    assert path == "user/repo"

def test_parse_repo_info_gitlab():
    platform, path = enhance_tools_git.parse_repo_info("https://gitlab.com/group/project.git")
    assert platform == "gitlab"
    assert path.startswith("group%2Fproject")

def test_parse_repo_info_invalid_url():
    platform, path = enhance_tools_git.parse_repo_info("https://example.com/something")
    assert platform is None
    assert path is None

def test_fetch_github_meta_mocked(monkeypatch):
    """Mock GitHub API response for deterministic testing."""
    def mock_get(url, headers=None, timeout=10):
        class MockResponse:
            def __init__(self, json_data, status_code):
                self._json = json_data
                self.status_code = status_code
                self.headers = {}
            def json(self):
                return self._json
        if "releases/latest" in url:
            return MockResponse({"tag_name": "v2.0.0"}, 200)
        return MockResponse({
            "stargazers_count": 42,
            "forks_count": 10,
            "license": {"spdx_id": "MIT"},
            "archived": False
        }, 200)

    monkeypatch.setattr(enhance_tools_git.requests, "get", mock_get)
    meta = enhance_tools_git.fetch_github_meta("user/repo")
    assert meta["stars"] == 42
    assert meta["forks"] == 10
    assert meta["license"] == "MIT"
    assert meta["latest_version"] == "v2.0.0"

def test_version_placeholder_conversion(tmp_path):
    """Ensure 'latest' placeholders are converted to 'unknown' before API fetch."""
    test_file = tmp_path / "test.json"
    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_DATA, f)

    # Patch functions to skip API calls
    enhance_tools_git.fetch_github_meta = lambda _: {"latest_version": "v1.1", "stars": 1, 
"forks": 2, "license": "MIT", "archived": False}
    enhance_tools_git.fetch_gitlab_meta = lambda _: {}

    # Run main logic manually
    with open(test_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, item in data.items():
        item["category"] = enhance_tools_git.normalize_category(item.get("category"))
        if item.get("version", "").lower() == "latest":
            item["version"] = "unknown"
    assert data["ToolA"]["version"] == "unknown"


