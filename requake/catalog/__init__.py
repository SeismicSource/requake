# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions and data structures for managing earthquake catalogs.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .catalog import (  # noqa
    RequakeCatalog, RequakeEvent, generate_evid,
    fix_non_locatable_events, read_stored_catalog
)
from .read_catalog import read_catalog  # noqa
from .print_catalog import print_catalog  # noqa
