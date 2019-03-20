from django.conf.urls import include, url

from .views import onlinemetrix_view

event_patterns = [
    url(r'^qpaypro/', include([
        url(r'^onlinemetrix/$', onlinemetrix_view, name='onlinemetrix'),
    ])),
]
