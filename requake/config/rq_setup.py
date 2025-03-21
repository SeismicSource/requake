# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Setup functions for Requake.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
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
from obspy.clients.filesystem.sds import Client as SDSClient
from obspy.clients.fdsn import Client as FDSNClient
from obspy.clients.fdsn.header import FDSNNoServiceException
from .._version import get_versions
from .config import config
from .utils import (
    parse_configspec, read_config, validate_config, write_sample_config,
    update_config_file, write_ok
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


def _make_outdir(outdir):
    """Create the output directory if it doesn't exist."""
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    readme = os.path.join(outdir, 'README.txt')
    if not os.path.exists(readme):
        with open(readme, 'w', encoding='utf8') as fp:
            fp.write('This is the Requake output directory.\n\n')
            fp.write('''\
Do not manually edit the files in this directory, unless you know what you
are doing.
''')


def _color_handler_emit(fn):
    """
    Add color-coding to the logging handler emitter.

    Source: https://stackoverflow.com/a/20707569/2021880
    """
    def new(*args):
        levelno = args[0].levelno
        if levelno >= logging.CRITICAL:
            color = '\x1b[31;1m'  # red
        elif levelno >= logging.ERROR:
            color = '\x1b[31;1m'  # red
        elif levelno >= logging.WARNING:
            color = '\x1b[33;1m'  # yellow
        elif levelno >= logging.INFO:
            # color = '\x1b[32;1m'  # green
            color = '\x1b[0m'  # no color
        elif levelno >= logging.DEBUG:
            color = '\x1b[35;1m'  # purple
        else:
            color = '\x1b[0m'  # no color
        # Color-code the message
        args[0].msg = f'{color}{args[0].msg}\x1b[0m'
        return fn(*args)
    return new


def _setup_tqdm_logging(logger_root):
    """Set up a tqdm logging handler."""

    class TqdmLoggingHandler(logging.Handler):
        """A logging handler that writes to tqdm."""
        def __init__(self, level=logging.NOTSET):
            super().__init__(level)

        def emit(self, record):
            try:
                msg = self.format(record)
                tqdm.tqdm.write(msg)
                self.flush()
            except (ValueError, TypeError, IOError, OSError):
                self.handleError(record)
    console = TqdmLoggingHandler()
    console.setLevel(logging.INFO)
    # Add logger color coding on all platforms but win32
    if sys.platform != 'win32' and sys.stdout.isatty():
        console.emit = _color_handler_emit(console.emit)
    logger_root.addHandler(console)


def _setup_logging(progname, action_name):
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
        _make_outdir(config.args.outdir)
        logfile = os.path.join(
            config.args.outdir, f'{progname}.{action_name}.log')
        filehand = logging.FileHandler(filename=logfile, mode='a')
        filehand.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(name)-20s '
                                      '%(levelname)-8s %(message)s')
        filehand.setFormatter(formatter)
        logger_root.addHandler(filehand)

    if sys.stderr.isatty():
        _setup_tqdm_logging(logger_root)
    else:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter('%(levelname)-8s %(message)s')
        console.setFormatter(formatter)
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


def _connect_station_dataselect():
    """
    Connect to station and dataselect services.

    Those can be either FDSN web services or local files.
    """
    if config.station_metadata_path is None:
        config.station_client = FDSNClient(config.fdsn_station_url)
        logger.info(
            f'Connected to FDSN station server: {config.fdsn_station_url}'
        )
    config.dataselect_client = None
    if config.sds_data_path is not None:
        _connect_sds()
    if config.event_data_path is not None:
        return
    config.dataselect_client = FDSNClient(config.fdsn_dataselect_url)
    logger.info(
        'Connected to FDSN dataselect server: '
        f'{config.fdsn_dataselect_url}'
    )


def _connect_sds():
    """
    Connect to a local SeisComP Data Structure (SDS) archive.
    """
    _client = SDSClient(config.sds_data_path)
    all_nslc = _client.get_all_nslc()
    if not all_nslc:
        raise FileNotFoundError(
            f'No SDS archive found in {config.sds_data_path}'
        )
    config.dataselect_client = _client
    logger.info(
        'Reading waveform data from local SDS archive: '
        f'{config.sds_data_path}'
    )
    all_nslc_str = '\n'.join('.'.join(nslc) for nslc in all_nslc)
    logger.info(f'Found the following NSLC codes:\n{all_nslc_str}')


def _parse_catalog_options():
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


def _connect_fdsn_catalog():
    """Connect to FDSN catalog services."""
    config.catalog_fdsn_event_clients = []
    for url in config.catalog_fdsn_event_urls:
        config.catalog_fdsn_event_clients.append(FDSNClient(url))
        logger.info(f'Connected to FDSN event server: {url}')


def configure(args):
    """
    Configure Requake.

    This function is called by the main script to set up the configuration
    object and the logging infrastructure.

    :param args: The parsed command-line arguments.
    :type args: argparse.Namespace
    """
    configspec = parse_configspec()
    if args.action == 'sample_config':
        write_sample_config(configspec, 'requake')
        sys.exit(0)
    if args.action == 'update_config':
        update_config_file(args.configfile, configspec)
        sys.exit(0)
    config_obj = read_config(args.configfile, configspec)
    # Set to None all the 'None' strings
    for key, value in config_obj.dict().items():
        if value == 'None':
            config_obj[key] = None
    validate_config(config_obj)
    # update config with the contents of config_obj
    config.update(config_obj)
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
        not write_ok(config.scan_catalog_file, args.force)
    ):
        print('Exiting now.')
        sys.exit(0)
    if (
        args.action == 'scan_catalog' and
        not write_ok(config.scan_catalog_pairs_file, args.force)
    ):
        print('Exiting now.')
        sys.exit(0)
    if (
        args.action == 'build_families' and
        not write_ok(config.build_families_outfile, args.force)
    ):
        print('Exiting now.')
        sys.exit(0)
    # config.inventory needs to exist
    config.inventory = None
    # Check library versions
    _check_library_versions()
    # Set up logging
    _setup_logging('requake', args.action)
    # save config to output dir (only for actions that write to outdir)
    actions_writing_to_outdir = (
        'read_catalog', 'scan_catalog', 'build_families',
        'build_templates', 'scan_templates'
    )
    if args.action in actions_writing_to_outdir:
        shutil.copy(args.configfile, args.outdir)
    _parse_catalog_options()
    actions_needing_fdsn_station_dataselect = (
        'scan_catalog', 'plot_pair', 'plot_families', 'build_templates',
        'scan_templates'
    )
    try:
        if args.action in actions_needing_fdsn_station_dataselect:
            _connect_station_dataselect()
        if args.action == 'read_catalog' and not args.catalog_file:
            _connect_fdsn_catalog()
    except (FileNotFoundError, ValueError, FDSNNoServiceException) as msg:
        logger.error(msg)
        rq_exit(1)
    # Template times must be UTCDateTime objects
    config.template_start_time = UTCDateTime(config.template_start_time)
    config.template_end_time = UTCDateTime(config.template_end_time)


def rq_exit(retval=0, abort=False, progname='requake'):
    """Exit as gracefully as possible."""
    if abort:
        print('\nAborting.')
        if logger is not None:
            logger.debug(f'{progname} ABORTED\n\n')
    elif logger is not None:
        logger.debug(f'{progname} END\n\n')
    logging.shutdown()
    sys.exit(retval)


def sigint_handler(_sig, _frame):
    """Abort gracefully."""
    rq_exit(1, abort=True)


signal.signal(signal.SIGINT, sigint_handler)
