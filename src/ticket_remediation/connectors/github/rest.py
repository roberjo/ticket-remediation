from github import Auth, Github

from .base import PullRequestRef, PullRequestState


class GitHubRestClient:
    """PyGithub-backed client for the remote-API operations pipeline B needs
    (repo lookup, PR creation) — local git mechanics live in git_ops.py instead.
    """

    def __init__(self, token: str):
        self._gh = Github(auth=Auth.Token(token))

    def get_default_branch(self, repo_full_name: str) -> str:
        repo = self._gh.get_repo(repo_full_name)
        return repo.default_branch

    def create_pull_request(
        self, repo_full_name: str, head: str, base: str, title: str, body: str
    ) -> PullRequestRef:
        repo = self._gh.get_repo(repo_full_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        return PullRequestRef(number=pr.number, url=pr.html_url)

    def get_pull_request(self, repo_full_name: str, pr_number: int) -> PullRequestState:
        repo = self._gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        return PullRequestState(number=pr.number, state=pr.state, merged=pr.merged)
