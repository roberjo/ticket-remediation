from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from mock_servers.common.state import RecordStore, mount_debug_routes

from .jql import parse_jql

app = FastAPI(title="Jira AVREM Mock")

PROJECT_KEY = "AVREM"
PROJECT_NAME = "Application Vulnerability Remediation"
COMPONENTS = ["frontend", "backend-api", "auth", "infra-config"]
WORKFLOW = [
    "Backlog",
    "Triage",
    "Ready for Remediation",
    "In Progress",
    "In Review",
    "Done",
    "Won't Fix",
]

_issues = RecordStore(id_prefix=PROJECT_KEY)


def _seed() -> None:
    _issues.reset()
    key = _issues.next_key()
    _issues.put(
        key,
        {
            "key": key,
            "project_key": PROJECT_KEY,
            "issue_type": "Vulnerability",
            "summary": "[High] Reflected Cross-Site Scripting (XSS) in frontend: search page",
            "description": (
                "User-supplied input from the 'q' query parameter on /search is rendered into "
                "the page via dangerouslySetInnerHTML without sanitization, allowing arbitrary "
                "JavaScript execution in a victim's browser.\n\n"
                "Remediation guidance: Sanitize/escape user input before rendering; avoid "
                "dangerouslySetInnerHTML for untrusted data."
            ),
            "status": "Ready for Remediation",
            "components": ["frontend"],
            "labels": ["High", "Reflected-Cross-Site-Scripting-XSS"],
            "comments": [],
        },
    )


_seed()
mount_debug_routes(app, _seed)


class CreateIssueRequest(BaseModel):
    fields: dict[str, Any]


class TransitionRequest(BaseModel):
    transition: dict[str, str]


class CommentRequest(BaseModel):
    body: str


def _issue_to_jira_shape(record: dict) -> dict:
    return {
        "key": record["key"],
        "id": record["key"],
        "self": f"/rest/api/2/issue/{record['key']}",
        "fields": {
            "project": {"key": record["project_key"]},
            "issuetype": {"name": record["issue_type"]},
            "summary": record["summary"],
            "description": record["description"],
            "status": {"name": record["status"]},
            "components": [{"name": c} for c in record["components"]],
            "labels": record["labels"],
        },
    }


@app.post("/rest/api/2/issue", status_code=201)
def create_issue(request: CreateIssueRequest) -> dict:
    fields = request.fields
    key = _issues.next_key()
    record = {
        "key": key,
        "project_key": fields["project"]["key"],
        "issue_type": fields["issuetype"]["name"],
        "summary": fields["summary"],
        "description": fields.get("description", ""),
        "status": "Backlog",
        "components": [c["name"] for c in fields.get("components", [])],
        "labels": fields.get("labels", []),
        "comments": [],
    }
    _issues.put(key, record)
    return {"key": key, "id": key, "self": f"/rest/api/2/issue/{key}"}


@app.get("/rest/api/2/issue/{key}")
def get_issue(key: str) -> dict:
    record = _issues.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Issue {key} not found")
    return _issue_to_jira_shape(record)


@app.put("/rest/api/2/issue/{key}", status_code=204)
def update_issue(key: str, request: CreateIssueRequest) -> None:
    record = _issues.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Issue {key} not found")
    fields = request.fields
    if "summary" in fields:
        record["summary"] = fields["summary"]
    if "description" in fields:
        record["description"] = fields["description"]
    if "components" in fields:
        record["components"] = [c["name"] for c in fields["components"]]
    if "labels" in fields:
        record["labels"] = fields["labels"]
    _issues.put(key, record)


@app.delete("/rest/api/2/issue/{key}", status_code=204)
def delete_issue(key: str) -> None:
    if not _issues.delete(key):
        raise HTTPException(status_code=404, detail=f"Issue {key} not found")


@app.get("/rest/api/2/search")
def search_issues(jql: str = Query(...), maxResults: int = Query(default=50)) -> dict:
    clauses = parse_jql(jql)
    results = []
    for record in _issues.all():
        if "project" in clauses and record["project_key"] != clauses["project"]:
            continue
        if "status" in clauses and record["status"] != clauses["status"]:
            continue
        if "component" in clauses and clauses["component"] not in record["components"]:
            continue
        if "labels" in clauses and clauses["labels"] not in record["labels"]:
            continue
        results.append(_issue_to_jira_shape(record))
    return {"issues": results[:maxResults]}


@app.get("/rest/api/2/issue/{key}/transitions")
def list_transitions(key: str) -> dict:
    record = _issues.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Issue {key} not found")
    transitions = [
        {"id": str(i), "name": status, "to": {"name": status}}
        for i, status in enumerate(WORKFLOW)
        if status != record["status"]
    ]
    return {"transitions": transitions}


@app.post("/rest/api/2/issue/{key}/transitions", status_code=204)
def do_transition(key: str, request: TransitionRequest) -> None:
    record = _issues.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Issue {key} not found")
    transition_id = int(request.transition["id"])
    if transition_id < 0 or transition_id >= len(WORKFLOW):
        raise HTTPException(status_code=400, detail="Unknown transition id")
    record["status"] = WORKFLOW[transition_id]
    _issues.put(key, record)


@app.post("/rest/api/2/issue/{key}/comment", status_code=201)
def add_comment(key: str, request: CommentRequest) -> dict:
    record = _issues.get(key)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Issue {key} not found")
    comment = {"id": str(len(record["comments"]) + 1), "body": request.body}
    record["comments"].append(comment)
    _issues.put(key, record)
    return comment
