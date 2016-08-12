from django.conf.urls import *

from migrate.views import RegionPageMigrateView


urlpatterns = patterns('',
    url(r'^(?P<region>[^/]+?)/_import/?$', RegionPageMigrateView.as_view(), name="regions"),
)
