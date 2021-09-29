# -*- coding: utf-8 -*-
"""setup.py: setuptools control."""
from setuptools import setup
import versioneer

with open('README.md', 'rb') as f:
    long_descr = f.read().decode('utf-8')


setup(
    name='requake',
    packages=['requake', 'requake.scripts', 'requake.configobj'],
    include_package_data=True,
    entry_points={
        'console_scripts': ['requake = requake.scripts.requake:main']
        },
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description='Repeating earthquakes search and analysis',
    long_description=long_descr,
    long_description_content_type='text/markdown',
    author='Claudio Satriano',
    author_email='satriano@ipgp.fr',
    url='http://www.ipgp.fr/~satriano',
    license='CeCILL Free Software License Agreement, Version 2.1',
    platforms='OS Independent',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: CEA CNRS Inria Logiciel Libre '
            'License, version 2.1 (CeCILL-2.1)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Physics'],
    install_requires=['obspy>=1.2.0', 'argcomplete', 'tqdm'],
    python_requires='>3.7'
    )
