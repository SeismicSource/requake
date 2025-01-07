# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Function to convert data types.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""


def float_or_none(string):
    """
    Convert string to float, return None if conversion fails.

    :param string: Input string.
    :type string: str
    :return: Float value or None.
    :rtype: float or None
    """
    try:
        val = float(string)
    except (TypeError, ValueError):
        val = None
    return val


def int_or_none(string):
    """
    Convert string to int, return None if conversion fails.

    :param string: Input string.
    :type string: str
    :return: Integer value or None.
    :rtype: int or None
    """
    try:
        val = int(string)
    except (TypeError, ValueError):
        val = None
    return val
