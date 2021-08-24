
#!/usr/bin/env python
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
import argparse
import logging
import signal
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from ._version import get_versions
from .utils import (
    parse_configspec, read_config, validate_config, write_sample_config
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


def _parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run requake.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-c', '--configfile', type=str,
        help='config file for data sources and processing params')
    group.add_argument(
        '-s', '--sampleconfig', default=False, action='store_true',
        required=False,
        help='write sample config file to current directory and exit')
    parser.add_argument(
        '-o', '--outdir', dest='outdir',
        action='store', default='requake_out',
        help='save output to OUTDIR (default: requake_out)',
        metavar='OUTDIR')
    parser.add_argument(
        '-v', '--version', action='version',
        version='%(prog)s {}'.format(get_versions()['version']))
    args = parser.parse_args()
    return args


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


def _setup_logging(config, basename=None, progname='requake'):
    """Set up the logging infrastructure."""
    global logger
    # Create outdir
    if not os.path.exists(config.args.outdir):
        os.makedirs(config.args.outdir)

    logfile = os.path.join(config.args.outdir, '{}.log'.format(progname))

    logger_root = logging.getLogger()

    # captureWarnings is not supported in old versions of python
    try:
        logging.captureWarnings(True)
    except Exception:
        pass
    logger_root.setLevel(logging.DEBUG)
    filehand = logging.FileHandler(filename=logfile, mode='w')
    filehand.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)-20s '
                                  '%(levelname)-8s %(message)s')
    filehand.setFormatter(formatter)
    logger_root.addHandler(filehand)

    console = logging.StreamHandler()
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
    config.client_fdsn_station = Client(config.fdsn_station_url)
    logger.info('Connected to FDSN station server: {}'.format(
        config.fdsn_station_url))
    config.client_fdsn_dataselect = Client(config.fdsn_dataselect_url)
    logger.info('Connected to FDSN dataselect server: {}'.format(
        config.fdsn_dataselect_url))
    if config.catalog_fdsn_event_url is None:
        return
    config.clients_fdsn_event = list()
    config.catalog_start_times = list()
    config.catalog_end_times = list()
    config.clients_fdsn_event.append(Client(config.catalog_fdsn_event_url))
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
        config.clients_fdsn_event.append(Client(url))
        logger.info('Connected to FDSN event server: {}'.format(url))
        start_time = config['catalog_start_time_{:1d}'.format(n)]
        end_time = config['catalog_start_time_{:1d}'.format(n)]
        if start_time is None or end_time is None:
            continue
        config.catalog_start_times.append(UTCDateTime(start_time))
        config.catalog_end_times.append(UTCDateTime(end_time))


def configure():
    """Read command line arguments. Read config file. Set up logging."""
    args = _parse_arguments()
    configspec = parse_configspec()
    if args.sampleconfig:
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
    # Check library versions
    _check_library_versions()
    # Set up logging
    _setup_logging(config)
    # save config to output dir
    shutil.copy(args.configfile, args.outdir)
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
        logger.debug('{} ABORTED'.format(progname))
    else:
        logger.debug('{} END'.format(progname))
    logging.shutdown()
    sys.exit(retval)


def sigint_handler(sig, frame):
    """Abort gracefully."""
    rq_exit(1, abort=True)


signal.signal(signal.SIGINT, sigint_handler)
