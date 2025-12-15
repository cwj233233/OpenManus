import os


# 要从操作中排除的文件
EXCLUDED_FILES = {
    ".DS_Store",
    ".gitignore",
    "package-lock.json",
    "postcss.config.js",
    "postcss.config.mjs",
    "jsconfig.json",
    "components.json",
    "tsconfig.tsbuildinfo",
    "tsconfig.json",
}

# 要从操作中排除的目录
EXCLUDED_DIRS = {"node_modules", ".next", "dist", "build", ".git"}

# 要从操作中排除的文件扩展名
EXCLUDED_EXT = {
    ".ico",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".webp",
    ".db",
    ".sql",
}


def should_exclude_file(rel_path: str) -> bool:
    """Check if a file should be excluded based on path, name, or extension

    Args:
        rel_path: Relative path of the file to check

    Returns:
        True if the file should be excluded, False otherwise
    """
    # 检查文件名
    filename = os.path.basename(rel_path)
    if filename in EXCLUDED_FILES:
        return True

    # 检查目录
    dir_path = os.path.dirname(rel_path)
    if any(excluded in dir_path for excluded in EXCLUDED_DIRS):
        return True

    # 检查扩展名
    _, ext = os.path.splitext(filename)
    if ext.lower() in EXCLUDED_EXT:
        return True

    return False


def clean_path(path: str, workspace_path: str = "/workspace") -> str:
    """Clean and normalize a path to be relative to the workspace

    Args:
        path: The path to clean
        workspace_path: The base workspace path to remove (default: "/workspace")

    Returns:
        The cleaned path, relative to the workspace
    """
    # 移除any leading slash
    path = path.lstrip("/")

    # 移除workspace prefix if present
    if path.startswith(workspace_path.lstrip("/")):
        path = path[len(workspace_path.lstrip("/")) :]

    # 移除workspace/ prefix if present
    if path.startswith("workspace/"):
        path = path[9:]

    # 移除any remaining leading slash
    path = path.lstrip("/")

    return path
