"""Dependency-free packaging/link check; this is not a behavioral skill evaluation."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
skill = root / "skills/research-relay"
text = (skill / "SKILL.md").read_text()
assert text.startswith("---\nname: research-relay\ndescription: ")
assert len(text.split("---", 2)) == 3
assert (skill / "scripts/relay.py").is_file()
for file in [*skill.rglob("*.md"), *(root / "examples").rglob("*.md")]:
    for target in re.findall(r"\]\(([^)]+)\)", file.read_text()):
        if not target.startswith(("http:", "https:", "#")):
            assert (file.parent / target.split("#")[0]).exists(), (file, target)
print("Skill metadata, launcher and local Markdown links: OK (static checks only)")
