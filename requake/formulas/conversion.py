# -*- coding: utf-8 -*-
"""
Function to convert data types.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
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
