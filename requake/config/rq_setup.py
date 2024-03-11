# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Setup functions for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import contextlib
import sys
import os
import shutil
import logging
import signal
import tqdm
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from .._version import get_versions
from .config import Config
from .utils import (
    parse_configspec, read_config, validate_config, write_sample_config,
    write_ok
)
# pylint: disable=global-statement,import-outside-toplevel

logger = None  # pylint: disable=invalid-name
PYTHON_VERSION_STR = None
NUMPY_VERSION_STR = None
SCIPY_VERSION_STR = None
OBSPY_VERSION_STR = None


def _check_library_versions():
    global PYTHON_VERSION_STR
    PYTHON_VERSION_STR = '.'.join(map(str, sys.version_info[:3]))
    import numpy
    global NUMPY_VERSION_STR
    NUMPY_VERSION_STR = numpy.__version__
    import scipy
    global SCIPY_VERSION_STR
    SCIPY_VERSION_STR = scipy.__version__
    import obspy
    global OBSPY_VERSION_STR
    OBSPY_VERSION_STR = obspy.__version__


def _setup_logging(config, progname, action_name):
    """Set up the logging infrastructure."""
    global logger

    logger_root = logging.getLogger()
    # captureWarnings is not supported in old versions of python
    with contextlib.suppress(Exception):
        logging.captureWarnings(True)
    logger_root.setLevel(logging.DEBUG)

    # Actions that will produce a logfile
    logging_actions = [
        'read_catalog',
        'scan_catalog',
        'scan_templates',
        'build_families'
    ]
    if action_name in logging_actions:
        if not os.path.exists(config.args.outdir):
            os.makedirs(config.args.outdir)
        logfile = os.path.join(
            config.args.outdir, f'{progname}.{action_name}.log')
        filehand = logging.FileHandler(filename=logfile, mode='a')
        filehand.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(name)-20s '
                                      '%(levelname)-8s %(message)s')
        filehand.setFormatter(formatter)
        logger_root.addHandler(filehand)

    class TqdmLoggingHandler(logging.Handler):
        """A logging handler that writes to tqdm."""
        def __init__(self, level=logging.NOTSET):
            super().__init__(level)

        def emit(self, record):
            try:
                msg = self.format(record)
                tqdm.tqdm.write(msg)
                self.flush()
            except Exception:
                self.handleError(record)
    console = TqdmLoggingHandler()
    console.setLevel(logging.INFO)
    logger_root.addHandler(console)

    logger = logging.getLogger(progname)

    logger.debug(f'{progname} START')
    logger.debug(f"{progname} version: {get_versions()['version']}")
    logger.debug(f'Python version: {PYTHON_VERSION_STR}')
    logger.debug(f'NumPy version: {NUMPY_VERSION_STR}')
    logger.debug(f'SciPy version: {SCIPY_VERSION_STR}')
    logger.debug(f'ObsPy version: {OBSPY_VERSION_STR}')
    logger.debug('Running arguments:')
    logger.debug(' '.join(sys.argv))


def _connect_fdsn_station_dataselect(config):
    """Connect to FDSN station and dataselect services."""
    config.fdsn_station_client = Client(config.fdsn_station_url)
    logger.info(f'Connected to FDSN station server: {config.fdsn_station_url}')
    config.fdsn_dataselect_client = Client(config.fdsn_dataselect_url)
    logger.info(
        f'Connected to FDSN dataselect server: {config.fdsn_dataselect_url}'
    )


def _parse_catalog_options(config):
    """Parse catalog options into lists."""
    config.catalog_start_times = []
    config.catalog_end_times = []
    config.catalog_fdsn_event_urls = [config.catalog_fdsn_event_url]
    config.catalog_start_times.append(
        UTCDateTime(config.catalog_start_time))
    config.catalog_end_times.append(
        UTCDateTime(config.catalog_end_time))
    for n in 1, 2, 3:
        url = config[f'catalog_fdsn_event_url_{n:1d}']
        if url is None:
            continue
        config.catalog_fdsn_event_urls.append(url)
        start_time = config[f'catalog_start_time_{n:1d}']
        end_time = config[f'catalog_end_time_{n:1d}']
        if start_time is None or end_time is None:
            continue
        config.catalog_start_times.append(UTCDateTime(start_time))
        config.catalog_end_times.append(UTCDateTime(end_time))


def _connect_fdsn_catalog(config):
    """Connect to FDSN catalog services."""
    config.catalog_fdsn_event_clients = []
    for url in config.catalog_fdsn_event_urls:
        config.catalog_fdsn_event_clients.append(Client(url))
        logger.info(f'Connected to FDSN event server: {url}')


def configure(args):
    """Read command line arguments. Read config file. Set up logging."""
    configspec = parse_configspec()
    if args.action == 'sample_config':
        write_sample_config(configspec, 'requake')
        sys.exit(0)
    config_obj = read_config(args.configfile, configspec)
    # Set to None all the 'None' strings
    for key, value in config_obj.dict().items():
        if value == 'None':
            config_obj[key] = None
    validate_config(config_obj)
    # Create a config class
    config = Config(config_obj)
    config.args = args
    config.scan_catalog_file = os.path.join(
        config.args.outdir, 'requake.catalog.txt'
    )
    config.scan_catalog_pairs_file = os.path.join(
        config.args.outdir, 'requake.event_pairs.csv'
    )
    config.build_families_outfile = os.path.join(
        config.args.outdir, 'requake.event_families.csv'
    )
    config.template_dir = os.path.join(
        config.args.outdir, 'templates'
    )
    if (
        args.action == 'read_catalog' and
        not args.append and
        not write_ok(config.scan_catalog_file)
    ):
        print('Exiting now.')
        sys.exit(0)
    if (
        args.action == 'scan_catalog' and
        not write_ok(config.scan_catalog_pairs_file)
    ):
        print('Exiting now.')
        sys.exit(0)
    if (
        args.action == 'build_families' and
        not write_ok(config.build_families_outfile)
    ):
        print('Exiting now.')
        sys.exit(0)
    # config.inventory needs to exist
    config.inventory = None
    # Check library versions
    _check_library_versions()
    # Set up logging
    _setup_logging(config, 'requake', args.action)
    # save config to output dir
    shutil.copy(args.configfile, args.outdir)
    _parse_catalog_options(config)
    actions_needing_fdsn_station_dataselect = (
        'scan_catalog', 'plot_pair', 'plot_families', 'build_templates',
        'scan_templates'
    )
    try:
        if args.action in actions_needing_fdsn_station_dataselect:
            _connect_fdsn_station_dataselect(config)
        if args.action == 'read_catalog' and not args.catalog_file:
            _connect_fdsn_catalog(config)
    except Exception as m:
        logger.error(m)
        rq_exit(1)
    # Template times must be UTCDateTime objects
    config.template_start_time = UTCDateTime(config.template_start_time)
    config.template_end_time = UTCDateTime(config.template_end_time)
    return config


def rq_exit(retval=0, abort=False, progname='requake'):
    """Exit as gracefully as possible."""
    if abort:
        print('\nAborting.')
        logger.debug(f'{progname} ABORTED\n\n')
    else:
        logger.debug(f'{progname} END\n\n')
    logging.shutdown()
    sys.exit(retval)


def sigint_handler(_sig, _frame):
    """Abort gracefully."""
    rq_exit(1, abort=True)


signal.signal(signal.SIGINT, sigint_handler)
