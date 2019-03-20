import logging

from django.conf import settings
from django.core import signing
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils.translation import ugettext_lazy as _

logger = logging.getLogger(__name__)


def onlinemetrix_view(request, *args, **kwargs):
    signer = signing.Signer(salt='safe-redirect')
    try:
        url_script = signer.unsign(request.GET.get('url_script', ''))
        url_iframe = signer.unsign(request.GET.get('url_iframe', ''))
        url_next = signer.unsign(request.GET.get('url_next', ''))
    except signing.BadSignature:
        return HttpResponseBadRequest(_('Invalid parameters'))

    r = render(request, 'pretix_qpaypro/onlinemetrix.html', {
        'url_script': url_script,
        'url_iframe': url_iframe,
        'url_next': url_next,
        'settings': settings,
    })
    r._csp_ignore = True
    return r
