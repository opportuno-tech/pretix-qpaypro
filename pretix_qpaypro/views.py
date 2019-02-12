import hashlib
import json
import logging
import time
from decimal import Decimal

import requests
from django.contrib import messages
from django.core import signing
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pretix.base.models import Event, Order, OrderPayment, Quota
from pretix.base.payment import PaymentException
from pretix.base.services.locking import LockTimeoutException
from pretix.base.settings import GlobalSettingsObject
from pretix.control.permissions import event_permission_required
from pretix.helpers.urls import build_absolute_uri
from pretix.multidomain.urlreverse import eventreverse
from requests import HTTPError

logger = logging.getLogger(__name__)


@xframe_options_exempt
def redirect_view(request, *args, **kwargs):
    signer = signing.Signer(salt='safe-redirect')
    try:
        url = signer.unsign(request.GET.get('url', ''))
    except signing.BadSignature:
        return HttpResponseBadRequest('Invalid parameter')

    r = render(request, 'pretix_qpaypro/redirect.html', {
        'url': url,
    })
    r._csp_ignore = True
    return r


def oauth_return(request, *args, **kwargs):
    if 'payment_qpaypro_oauth_event' not in request.session:
        messages.error(request, _('An error occurred during connecting with QPayPro, please try again.'))
        return redirect(reverse('control:index'))

    event = get_object_or_404(Event, pk=request.session['payment_qpaypro_oauth_event'])

    if request.GET.get('state') != request.session['payment_qpaypro_oauth_token']:
        messages.error(request, _('An error occurred during connecting with QPayPro, please try again.'))
        return redirect(reverse('control:event.settings.payment.provider', kwargs={
            'organizer': event.organizer.slug,
            'event': event.slug,
            'provider': 'QPayPro'
        }))

    gs = GlobalSettingsObject()

    try:
        resp = requests.post('https://api.qpaypro.com/oauth2/tokens', auth=(
            gs.settings.payment_qpaypro_connect_client_id,
            gs.settings.payment_qpaypro_connect_client_secret
        ), data={
            'grant_type': 'authorization_code',
            'code': request.GET.get('code'),
            'redirect_uri': build_absolute_uri('plugins:pretix_qpaypro:oauth.return'),
        })
        resp.raise_for_status()
        data = resp.json()

        if 'error' not in data:
            orgaresp = requests.get('https://api.qpaypro.com/v2/organizations/me', headers={
                'Authorization': 'Bearer ' + data.get('access_token')
            })
            orgaresp.raise_for_status()
            orgadata = orgaresp.json()

            profilesurl = 'https://api.qpaypro.com/v2/profiles'
            profiles = []
            while profilesurl:
                profilesresp = requests.get(profilesurl, headers={
                    'Authorization': 'Bearer ' + data.get('access_token')
                })
                profilesresp.raise_for_status()
                d = profilesresp.json()
                profiles += d['_embedded']['profiles']
                if d['_links']['next']:
                    profilesurl = d['_links']['next']['href']
                else:
                    profilesurl = None
    except:
        logger.exception('Failed to obtain OAuth token')
        messages.error(request, _('An error occurred during connecting with QPayPro, please try again.'))
    else:
        if 'error' in data:
            messages.error(request, _('QPayPro returned an error: {}').format(data['error_description']))
        elif not profiles:
            messages.error(request, _('Please create a website profile in your QPayPro account and try again.'))
        elif not orgadata.get('id', '') or not orgadata.get('name', ''):
            messages.error(request, _('Please fill in your company details in your QPayPro account and try again.'))
        else:
            messages.success(request,
                             _('Your QPayPro account is now connected to pretix. You can change the settings in '
                               'detail below.'))
            event.settings.payment_qpaypro_access_token = data['access_token']
            event.settings.payment_qpaypro_refresh_token = data['refresh_token']
            event.settings.payment_qpaypro_expires = time.time() + data['expires_in']
            event.settings.payment_qpaypro_connect_org_id = orgadata.get('id')
            event.settings.payment_qpaypro_connect_org_name = orgadata.get('name', '')
            event.settings.payment_qpaypro_connect_profiles = [
                [
                    p.get('id'),
                    p.get('name') + ' - ' + p.get('website', '')
                ] for p in profiles
            ]
            event.settings.payment_qpaypro_connect_profile = profiles[0].get('id')

            if request.session.get('payment_qpaypro_oauth_enable', False):
                event.settings.payment_qpaypro__enabled = True
                del request.session['payment_qpaypro_oauth_enable']

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': event.organizer.slug,
        'event': event.slug,
        'provider': 'QPayPro'
    }))


