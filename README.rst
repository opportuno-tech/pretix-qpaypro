QPayPro payment integration for pretix
==========================

.. image:: https://gitlab.com/aruanoguate/pretix-qpaypro/badges/master/pipeline.svg
   :target: https://gitlab.com/aruanoguate/pretix-qpaypro/commits/master

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


License
-------

Copyright 2019 Alvaro Enrique Ruano

Released under the terms of the Apache License 2.0


.. _pretix: https://github.com/pretix/pretix
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
.. _qpaypro: https://qpaypro.zendesk.com/hc/es
