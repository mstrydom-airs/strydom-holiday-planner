"""Sphinx configuration for the Trip Planner docs.

Build with::

    sphinx-build -W -b html docs docs/_build/html

The ``-W`` flag turns warnings into errors so missing/dangling sphinx-needs
links break the build, as required by .cursor/rules/project-standards.mdc §4.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# sphinx-needs 4.x + Python 3.14: ``ast.NameConstant`` removed; keep the alias
# for older import paths. Newer sphinx-needs (8.x) uses ``ast.Constant`` parsing.
if not hasattr(ast, "NameConstant"):
    ast.NameConstant = ast.Constant  # type: ignore[attr-defined]

project = "Strydom Travel Hub"
author = "Strydom"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",  # Google-style docstrings
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_needs",  # requirement / decision / test traceability
    "sphinxcontrib.mermaid",  # Mermaid diagrams
    "sphinx_copybutton",
    "myst_parser",  # allow Markdown sources
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
# sphinx-needs 8.x deprecations until we migrate ``needs_extra_*`` to ``needs_fields``.
suppress_warnings = ["needs.deprecated", "misc.copy_overwrite"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["holiday.css"]
html_title = "Strydom Travel Hub Holiday Guide"

# ---------------------------------------------------------------------------
# sphinx-needs configuration
# Custom need types for our traceability scheme — see project-standards.mdc §4.
# ---------------------------------------------------------------------------
needs_types = [
    {
        "directive": "req",
        "title": "Requirement",
        "prefix": "REQ-",
        "color": "#BFD8D2",
        "style": "node",
    },
    {
        "directive": "uc",
        "title": "Usability Criterion",
        "prefix": "UC-",
        "color": "#DCB239",
        "style": "node",
    },
    {
        "directive": "spec",
        "title": "Specification",
        "prefix": "SPEC-",
        "color": "#FEDCD2",
        "style": "node",
    },
    {
        "directive": "adr",
        "title": "Architecture Decision",
        "prefix": "ADR-",
        "color": "#DF744A",
        "style": "node",
    },
    {
        "directive": "impl",
        "title": "Implementation",
        "prefix": "IMPL-",
        "color": "#DCB239",
        "style": "node",
    },
    {"directive": "test", "title": "Test", "prefix": "TEST-", "color": "#9B9B9B", "style": "node"},
]

needs_extra_links = [
    {"option": "implements", "incoming": "implemented by", "outgoing": "implements"},
    {"option": "verifies", "incoming": "verified by", "outgoing": "verifies"},
    {"option": "decided_by", "incoming": "decides", "outgoing": "decided by"},
]

needs_id_required = True
needs_id_regex = r"^[A-Z]+-[A-Z0-9_]+$"
needs_extra_options = ["priority", "source", "owner"]

needs_statuses = [
    {"name": "draft"},
    {"name": "approved"},
    {"name": "implemented"},
    {"name": "verified"},
    {"name": "rejected"},
]

mermaid_version = "10.9.0"
