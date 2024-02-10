# -*- coding: utf8 -*-
"""
Initialize requake package.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
