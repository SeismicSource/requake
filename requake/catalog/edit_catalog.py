# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Change the label of a catalog.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from ..config import config, rq_exit
from ..database.catalogs import (
    CatalogNotFoundError,
    resolve_catalog_id,
    update_catalog_label,
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def edit_catalog():
    """Change the label of a catalog."""
    label = str(config.args.label).strip() or None
    try:
        catalog_id = resolve_catalog_id(config.args.catalog_id)
    except CatalogNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    update_catalog_label(catalog_id, label)
    if label is None:
        logger.info(f'Catalog {catalog_id} label removed')
    else:
        logger.info(f'Catalog {catalog_id} label set to "{label}"')
