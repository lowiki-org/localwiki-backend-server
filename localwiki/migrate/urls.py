from django.conf.urls import *

from migrate.views import RegionPageMigrateView, RegionPageExportView


urlpatterns = patterns('',
    url(r'^(?P<region>[^/]+?)/_import/?$', RegionPageMigrateView.as_view(), name="regions"),
    url(r'^(?P<region>[^/]+?)/_export/?$', RegionPageExportView.as_view(), name="export"),
)
