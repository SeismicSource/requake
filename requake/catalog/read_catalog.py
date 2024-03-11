# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Read an event catalog from web services or from a file.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import contextlib
from ..catalog.catalog import RequakeCatalog
from ..config.rq_setup import rq_exit
from .read_catalog_from_fdsnws import read_catalog_from_fdsnws
from .read_catalog_from_quakeml import read_catalog_from_quakeml
from .read_catalog_from_csv import read_catalog_from_csv
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _read_catalog_from_file(config):
    """
    Read an event catalog from a file.

    Supported formats are QuakeML, FDSN text and CSV.

    :param config: Configuration object.
    :type config: requake.rq_setup.RequakeConfig
    :return: Event catalog.
    :rtype: requake.catalog.RequakeCatalog

    :raises FileNotFoundError: if the file does not exist
    :raises ValueError: if the file format is not supported
    """
    catalog_file = config.args.catalog_file
    # try to read the catalog as a QuakeML file
    with contextlib.suppress(TypeError):
        return read_catalog_from_quakeml(catalog_file)
    # try to read the catalog as a FDSN text file
    with contextlib.suppress(ValueError):
        cat = RequakeCatalog()
        cat.read(catalog_file)
        return cat
    # try to read the catalog as a CSV file
    # raises ValueError in case of failure
    return read_catalog_from_csv(catalog_file)


def read_catalog(config):
    """
    Read an event catalog from web services or from a file.

    Write the catalog to the output directory.

    :param config: Configuration object.
    :type config: requake.rq_setup.RequakeConfig
    :return: Event catalog.
    :rtype: requake.catalog.RequakeCatalog
    """
    catalog = RequakeCatalog()
    out_cat_file = config.scan_catalog_file
    nevs_read = 0
    if config.args.append:
        with contextlib.suppress(FileNotFoundError):
            catalog = RequakeCatalog()
            catalog.read(out_cat_file)
            nevs_read = len(catalog)
            logger.info(f'{nevs_read} events read from "{out_cat_file}"')
    logger.info('Reading catalog...')
    in_cat_file = config.args.catalog_file
    if in_cat_file is not None:
        try:
            catalog += _read_catalog_from_file(config)
        except FileNotFoundError:
            logger.error(f'File "{in_cat_file}" not found')
            rq_exit(1)
        except ValueError as m:
            logger.error(f'Error reading catalog file "{in_cat_file}": {m}')
            rq_exit(1)
    else:
        catalog += read_catalog_from_fdsnws(config)
    if not catalog:
        logger.error('No event read')
        rq_exit(1)
    catalog.deduplicate()
    # Sort catalog in increasing time order
    catalog.sort()
    # Write catalog to output file
    catalog.write(out_cat_file)
    nevs_written = len(catalog) - nevs_read
    logger.info(f'{nevs_written} events written to "{out_cat_file}"')
