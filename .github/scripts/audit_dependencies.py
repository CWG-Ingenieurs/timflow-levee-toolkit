"""Process a pip-audit report for the security workflow (.github/workflows/security.yml).

Usage: python audit_dependencies.py <pip-audit.json> <pyproject.toml> <report.md>

- Keeps only vulnerabilities in packages the toolkit depends on (directly or indirectly,
  with all extras), so tools in the environment such as pip are left out.
- For a direct dependency with a fixed version, raises the minimum version in pyproject.toml.
- Writes a Markdown report and sets the step outputs 'vulnerable' and 'changed'.
"""
import json
import os
import re
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

PACKAGE = "timflow_levee_toolkit"


def dependency_tree(package):
    """Names of all packages `package` depends on, with all of its extras."""
    seen = {}
    todo = [(package, set(metadata.metadata(package).get_all("Provides-Extra") or []), None)]
    while todo:
        name, extras, parent = todo.pop()
        key = canonicalize_name(name)
        if key in seen:
            continue
        seen[key] = parent
        try:
            requires = metadata.requires(name) or []
        except metadata.PackageNotFoundError:
            continue
        for line in requires:
            req = Requirement(line)
            if req.marker and not any(req.marker.evaluate({"extra": e}) for e in (extras or {""})):
                continue
            todo.append((req.name, set(req.extras), key))
    seen.pop(canonicalize_name(package))
    return seen


def direct_requirements(pyproject_text):
    """Requirement strings in pyproject.toml: dependencies and optional dependencies."""
    return {canonicalize_name(Requirement(r).name): r for r in re.findall(r'^\s+"([^"]+)",?', pyproject_text, re.M)
            if re.match(r"^[A-Za-z0-9]", r)}


def raise_minimum(requirement, version):
    """'timflow[lmfit]>=0.5' + 1.2 -> 'timflow[lmfit]>=1.2' (other specifiers dropped)."""
    req = Requirement(requirement)
    extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    marker = f"; {req.marker}" if req.marker else ""
    return f"{req.name}{extras}>={version}{marker}"


def main(audit_file, pyproject_file, report_file):
    audit = json.loads(Path(audit_file).read_text(encoding="utf-8"))
    pyproject = Path(pyproject_file)
    text = pyproject.read_text(encoding="utf-8")
    tree = dependency_tree(PACKAGE)
    direct = direct_requirements(text)

    rows, bumps = [], {}
    for dep in audit.get("dependencies", []):
        key = canonicalize_name(dep["name"])
        if key not in tree or not dep.get("vulns"):
            continue
        for vuln in dep["vulns"]:
            fixes = sorted(vuln.get("fix_versions") or [], key=Version)
            fixed = next((f for f in fixes if Version(f) > Version(dep["version"])), None)
            via = "direct" if key in direct else f"via {tree[key]}"
            ids = ", ".join([vuln["id"], *vuln.get("aliases", [])])
            rows.append(f"| {dep['name']} | {dep['version']} | {via} | {ids} | {fixed or 'no fix yet'} |")
            if fixed and key in direct:
                bumps[key] = max(bumps.get(key, fixed), fixed, key=Version)

    for key, version in bumps.items():
        old = direct[key]
        text = text.replace(f'"{old}"', f'"{raise_minimum(old, version)}"')
    if bumps:
        pyproject.write_text(text, encoding="utf-8")

    lines = []
    if rows:
        lines += ["Vulnerabilities in the dependencies of the toolkit (pip-audit):", "",
                  "| Package | Installed | Dependency | Vulnerability | Fixed in |", "|---|---|---|---|---|", *rows, ""]
        if bumps:
            lines += ["Minimum versions raised in `pyproject.toml`:", ""]
            lines += [f"- `{direct[k]}` → `{raise_minimum(direct[k], v)}`" for k, v in bumps.items()]
            lines += [""]
        if any("no fix yet" in r or "| via " in r for r in rows):
            lines += ["Indirect dependencies and vulnerabilities without a fix are not changed automatically: "
                      "check whether the vulnerable code is used, and update when a fixed version is released."]
    else:
        lines = ["No known vulnerabilities in the dependencies of the toolkit."]
    Path(report_file).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as out:
        out.write(f"vulnerable={'true' if rows else 'false'}\n")
        out.write(f"changed={'true' if bumps else 'false'}\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
