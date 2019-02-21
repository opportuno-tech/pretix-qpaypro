import hashlib
import json
import logging
import urllib.parse
from collections import OrderedDict
from datetime import timedelta

import requests
from django import forms
from django.core import signing
from django.http import HttpRequest
from django.template.loader import get_template
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils.http import urlquote
from django.utils.translation import pgettext, ugettext_lazy as _
from pretix.base.models import Event, OrderPayment, OrderRefund
from pretix.base.payment import BasePaymentProvider, PaymentException
from pretix.base.settings import SettingsSandbox
from pretix.helpers.urls import build_absolute_uri as build_global_uri
from pretix.multidomain.urlreverse import build_absolute_uri
from requests import HTTPError

from .settingsform import get_settings_form_fields

logger = logging.getLogger(__name__)


class QPayProSettingsHolder(BasePaymentProvider):
    identifier = 'QPayPro'
    verbose_name = _('QPayPro')
    is_enabled = False
    is_meta = True

    def __init__(self, event: Event):
        super().__init__(event)
        self.settings = SettingsSandbox('payment', 'qpaypro', event)

    def get_connect_url(self, request):
        request.session['payment_qpaypro_oauth_event'] = request.event.pk
        if 'payment_qpaypro_oauth_token' not in request.session:
            request.session['payment_qpaypro_oauth_token'] = get_random_string(32)
        return (
            "https://www.qpaypro.com/oauth2/authorize?client_id={}&redirect_uri={}"
            "&state={}&scope=payments.read+payments.write+refunds.read+refunds.write+profiles.read+organizations.read"
            "&response_type=code&approval_prompt=auto"
        ).format(
            self.settings.connect_client_id,
            urlquote(build_global_uri('plugins:pretix_qpaypro:oauth.return')),
            request.session['payment_qpaypro_oauth_token'],
        )

    def settings_content_render(self, request):
        if self.settings.connect_client_id and not self.settings.api_key:
            # Use QPayPro Connect
            if not self.settings.access_token:
                return (
                    "<p>{}</p>"
                    "<a href='{}' class='btn btn-primary btn-lg'>{}</a>"
                ).format(
                    _('To accept payments via QPayPro, you will need an account at QPayPro. By clicking on the '
                      'following button, you can either create a new QPayPro account connect pretix to an existing '
                      'one.'),
                    self.get_connect_url(request),
                    _('Connect with QPayPro')
                )
            else:
                return (
                    "<button formaction='{}' class='btn btn-danger'>{}</button>"
                ).format(
                    reverse('plugins:pretix_qpaypro:oauth.disconnect', kwargs={
                        'organizer': self.event.organizer.slug,
                        'event': self.event.slug,
                    }),
                    _('Disconnect from QPayPro')
                )

    @property
    def settings_form_fields(self):
        if (self.settings.connect_x_login and self.settings.connect_x_private_key and self.settings.connect_x_api_secret):
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
                     label=_('Visa en cuotas'),
                     required=False,
                 )),
            ] + list(super().settings_form_fields.items())
        )
        d.move_to_end('_enabled', last=False)
        return d


