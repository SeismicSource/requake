Running
-------

Command line arguments
^^^^^^^^^^^^^^^^^^^^^^

Requake is based on a single executable, aptly named ``requake`` 😉.

To get help, use:

.. code-block::

   requake -h


The different running modes are specified as "verbs" (positional arguments).
Currently supported verbs are:

.. code-block:: text

   sample_config       write sample config file to current directory and exit
   read_catalog        read an event catalog from web services or from a file
   scan_catalog        scan an existing catalog for earthquake pairs
   plot_pair           plot traces for a given event pair
   build_families      build families of repeating earthquakes from a catalog
                       of pairs
   print_families      print families to screen
   plot_families       plot traces for one ore more event families
   plot_timespans      plot family timespans
   plot_cumulative     cumulative plot for one or more families
   map_families        plot families on a map
   flag_family         flag a family of repeating earthquakes as valid or not
                       valid. Note that all families are valid by default
                       when first created
   build_templates     build waveform templates for one or more event
                       families
   scan_templates      scan a continuous waveform stream using one or more
                       templates


Certain running modes (e.g., ``plot_pair``\ ) require further arguments (use, e.g.,
``requake plot_pair -h`` to get help).

Requake supports command line tab completion for arguments, thanks to
`argcomplete <https://kislyuk.github.io/argcomplete/>`_.
To enable command line tab completion, add the following line to your ``.bashrc``
or ``.zshrc``\ :

.. code-block::

   eval "$(register-python-argcomplete requake)"


Typical workflow
^^^^^^^^^^^^^^^^

The first thing you will want to do is to generate a sample config file:

.. code-block::

   requake sample_config


Edit the config file according to your needs, then read or download the event
catalog:

.. code-block::

   requake read_catalog


or

.. code-block::

   requake read_catalog CATALOG_FILE


Now, build the catalog of event pairs with:

.. code-block::

   requake scan_catalog


Once done (\ `it will take time! <performances.html#performances>`_\ ), you are ready to build
repeating earthquake families:

.. code-block::

   requake build_families

