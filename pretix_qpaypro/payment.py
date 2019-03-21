import logging
import urllib.parse
from collections import OrderedDict
from datetime import datetime

import requests
from django import forms
from django.core import signing
from django.http import HttpRequest
from django.template.loader import get_template
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy as _
from pretix.base.models import Event, OrderPayment, Quota
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.settings import SettingsSandbox
from pretix.multidomain.urlreverse import build_absolute_uri, eventreverse
from requests import HTTPError

from .formfields.custom_validators import mask_cc_number
from .formfields.payment import get_payment_form_fields
from .formfields.settings import get_settings_form_fields

logger = logging.getLogger(__name__)


class QPayProSettingsHolder(BasePaymentProvider):
    identifier = 'qpaypro'
    verbose_name = _('QPayPro')
    is_enabled = False
    is_meta = True
    url_onlinemetrix = 'https://h.online-metrix.net'

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'qpaypro', event)

    @property
    def were_general_settings_provided(self):
        return bool(self.settings.general_x_login
                    and self.settings.general_x_private_key
                    and self.settings.general_x_api_secret
                    and self.settings.general_x_endpoint
                    and self.settings.general_x_org_id
                    and self.settings.general_x_country
                    and self.settings.general_x_state
                    and self.settings.general_x_city
                    and self.settings.general_x_address)

    @property
    def settings_form_fields(self):
        if (self.were_general_settings_provided):
            fields = []
        else:
            fields = get_settings_form_fields('', True)
        d = OrderedDict(
            fields + [
                ('method_creditcard',
                 forms.BooleanField(
                     label=_('Credit card'),
                     required=False,
                 )),
                ('method_visaencuotas',
                 forms.BooleanField(
                     label=_('Monthly payments'),
                     required=False,
                 )),
            ] + list(super().settings_form_fields.items())
        )
        d.move_to_end('_enabled', last=False)
        return d

    def get_settings_key(self, key):
        if (self.were_general_settings_provided):
            key = 'general_{0}'.format(key)
        return self.settings.get(key)


