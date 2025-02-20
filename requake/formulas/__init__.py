# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Formulas for the Requake package.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .moment import mag_to_moment  # noqa
from .slip import mag_to_slip_in_cm  # noqa
from .conversion import (  # noqa
    float_or_none, int_or_none, field_match_score, guess_field_names
)
