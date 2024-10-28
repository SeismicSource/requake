Requake
=======

Repeating earthquakes search and analysis.

:Copyright: 2021-2024 Claudio Satriano satriano@ipgp.fr
:Release: |release|
:Date:    |release date|

Description
-----------

Requake is a command line tool to search and analyse repeating earthquakes.

It can either scan an existing earthquake catalog to search for similar events,
or perform template matching on a continuous waveform stream.

Catalogs and waveforms can be read from local files or downloaded using
standard `FDSN web services <https://www.fdsn.org/webservices/>`_.

Requake is written in Python and uses `ObsPy <https://obspy.org>`_ as backend.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   running
   performances
   slip_models
   configuration_file
   changelog
   citing
   bibliography



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
