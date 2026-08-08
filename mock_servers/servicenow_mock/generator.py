import random
from datetime import UTC, datetime, timedelta

from faker import Faker

from .vuln_catalog import CATALOG, CatalogEntry

SCANNERS = ["Checkmarx", "Snyk", "Tenable", "Qualys", "OWASP ZAP", "Semgrep"]
PARAM_NAMES = ["q", "search", "redirect", "callback", "userId", "token", "next", "id", "sort"]
PRIORITIES = ["1 - Critical", "2 - High", "3 - Moderate", "4 - Low"]
APP_CODE_EXTENSIONS = ["js", "jsx", "ts", "json"]
INFRA_CODE_EXTENSIONS = ["tf"]


def _priority_for_severity(severity: str) -> str:
    return {
        "Critical": PRIORITIES[0],
        "High": PRIORITIES[1],
        "Medium": PRIORITIES[2],
        "Low": PRIORITIES[3],
    }.get(severity, PRIORITIES[2])


def _render(entry: CatalogEntry, fake: Faker) -> dict:
    endpoint = "/" + "/".join(fake.uri_path().split("/")[:3])
    extensions = INFRA_CODE_EXTENSIONS if entry["component"] == "infra-config" else APP_CODE_EXTENSIONS
    file_path = fake.file_path(depth=2, extension=random.choice(extensions))
    param = random.choice(PARAM_NAMES)
    ctx = {"endpoint": endpoint, "file": file_path, "param": param}

    cvss = round(random.uniform(*entry["cvss_range"]), 1)
    discovered = datetime.now(UTC) - timedelta(days=random.randint(0, 30))

    return {
        "sys_id": fake.uuid4(),
        "number": f"AVIT{fake.unique.random_number(digits=7, fix_len=True)}",
        "short_description": entry["short_description"].format(**ctx),
        "description": entry["description"].format(**ctx)
        + f"\n\nRemediation guidance: {entry['remediation_hint']}",
        "severity": entry["severity"],
        "cvss_score": cvss,
        "vuln_type": entry["vuln_type"],
        "cwe_id": entry["cwe_id"],
        "affected_component": entry["component"],
        "affected_url_or_file": (
            file_path if entry["component"] == "infra-config" or random.random() >= 0.6 else endpoint
        ),
        "source_scanner": random.choice(SCANNERS),
        "discovered_at": discovered.isoformat(),
        "priority": _priority_for_severity(entry["severity"]),
    }


def generate_tickets(count: int = 8, seed: int | None = None, demo_relevant_only: bool = False) -> list[dict]:
    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    pool = [e for e in CATALOG if e["demo_relevant"]] if demo_relevant_only else CATALOG
    entries = random.choices(pool, k=count)
    return [_render(entry, fake) for entry in entries]
