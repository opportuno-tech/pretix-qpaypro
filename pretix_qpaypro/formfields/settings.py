from django import forms
from django.utils.translation import ugettext_lazy as _


def get_settings_form_fields(prefix, required):
    return [
        (
            '{prefix}x_login'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Login'),
                required=required,
                help_text='{text1} <a target="_blank" rel="noopener" href="{docs_url}">{text2}</a>'.format(
                    text1=_('Also referred to as \"Public Key\".'),
                    text2=_('Click here to access the API information.'),
                    docs_url='https://qpaypro.zendesk.com/hc/es/articles/115001625892-Manual-de-integración-de-pago-QPayPro-via-API-V1-0'
                ),
            )
        ),
        (
            '{prefix}x_private_key'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Private Key'),
                required=required,
                max_length=32,
                min_length=11,
                help_text=_('Also referred to as \"API Key\".'),
            )
        ),
        (
            '{prefix}x_api_secret'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: API Secret'),
                required=required,
                max_length=32,
                min_length=11,
            )
        ),
        (
            '{prefix}x_endpoint'.format(
                prefix=prefix
            ),
            forms.ChoiceField(
                label=_('QPayPro: Endpoint'),
                required=required,
                initial='sandbox',
                choices=(
                    ('sandbox', _('Sandbox')),
                    ('live', _('Live')),
                ),
            )
        ),
        (
            '{prefix}x_org_id'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Org ID'),
                required=required,
                max_length=8,
                min_length=8,
                help_text='{text1} <a target="_blank" rel="noopener" href="{docs_url}">{text2}</a>'.format(
                    text1=_('Required to generate client device fingerprint.'),
                    text2=_('Click here to access the associated documentation.'),
                    docs_url='https://qpaypro.zendesk.com/hc/es/articles/115002159651-Device-Fingerprint'
                ),
            )
        ),
        (
            '{prefix}x_country'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Default Country'),
                required=required,
            )
        ),
        (
            '{prefix}x_state'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Default State'),
                required=required,
            )
        ),
        (
            '{prefix}x_city'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Default City'),
                required=required,
            )
        ),
        (
            '{prefix}x_zip'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Default Zip Code'),
                required=False,
            )
        ),
        (
            '{prefix}x_address'.format(
                prefix=prefix
            ),
            forms.CharField(
                label=_('QPayPro: Default Address'),
                required=required,
            )
        ),
    ]
