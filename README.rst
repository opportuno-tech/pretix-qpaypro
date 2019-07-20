QPayPro payment integration for pretix
========================================

.. image:: https://img.shields.io/pypi/v/pretix-qpaypro.svg
   :target: https://pypi.python.org/pypi/pretix-qpaypro

.. image:: https://travis-ci.org/opportuno-tech/pretix-qpaypro.svg?branch=master
    :target: https://travis-ci.org/opportuno-tech/pretix-qpaypro

.. image:: https://hosted.weblate.org/widgets/pretix-qpaypro/-/svg-badge.svg
    :alt: Translation status
    :target: https://hosted.weblate.org/engage/pretix-qpaypro/?utm_source=widget


This is a plugin for `pretix`_ to be able to use the `qpaypro`_ payments provider. 

Development setup
-----------------

1. Make sure that you have a working `pretix development setup`_.

2. Clone this repository, eg to ``local/pretix-qpaypro``.

3. Activate the virtual environment you use for pretix development.

4. Execute ``python setup.py develop`` within this directory to register this application with pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local pretix server. You can now use the plugin from this repository for your events by enabling it in
   the 'plugins' tab in the settings.


Translations
------------

The language translations for this project are handled on Weblate.org, you can see the current status below.

.. image:: https://hosted.weblate.org/widgets/pretix-qpaypro/-/multi-blue.svg
    :alt: Translation status
    :target: https://hosted.weblate.org/engage/pretix-qpaypro/?utm_source=widget


License
-------

Copyright 2019 Opportuno Tech

Released under the terms of the Apache License 2.0


.. _pretix: https://github.com/pretix/pretix
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
.. _qpaypro: https://qpaypro.zendesk.com/hc/es
