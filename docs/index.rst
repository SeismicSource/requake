Requake
=======

Repeating earthquakes search and analysis.

:Copyright: 2021-2026 Claudio Satriano satriano@ipgp.fr
:Release: |release|
:Date:    |release date|
:Project Page: `GitHub`_

Description
-----------

Requake is a command line tool to search and analyse repeating earthquakes.

It can either scan an existing earthquake catalog to search for similar events,
or perform template matching on a continuous waveform stream.

Catalogs and waveforms can be read from local files or downloaded using
standard `FDSN web services <https://www.fdsn.org/webservices/>`_.

Requake is written in Python and uses `ObsPy <https://obspy.org>`_ as backend.

Commands are a verb followed by the object the verb acts on, as in
``requake print pairs``; they are described in :doc:`commands`.


.. toctree::
   :maxdepth: 2
   :caption: Start

   Home <self>
   installation
   running

.. toctree::
   :maxdepth: 2
   :caption: Using Requake

   commands
   configuration_file
   pager

.. toctree::
   :maxdepth: 2
   :caption: Analysis

   read_catalog
   scan_catalog
   pairs
   wfcache

.. toctree::
   :maxdepth: 2
   :caption: Results and reference

   catalogs_scans_builds
   database_schemas
   slip_models
   performances

.. toctree::
   :maxdepth: 2
   :caption: About

   changelog
   citing
   bibliography



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. links
.. _GitHub: https://github.com/seismicsource/requake