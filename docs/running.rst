########
Running
########

Command line arguments
----------------------

Requake is based on a single executable, aptly named ``requake`` 😉.

For a summary of the commands, and for the options of each command,
use:

.. code-block::

   requake -h
   requake COMMAND -h


Requake supports command line tab completion for commands and arguments,
thanks to `argcomplete <https://kislyuk.github.io/argcomplete/>`_.
To enable command line tab completion run:

.. code-block::

   activate-global-python-argcomplete


(This is a one-time command that needs to be run only once).

Or, alternatively, add the following line to your ``.bashrc`` or ``.zshrc``:

.. code-block::

   eval "$(register-python-argcomplete requake)"


Finding a Command
-----------------

Typing ``requake`` with no arguments lists the verbs, and typing a verb
alone lists the objects it can act on:

.. code-block:: text

   requake
   requake plot

The commands are described one by one in :doc:`commands`; the sections
below show how to combine them in a real analysis.


Typical workflow
----------------

The first thing you will want to do is to generate a sample
:ref:`configuration_file`:

.. code-block::

   requake config sample


Edit the :ref:`configuration_file` according to your needs, then read or
download the event catalog:

.. code-block::

   requake read catalog


or

.. code-block::

   requake read catalog CATALOG_FILE


When relying on FDSN web services for waveform data, it is strongly
recommended to prefetch all waveform windows before running the scan.
This downloads every required waveform once and stores it in a local
SQLite cache, avoiding repeated downloads and dramatically reducing
overall runtime for large catalogs:

.. code-block::

   requake wfcache prefetch


Now, build the catalog of event pairs with:

.. code-block::

   requake scan catalog


Once done (:doc:`it will take time! <performances>`), flag the
duplicate events, if any (see :doc:`pairs`), so that they do not
inflate the families:

.. code-block::

   requake flag duplicates


Then, build the repeating earthquake families:

.. code-block::

   requake build families


Inspect the families with ``print families``, ``plot families`` and
``plot map`` (see :doc:`commands`).
