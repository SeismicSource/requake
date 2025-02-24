Installation
------------

Installing the latest release
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Using Anaconda
~~~~~~~~~~~~~~

The following command will automatically create an `Anaconda`_ environment
named ``requake``, install the required packages and install the latest
version of SourceSpec via `pip`:

.. code-block:: text

    conda env create --file https://raw.githubusercontent.com/SeismicSource/requake/main/requake_conda_env.yml


If you want a different name for your environment, use:

.. code-block:: text

    conda env create -n YOUR_ENV_NAME --file https://raw.githubusercontent.com/SeismicSource/requake/main/requake_conda_env.yml


Activate the environment with:

.. code-block:: text

    conda activate requake


(or ``conda activate YOUR_ENV_NAME``)

To keep Requake updated run the following command from within the environment:

.. code-block:: text

    pip install --upgrade requake


Or, to switch to a development snapshot, run:

.. code-block:: text

    pip install git+https://github.com/SeismicSource/requake.git


Using pip and PyPI
~~~~~~~~~~~~~~~~~~

The latest release of Requake is available on the `Python Package Index`_.

You can install it easily through ``pip``\ :

.. code-block:: text

   pip install requake


Installing a development snapshot
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you need a recent feature that is not in the latest release (see the
``unreleased`` section in the :ref:`changelog`), you want to use the more
recent development snapshot from the `Requake GitHub repository`_.

Using pip
~~~~~~~~~

The easiest way to install the most recent development snapshot is to download
and install it through ``pip``\ , using its builtin ``git`` client:

.. code-block:: text

   pip install git+https://github.com/SeismicSource/requake.git


Run this command again, from times to times, to keep Requake updated with
the development version.

Cloning the Requake GitHub repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to take a look at the source code (and possibly modify it 😉),
clone the project using ``git``\ :

.. code-block:: text

   git clone https://github.com/SeismicSource/requake.git


or, using SSH:

.. code-block:: text

   git clone git@github.com:SeismicSource/requake.git


(avoid using the "Download ZIP" option from the green "Code" button, since
version number is lost).

Then, go into the ``requake`` main directory and install the code in "editable
mode" by running:

.. code-block:: text

   pip install -e .


You can keep your local Requake repository updated by running ``git pull``
from times to times. Thanks to ``pip``\ 's "editable mode", you don't need to
reinstall Requake after each update.


.. Links:
.. _Anaconda: https://www.anaconda.com/download
.. _Python Package Index: https://pypi.org/project/requake/
.. _Requake GitHub repository: https://github.com/SeismicSource/requake