# -*- coding: utf-8 -*-
"""Sphinx configuration file."""
# pylint: disable=wrong-import-position,invalid-name
import sys
import os
from datetime import datetime
import sphinxcontrib.katex as katex
sys.path.insert(0, os.path.abspath('.'))
from write_configfile import write_configfile  # noqa

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath('..'))
sys.path.insert(0, os.path.join(os.path.abspath('..'), 'requake'))
from requake._version import get_versions  # NOQA
__version__ = get_versions()['version']
__release_date__ = get_versions()['date']

# -- Project information -----------------------------------------------------

project = 'Requake'
copyright = '2021-2024, Claudio Satriano'  # pylint: disable=redefined-builtin
author = 'Claudio Satriano'
# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The full version, including alpha/beta/rc tags.
release = __version__
# The short X.Y version.
version = release.split('-')[0]

# Release date in the format "Month DD, YYYY"
release_date = datetime.strptime(
    __release_date__, '%Y-%m-%dT%H:%M:%S%z'
).strftime('%b %d, %Y')
rst_epilog = f'\n.. |release date| replace:: {release_date}'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.doctest',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.viewcode',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.intersphinx',
    'sphinx_favicon',
    'sphinx_rtd_theme',
    'sphinxcontrib.bibtex',
    'sphinxcontrib.katex',
    'sphinx_mdinclude',
]
bibtex_bibfiles = ['refs.bib']
bibtex_reference_style = 'author_year'
bibtex_default_style = 'unsrt'

latex_macros = r"""
    \def \Nm                {\mathrm{N}\cdot\mathrm{m}}
    \def \dynecm            {\mathrm{dyne}\cdot\mathrm{cm}}
    \def \cm                {\mathrm{cm}}
    \def \MPa               {\mathrm{MPa}}
    \def \MPacm             {\mathrm{MPa/cm}}
"""

# Translate LaTeX macros to KaTeX and add to options for HTML builder
katex_macros = katex.latex_defs_to_katex_macros(latex_macros)
katex_options = 'macros: {' + katex_macros + '}'

# Add LaTeX macros for LATEX builder
# latex_elements = {'preamble': latex_macros}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_logo = '../imgs/Requake_logo_white.svg'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_css_files = ['custom.css']


def setup(app):
    """Add custom functions to Sphinx."""
    app.connect('builder-inited', write_configfile)
