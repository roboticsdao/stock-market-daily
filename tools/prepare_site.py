import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
site = root / "_site"
if site.exists():
    shutil.rmtree(site)
site.mkdir()
for pattern in ("*.html", "*.json"):
    for path in root.glob(pattern):
        shutil.copy2(path, site / path.name)
for directory in ("hub", "dexterous-hand-news"):
    source = root / directory
    if not source.exists():
        continue
    for path in source.rglob("*"):
        if path.is_file() and path.suffix in (".html", ".json", ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2"):
            target = site / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
(site / ".nojekyll").touch()
print(f"Prepared {sum(1 for p in site.rglob('*') if p.is_file())} static files")
