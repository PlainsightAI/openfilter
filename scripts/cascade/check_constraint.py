"""Check openfilter version constraint compatibility.

Reads OF_VERSION from env, scans pyproject.toml for openfilter dependency.
Outputs: none | ok:<spec> | skip:<spec> | error:<msg>
"""
import sys, os, tomllib

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

try:
    if not os.path.exists("pyproject.toml"):
        print("none")
        sys.exit(0)
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = list(data.get("project", {}).get("dependencies", []))
    for g in data.get("project", {}).get("optional-dependencies", {}).values():
        deps.extend(g)
    req = None
    for d in deps:
        r = Requirement(d)
        if r.name == "openfilter":
            req = r
            break
    if req is None:
        print("none")
        sys.exit(0)
    if not req.specifier:
        print("ok:")
        sys.exit(0)
    v_str = os.environ.get("OF_VERSION", "")
    if not v_str:
        print("error:OF_VERSION not set")
        sys.exit(0)
    v = Version(v_str)
    spec = str(req.specifier)
    print(("ok:" if v in req.specifier else "skip:") + spec)
except Exception as e:
    print("error:" + str(e))
