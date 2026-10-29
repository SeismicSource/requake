# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Change the label of a family build.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config, rq_exit
from ..database.family_builds import (
    FamilyBuildNotFoundError,
    resolve_build_id,
    update_family_build_label,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def edit_family_build():
    """Change the label of a family build."""
    label = str(config.args.label).strip() or None
    try:
        build_id = resolve_build_id(getattr(config.args, 'build_id', None))
    except FamilyBuildNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    update_family_build_label(build_id, label)
    if label is None:
        logger.info(f'Family build {build_id} label removed')
    else:
        logger.info(f'Family build {build_id} label set to "{label}"')
