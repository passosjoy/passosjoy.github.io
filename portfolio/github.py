import base64
import time

import requests

API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token=None, session=None, retries=3):
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "passosjoy-portfolio-builder",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.retries = retries

    def _get(self, path, **params):
        for attempt in range(self.retries):
            resp = self.session.get(f"{API}{path}", params=params, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500 and attempt < self.retries - 1:
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        return None

    def user(self, login):
        return self._get(f"/users/{login}")

    def repos(self, login):
        repos, page = [], 1
        while True:
            batch = self._get(
                f"/users/{login}/repos", per_page=100, page=page, type="owner", sort="pushed"
            )
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    def readme(self, owner, repo):
        data = self._get(f"/repos/{owner}/{repo}/readme")
        if not data or "content" not in data:
            return None, ""
        text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return text, data.get("path", "README.md")

    def languages(self, owner, repo):
        return self._get(f"/repos/{owner}/{repo}/languages") or {}

    def contents(self, owner, repo, path=""):
        data = self._get(f"/repos/{owner}/{repo}/contents/{path}")
        return data if isinstance(data, list) else []
