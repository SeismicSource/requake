# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utility functions for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os
import sys
import locale
import shutil
from datetime import datetime
from .configobj import ConfigObj
from .configobj.validate import Validator
locale.setlocale(locale.LC_ALL, '')


def err_exit(msg):
    """
    Exit with error message.

    :param msg: Error message.
    :type msg: str
    """
    msg = str(msg)
    sys.stderr.write(msg + '\n')
    sys.exit(1)


def parse_configspec():
    """
    Parse configuration specification file.

    :return: Configuration specification object.
    :rtype: configobj.ConfigObj
    """
    curdir = os.path.dirname(__file__)
    configspec_file = os.path.join(curdir, 'configspec.conf')
    return read_config(configspec_file)


def write_ok(filepath):
    """
    Check if a file can be written.

    :param filepath: File path.
    :type filepath: str
    :return: True if file can be written, False otherwise.
    :rtype: bool
    """
    if os.path.exists(filepath):
        ans = input(
            f'"{filepath}" already exists. Do you want to overwrite it? [y/N] '
        )
        return ans in ['y', 'Y']
    return True


def write_sample_config(configspec, progname):
    """
    Write a sample configuration file.

    :param configspec: Configuration specification file.
    :type configspec: str
    :param progname: Program name.
    :type progname: str
    """
    c = ConfigObj(configspec=configspec, default_encoding='utf8')
    val = Validator()
    c.validate(val)
    c.defaults = []
    c.initial_comment = configspec.initial_comment
    c.comments = configspec.comments
    configfile = f'{progname}.conf'
    if write_ok(configfile):
        with open(configfile, 'wb') as fp:
            c.write(fp)
        print(f'Sample config file written to: "{configfile}"')


def read_config(config_file, configspec=None):
    """
    Read a configuration file.

    :param config_file: Configuration file.
    :type config_file: str
    :param configspec: Configuration specification file.
    :type configspec: str
    :return: Configuration object.
    :rtype: configobj.ConfigObj
    """
    kwargs = {
        'configspec': configspec,
        'file_error': True,
        'default_encoding': 'utf8'
    }
    if configspec is None:
        kwargs.update({
            'interpolation': False,
            'list_values': False,
            '_inspec': True
        })
    try:
        config_obj = ConfigObj(config_file, **kwargs)
    except IOError as err:
        err_exit(err)
    except Exception as err:
        msg = f'Unable to read "{config_file}": {err}'
        err_exit(msg)
    return config_obj


def validate_config(config_obj):
    """
    Validate a configuration object.

    :param config_obj: Configuration object.
    :type config_obj: configobj.ConfigObj
    """
    val = Validator()
    test = config_obj.validate(val)
    if isinstance(test, dict):
        for entry in test:
            if not test[entry]:
                sys.stderr.write(
                    f'Invalid value for "{entry}": "{config_obj[entry]}"\n')
        sys.exit(1)
    if not test:
        err_exit('No configuration value present!')


def update_config_file(config_file, configspec):
    """
    Update a configuration file to the latest version.

    :param config_file: Configuration file.
    :type config_file: str
    :param configspec: Configuration specification file.
    :type configspec: str
    """
    config_obj = read_config(config_file, configspec)
    val = Validator()
    config_obj.validate(val)
    mod_time = datetime.fromtimestamp(os.path.getmtime(config_file))
    mod_time_str = mod_time.strftime('%Y%m%d_%H%M%S')
    config_file_old = f'{config_file}.{mod_time_str}'
    ans = input(
        f'Ok to update {config_file}? [y/N]\n'
        f'(Old file will be saved as {config_file_old}) '
    )
    if ans not in ['y', 'Y']:
        sys.exit(0)
    config_new = ConfigObj(configspec=configspec, default_encoding='utf8')
    config_new = read_config(None, configspec)
    config_new.validate(val)
    config_new.defaults = []
    config_new.comments = configspec.comments
    config_new.initial_comment = config_obj.initial_comment
    config_new.final_comment = configspec.final_comment
    for k, v in config_obj.items():
        if k not in config_new:
            continue
        # Fix for force_list(default=None)
        if v == ['None', ]:
            v = None
        config_new[k] = v
    migrate_options = {
        # 'old_option': 'new_option'
    }
    for old_opt, new_opt in migrate_options.items():
        if old_opt in config_obj and config_obj[old_opt] != 'None':
            config_new[new_opt] = config_obj[old_opt]
    shutil.copyfile(config_file, config_file_old)
    with open(config_file, 'wb') as fp:
        config_new.write(fp)
        print(f'{config_file}: updated')


def manage_uncaught_exception(exception):
    """
    Manage an uncaught exception.

    :param exception: Exception object.
    :type exception: Exception
    """
    # pylint: disable=import-outside-toplevel
    from .. import __version__
    import traceback
    import numpy as np
    import scipy as sp
    import obspy
    import matplotlib
    sys.stderr.write("""
# BEGIN TRACEBACK #############################################################
""")
    sys.stderr.write('\n')
    traceback.print_exc()
    sys.stderr.write("""
# END TRACEBACK ###############################################################
""")
    sys.stderr.write("""

Congratulations, you've found a bug in Requake! 🐞

Please report it on https://github.com/SeismicSource/requake/issues
or by email to satriano@ipgp.fr.

Include the following information in your report:

""")
    sys.stderr.write(f'  Requake version: {__version__}\n')
    sys.stderr.write(f'  Python version: {sys.version}\n')
    sys.stderr.write(f'  NumPy version: {np.__version__}\n')
    sys.stderr.write(f'  SciPy version: {sp.__version__}\n')
    sys.stderr.write(f'  ObsPy version: {obspy.__version__}\n')
    sys.stderr.write(f'  Matplotlib version: {matplotlib.__version__}\n')
    sys.stderr.write(f'  Platform: {sys.platform}\n')
    sys.stderr.write(f'  Command line: {" ".join(sys.argv)}\n')
    sys.stderr.write(f'  Error message: {str(exception)}\n')
    sys.stderr.write('\n')
    sys.stderr.write(
        'Also, please copy and paste the traceback above in your '
        'report.\n\n')
    sys.stderr.write('Thank you for your help!\n\n')
    sys.exit(1)
