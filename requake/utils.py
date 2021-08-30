# -*- coding: utf-8 -*-
"""
Utility functions for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import os
import sys
import locale
locale.setlocale(locale.LC_ALL, '')
from .configobj import ConfigObj
from .configobj.validate import Validator


def err_exit(msg):
    msg = str(msg)
    sys.stderr.write(msg + '\n')
    sys.exit(1)


def parse_configspec():
    curdir = os.path.dirname(__file__)
    configspec_file = os.path.join(curdir, 'conf', 'configspec.conf')
    configspec = read_config(configspec_file)
    return configspec


def write_ok(filepath):
    if os.path.exists(filepath):
        ans = input(
            '"{}" already exists. '
            'Do you want to overwrite it? [y/N] '.format(filepath))
        if ans in ['y', 'Y']:
            return True
        else:
            return False
    return True


def write_sample_config(configspec, progname):
    c = ConfigObj(configspec=configspec, default_encoding='utf8')
    val = Validator()
    c.validate(val)
    c.defaults = []
    c.initial_comment = configspec.initial_comment
    c.comments = configspec.comments
    configfile = progname + '.conf'
    if write_ok(configfile):
        with open(configfile, 'wb') as fp:
            c.write(fp)
        print('Sample config file written to: "{}"'.format(configfile))


def read_config(config_file, configspec=None):
    kwargs = dict(
        configspec=configspec, file_error=True, default_encoding='utf8')
    if configspec is None:
        kwargs.update(
            dict(interpolation=False, list_values=False, _inspec=True))
    try:
        config_obj = ConfigObj(config_file, **kwargs)
    except IOError as err:
        err_exit(err)
    except Exception as err:
        msg = 'Unable to read "{}": {}'.format(config_file, err)
        err_exit(msg)
    return config_obj


def validate_config(config_obj):
    val = Validator()
    test = config_obj.validate(val)
    if isinstance(test, dict):
        for entry in test:
            if not test[entry]:
                sys.stderr.write(
                    'Invalid value for "{}": "{}"\n'.format(
                        entry, config_obj[entry]))
        sys.exit(1)
    if not test:
        err_exit('No configuration value present!')


def update_progress(num, total, status=None):
    """
    Display or update a console progress bar.

    Accepts a float between 0 and 1.
    A value under 0 represents a 'halt'.
    A value at 1 or bigger represents 100%

    Modified from: https://stackoverflow.com/a/15860757/2021880
    """
    barLength = 40  # Modify this to change the length of the progress bar
    progress = num/total
    if status is None:
        status = ''
        if progress < 0:
            progress = 0
            status = 'Halt...\r\n'
        if progress >= 1:
            progress = 1
            status = 'Done.\r\n'
    block = int(round(barLength*progress))
    text = '\rProgress: [{}] {:n} of {:n} {}'.format(
        '#'*block + '-'*(barLength-block), num, total, status)
    sys.stdout.write(text)
    sys.stdout.flush()
