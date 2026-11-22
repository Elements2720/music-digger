"""Automated enforcement of the domain dependency rule.

The domain layer may import only the Python standard library. It may not import
outer layers, frameworks, ML libraries, storage clients, HTTP clients, or
dynamic-import helpers. Intra-domain imports must be relative and may not
escape the ``domain`` package.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

DOMAIN_ROOT = Path(__file__).resolve().parents[2] / "src" / "domain"
SRC_ROOT = DOMAIN_ROOT.parent

FORBIDDEN_ROOTS = frozenset(
    {
        # Outer layers / composition
        "backend",
        "container",
        "data",
        "presentation",
        "src",
        # Web / HTTP / serialization
        "aiohttp",
        "fastapi",
        "httpx",
        "pydantic",
        "requests",
        "starlette",
        "urllib3",
        "http",
        "urllib",
        "socket",
        "ssl",
        # ML / audio
        "aubio",
        "essentia",
        "huggingface_hub",
        "librosa",
        "madmom",
        "numpy",
        "pandas",
        "scipy",
        "soundfile",
        "torch",
        "torchaudio",
        "transformers",
        # Storage
        "alembic",
        "lancedb",
        "pyarrow",
        "sqlalchemy",
        "sqlite3",
        # Integrations / dynamic imports
        "dotenv",
        "importlib",
        "mutagen",
        "pkgutil",
        "runpy",
        "yt_dlp",
    }
)

ALLOWED_ROOTS = frozenset(sys.stdlib_module_names) - FORBIDDEN_ROOTS


def domain_python_files() -> list[Path]:
    return sorted(DOMAIN_ROOT.rglob("*.py"))


def find_import_violations(
    source: str,
    *,
    filename: str = "<unknown>",
    package_depth: int | None = None,
) -> list[str]:
    """Return human-readable violations found in ``source``.

    ``package_depth`` is the number of package levels between the file and the
    repository source root. For ``domain/entities/track.py`` it is 2, so
    ``from ...data import X`` (level 3) is flagged as escaping the domain.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root not in ALLOWED_ROOTS:
                    violations.append(
                        f"{filename}:{node.lineno}: forbidden import {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if package_depth is not None and node.level > package_depth:
                    violations.append(
                        f"{filename}:{node.lineno}: relative import escapes the domain package"
                    )
                continue
            if node.module is None:
                violations.append(
                    f"{filename}:{node.lineno}: malformed absolute import"
                )
                continue
            root = node.module.split(".", 1)[0]
            if root not in ALLOWED_ROOTS:
                violations.append(
                    f"{filename}:{node.lineno}: forbidden import from {node.module!r}"
                )
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id == "__import__":
                violations.append(
                    f"{filename}:{node.lineno}: dynamic __import__ is forbidden"
                )
            elif isinstance(function, ast.Attribute) and function.attr in {
                "__import__",
                "import_module",
            }:
                violations.append(
                    f"{filename}:{node.lineno}: dynamic import via {function.attr!r} is forbidden"
                )

    return violations


def test_domain_package_exists_and_has_modules() -> None:
    assert DOMAIN_ROOT.is_dir()
    files = domain_python_files()
    assert len(files) >= 10
    assert (DOMAIN_ROOT / "value_objects" / "audio_features.py").is_file()
    assert (DOMAIN_ROOT / "entities" / "track.py").is_file()
    assert (DOMAIN_ROOT / "interfaces" / "llm.py").is_file()


@pytest.mark.parametrize(
    "path",
    domain_python_files(),
    ids=lambda path: path.relative_to(DOMAIN_ROOT).as_posix(),
)
def test_domain_module_imports_only_the_standard_library(path: Path) -> None:
    relative = path.relative_to(DOMAIN_ROOT)
    violations = find_import_violations(
        path.read_text(encoding="utf-8"),
        filename=str(relative),
        package_depth=len(relative.parts),
    )
    assert not violations, "\n".join(violations)


def test_checker_detects_absolute_outer_layer_and_forbidden_stdlib_imports() -> None:
    source = """
import os
import numpy as np
from data.repositories import SqliteTrackRepository
from presentation.api import app
import sqlite3
from .local import helper
"""
    violations = find_import_violations(source, package_depth=2)
    assert len(violations) == 4
    assert any("numpy" in violation for violation in violations)
    assert any("data.repositories" in violation for violation in violations)
    assert any("presentation.api" in violation for violation in violations)
    assert any("sqlite3" in violation for violation in violations)


def test_checker_detects_relative_imports_that_escape_the_domain() -> None:
    source = "from ...data import SqliteTrackRepository\nfrom .local import helper\n"
    violations = find_import_violations(source, package_depth=2)
    assert len(violations) == 1
    assert "escapes the domain" in violations[0]


def test_checker_detects_dynamic_imports() -> None:
    source = """
__import__("torch")
importlib.import_module("numpy")
"""
    violations = find_import_violations(source)
    assert len(violations) == 2
    assert all("dynamic" in violation for violation in violations)


def test_every_domain_module_imports_cleanly() -> None:
    for path in domain_python_files():
        relative = path.relative_to(SRC_ROOT).with_suffix("")
        parts = relative.parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_name = ".".join(parts)
        importlib.import_module(module_name)
