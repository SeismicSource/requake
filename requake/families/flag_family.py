# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Flag a family of repeating earthquakes as valid or not valid.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config
from ..database.families import update_family_valid
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def flag_family():
    """Flag a family of repeating earthquakes as valid or not valid."""
    family_number = config.args.family_number
    is_valid = str(config.args.is_valid).strip().lower()
    if is_valid not in {'true', 't', 'false', 'f'}:
        logger.error(
            f'Invalid choice for "is_valid": "{config.args.is_valid}". '
            'Enter either "true" ("t") or "false" ("f")'
        )
        return
    is_valid = is_valid in {'true', 't'}
    update_family_valid(family_number, is_valid)
    text = {True: 'valid', False: 'not valid'}
    logger.info(f'Family "{family_number}" flagged as {text[is_valid]}')
