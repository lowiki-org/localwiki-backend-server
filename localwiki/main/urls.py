from django.conf.urls import *
from django.conf import settings
from django.contrib import admin
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.cache import cache_control

import pages
import maps
import redirects
import crap_comments
import dashboard
import links
import regions
import tags
from users.views import GlobalUserpageRedirectView
from utils.views import NamedRedirectView
from users.admin import SubscribedList

from api import load_api_handlers
# We load all of the api.py files right now.
# TODO: Change this once Django (1.6?) supports the
# apps_loaded signal.  Right now, we need to do this
# to avoid nasty circular imports.
load_api_handlers()
from api import router

admin.autodiscover()


urlpatterns = patterns('',
    # Mostly-static-ish content & the main page ("/")
    (r'^', include('main_content.urls')),

    # Blog
    (r'^blog/', include('blog.urls')),

    # Users / registration URLs
    (r'^(?i)Users/', include('users.urls')),

    # Follow-related URLs
    (r'^_follow/', include('follow.urls')),
    (r'^_stars/', include('stars.urls')),

    # Region routing URLs
    (r'^', include(regions.site.urls)),

    # API URLs
    url(r'^api/{0,1}$', RedirectView.as_view(url='/api/v4/', permanent=False)),
    url(r'^api/v4/', include(router.urls)),

    # Internal API URLs
    (r'^_api/', include('main.api.internal_urls')),

    # Comments
    (r'^_comment/(?P<region>[^/]+?)/', include(crap_comments.site.urls)),

    (r'^(?P<region>[^/]+?)/map$', NamedRedirectView.as_view(name='maps:global')),
    (r'^', include(maps.site.urls)),
    (r'^(?P<region>[^/]+?)/tags$', NamedRedirectView.as_view(name='tags:list')),
    (r'^', include(tags.site.urls)),
    (r'^_redirect/', include(redirects.site.urls)),
    (r'^_links/', include(links.site.urls)),
    (r'^', include('search.urls')),
    (r'^', include('activity.urls')),

    (r'^(?P<region>[^/]+?)/', include('explore.urls')),
    (r'^', include('explore.global_urls')),

    # Region userpage -> global userpage redirect
    (r'^(?P<region>[^/]+?)/((?i)Users)/(?P<username>[^/]+?)/*(?P<rest>(/[^/_]+)|)$', GlobalUserpageRedirectView.as_view()),

    # Historical URL for dashboard:
    (r'^(?P<region>[^/]+?)/tools/dashboard/?$', NamedRedirectView.as_view(name='dashboard:main')),
    (r'^_tools/dashboard/', include(dashboard.site.urls)),

    (r'^admin$', RedirectView.as_view(url='/admin/')),
    (r'^admin/subscribers/$', user_passes_test(lambda u: u.is_superuser)(SubscribedList.as_view())),
    (r'^admin/', include(admin.site.urls)),

    # Search engine sitemap
    # (Usually served via apache, but including here as well if using dev server)
    url(r'^sitemap.xml', include('static_sitemaps.urls')),

    (r'^', include('migrate.urls', 'migrate', 'migrate')),

    (r'^(?P<region>[^/]+?)/(((?i)Front[_ ]Page)/?)?', include('frontpage.urls')),

) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# This should only happen if you're using the local dev server with
# DEBUG=False.
if not settings.DEBUG:
    urlpatterns += patterns('',
        (r'^static/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.STATIC_ROOT}),
        (r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.MEDIA_ROOT}),
    )

# Fall back to pages.
urlpatterns += patterns('',
    (r'^(?P<region>[^/]+?)/', include(pages.site.urls)),
)

handler500 = 'utils.views.server_error'
