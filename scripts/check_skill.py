"""Dependency-free packaging check: skill frontmatter, launcher, and local Markdown links resolve."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from research_relay.links import markdown_links  # noqa: E402

skill = root / "skills/research-relay"
text = (skill / "SKILL.md").read_text()
assert text.startswith("---\nname: research-relay\ndescription: "), "SKILL.md frontmatter"
assert len(text.split("---", 2)) == 3, "SKILL.md frontmatter is not closed"
assert (skill / "scripts/relay.py").is_file(), "launcher missing"
for name in ("convention.md", "autoresearch.md", "codex.md", "claude-code.md"):
    assert (skill / "references" / name).is_file(), f"references/{name} missing"
# Only this skill's shipped resources are checked; research notes have no imposed shape.
broken = []
for file in [root / "README.md", *sorted(skill.rglob("*.md"))]:
    for link in markdown_links(file.read_text()):
        href = link["href"].split("#")[0]
        if href and "://" not in href and not (file.parent / href).exists():
            broken.append(f"{file.relative_to(root)}:{link['line']} -> {link['href']}")
assert not broken, "broken links:\n" + "\n".join(broken)
print("Skill metadata, launcher and local Markdown links: OK (static checks only)")
