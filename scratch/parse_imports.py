import os
import ast
import sys

def get_imported_modules(dir_path):
    imports = set()
    for root, _, files in os.walk(dir_path):
        if "scratch" in root or "tests" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        node = ast.parse(f.read(), filename=file_path)
                    for child in ast.walk(node):
                        if isinstance(child, ast.Import):
                            for alias in child.names:
                                imports.add(alias.name.split('.')[0])
                        elif isinstance(child, ast.ImportFrom):
                            if child.level == 0 and child.module:
                                imports.add(child.module.split('.')[0])
                except Exception as e:
                    print(f"Error parsing {file_path}: {e}")
    return imports

if __name__ == "__main__":
    app_dir = r"c:\Users\golu\Desktop\freightforce.ai\backend\app"
    imported = get_imported_modules(app_dir)
    print("All top-level modules imported in application:")
    # Filter standard library
    std_libs = set(sys.builtin_module_names) | set(dir(sys)) | {
        "os", "sys", "re", "json", "math", "datetime", "time", "uuid", "typing", "collections",
        "functools", "logging", "asyncio", "socket", "contextlib", "secrets", "traceback", "mimetypes",
        "base64", "hashlib", "hmac", "tempfile", "shutil", "urllib", "copy", "csv", "inspect"
    }
    third_party = [imp for imp in imported if imp not in std_libs and imp != "app"]
    print(third_party)
