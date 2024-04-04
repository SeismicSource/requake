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
import os
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
    # return ValueError if the file is empty
    if os.stat(catalog_file).st_size == 0:
        raise ValueError('Empty file')
    # return ValueError if the file is a directory
    if os.path.isdir(catalog_file):
        raise ValueError('Is a directory')
    # try to read the catalog as a QuakeML file
    with contextlib.suppress(TypeError, IndexError, ValueError):
        return read_catalog_from_quakeml(catalog_file)
    # try to read the catalog as a FDSN text file
    with contextlib.suppress(ValueError):
        cat = RequakeCatalog()
        cat.read(catalog_file)
        return cat
    # try to read the catalog as a CSV file
    # raises ValueError in case of failure
    return read_catalog_from_csv(catalog_file)


def _filter_catalog(catalog, config):
    """
    Filter an event catalog, based on the criteria specified
    in the configuration.

    :param catalog: Event catalog.
    :type catalog: requake.catalog.RequakeCatalog
    :param config: Configuration object.
    :type config: requake.rq_setup.RequakeConfig
    :return: Filtered event catalog.
    :rtype: requake.catalog.RequakeCatalog
    """
    lon_min = config.catalog_lon_min
    lon_max = config.catalog_lon_max
    lat_min = config.catalog_lat_min
    lat_max = config.catalog_lat_max
    depth_min = config.catalog_depth_min
    depth_max = config.catalog_depth_max
    mag_min = config.catalog_mag_min
    mag_max = config.catalog_mag_max
    outcat = catalog
    for start_time, end_time in zip(config.catalog_start_times,
                                    config.catalog_end_times):
        outcat = outcat.filter(
            starttime=start_time, endtime=end_time,
            minlatitude=lat_min, maxlatitude=lat_max,
            minlongitude=lon_min, maxlongitude=lon_max,
            mindepth=depth_min, maxdepth=depth_max,
            minmagnitude=mag_min, maxmagnitude=mag_max
        )
    nevents_in = len(catalog)
    nevents_out = len(outcat)
    logger.info(
        'Catalog filtered based on configuration file: '
        f'{nevents_out} events out of {nevents_in}'
    )
    return outcat


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
    output_cat_file = config.scan_catalog_file
    nevs_read = 0
    if config.args.append:
        with contextlib.suppress(FileNotFoundError):
            catalog = RequakeCatalog()
            catalog.read(output_cat_file)
            nevs_read = len(catalog)
            logger.info(f'{nevs_read} events read from "{output_cat_file}"')
    logger.info('Reading catalog...')
    input_cat_file = config.args.catalog_file
    if input_cat_file is not None:
        try:
            catalog += _read_catalog_from_file(config)
            # Filter catalog based on configuration
            catalog = _filter_catalog(catalog, config)
        except FileNotFoundError:
            logger.error(f'File "{input_cat_file}" not found')
            rq_exit(1)
        except ValueError as m:
            logger.error(f'Error reading catalog file "{input_cat_file}": {m}')
            rq_exit(1)
    else:
        catalog += read_catalog_from_fdsnws(config)
    if not catalog:
        logger.error('No event read')
        rq_exit(1)
    # Deduplicate catalog
    len_before = len(catalog)
    catalog.deduplicate()
    len_after = len(catalog)
    nevs_dedup = len_before - len_after
    if nevs_dedup > 0:
        logger.info(f'{nevs_dedup} duplicate events removed')
    # Sort catalog in increasing time order
    catalog.sort()
    # Write catalog to output file
    catalog.write(output_cat_file)
    nevs_written = len(catalog) - nevs_read
    logger.info(f'{nevs_written} events written to "{output_cat_file}"')