def handle_payment(payment, qpaypro_id):
    pprov = payment.payment_provider
    if pprov.settings.connect_client_id and pprov.settings.access_token and pprov.settings.endpoint == "test":
        qp = 'testmode=true'
    else:
        qp = ''
    try:
        resp = requests.get(
            'https://api.qpaypro.com/v2/payments/' + qpaypro_id + '?' + qp,
            headers=pprov.request_headers
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get('amountRefunded') and data.get('status') == 'paid':
            refundsresp = requests.get(
                'https://api.qpaypro.com/v2/payments/' + qpaypro_id + '/refunds?' + qp,
                headers=pprov.request_headers
            )
            refundsresp.raise_for_status()
            refunds = refundsresp.json()['_embedded']['refunds']
        else:
            refunds = []

        if data.get('status') == 'paid':
            chargebacksresp = requests.get(
                'https://api.qpaypro.com/v2/payments/' + qpaypro_id + '/chargebacks?' + qp,
                headers=pprov.request_headers
            )
            chargebacksresp.raise_for_status()
            chargebacks = chargebacksresp.json()['_embedded']['chargebacks']
        else:
            chargebacks = []

        payment.info = json.dumps(data)
        payment.save()

        if payment.state in (OrderPayment.PAYMENT_STATE_CREATED, OrderPayment.PAYMENT_STATE_PENDING):
            if data.get('status') == 'canceled':
                payment.state = OrderPayment.PAYMENT_STATE_CANCELED
                payment.save()
                payment.order.log_action('pretix_qpaypro.event.canceled')
            elif data.get('status') == 'pending' and payment.state == OrderPayment.PAYMENT_STATE_CREATED:
                payment.state = OrderPayment.PAYMENT_STATE_PENDING
                payment.save()
            elif data.get('status') in ('expired', 'failed'):
                payment.state = OrderPayment.PAYMENT_STATE_CANCELED
                payment.save()
                payment.order.log_action('pretix_qpaypro.event.' + data.get('status'))
            elif data.get('status') == 'paid':
                payment.order.log_action('pretix_qpaypro.event.paid')
                payment.confirm()
        elif payment.state == OrderPayment.PAYMENT_STATE_CONFIRMED:
            known_refunds = [r.info_data.get('id') for r in payment.refunds.all()]
            for r in refunds:
                if r.get('status') != 'failed' and r.get('id') not in known_refunds:
                    payment.create_external_refund(
                        amount=Decimal(r['amount']['value']),
                        info=json.dumps(r)
                    )
            for r in chargebacks:
                if r.get('id') not in known_refunds:
                    payment.create_external_refund(
                        amount=Decimal(r['amount']['value']),
                        info=json.dumps(r)
                    )
    except HTTPError:
        raise PaymentException(_('We had trouble communicating with QPayPro. Please try again and get in touch '
                                 'with us if this problem persists.'))


@event_permission_required('can_change_event_settings')
@require_POST
def oauth_disconnect(request, **kwargs):
    del request.event.settings.payment_qpaypro_access_token
    del request.event.settings.payment_qpaypro_refresh_token
    del request.event.settings.payment_qpaypro_expires
    del request.event.settings.payment_qpaypro_connect_org_id
    del request.event.settings.payment_qpaypro_connect_org_name
    del request.event.settings.payment_qpaypro_connect_profiles
    request.event.settings.payment_qpaypro__enabled = False
    messages.success(request, _('Your QPayPro account has been disconnected.'))

    return redirect(reverse('control:event.settings.payment.provider', kwargs={
        'organizer': request.event.organizer.slug,
        'event': request.event.slug,
        'provider': 'QPayPro'
    }))


class QPayProOrderView:
    def dispatch(self, request, *args, **kwargs):
        try:
            self.order = request.event.orders.get(code=kwargs['order'])
            if hashlib.sha1(self.order.secret.lower().encode()).hexdigest() != kwargs['hash'].lower():
                raise Http404('')
        except Order.DoesNotExist:
            # Do a hash comparison as well to harden timing attacks
            if 'abcdefghijklmnopq'.lower() == hashlib.sha1('abcdefghijklmnopq'.encode()).hexdigest():
                raise Http404('')
            else:
                raise Http404('')
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def payment(self):
        return get_object_or_404(self.order.payments,
                                 pk=self.kwargs['payment'],
                                 provider__startswith='QPayPro')

    @cached_property
    def pprov(self):
        return self.payment.payment_provider


@method_decorator(xframe_options_exempt, 'dispatch')
class ReturnView(QPayProOrderView, View):
    def get(self, request, *args, **kwargs):
        if self.payment.state not in (OrderPayment.PAYMENT_STATE_CONFIRMED, OrderPayment.PAYMENT_STATE_FAILED,
                                      OrderPayment.PAYMENT_STATE_CANCELED):
            try:
                handle_payment(self.payment, self.payment.info_data.get('id'))
            except LockTimeoutException:
                messages.error(self.request, _('We received your payment but were unable to mark your ticket as '
                                               'the server was too busy. Please check beck in a couple of '
                                               'minutes.'))
            except Quota.QuotaExceededException:
                messages.error(self.request, _('We received your payment but were unable to mark your ticket as '
                                               'paid as one of your ordered products is sold out. Please contact '
                                               'the event organizer for further steps.'))
        return self._redirect_to_order()

    def _redirect_to_order(self):
        if self.request.session.get('payment_qpaypro_order_secret') != self.order.secret:
            messages.error(self.request, _('Sorry, there was an error in the payment process. Please check the link '
                                           'in your emails to continue.'))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        return redirect(eventreverse(self.request.event, 'presale:event.order', kwargs={
            'order': self.order.code,
            'secret': self.order.secret
        }) + ('?paid=yes' if self.order.status == Order.STATUS_PAID else ''))


@method_decorator(csrf_exempt, 'dispatch')
class WebhookView(View):
    def post(self, request, *args, **kwargs):
        try:
            handle_payment(self.payment, request.POST.get('id'))
        except LockTimeoutException:
            return HttpResponse(status=503)
        except Quota.QuotaExceededException:
            pass
        return HttpResponse(status=200)

    @cached_property
    def payment(self):
        return get_object_or_404(OrderPayment.objects.filter(order__event=self.request.event),
                                 pk=self.kwargs['payment'],
                                 provider__startswith='QPayPro')
