import datetime

from django import forms
from django.utils.translation import ugettext_lazy as _

from .custom_validators import CreditCardField

now = datetime.datetime.now()


def get_payment_form_fields():
    return [
        (
            'cc_type',
            forms.ChoiceField(
                label=_('Card Type'),
                required=True,
                initial='visa',
                choices=(
                    ('visa', _('Visa')),
                    ('mastercard', _('Mastercard')),
                ),
            )
        ),
        (
            'cc_number',
            CreditCardField(
                label=_('Credit Card Number'),
                required=True,
                placeholder=u'0000 0000 0000 0000',
                min_length=13,
                max_length=16
            )
        ),
        (
            'cc_exp_month',
            forms.IntegerField(
                label=_('Expiration Month'),
                required=True,
                max_value=12,
                min_value=1,
            )
        ),
        (
            'cc_exp_year',
            forms.IntegerField(
                label=_('Expiration Year'),
                required=True,
                max_value=now.year + 10,
                min_value=now.year,
                help_text=_('The full year should be provided, for example {0}.'.format(now.year)),
            )
        ),
        (
            'cc_cvv2',
            forms.IntegerField(
                label=_('CVV2'),
                required=True,
                max_value=9999,
                min_value=100,
                help_text=_('3 or 4 digits code usually found in the back of the card.'),
            )
        ),
        (
            'cc_first_name',
            forms.CharField(
                label=_('Cardholder\'s First Name'),
                required=True,
                max_length=50,
                help_text=_('Exactly as appears in the card.'),
            )
        ),
        (
            'cc_last_name',
            forms.CharField(
                label=_('Cardholder\'s Last Name'),
                required=True,
                max_length=50,
                help_text=_('Exactly as appears in the card.'),
            )
        ),
    ]
