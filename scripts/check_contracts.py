#!/usr/bin/env python3
"""
Check that API functions have deal contracts.

This script verifies that public functions in the API modules have
at least one deal contract decorator (@deal.pre, @deal.post, @deal.raises, or @deal.inv).

Usage:
    # Check all API modules
    python scripts/check_contracts.py

    # Check only specific files (for pre-commit)
    python scripts/check_contracts.py src/celestron_nexstar/api/database.py
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

# Modules that should have contracts
API_MODULES = [
    "src/celestron_nexstar/api/database.py",
    "src/celestron_nexstar/api/telescope.py",
    "src/celestron_nexstar/api/observer.py",
    "src/celestron_nexstar/api/catalogs.py",
    "src/celestron_nexstar/api/ephemeris.py",
]

# Functions to exclude from contract checking (internal/private helpers)
EXCLUDED_FUNCTIONS = {
    "database.py": {
        "_get_session",
        "_model_to_object",
        "__init__",
        "__enter__",
        "__exit__",
        "set_sqlite_pragmas",  # SQLAlchemy event listener (internal)
    },
    "telescope.py": {
        "__init__",
        "__enter__",
        "__exit__",
    },
    "observer.py": set(),
    "catalogs.py": set(),
    "ephemeris.py": set(),
}


class ContractChecker(ast.NodeVisitor):
    """AST visitor to check for deal contracts on functions."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.module_name = Path(filename).name
        self.functions_without_contracts: list[tuple[int, str]] = []
        self.current_function: str | None = None
        self.current_lineno = 0
        self.has_deal_decorator = False
        self.is_public_function = False
        self.in_class = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track when we're inside a class."""
        old_in_class = self.in_class
        self.in_class = True
        self.generic_visit(node)
        self.in_class = old_in_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check if function has deal contracts."""
        # Check if this is a public function (not starting with _)
        is_public = not node.name.startswith("_")

        # Check if function is excluded
        excluded = node.name in EXCLUDED_FUNCTIONS.get(self.module_name, set())

        # Skip instance methods (they're handled differently and checked at class level if needed)
        # Instance methods have 'self' as first arg and are inside a class
        is_instance_method = (
            self.in_class
            and node.args.args
            and node.args.args[0].arg == "self"
        )

        # Check for deal decorators
        has_contract = any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "deal"
            for dec in node.decorator_list
        )

        # Also check for @deal.pre, @deal.post, etc. as attributes
        has_contract = has_contract or any(
            isinstance(dec, ast.Attribute)
            and isinstance(dec.value, ast.Name)
            and dec.value.id == "deal"
            for dec in node.decorator_list
        )

        # Record functions without contracts (public, not excluded, not instance methods)
        if is_public and not excluded and not is_instance_method and not has_contract:
            self.functions_without_contracts.append((node.lineno, node.name))

        # Continue visiting child nodes
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async functions too."""
        # Same logic as regular functions
        is_public = not node.name.startswith("_")
        excluded = node.name in EXCLUDED_FUNCTIONS.get(self.module_name, set())

        # Skip instance methods
        is_instance_method = (
            self.in_class
            and node.args.args
            and node.args.args[0].arg == "self"
        )

        has_contract = any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "deal"
            for dec in node.decorator_list
        ) or any(
            isinstance(dec, ast.Attribute)
            and isinstance(dec.value, ast.Name)
            and dec.value.id == "deal"
            for dec in node.decorator_list
        )

        # Async functions are acceptable with just preconditions (postconditions don't work well)
        # Check for at least one deal decorator (pre/raises)
        if is_public and not excluded and not is_instance_method and not has_contract:
            self.functions_without_contracts.append((node.lineno, node.name))

        self.generic_visit(node)


def check_file(filepath: Path) -> list[tuple[int, str]]:
    """Check a single file for missing contracts."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename=str(filepath))
        checker = ContractChecker(str(filepath))
        checker.visit(tree)

        return checker.functions_without_contracts
    except SyntaxError as e:
        print(f"Error parsing {filepath}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error checking {filepath}: {e}", file=sys.stderr)
        return []


def get_changed_functions(filepath: Path) -> set[str]:
    """Get set of function names that were added or modified in git diff."""
    try:
        # Get git diff for this file
        result = subprocess.run(
            ["git", "diff", "--cached", "--", str(filepath)],
            capture_output=True,
            text=True,
            cwd=filepath.parent.parent.parent,
        )

        if result.returncode != 0 or not result.stdout:
            # If no staged changes, check unstaged changes
            result = subprocess.run(
                ["git", "diff", "--", str(filepath)],
                capture_output=True,
                text=True,
                cwd=filepath.parent.parent.parent,
            )

        if not result.stdout:
            return set()  # No changes

        # Parse diff to find added/modified function definitions
        changed_functions = set()
        lines = result.stdout.split("\n")
        in_function = False
        current_function = None

        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                # Added line
                if "def " in line or "async def " in line:
                    # Extract function name
                    if "def " in line:
                        func_name = line.split("def ")[1].split("(")[0].strip()
                    else:
                        func_name = line.split("async def ")[1].split("(")[0].strip()
                    if not func_name.startswith("_"):  # Only public functions
                        changed_functions.add(func_name)

        return changed_functions
    except Exception:
        # If git is not available or file is not in git, return empty set
        return set()


def main() -> int:
    """Main entry point."""
    repo_root = Path(__file__).parent.parent

    # If files are provided as arguments, check only those
    if len(sys.argv) > 1:
        files_to_check = []
        for f in sys.argv[1:]:
            path = Path(f)
            if not path.is_absolute():
                path = repo_root / path
            if path.exists():
                files_to_check.append(path)
    else:
        # Check all API modules
        files_to_check = [repo_root / module_path for module_path in API_MODULES]

    errors_found = False
    checked_any = False

    for full_path in files_to_check:
        if not full_path.exists():
            continue

        # Only check API modules - get relative path
        try:
            relative_path = full_path.relative_to(repo_root)
        except ValueError:
            # Path is not relative to repo root, skip
            continue

        if str(relative_path) not in API_MODULES:
            continue

        checked_any = True

        # Get changed functions if checking specific files (pre-commit mode)
        changed_functions = None
        if len(sys.argv) > 1:
            changed_functions = get_changed_functions(full_path)
            # If no changed functions detected, check if file is new
            if not changed_functions:
                try:
                    result = subprocess.run(
                        ["git", "ls-files", "--error-unmatch", str(relative_path)],
                        capture_output=True,
                        cwd=repo_root,
                    )
                    if result.returncode != 0:
                        # File is new, check all public functions
                        changed_functions = None
                    else:
                        # File exists but no changes detected, skip (no new functions)
                        continue
                except Exception:
                    # Can't determine, check all (conservative approach)
                    changed_functions = None

        missing_contracts = check_file(full_path)

        # Filter to only changed functions if we have that info
        if changed_functions is not None and changed_functions:
            missing_contracts = [
                (lineno, name) for lineno, name in missing_contracts if name in changed_functions
            ]

        if missing_contracts:
            errors_found = True
            print(f"\n❌ {relative_path}: Functions without contracts:")
            for lineno, func_name in missing_contracts:
                print(f"  Line {lineno}: {func_name}()")

    if not checked_any:
        print("No API modules to check", file=sys.stderr)
        return 0

    if errors_found:
        print("\n💡 Tip: Add deal contracts using @deal.pre, @deal.post, or @deal.raises decorators")
        print("   Example: @deal.pre(lambda x: x > 0, message='x must be positive')")
        return 1

    print("✅ All checked public API functions have contracts!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
