Installation
------------

Installing the latest release
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Using pip and PyPI (preferred method)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The latest release of Requake is available on the
`Python Package Index <https://pypi.org/project/requake/>`_.

You can install it easily through ``pip``\ :

.. code-block::

   pip install requake


Installing a development snapshot
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you need a recent feature that is not in the latest release (see the
``unreleased`` section in `CHANGELOG <CHANGELOG.md>`_\ ), you want to use the more
recent development snapshot from the
`Requake GitHub repository <https://github.com/SeismicSource/requake>`_.

Using pip
~~~~~~~~~

The easiest way to install the most recent development snapshot is to download
and install it through ``pip``\ , using its builtin ``git`` client:

.. code-block::

   pip install git+https://github.com/SeismicSource/requake.git


Run this command again, from times to times, to keep Requake updated with
the development version.

Cloning the Requake GitHub repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to take a look at the source code (and possibly modify it 😉),
clone the project using ``git``\ :

.. code-block::

   git clone https://github.com/SeismicSource/requake.git


or, using SSH:

.. code-block::

   git clone git@github.com:SeismicSource/requake.git


(avoid using the "Download ZIP" option from the green "Code" button, since
version number is lost).

Then, go into the ``requake`` main directory and install the code in "editable
mode" by running:

.. code-block::

   pip install -e .


You can keep your local Requake repository updated by running ``git pull``
from times to times. Thanks to ``pip``\ 's "editable mode", you don't need to
reinstall Requake after each update.