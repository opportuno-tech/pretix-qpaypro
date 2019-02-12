from django.apps import AppConfig
from django.utils.translation import ugettext_lazy


class PluginApp(AppConfig):
    name = 'pretix_qpaypro'
    verbose_name = 'QPayPro payment integration for pretix'

    class PretixPluginMeta:
        name = ugettext_lazy('QPayPro payment integration for pretix')
        author = 'Alvaro Enrique Ruano'
        description = ugettext_lazy('Integration for the QPayPro payment provider.')
        visible = True
        version = '1.0.0'

    def ready(self):
        from . import signals  # NOQA


default_app_config = 'pretix_qpaypro.PluginApp'
