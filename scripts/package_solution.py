"""Package tracked source and its real local history, excluding all runtime secrets/data."""
import subprocess
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / "output"
output.mkdir(exist_ok=True)
git = ["git", "-c", f"safe.directory={root.as_posix()}"]
files = subprocess.check_output(git + ["ls-files", "-z"], cwd=root).decode("utf-8").split("\0")
history = subprocess.check_output(git + ["log", "--oneline", "--all"], cwd=root)
bundle = output / "template-workshop-history.bundle"
subprocess.run(git + ["bundle", "create", str(bundle), "--all"], cwd=root, check=True)
archive = output / "Hive_Template_Workshop_Solution.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
    for name in files:
        if name:
            package.write(root / name, name)
    package.write(bundle, "repository-history.bundle")
    package.writestr("GIT_HISTORY.txt", history)
print(f"Packaged {len([f for f in files if f])} source files with local repository history.")
print(archive)
