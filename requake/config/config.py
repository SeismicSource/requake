# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Config class for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""


class Config(dict):
    """A class to access config values with dot notation."""

    def __setitem__(self, key, value):
        """Make Config keys accessible as attributes."""
        super().__setattr__(key, value)
        super().__setitem__(key, value)

    def __getattr__(self, key):
        """Make Config keys accessible as attributes."""
        try:
            return self.__getitem__(key)
        except KeyError as err:
            raise AttributeError(err) from err

    __setattr__ = __setitem__
