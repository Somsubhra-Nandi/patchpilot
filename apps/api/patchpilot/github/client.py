from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class GitHubError(RuntimeError):
    pass


@dataclass(slots=True)
class GitHubClient:
    token: str | None = None
    base_url: str = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PatchPilot/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _get(self, path: str, **params: Any) -> Any:
        return await self._request("GET", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url, headers=self._headers(), timeout=20
        ) as client:
            response = await client.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            raise GitHubError(f"GitHub returned {response.status_code} for {path}")
        return response.json()

    async def issue(self, full_name: str, number: int) -> dict[str, Any]:
        issue = await self._get(f"/repos/{full_name}/issues/{number}")
        if "pull_request" in issue:
            raise GitHubError("The requested number belongs to a pull request, not an issue")
        comments = await self._get(f"/repos/{full_name}/issues/{number}/comments", per_page=30)
        repository = await self._get(f"/repos/{full_name}")
        return {
            "title": issue.get("title") or f"Issue #{number}",
            "body": issue.get("body") or "",
            "labels": [item.get("name") for item in issue.get("labels", [])],
            "comments": [item.get("body", "") for item in comments],
            "html_url": issue.get("html_url"),
            "repository": {
                "default_branch": repository.get("default_branch", "main"),
                "description": repository.get("description"),
                "language": repository.get("language"),
            },
        }

    async def tree(self, full_name: str, branch: str) -> list[dict[str, Any]]:
        payload = await self._get(f"/repos/{full_name}/git/trees/{branch}", recursive="1")
        return [item for item in payload.get("tree", []) if item.get("type") == "blob"]

    async def file(self, full_name: str, path: str, branch: str) -> str | None:
        try:
            payload = await self._get(f"/repos/{full_name}/contents/{path}", ref=branch)
        except GitHubError:
            return None
        if payload.get("encoding") != "base64" or not payload.get("content"):
            return None
        import base64

        return base64.b64decode(payload["content"]).decode("utf-8", errors="replace")

    async def create_proposal_draft_pr(
        self,
        *,
        full_name: str,
        base_branch: str,
        branch_name: str,
        artifact_path: str,
        artifact_content: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        """Create a new branch, commit one generated proposal artifact, and open a draft PR.

        This never updates an existing ref, force-pushes, merges, or writes to the base branch.
        """
        if not self.token:
            raise GitHubError("GITHUB_WRITE_ENABLED requires GITHUB_TOKEN")
        import base64

        base_ref = await self._get(f"/repos/{full_name}/git/ref/heads/{base_branch}")
        base_sha = base_ref.get("object", {}).get("sha")
        if not base_sha:
            raise GitHubError(f"Could not resolve base branch {base_branch}")
        await self._request(
            "POST",
            f"/repos/{full_name}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        await self._request(
            "PUT",
            f"/repos/{full_name}/contents/{artifact_path}",
            json={
                "message": f"docs: add PatchPilot proposal for {title}",
                "content": base64.b64encode(artifact_content.encode()).decode(),
                "branch": branch_name,
            },
        )
        return await self._request(
            "POST",
            f"/repos/{full_name}/pulls",
            json={
                "title": title,
                "head": branch_name,
                "base": base_branch,
                "body": body,
                "draft": True,
            },
        )

    async def create_draft_pr(
        self, *, full_name: str, base_branch: str, branch_name: str, title: str, body: str
    ) -> dict[str, Any]:
        if not self.token:
            raise GitHubError("GITHUB_WRITE_ENABLED requires GITHUB_TOKEN")
        if branch_name == base_branch:
            raise GitHubError("Draft PR head cannot be the default branch")
        return await self._request(
            "POST",
            f"/repos/{full_name}/pulls",
            json={"title": title, "head": branch_name, "base": base_branch, "body": body, "draft": True},
        )
