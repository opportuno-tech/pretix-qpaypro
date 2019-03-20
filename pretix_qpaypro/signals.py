import logging
from collections import OrderedDict

from django.dispatch import receiver
from pretix.base.settings import settings_hierarkey
from pretix.base.signals import (
    register_global_settings, register_payment_providers,
)

from .formfields.settings import get_settings_form_fields

logger = logging.getLogger(__name__)


@receiver(register_payment_providers, dispatch_uid="payment_qpaypro")
def register_payment_provider(sender, **kwargs):
    from .payment import (
        QPayProSettingsHolder, QPayProCC, QPayProVisaEnCuotas
    )

    return [
        QPayProSettingsHolder,
        QPayProCC,
        QPayProVisaEnCuotas
    ]


settings_hierarkey.add_default('payment_qpaypro_method_creditcard', True, bool)


@receiver(register_global_settings, dispatch_uid='qpaypro_global_settings')
def register_global_setting(sender, **kwargs):
    return OrderedDict(get_settings_form_fields('payment_qpaypro_general_', False))