class QPayProMethod(BasePaymentProvider):
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
        return self.settings.get('_enabled', as_type=bool) and self.settings.get('method_{}'.format(self.method),
                                                                                 as_type=bool)

    def payment_refund_supported(self, payment: OrderPayment) -> bool:
        return self.refunds_allowed

    def payment_partial_refund_supported(self, payment: OrderPayment) -> bool:
        return self.refunds_allowed

    def payment_prepare(self, request, payment):
        return self.checkout_prepare(request, None)

    def payment_is_valid_session(self, request: HttpRequest):
        return True

    @property
    def request_headers(self):
        headers = {}
        if self.settings.connect_client_id and self.settings.access_token:
            headers['Authorization'] = 'Bearer %s' % self.settings.access_token
        else:
            headers['Authorization'] = 'Bearer %s' % self.settings.api_key
        return headers

    def payment_form_render(self, request) -> str:
        template = get_template('pretix_qpaypro/checkout_payment_form.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings}
        return template.render(ctx)

    def checkout_confirm_render(self, request) -> str:
        template = get_template('pretix_qpaypro/checkout_payment_confirm.html')
        ctx = {'request': request, 'event': self.event, 'settings': self.settings, 'provider': self}
        return template.render(ctx)

    def payment_can_retry(self, payment):
        return self._is_still_available(order=payment.order)

    def payment_pending_render(self, request, payment) -> str:
        if payment.info:
            payment_info = json.loads(payment.info)
        else:
            payment_info = None
        template = get_template('pretix_qpaypro/pending.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'provider': self,
            'order': payment.order,
            'payment': payment,
            'payment_info': payment_info,
        }
        return template.render(ctx)

    def payment_control_render(self, request, payment) -> str:
        if payment.info:
            payment_info = json.loads(payment.info)
        else:
            payment_info = None
        template = get_template('pretix_qpaypro/control.html')
        ctx = {
            'request': request,
            'event': self.event,
            'settings': self.settings,
            'payment_info': payment_info,
            'payment': payment,
            'method': self.method,
            'provider': self,
        }
        return template.render(ctx)

    def execute_refund(self, refund: OrderRefund):
        payment = refund.payment.info_data.get('id')
        body = {
            'amount': {
                'currency': self.event.currency,
                'value': str(refund.amount)
            },
        }
        if self.settings.connect_client_id and self.settings.access_token:
            body['testmode'] = self.settings.endpoint == 'test'
        try:
            print(self.request_headers, body)
            req = requests.post(
                'https://api.qpaypro.com/v2/payments/{}/refunds'.format(payment),
                json=body,
                headers=self.request_headers
            )
            req.raise_for_status()
            req.json()
        except HTTPError:
            logger.exception('QPayPro error: %s' % req.text)
            try:
                refund.info_data = req.json()
            except:
                refund.info_data = {
                    'error': True,
                    'detail': req.text
                }
            raise PaymentException(_('QPayPro reported an error: {}').format(refund.info_data.get('detail')))
        else:
            refund.done()

    def get_locale(self, language):
        pretix_to_qpaypro_locales = {
            'en': 'en_US',
            'nl': 'nl_NL',
            'nl_BE': 'nl_BE',
            'fr': 'fr_FR',
            'de': 'de_DE',
            'es': 'es_ES',
            'ca': 'ca_ES',
            'pt': 'pt_PT',
            'it': 'it_IT',
            'nb': 'nb_NO',
            'sv': 'sv_SE',
            'fi': 'fi_FI',
            'da': 'da_DK',
            'is': 'is_IS',
            'hu': 'hu_HU',
            'pl': 'pl_PL',
            'lv': 'lv_LV',
            'lt': 'lt_LT'
        }
        return pretix_to_qpaypro_locales.get(
            language,
            pretix_to_qpaypro_locales.get(
                language.split('-')[0],
                pretix_to_qpaypro_locales.get(
                    language.split('_')[0],
                    'en'
                )
            )
        )

    def _get_payment_body(self, payment):
        b = {
            'amount': {
                'currency': self.event.currency,
                'value': str(payment.amount),
            },
            'description': 'Order {}-{}'.format(self.event.slug.upper(), payment.full_id),
            'redirectUrl': build_absolute_uri(self.event, 'plugins:pretix_qpaypro:return', kwargs={
                'order': payment.order.code,
                'payment': payment.pk,
                'hash': hashlib.sha1(payment.order.secret.lower().encode()).hexdigest(),
            }),
            'webhookUrl': build_absolute_uri(self.event, 'plugins:pretix_qpaypro:webhook', kwargs={
                'payment': payment.pk
            }),
            'locale': self.get_locale(payment.order.locale),
            'method': self.method,
            'metadata': {
                'organizer': self.event.organizer.slug,
                'event': self.event.slug,
                'order': payment.order.code,
                'payment': payment.local_id,
            }
        }
        if self.settings.connect_client_id and self.settings.access_token:
            b['profileId'] = self.settings.connect_profile
            b['testmode'] = self.settings.endpoint == 'test'
        return b

    def execute_payment(self, request: HttpRequest, payment: OrderPayment):
        try:
            req = requests.post(
                'https://api.qpaypro.com/v2/payments',
                json=self._get_payment_body(payment),
                headers=self.request_headers
            )
            req.raise_for_status()
        except HTTPError:
            logger.exception('QPayPro error: %s' % req.text)
            try:
                payment.info_data = req.json()
            except:
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

        data = req.json()
        payment.info = json.dumps(data)
        payment.state = OrderPayment.PAYMENT_STATE_CREATED
        payment.save()
        request.session['payment_qpaypro_order_secret'] = payment.order.secret
        return self.redirect(request, data.get('_links').get('checkout').get('href'))

    def redirect(self, request, url):
        if request.session.get('iframe_session', False):
            signer = signing.Signer(salt='safe-redirect')
            return (
                    build_absolute_uri(request.event, 'plugins:pretix_qpaypro:redirect') + '?url=' +
                    urllib.parse.quote(signer.sign(url))
            )
        else:
            return str(url)

    def shred_payment_info(self, obj: OrderPayment):
        if not obj.info:
            return
        d = json.loads(obj.info)
        if 'details' in d:
            d['details'] = {
                k: '█' for k in d['details'].keys()
                if k not in ('bitcoinAmount', )
            }

        d['_shredded'] = True
        obj.info = json.dumps(d)
        obj.save(update_fields=['info'])


class QPayProCC(QPayProMethod):
    method = 'creditcard'
    verbose_name = _('Credit card via QPayPro')
    public_name = _('Credit card')


class QPayProVisaEnCuotas(QPayProMethod):
    method = 'visaencuotas'
    verbose_name = _('Visa en cuotas via QPayPro')
    public_name = _('Visa en cuotas')
