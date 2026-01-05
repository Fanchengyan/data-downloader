# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "DataDownloader"
copyright = "2024, Fan Chengyan (Fancy)"
author = "Fan Chengyan (Fancy)"
release = "v1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
from pathlib import Path



extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "myst_nb",
    "sphinx_copybutton",
    "sphinx_design",
    "myst_sphinx_gallery",
]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "myst-nb",
    ".myst": "myst-nb",
}

myst_enable_extensions = ["colon_fence"]
myst_url_schemes = ["http", "https", "mailto"]
suppress_warnings = ["mystnb.unknown_mime_type"]
nb_execution_mode = "off"
autodoc_inherit_docstrings = True
# templates_path = ['_templates']
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_static_path = ["_static"]
html_css_files = ["css/custom.css", "css/gallery.css"]
html_theme = "pydata_sphinx_theme"
html_logo = "_static/logo/logo.png"
html_favicon = "_static/logo/icon_square.svg"
html_theme_options = {
    "show_toc_level": 3,
    "show_nav_level": 2,
    "use_edit_page_button": True,
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/Fanchengyan/data-downloader", 
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        },
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/data-downloader/",
            "icon": "fa-brands fa-python",
            "type": "fontawesome",
        },
    ],
}
html_context = {
    "github_url": "https://github.com",  # or your GitHub Enterprise site
    "github_user": "Fanchengyan",
    "github_repo": "data-downloader",
    "github_version": "master",
    "doc_path": "docs/source",
}

video_enforce_extra_source = True

autodoc_default_options = {
    "members": True,
    "inherited-members": True,
    "undoc-members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    ":show-inheritance:": True,
}

# -- faninsar package ----------------------------------------------------------
import os
import sys

# Location of Sphinx files
sys.path.insert(0, os.path.abspath("./../.."))
