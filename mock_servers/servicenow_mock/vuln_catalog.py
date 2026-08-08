"""Curated catalog of common web-app/config vulnerability types, used to generate
synthetic AVIT (application-vulnerability) ServiceNow findings. Entries flagged
demo_relevant=True correspond to a vulnerability actually seeded in
scaffold/vulnerable-react-demo-app, so the v1 end-to-end walkthrough can filter for
those specifically; the rest just give the mock realistic variety.
"""

from typing import TypedDict


class CatalogEntry(TypedDict):
    vuln_type: str
    cwe_id: str
    cvss_range: tuple[float, float]
    severity: str
    short_description: str
    description: str
    remediation_hint: str
    component: str
    demo_relevant: bool


CATALOG: list[CatalogEntry] = [
    {
        "vuln_type": "Reflected Cross-Site Scripting (XSS)",
        "cwe_id": "CWE-79",
        "cvss_range": (6.1, 7.5),
        "severity": "High",
        "short_description": "Reflected XSS in {endpoint} via '{param}' parameter",
        "description": (
            "User-supplied input from the '{param}' query parameter on {endpoint} is rendered "
            "into the page (via dangerouslySetInnerHTML) without sanitization or output encoding, "
            "allowing an attacker to execute arbitrary JavaScript in a victim's browser via a "
            "crafted link."
        ),
        "remediation_hint": (
            "Sanitize/escape user input before rendering; avoid dangerouslySetInnerHTML for untrusted data."
        ),
        "component": "frontend",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Hardcoded API Key",
        "cwe_id": "CWE-798",
        "cvss_range": (7.0, 8.6),
        "severity": "High",
        "short_description": "Hardcoded API key committed in {file}",
        "description": (
            "A live-looking API key/secret is hardcoded directly in {file} and committed to source "
            "control, exposing it to anyone with repo access and to the public if the repo is or "
            "becomes public."
        ),
        "remediation_hint": (
            "Move the secret to an environment variable / secrets manager and rotate the exposed key."
        ),
        "component": "frontend",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Missing Security Headers",
        "cwe_id": "CWE-693",
        "cvss_range": (4.3, 5.9),
        "severity": "Medium",
        "short_description": "Missing security headers (CSP/HSTS/X-Frame-Options) on {endpoint}",
        "description": (
            "Responses from {endpoint} do not set Content-Security-Policy, Strict-Transport-Security, "
            "or X-Frame-Options headers, weakening protection against XSS, protocol downgrade, and "
            "clickjacking attacks."
        ),
        "remediation_hint": (
            "Add the helmet middleware (or equivalent) to set standard security headers on all responses."
        ),
        "component": "backend-api",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Insecure Session Cookie Configuration",
        "cwe_id": "CWE-614",
        "cvss_range": (5.3, 6.5),
        "severity": "Medium",
        "short_description": "Session cookie missing Secure/HttpOnly/SameSite flags on {endpoint}",
        "description": (
            "The session cookie set by {endpoint} is missing the Secure, HttpOnly, and SameSite "
            "attributes, making it accessible to client-side scripts and susceptible to transmission "
            "over unencrypted connections or in cross-site requests."
        ),
        "remediation_hint": "Set httpOnly, secure, and sameSite on the session cookie configuration.",
        "component": "backend-api",
        "demo_relevant": True,
    },
    {
        "vuln_type": "CORS Misconfiguration",
        "cwe_id": "CWE-942",
        "cvss_range": (6.5, 8.1),
        "severity": "High",
        "short_description": "Overly permissive CORS policy (wildcard origin + credentials) on {endpoint}",
        "description": (
            "{endpoint} responds with Access-Control-Allow-Origin: * combined with "
            "Access-Control-Allow-Credentials: true, which most browsers will reject but which "
            "indicates a fundamentally unsafe CORS configuration allowing any origin to make "
            "credentialed requests once corrected to a reflected origin."
        ),
        "remediation_hint": (
            "Restrict allowed origins to a known allowlist; never combine wildcard origin with credentials."
        ),
        "component": "backend-api",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Outdated Dependency with Known CVE",
        "cwe_id": "CWE-1104",
        "cvss_range": (7.5, 9.1),
        "severity": "Critical",
        "short_description": "Outdated dependency '{param}' with known CVE in {file}",
        "description": (
            "{file} pins '{param}' at a version with a publicly disclosed CVE. Continuing to run "
            "this version exposes the application to the vulnerability the newer release patches."
        ),
        "remediation_hint": "Upgrade the dependency to a patched version and re-run the dependency audit.",
        "component": "backend-api",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Verbose Error / Stack Trace Disclosure",
        "cwe_id": "CWE-209",
        "cvss_range": (4.3, 5.3),
        "severity": "Medium",
        "short_description": "Stack trace disclosure in error responses from {endpoint}",
        "description": (
            "Unhandled errors on {endpoint} return the raw stack trace and internal file paths to "
            "the client, which can help an attacker map the application's internals."
        ),
        "remediation_hint": (
            "Use a generic error handler in production that logs details server-side "
            "and returns a minimal response."
        ),
        "component": "backend-api",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Stored Cross-Site Scripting (XSS)",
        "cwe_id": "CWE-79",
        "cvss_range": (7.2, 8.8),
        "severity": "High",
        "short_description": "Stored XSS via '{param}' field persisted from {endpoint}",
        "description": (
            "Input submitted to the '{param}' field via {endpoint} is stored and later rendered to "
            "other users without sanitization, allowing a persistent XSS payload."
        ),
        "remediation_hint": (
            "Sanitize on write or encode on render; consider a strict CSP as defense in depth."
        ),
        "component": "backend-api",
        "demo_relevant": False,
    },
    {
        "vuln_type": "DOM-based Cross-Site Scripting (XSS)",
        "cwe_id": "CWE-79",
        "cvss_range": (6.1, 7.5),
        "severity": "High",
        "short_description": "DOM-based XSS via location.hash on {endpoint}",
        "description": (
            "Client-side script on {endpoint} reads a URL fragment and inserts it into the DOM "
            "without sanitization, allowing script execution purely on the client side."
        ),
        "remediation_hint": (
            "Avoid unsanitized DOM sinks (innerHTML, document.write) with untrusted URL data."
        ),
        "component": "frontend",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Cross-Site Request Forgery (CSRF)",
        "cwe_id": "CWE-352",
        "cvss_range": (5.4, 6.8),
        "severity": "Medium",
        "short_description": "Missing CSRF protection on state-changing endpoint {endpoint}",
        "description": (
            "{endpoint} performs a state-changing action based solely on session cookies with no "
            "anti-CSRF token, allowing a malicious site to trigger the action on behalf of a "
            "logged-in user."
        ),
        "remediation_hint": (
            "Add anti-CSRF tokens (or SameSite=Strict cookies plus origin checks) to state-changing routes."
        ),
        "component": "backend-api",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Insecure Direct Object Reference (IDOR)",
        "cwe_id": "CWE-639",
        "cvss_range": (6.5, 8.2),
        "severity": "High",
        "short_description": "IDOR on {endpoint} allows access to other users' records via '{param}'",
        "description": (
            "{endpoint} returns a resource looked up directly by the '{param}' identifier without "
            "verifying the requesting user owns that resource, allowing enumeration of other users' data."
        ),
        "remediation_hint": (
            "Add an authorization check that the resource belongs to the authenticated "
            "user before returning it."
        ),
        "component": "auth",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Server-Side Request Forgery (SSRF)",
        "cwe_id": "CWE-918",
        "cvss_range": (7.5, 9.0),
        "severity": "Critical",
        "short_description": "SSRF via '{param}' URL parameter on {endpoint}",
        "description": (
            "{endpoint} fetches a server-side resource from a URL supplied in the '{param}' "
            "parameter without validating the target host, allowing requests to internal/metadata "
            "endpoints."
        ),
        "remediation_hint": "Validate/allowlist target hosts and block requests to internal IP ranges.",
        "component": "backend-api",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Open Redirect",
        "cwe_id": "CWE-601",
        "cvss_range": (4.7, 6.1),
        "severity": "Medium",
        "short_description": "Open redirect via '{param}' on {endpoint}",
        "description": (
            "{endpoint} redirects to a URL taken directly from the '{param}' parameter without "
            "validating it is a same-site destination, which can be used in phishing campaigns."
        ),
        "remediation_hint": "Validate the redirect target against an allowlist of known-safe paths/hosts.",
        "component": "frontend",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Directory Listing Enabled",
        "cwe_id": "CWE-548",
        "cvss_range": (5.0, 6.0),
        "severity": "Medium",
        "short_description": "Directory listing enabled under {endpoint}",
        "description": (
            "The static file server exposes directory listings under {endpoint}, revealing file "
            "names and structure that should not be publicly browsable."
        ),
        "remediation_hint": "Disable autoindex/directory listing in the static file server configuration.",
        "component": "infra-config",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Weak Session Expiration",
        "cwe_id": "CWE-613",
        "cvss_range": (4.0, 5.4),
        "severity": "Medium",
        "short_description": "Session tokens issued by {endpoint} do not expire",
        "description": (
            "Session tokens issued by {endpoint} have no expiration and remain valid indefinitely, "
            "increasing the impact of a leaked token."
        ),
        "remediation_hint": (
            "Set a reasonable session/token expiration and enforce re-authentication after it."
        ),
        "component": "auth",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Clickjacking",
        "cwe_id": "CWE-1021",
        "cvss_range": (4.3, 5.4),
        "severity": "Medium",
        "short_description": "Page at {endpoint} can be framed by third-party sites",
        "description": (
            "{endpoint} does not restrict framing (no X-Frame-Options / frame-ancestors CSP "
            "directive), allowing the page to be embedded in a malicious iframe for "
            "UI-redress attacks."
        ),
        "remediation_hint": "Set X-Frame-Options: DENY or a frame-ancestors CSP directive.",
        "component": "infra-config",
        "demo_relevant": False,
    },
    {
        "vuln_type": "Unrestricted File Upload",
        "cwe_id": "CWE-434",
        "cvss_range": (7.0, 8.6),
        "severity": "High",
        "short_description": "Unrestricted file upload on {endpoint}",
        "description": (
            "{endpoint} accepts file uploads with no validation of file type, size, or content, "
            "allowing an attacker to upload executable or oversized files."
        ),
        "remediation_hint": (
            "Validate file type/size server-side and store uploads outside the web root "
            "with randomized names."
        ),
        "component": "backend-api",
        "demo_relevant": False,
    },
    {
        "vuln_type": "S3 Bucket Publicly Accessible",
        "cwe_id": "CWE-284",
        "cvss_range": (7.1, 8.6),
        "severity": "High",
        "short_description": "S3 bucket has a public-read ACL with no block-public-access in {file}",
        "description": (
            "The S3 bucket defined in {file} is configured with a public-read ACL and has no "
            "aws_s3_bucket_public_access_block resource guarding it, exposing its contents to "
            "anyone on the internet."
        ),
        "remediation_hint": (
            "Remove the public-read ACL, add an aws_s3_bucket_public_access_block resource "
            "blocking all public access, and serve content via CloudFront with origin access "
            "control instead of a public bucket."
        ),
        "component": "infra-config",
        "demo_relevant": True,
    },
    {
        "vuln_type": "S3 Bucket Missing Server-Side Encryption",
        "cwe_id": "CWE-311",
        "cvss_range": (4.9, 6.5),
        "severity": "Medium",
        "short_description": "S3 bucket has no server-side encryption configured in {file}",
        "description": (
            "The S3 bucket defined in {file} has no server-side encryption configuration, "
            "leaving data at rest unencrypted."
        ),
        "remediation_hint": (
            "Add an aws_s3_bucket_server_side_encryption_configuration resource enabling SSE "
            "(AES256 or a customer-managed KMS key)."
        ),
        "component": "infra-config",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Security Group Allows Unrestricted SSH Access",
        "cwe_id": "CWE-284",
        "cvss_range": (8.1, 9.8),
        "severity": "Critical",
        "short_description": "Security group allows SSH from 0.0.0.0/0 in {file}",
        "description": (
            "The security group defined in {file} allows inbound TCP port 22 (SSH) from "
            "0.0.0.0/0, exposing the host to SSH access attempts from anywhere on the internet."
        ),
        "remediation_hint": (
            "Restrict SSH ingress to a known CIDR range (VPN/bastion), or remove direct SSH "
            "access entirely in favor of SSM Session Manager."
        ),
        "component": "infra-config",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Overly Permissive IAM Policy",
        "cwe_id": "CWE-732",
        "cvss_range": (8.6, 9.8),
        "severity": "Critical",
        "short_description": "IAM policy grants wildcard Action and Resource in {file}",
        "description": (
            'The IAM policy defined in {file} grants Action "*" on Resource "*", giving the '
            "attached role full access to every action on every resource in the account."
        ),
        "remediation_hint": (
            "Scope the policy's Action and Resource lists to only the specific permissions the "
            "role actually needs (least privilege)."
        ),
        "component": "infra-config",
        "demo_relevant": True,
    },
    {
        "vuln_type": "Hardcoded Secret in Terraform Variable Default",
        "cwe_id": "CWE-798",
        "cvss_range": (7.0, 8.6),
        "severity": "High",
        "short_description": "Hardcoded secret default value in {file}",
        "description": (
            "A Terraform variable in {file} has a live-looking secret hardcoded as its default "
            "value and is not marked sensitive, exposing it in source control, plan output, and "
            "state files."
        ),
        "remediation_hint": (
            "Remove the hardcoded default, mark the variable sensitive = true, and source the "
            "real value from a secrets manager (AWS Secrets Manager / SSM Parameter Store) at "
            "apply time."
        ),
        "component": "infra-config",
        "demo_relevant": True,
    },
]
