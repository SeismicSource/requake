#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Main script for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
from ..rq_setup import configure, rq_exit


def main():
    config = configure()
    rq_exit(0)
