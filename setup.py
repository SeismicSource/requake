# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""setup.py: setuptools control."""
from setuptools import setup, find_packages
import versioneer


with open('README.md', 'rb') as f:
    long_descr = f.read().decode('utf-8')

project_urls = {
    'Homepage': 'https://requake.seismicsource.org',
    'Source': 'https://github.com/SeismicSource/requake',
    'Documentation': 'https://requake.readthedocs.io'
}

setup(
    name='requake',
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'console_scripts': ['requake = requake.requake:main']
        },
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description='Repeating earthquakes search and analysis',
    long_description=long_descr,
    long_description_content_type='text/markdown',
    author='Claudio Satriano',
    author_email='satriano@ipgp.fr',
    url=project_urls['Homepage'],
    project_urls=project_urls,
    license='GNU General Public License v3 or later (GPLv3+)',
    platforms='OS Independent',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: '
            'GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Physics'],
    install_requires=[
        'scipy>=1.5.0', 'obspy>=1.2.0', 'argcomplete', 'tqdm', 'tabulate'],
    python_requires='>3.7'
    )
