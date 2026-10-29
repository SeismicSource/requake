# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Change the label of a catalog scan.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config, rq_exit
from ..database.scans import (
    ScanNotFoundError,
    resolve_scan_id,
    update_scan_label,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def edit_scan():
    """Change the label of a catalog scan."""
    label = str(config.args.label).strip() or None
    try:
        scan_id = resolve_scan_id(config.args.scan_id)
    except ScanNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    update_scan_label(scan_id, label)
    if label is None:
        logger.info(f'Scan {scan_id} label removed')
    else:
        logger.info(f'Scan {scan_id} label set to "{label}"')
