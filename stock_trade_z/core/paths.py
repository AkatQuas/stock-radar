from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _PKG_DIR.parent


def get_package_dir() -> Path:
    """Application package directory (``stock_trade_z/``)."""
    return _PKG_DIR


def get_project_root() -> Path:
    """Repository root (parent of the application package)."""
    return _ROOT_DIR


def get_file_in_pack(*path_segments: str | Path) -> Path:
    """Resolve paths relative to the application package directory."""
    combined_path = _PKG_DIR
    for segment in path_segments:
        combined_path = combined_path / segment

    return combined_path.resolve()


def get_config_path(*path_segments: str | Path) -> Path:
    """Resolve paths relative to ``config/`` at the project root."""
    combined_path = _ROOT_DIR / "config"
    for segment in path_segments:
        combined_path = combined_path / segment

    return combined_path.resolve()


# Backward-compatible alias
get_script_parent_folder_path = get_package_dir


if __name__ == "__main__":
    print(get_file_in_pack("stocklist.total.csv"))
