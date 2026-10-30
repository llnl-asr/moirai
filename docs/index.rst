.. moirai documentation master file.

===============================================================================
moirai: data provenance for HPC applications, traced by dftracer.
===============================================================================

moirai records where an application's data comes from and where it goes:
the entities it works with (files, datasets, models, buffers), what each
activity used, generated, invalidated or updated, and how entities relate
to each other. It runs `dftracer <https://dftracer.readthedocs.io>`_
underneath it, configured for provenance, so the records land in dftracer
traces next to the application's I/O.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   overview
   build
   api
   configuration
   running
   trace_format

.. toctree::
   :maxdepth: 2
   :caption: Contributing

   developer-guide
   testing

.. toctree::
   :maxdepth: 1
   :caption: Links:

   GitHub <https://github.com/llnl-asr/moirai>
   dftracer Documentation <https://dftracer.readthedocs.io>
   dftracer GitHub <https://github.com/llnl-asr/dftracer>

==================
Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
