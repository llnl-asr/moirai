# -*- coding: utf-8 -*-
#
# Configuration file for the Sphinx documentation builder.
# http://www.sphinx-doc.org/en/stable/config

import os

# -- Project information -----------------------------------------------------

project = "moirai"
copyright = "2026, Lawrence Livermore National Security, LLC"
author = "Hariharan Devarajan"

# Read the library version from the VERSION file
version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
with open(version_file, "r") as f:
    full_version = f.read().strip()

# The short X.Y version
version = ".".join(full_version.split(".")[:2])
# The full version, including alpha/beta/rc tags
release = full_version

# -- General configuration ---------------------------------------------------

extensions = []
templates_path = ["_templates"]
source_suffix = ".rst"
master_doc = "index"
language = "en"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
pygments_style = "sphinx"

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = []
htmlhelp_basename = "moirai-doc"

# -- Options for other outputs -----------------------------------------------

latex_documents = [
    (master_doc, "moirai.tex", "moirai Documentation", author, "manual"),
]
man_pages = [(master_doc, "moirai", "moirai Documentation", [author], 1)]
texinfo_documents = [
    (
        master_doc,
        "moirai",
        "moirai Documentation",
        author,
        "moirai",
        "moirai records data provenance of HPC applications through dftracer.",
        "Miscellaneous",
    ),
]
