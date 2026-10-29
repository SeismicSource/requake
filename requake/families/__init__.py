# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Modules and functions for building and analyzing repeating families.

Families can be built, printed, filtered, and converted into templates.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .print_pairs import print_pairs  # noqa
from .dedup_events import dedup_events  # noqa
from .build_families import build_families  # noqa
from .print_families import print_families  # noqa
from .print_family_builds import print_family_builds  # noqa
from .delete_family_build import delete_family_build  # noqa
from .edit_family_build import edit_family_build  # noqa
from .flag_family import flag_family  # noqa
from .build_templates import build_templates  # noqa
from .families import (  # noqa
    read_families, read_selected_families,
    get_family_aligned_waveforms_and_template,
    FamilyNotFoundError
)
