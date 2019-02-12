from django.conf.urls import include, url
from pretix.multidomain import event_url

from .views import (
    ReturnView, WebhookView, oauth_disconnect, oauth_return, redirect_view,
)

event_patterns = [
    url(r'^QPayPro/', include([
        event_url(r'^webhook/(?P<payment>[0-9]+)/$', WebhookView.as_view(), name='webhook', require_live=False),
        url(r'^redirect/$', redirect_view, name='redirect'),
        url(r'^return/(?P<order>[^/]+)/(?P<hash>[^/]+)/(?P<payment>[0-9]+)/$', ReturnView.as_view(), name='return'),
    ])),
]

urlpatterns = [
    url(r'^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/QPayPro/disconnect/',
        oauth_disconnect, name='oauth.disconnect'),
    url(r'^_qpaypro/oauth_return/$', oauth_return, name='oauth.return'),
]
