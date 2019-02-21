from django import forms
from django.utils.translation import ugettext_lazy as _


def get_settings_form_fields(prefix, required):
    return [
        (('{prefix}x_login').format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro Connect: Login'),
                required=required,
                help_text=_('{text1} <a target="_blank" rel="noopener" href="{docs_url}">{text2}</a>').format(
                    text1=_('Also referred to as \"Public Key\".'),
                    text2=_('Click here to access the API information.'),
                    docs_url='https://qpaypro.zendesk.com/hc/es/articles/115001625892-Manual-de-integración-de-pago-QPayPro-via-API-V1-0'
                ),
            )),
        (('{prefix}x_private_key').format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro Connect: Private Key'),
                required=required,
                max_length=32,
                min_length=11,
                help_text=_('Also referred to as \"API Key\".'),
            )),
        (('{prefix}x_api_secret').format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro Connect: API Secret'),
                required=required,
                max_length=32,
                min_length=11,
            )),
    ]