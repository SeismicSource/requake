# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Write configuration file documentation page.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import os

def write_configfile(_app):
    """Write configuration file documentation page."""
    with open('configuration_file.rst', 'w', encoding='utf-8') as fp:
        fp.write('''.. _configuration_file:

##################
Configuration File
##################

Configuration file (default name: ``requake.conf``) is a plain text file
with keys and values in the form ``key = value``.
Comment lines start with ``#``.

Here is the default config file, generated through ``requake sample_config``::

''')
        configspec = os.path.join(
            '..', 'requake', 'config', 'configspec.conf')
        for line in open(configspec, encoding='utf-8'):
            if '=' in line and line[0] != '#':
                key, val = line.split(' = ')
                val = val.split('default=')[1]
                # remove the word "list" from val
                val = val.replace('list', '')
                # remove single quotes and parentheses from val
                val = val.replace("'", '').replace('(', '').replace(')', '')
                line = f'{key} = {val}'
            fp.write(f'  {line}')