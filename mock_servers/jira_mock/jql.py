import re

_CLAUSE_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|(\S+))')


def parse_jql(jql: str) -> dict[str, str]:
    """Supports a tiny subset of JQL: `field = value` or `field = "quoted value"`
    clauses joined by AND (case-insensitive). Enough for the one status/project/
    component/label filters this project's connectors actually issue."""
    clauses: dict[str, str] = {}
    for part in re.split(r"\bAND\b", jql, flags=re.IGNORECASE):
        part = part.strip()
        if not part:
            continue
        match = _CLAUSE_RE.match(part)
        if not match:
            continue
        field = match.group(1).lower()
        value = match.group(2) if match.group(2) is not None else match.group(3)
        clauses[field] = value
    return clauses
