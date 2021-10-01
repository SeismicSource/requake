
#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf8 -*-
"""
Setup functions for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import sys
import os
import shutil
import logging
import tqdm
import signal
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from ._version import get_versions
from .utils import (
    parse_configspec, read_config, validate_config, write_sample_config,
    write_ok
)


logger = None
PYTHON_VERSION_STR = None
NUMPY_VERSION_STR = None
SCIPY_VERSION_STR = None
OBSPY_VERSION_STR = None


class Config(dict):
    """A class to access config values with dot notation."""

    def __setitem__(self, key, value):
        """Make Config keys accessible as attributes."""
        super(Config, self).__setattr__(key, value)
        super(Config, self).__setitem__(key, value)

    def __getattr__(self, key):
        """Make Config keys accessible as attributes."""
        try:
            return self.__getitem__(key)
        except KeyError as err:
            raise AttributeError(err)

    __setattr__ = __setitem__


def _check_library_versions():
    global PYTHON_VERSION_STR
    PYTHON_VERSION_STR = '{}.{}.{}'.format(*sys.version_info[0:3])
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
    try:
        logging.captureWarnings(True)
    except Exception:
        pass
    logger_root.setLevel(logging.DEBUG)

    # Actions that will produce a logfile
    loggin_actions = [
        'scan_catalog',
        'scan_template',
        'build_families'
    ]
    if action_name in loggin_actions:
        if not os.path.exists(config.args.outdir):
            os.makedirs(config.args.outdir)
        logfile = os.path.join(
            config.args.outdir,
            '{}.{}.log'.format(progname, action_name))
        filehand = logging.FileHandler(filename=logfile, mode='a')
        filehand.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(name)-20s '
                                      '%(levelname)-8s %(message)s')
        filehand.setFormatter(formatter)
        logger_root.addHandler(filehand)

    # tqdm compatible console handler
    class TqdmLoggingHandler(logging.Handler):
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

    logger.debug('{} START'.format(progname))
    logger.debug('{} version: {}'.format(progname, get_versions()['version']))
    logger.debug('Python version: ' + PYTHON_VERSION_STR)
    logger.debug('NumPy version: ' + NUMPY_VERSION_STR)
    logger.debug('SciPy version: ' + SCIPY_VERSION_STR)
    logger.debug('ObsPy version: ' + OBSPY_VERSION_STR)
    logger.debug('Running arguments:')
    logger.debug(' '.join(sys.argv))


def _init_connections(config):
    """Connect to FDSN services."""
    config.fdsn_station_client = Client(config.fdsn_station_url)
    logger.info('Connected to FDSN station server: {}'.format(
        config.fdsn_station_url))
    config.fdsn_dataselect_client = Client(config.fdsn_dataselect_url)
    logger.info('Connected to FDSN dataselect server: {}'.format(
        config.fdsn_dataselect_url))
    if config.catalog_fdsn_event_url is None:
        return
    config.catalog_fdsn_event_clients = list()
    config.catalog_start_times = list()
    config.catalog_end_times = list()
    config.catalog_fdsn_event_urls = list()
    config.catalog_fdsn_event_urls.append(config.catalog_fdsn_event_url)
    config.catalog_fdsn_event_clients.append(
        Client(config.catalog_fdsn_event_url))
    logger.info('Connected to FDSN event server: {}'.format(
        config.catalog_fdsn_event_url))
    config.catalog_start_times.append(
        UTCDateTime(config.catalog_start_time))
    config.catalog_end_times.append(
        UTCDateTime(config.catalog_end_time))
    for n in 1, 2, 3:
        url = config['catalog_fdsn_event_url_{:1d}'.format(n)]
        if url is None:
            continue
        config.catalog_fdsn_event_urls.append(url)
        config.catalog_fdsn_event_clients.append(Client(url))
        logger.info('Connected to FDSN event server: {}'.format(url))
        start_time = config['catalog_start_time_{:1d}'.format(n)]
        end_time = config['catalog_end_time_{:1d}'.format(n)]
        if start_time is None or end_time is None:
            continue
        config.catalog_start_times.append(UTCDateTime(start_time))
        config.catalog_end_times.append(UTCDateTime(end_time))


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
    if (args.action == 'scan_catalog' and
            not write_ok(config.scan_catalog_pairs_file)):
        print('Exiting now.')
        sys.exit(0)
    if (args.action == 'build_families' and
            not write_ok(config.build_families_outfile)):
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
    actions_needing_connection = (
        'scan_catalog', 'plot_pair', 'plot_families', 'build_templates'
    )
    if args.action in actions_needing_connection:
        try:
            _init_connections(config)
        except Exception as m:
            logger.error(m)
            rq_exit(1)
    return config


def rq_exit(retval=0, abort=False, progname='requake'):
    """Exit as gracefully as possible."""
    if abort:
        print('\nAborting.')
        logger.debug('{} ABORTED\n\n'.format(progname))
    else:
        logger.debug('{} END\n\n'.format(progname))
    logging.shutdown()
    sys.exit(retval)


def sigint_handler(sig, frame):
    """Abort gracefully."""
    rq_exit(1, abort=True)


signal.signal(signal.SIGINT, sigint_handler)
