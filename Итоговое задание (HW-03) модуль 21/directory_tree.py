import os
from pathlib import Path


def print_project_structure(startpath='.', exclude_dirs=['__pycache__', 'migrations', '.git'], exclude_ext=['.pyc']):
    """Печатает древовидную структуру проекта"""
    for root, dirs, files in os.walk(startpath):
        # Исключаем ненужные директории
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")

        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if not any(file.endswith(ext) for ext in exclude_ext):
                print(f"{subindent}{file}")


if __name__ == "__main__":
    print("📁 Структура проекта News Portal:")
    print("=" * 50)
    print_project_structure()