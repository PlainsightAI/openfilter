"""Check openfilter version constraint compatibility.

Reads OF_VERSION from env, scans pyproject.toml for openfilter dependency.
Outputs: none | ok:<spec> | skip:<spec> | error:<msg>
"""
import tomllib, re, sys, os

try:
    if not os.path.exists("pyproject.toml"):
        print("none")
        sys.exit(0)
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = list(data.get("project", {}).get("dependencies", []))
    for g in data.get("project", {}).get("optional-dependencies", {}).values():
        deps.extend(g)
    found = False
    c = ""
    for d in deps:
        if d.strip().startswith("openfilter"):
            found = True
            m = re.match(r"openfilter(?:\[[^\]]*\])?\s*(.*)", d.strip())
            if m and m.group(1):
                c = m.group(1)
            break
    if not found:
        print("none")
        sys.exit(0)
    if not c:
        print("ok:")
        sys.exit(0)
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version
    v_str = os.environ.get("OF_VERSION", "")
    if not v_str:
        print("error:OF_VERSION not set")
        sys.exit(0)
    s = SpecifierSet(c)
    v = Version(v_str)
    print(("ok:" if v in s else "skip:") + str(c))
except Exception as e:
    print("error:" + str(e))
