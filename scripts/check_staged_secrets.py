"""Fail before publishing if staged content contains recognizable credentials.

Reports paths only, never matching secrets. Defense in depth, not a universal scan.
"""
import re
import subprocess

PATTERN = re.compile(rb"sk-or-v1-[a-zA-Z0-9]{20,}|(?:gh[pousr]_|github_pat_)[a-zA-Z0-9_]{20,}|hf_[a-zA-Z0-9]{20,}|rpa_[a-zA-Z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
paths = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"]).split(b"\0")
bad = []
for raw in filter(None, paths):
    path = raw.decode("utf-8")
    content = subprocess.check_output(["git", "show", ":" + path])
    if (PATTERN.search(content)
        or path.startswith(('runs/', 'Reference/', '_local_archive/', 'models/'))
        or path == 'AGENTS.md'
        or (path.rsplit("/", 1)[-1].startswith(".env") and not path.endswith(".env.example"))):
        bad.append(path)
if bad:
    raise SystemExit("Credential-like content or local env file staged: " + ", ".join(bad))
print("Staged credential scan passed (no secret values displayed).")
