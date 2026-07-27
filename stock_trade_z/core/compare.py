import shutil
import subprocess
from pathlib import Path


def open_diff_preview(new_file: Path, old_file: Path):
    """Open a VS Code diff preview between the new file and the old file.

    If `code` is not available, print the command the user can run manually.
    """
    try:
        subprocess.run(["code", "-d", str(new_file), str(old_file)])
    except FileNotFoundError:
        print("'code' command not found. Run the following to preview:")
        print(f"code -d {new_file} {old_file}")


def prompt_and_replace(new_file: Path, old_file: Path) -> bool:
    """Ask the user whether to replace `old_file` with `new_file` (default: yes)."""
    try:
        resp = input(f"Replace sibling '{old_file.name}' with {new_file.name}? [Y/n]: ").strip()
        print("")
    except (EOFError, KeyboardInterrupt):
        print("No input detected; defaulting to yes.")
        resp = ""

    if resp == "" or resp.lower().startswith("y"):
        try:
            shutil.copy2(new_file, old_file)
            print(f"Replaced {old_file} with {new_file.name}")
            return True
        except Exception as e:
            print(f"Failed to replace {old_file}: {e}")
            return False
    else:
        print("Skipped replacing old file")
        return False


def prompt_and_delete(file: Path):
    """Ask the user whether to delete `new_file` (default: yes)."""
    try:
        resp = input(f"Delete file {file}? [Y/n]: ").strip()
        print("")
    except (EOFError, KeyboardInterrupt):
        print("No input detected; defaulting to yes.")
        resp = ""

    if resp == "" or resp.lower().startswith("y"):
        try:
            file.unlink()
            print(f"{file} is deleted")
            return True
        except Exception as e:
            print(f"Failed to delete : {e}")
            return False
    else:
        print("Skipped deletion")
        return False


def compare_with_preview(new_file: Path, old_file: Path):
    if old_file.exists():
        open_diff_preview(new_file, old_file)
        replaced = prompt_and_replace(new_file, old_file)
        if replaced:
            prompt_and_delete(new_file)
    else:
        print(f"Old file not found at {old_file}; skipping preview, copying.")
        shutil.copy2(new_file, old_file)
