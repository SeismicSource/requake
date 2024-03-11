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
