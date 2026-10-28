# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Argument types and actions shared by the Requake command line.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import argparse


def nonnegative_int(value):
    """
    Return an integer greater than or equal to zero.

    :param value: the value given on the command line
    :type value: str
    :return: the value as an integer
    :rtype: int

    :raises argparse.ArgumentTypeError: if the value is not a
        non-negative integer
    """
    try:
        int_value = int(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(
            f'invalid non-negative integer value: {value}'
        ) from err
    if int_value < 0:
        raise argparse.ArgumentTypeError(
            f'invalid non-negative integer value: {value}'
        )
    return int_value


def timespec_to_sec(timespec):
    """
    Convert a time specification to seconds.

    :param timespec: Time specification, e.g., "10s", "3.3m", "2h", "1d",
                     "2M", "3y".
    :type timespec: str or None
    :return: Time in seconds.
    :rtype: float

    :raises ValueError: if the specification cannot be parsed
    """
    if timespec is None:
        return 1e999
    suffix = timespec[-1]
    time_in_seconds = float(timespec[:-1])
    if suffix == 's':
        time_in_seconds *= 1
    elif suffix == 'm':
        time_in_seconds *= 60
    elif suffix == 'h':
        time_in_seconds *= 60 * 60
    elif suffix == 'd':
        time_in_seconds *= 24 * 60 * 60
    elif suffix == 'M':
        time_in_seconds *= 30 * 24 * 60 * 60
    elif suffix == 'y':
        time_in_seconds *= 365 * 24 * 60 * 60
    else:
        raise ValueError(f'Invalid time specification: {timespec}')
    return time_in_seconds


class PrintFormatAction(argparse.Action):
    """
    Store the output format and disable the interactive pager.

    The pager draws the table with its own layout and ignores the
    requested output format, hence an explicitly requested format
    implies plain-text output.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        """Set the output format and disable the pager."""
        setattr(namespace, self.dest, values)
        setattr(namespace, 'no_pager', True)


def hide_aliases(action, *aliases):
    """
    Mark option strings as hidden, so that help does not show them.

    The aliases stay on the command line, so that the option spellings
    already in use keep working; only the help output changes.

    :param action: an argparse action
    :type action: argparse.Action
    :param aliases: the option strings to hide
    :type aliases: str
    """
    action.hidden_aliases = aliases
    return action