class QPayProMethod(QPayProSettingsHolder):
    method = ''
    abort_pending_allowed = False
    refunds_allowed = True

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'qpaypro', event)

    @property
    def settings_form_fields(self):
        return {}

    @property
    def identifier(self):
        return 'qpaypro_{}'.format(self.method)

    @property
    def is_enabled(self) -> bool:
        return (
            self.settings.get('_enabled', as_type=bool)
            and self.settings.get('method_{}'.format(self.method), as_type=bool)
        )

    def _fingerprint_prepare(self, request, url_next):
        if not super().checkout_prepare(request, None):
            return False

        # Device fingerprint session id
        session_onlinemetrix_key = self.get_payment_key_prefix() + 'session_onlinemetrix'
        if not request.session.get(session_onlinemetrix_key, False):
            request.session[session_onlinemetrix_key] = get_random_string(32)

        # Device fingerprint URLs
        params = 'org_id={x_org_id}&session_id={x_login}{session_id}'.format(
            x_org_id=self.get_settings_key('x_org_id'),
            x_login=self.get_settings_key('x_login'),
            session_id=request.session.get(session_onlinemetrix_key, '')
        )
        url_script = '{url}/fp/tags.js?{params}'.format(
            url=self.url_onlinemetrix,
            params=params,
        )
        url_iframe = '{url}/fp/tags?{params}'.format(
            url=self.url_onlinemetrix,
            params=params,
        )

        # Final URL using the result of all the previous steps
        signer = signing.Signer(salt='safe-redirect')
        url_final = (
            eventreverse(self.event, 'plugins:pretix_qpaypro:onlinemetrix') + '?'
            + 'url_script=' + urllib.parse.quote(signer.sign(url_script)) + '&'
            + 'url_iframe=' + urllib.parse.quote(signer.sign(url_iframe)) + '&'
            + 'url_next=' + urllib.parse.quote(signer.sign(url_next))
        )
        return url_final

    def payment_prepare(self, request, payment):
        url_next = eventreverse(self.event, 'presale:event.order.pay.confirm', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret,
            'payment': payment.pk
        })
        return self._fingerprint_prepare(request, url_next)

    def checkout_prepare(self, request, cart):
        url_next = eventreverse(self.event, 'presale:event.checkout', kwargs={
            'step': 'confirm',
        })
        return self._fingerprint_prepare(request, url_next)

    def get_payment_key_prefix(self):
        return 'payment_{0}_'.format(self.identifier)

    def payment_is_valid_session(self, request: HttpRequest):
        key_prefix = self.get_payment_key_prefix()
        return (
            request.session.get(key_prefix + 'cc_type', '') != ''
            and request.session.get(key_prefix + 'cc_number', '') != ''
            and request.session.get(key_prefix + 'cc_exp_month', '') != ''
            and request.session.get(key_prefix + 'cc_exp_year', '') != ''
            and request.session.get(key_prefix + 'cc_cvv2', '') != ''
            and request.session.get(key_prefix + 'cc_first_name', '') != ''
            and request.session.get(key_prefix + 'cc_last_name', '') != ''
            and request.session.get(key_prefix + 'session_onlinemetrix', '') != ''
        )

    @property
    def payment_form_fields(self):
        return OrderedDict(get_payment_form_fields())

    def payment_form_render(self, request) -> str:
        template = get_template('pretix_qpaypro/checkout_payment_form.html')
        ctx = {
            'form': self.payment_form(request),
        }
        return template.render(ctx)

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretix_qpaypro/checkout_payment_confirm.html')
        key_prefix = self.get_payment_key_prefix()
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'provider': self,
            'cc_type': request.session[key_prefix + 'cc_type'].upper(),
            'cc_number': mask_cc_number(request.session[key_prefix + 'cc_number']),
            'cc_exp_month': request.session[key_prefix + 'cc_exp_month'],
            'cc_exp_year': request.session[key_prefix + 'cc_exp_year'],
            'cc_first_name': request.session[key_prefix + 'cc_first_name'],
            'cc_last_name': request.session[key_prefix + 'cc_last_name'],
        }
        return template.render(ctx)

    def _get_payment_body(self, request: HttpRequest, payment: OrderPayment):
        key_prefix = self.get_payment_key_prefix()

        # Get a complete list of the cart contents
        x_line_item = ''
        for line in payment.order.positions.all():
            x_line_item += '{description}<|>{code}<|>{quantity}<|>{value}<|>'.format(
                description=line.item.name,
                code=line.item.name,
                quantity='1',
                value=line.price,
            )

        # Get the order page for relay URL
        x_relay_url = build_absolute_uri(self.event, 'presale:event.order', kwargs={
            'order': payment.order.code,
            'secret': payment.order.secret
        }) + '?paid=yes'

        # Generate all the transaction body
        b = {
            'x_login': self.get_settings_key('x_login'),
            'x_private_key': self.get_settings_key('x_private_key'),
            'x_api_secret': self.get_settings_key('x_api_secret'),
            'x_description': 'Order {} - {}'.format(self.event.slug.upper(), payment.full_id),
            'x_amount': str(payment.amount),
            'x_currency_code': self.event.currency,
            'x_product_id': payment.order.code,
            'x_audit_number': payment.order.code,
            'x_line_item': x_line_item,
            'x_email': payment.order.email,
            'x_fp_sequence': payment.order.code,
            'x_fp_timestamp': str(datetime.now()),
            'x_invoice_num': payment.order.code,
            'x_first_name': request.session.get(key_prefix + 'cc_first_name', ''),
            'x_last_name': request.session.get(key_prefix + 'cc_last_name', ''),
            'x_company': 'C/F',
            'x_address': self.get_settings_key('x_address'),
            'x_city': self.get_settings_key('x_city'),
            'x_state': self.get_settings_key('x_state'),
            'x_zip': self.get_settings_key('x_zip'),
            'x_country': self.get_settings_key('x_country'),
            'x_relay_response': 'TRUE',
            'x_relay_url': x_relay_url,
            'x_type': 'AUTH_ONLY',
            'x_method': 'CC',
            'visaencuotas': 0,
            'cc_number': request.session.get(key_prefix + 'cc_number', ''),
            'cc_exp': '{}/{}'.format(
                request.session.get(key_prefix + 'cc_exp_month', ''),
                str(request.session.get(key_prefix + 'cc_exp_year', ''))[-2:]
            ),
            'cc_cvv2': request.session.get(key_prefix + 'cc_cvv2', ''),
            'cc_name': '{} {}'.format(
                request.session.get(key_prefix + 'cc_first_name', ''),
                request.session.get(key_prefix + 'cc_last_name', ''),
            ),
            'cc_type': request.session.get(key_prefix + 'cc_type', ''),
            'device_fingerprint_id': request.session.get(key_prefix + 'session_onlinemetrix', ''),
        }
        return b

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            # Get the correct endpoint to consume
            x_endpoint = self.get_settings_key('x_endpoint')
            if x_endpoint == 'live':
                url = 'https://payments.qpaypro.com/checkout/api_v1'
            else:
                url = 'https://sandbox.qpaypro.com/payment/api_v1'

            # Get the message body
            payment_body = self._get_payment_body(request, payment)

            # # To save the information befor send
            # # TO DO: to delete this action because of security issues
            # payment.order.log_action('pretix.event.order.payment.started', {
            #     'local_id': payment.local_id,
            #     'provider': payment.provider,
            #     'data': payment_body
            # })

            # Perform the call to the endpoint
            req = requests.post(
                url,
                json=payment_body,
            )
            req.raise_for_status()

            # Load the response to be read
            data = req.json()

            # The result is evaluated to determine the next step
            if not (data['result'] == 1 and data['responseCode'] == 100):
                raise PaymentException(data['responseText'])

            # To save the result
            payment.info = req.json()
            payment.confirm()
        except (HTTPError, PaymentException, Quota.QuotaExceededException):
            logger.exception('QPayPro error: %s' % req.text)
            try:
                payment.info_data = req.json()
            except Exception:
                payment.info_data = {
                    'error': True,
                    'detail': req.text
                }
            payment.state = OrderPayment.PAYMENT_STATE_FAILED
            payment.save()
            payment.order.log_action('pretix.event.order.payment.failed', {
                'local_id': payment.local_id,
                'provider': payment.provider,
                'data': payment.info_data
            })
            raise PaymentException(_('We had trouble communicating with QPayPro. Please try again and get in touch '
                                     'with us if this problem persists.'))

        return None


class QPayProCC(QPayProMethod):
    method = 'creditcard'
    verbose_name = _('Credit card via QPayPro')
    public_name = _('Credit card')


class QPayProVisaEnCuotas(QPayProMethod):
    method = 'visaencuotas'
    verbose_name = _('Monthly payments via QPayPro')
    public_name = _('Monthly payments')
