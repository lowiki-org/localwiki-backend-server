# coding=utf-8
import copy
from dateutil.parser import parse as dateparser
from operator import attrgetter

from django.conf import settings
from django.views.generic import DetailView, ListView
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.http import HttpResponseNotFound
from django.db.models import Q
from django.db import IntegrityError
from django.views.generic.list import BaseListView
from olwidget.widgets import InfoMap as OLInfoMap
from django.contrib.gis.geos.polygon import Polygon
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.utils.translation import ugettext as _
from django.contrib.gis.measure import D
from django.utils.safestring import mark_safe
from django.utils.html import escape

from versionutils import diff
from utils.views import (Custom404Mixin, CreateObjectMixin, JSONResponseMixin,
                         JSONView, PermissionRequiredMixin, DeleteView, RevertView)
from utils.urlresolvers import reverse
from versionutils.versioning.views import UpdateView
from versionutils.versioning.views import VersionsList
from pages.models import Page, slugify, name_to_url, page_url
from regions.views import RegionMixin, region_404_response
from regions.models import Region
from users.views import AddContributorsMixin
from localwiki.utils.views import CacheMixin

from .widgets import Map, InfoLayer, InfoMap, map_options_for_region
from .models import MapData
from .forms import MapForm
from .osm import get_osm_geom, get_osm_xml, osm_xml_to_geom, osm_xml_to_tags


class MapDetailView(Custom404Mixin, AddContributorsMixin, RegionMixin, DetailView):
    model = MapData

    def handler404(self, request, *args, **kwargs):
        page_slug = kwargs.get('slug')
        try:
            region = self.get_region(request=request, kwargs=kwargs)
        except Http404:
            return region_404_response(request, kwargs['region'])

        try:
            page = Page.objects.get(slug=slugify(page_slug), region=region)
        except Page.DoesNotExist:
            page = Page(slug=slugify(page_slug), region=region)

        mapdata = MapData(page=page, region=region)
        return HttpResponseNotFound(
            render(request, 'maps/mapdata_new.html',
                   {'page': page, 'mapdata': mapdata})
        )

    def get_object(self):
        page_slug = self.kwargs.get('slug')
        region = self.get_region()
        page = get_object_or_404(Page, slug=slugify(page_slug), region=region)
        mapdata = get_object_or_404(MapData, page=page, region=region)
        return mapdata

    def get_object_date(self):
        return self.object.versions.most_recent().version_info.date

    def get_context_data(self, **kwargs):
        context = super(MapDetailView, self).get_context_data(**kwargs)

        options = map_options_for_region(self.get_region())
        options['permalink'] = True
        context['date'] = self.get_object_date()
        context['map'] = InfoMap([(self.object.geom, self.object.page.name)],
                                 options=options)
        return context


def filter_by_bounds(queryset, bbox):
    return queryset.filter(Q(points__intersects=bbox)
                           | Q(lines__within=bbox)
                           | Q(polys__intersects=bbox))


def filter_by_tags(queryset, tag_name):
    return queryset.filter(page__pagetagset__tags__name=tag_name)


def filter_by_zoom(queryset, zoom):
    if zoom < 14:
        # If 5 or more polygons, let's hide the points
        if queryset.filter(polys__isnull=False).count() >= 5:
            # exclude points
            queryset = queryset.exclude(Q(lines=None) & Q(polys=None))
    min_length = 100 * pow(2, 0 - zoom)
    queryset = queryset.exclude(Q(points=None) & Q(length__lt=min_length))
    return queryset


def popup_html(mapdata=None, pagename=None):
    if mapdata:
        pagename = mapdata.page.name
    url = page_url(pagename, mapdata.region)
    return mark_safe('<a href="%s">%s</a>' % (url, pagename))


class MapBaseListView(ListView):
    model = MapData
    template_name = 'maps/mapdata_list.html'
    dynamic = False
    zoom_to_data = True
    filter_by_zoom = False
    permalink = True

    def get_context_data(self, **kwargs):
        context = super(MapBaseListView, self).get_context_data(**kwargs)
        context['map'] = self.get_map()
        context['dynamic_map'] = self.dynamic
        return context

    def get_map_objects(self):
        return [(obj.geom, popup_html(obj)) for obj in self.object_list]

    def get_map(self):
        map_objects = self.get_map_objects()
        options = copy.deepcopy(getattr(settings,
                                        'OLWIDGET_DEFAULT_OPTIONS', {}))
        options.update({
            'dynamic': self.dynamic,
            'zoomToDataExtent': self.zoom_to_data,
            'permalink': self.permalink,
            'cluster': True
        })
        return InfoMap(map_objects, options=options)


class BaseMapRegionView(RegionMixin, MapBaseListView):
    template_name = 'maps/mapdata_list.html'
    dynamic = True
    zoom_to_data = False
    filter_by_zoom = True

    def get_queryset(self):
        queryset = super(BaseMapRegionView, self).get_queryset()
        # XXX TODO TEMPORARY HACK
        queryset = queryset.exclude(page__pagetagset__tags__slug='zipcode')
        queryset = queryset.exclude(
            page__pagetagset__tags__slug='supervisorialdistrict')
        if not filter_by_zoom:
            return queryset
        # We order by -length so that the geometries are in that
        # order when rendered by OpenLayers -- this creates the
        # correct stacking order.
        return filter_by_zoom(queryset, 12).order_by('-length')

    def get_map(self):
        map_objects = self.get_map_objects()
        options = map_options_for_region(self.get_region())
        options.update({
            'dynamic': self.dynamic,
            'zoomToDataExtent': self.zoom_to_data,
            'permalink': self.permalink,
            'cluster': True
        })
        _map = InfoMap(map_objects, options=options)
        return _map


class MapFullRegionView(CacheMixin, BaseMapRegionView):

    @staticmethod
    def get_cache_key(*args, **kwargs):
        from django.core.urlresolvers import get_urlconf
        from pages.models import name_to_url

        urlconf = get_urlconf() or settings.ROOT_URLCONF
        region = CacheMixin.get_region_slug_param(*args, **kwargs)
        # Control characters and whitespace not allowed in memcached keys
        return 'map:%s/%s/main_map' % (urlconf, name_to_url(region))

    def get_context_data(self, *args, **kwargs):
        context = super(MapFullRegionView, self).get_context_data(
            *args, **kwargs)
        context['allow_near_you'] = True
        return context


class MapFullRegionLayerView(MapFullRegionView):
    layer_names = [u'國道', u'省道', u'鄉道', u'鐵路', u'取水點', u'快速道路', u'指揮中心', u'消防單位', u'警察單位', u'醫療院所', u'高速鐵路', u'物資存備點', u'海嘯危險區域', u'直升機起降點',
                   u'老人福利機構', u'適用地震災害', u'適用水災災害', u'適用海嘯災害', u'人車轉運集結點', u'室內避難收容所', u'室外避難收容所', u'救援器材放置點', u'通訊設備放置點', u'適用土石流災害', u'海嘯避難收容處所', u'身心障礙福利機構']

    def get_map_objects_by_tag(self, tag_name):
        return [(obj.geom, popup_html(obj)) for obj in filter_by_tags(self.object_list, tag_name)]

    def get_map(self):
        map_objects = [InfoLayer(self.get_map_objects())]
        for layer_name in MapFullRegionLayerView.layer_names:
            layer_objects = self.get_map_objects_by_tag(layer_name)
            if len(layer_objects) > 0:
                map_objects.append(InfoLayer(layer_objects, {
                    'overlay_style': {
                        'external_graphic': '/static/tagicon/%s.png' % layer_name,
                        'graphic_height': 32,
                        'graphic_width': 32,
                        'graphic_opacity': 1.0
                    }
                }))
        options = map_options_for_region(self.get_region())
        options.update({
            'dynamic': self.dynamic,
            'zoomToDataExtent': self.zoom_to_data,
            'permalink': self.permalink,
            'cluster': True
        })
        _map = Map(map_objects, options=options)
        return _map


class MapAllObjectsAsPointsView(BaseMapRegionView):
    """
    Like MapFullRegionView, but return all objects as points and do not filter by
    zoom.
    """
    dynamic = False
    zoom_to_data = False
    filter_by_zoom = False

    def get_map_objects(self):
        return [(obj.geom.centroid, popup_html(obj))
                for obj in self.object_list
                ]


class EverythingEverywhereAsPointsView(MapAllObjectsAsPointsView):
    """
    All objects across all regions as points.
    """

    def get_queryset(self):
        return MapData.objects.all()


class MapForTag(BaseMapRegionView):
    """
    All objects whose pages have a particular tag within a region.
    """
    dynamic = False
    zoom_to_data = True
    template_name = 'maps/mapdata_list_for_tag.html'

    def get_queryset(self):
        import tags.models as tags

        qs = super(BaseMapRegionView, self).get_queryset()
        region = self.get_region()
        self.tag = tags.Tag.objects.get(
            slug=tags.slugify(self.kwargs['tag']),
            region=region
        )
        tagsets = tags.PageTagSet.objects.filter(tags=self.tag, region=region)
        pages = Page.objects.filter(pagetagset__in=tagsets, region=region)
        return MapData.objects.filter(page__in=pages).\
            select_related('page').defer('page__content').order_by('-length')

    def get_map_title(self):
        region = self.get_region()
        d = {
            'map_url': reverse('maps:global', kwargs={'region': region.slug}),
            'tag_url': reverse('tags:list', kwargs={'region': region.slug}),
            'page_tag_url': reverse('tags:tagged',
                                    kwargs={'slug': self.tag.slug, 'region': region.slug}),
            'tag_name': escape(self.tag.name)
        }
        return (
            _('<a href="%(map_url)s">Map</a> for tag "<a href="%(page_tag_url)s">%(tag_name)s</a>"') % d
        )

    def get_context_data(self, **kwargs):
        context = super(MapForTag, self).get_context_data(**kwargs)
        context['map_title'] = self.get_map_title()
        return context


class GlobalMapForTag(MapBaseListView):
    """
    All objects whose pages have a particular tag -- globally.
    """
    dynamic = False
    zoom_to_data = True
    template_name = 'maps/mapdata_list_for_tag.html'

    def get_queryset(self):
        self.tag_slug = self.kwargs['tag']
        return MapData.objects.filter(page__pagetagset__tags__slug=self.tag_slug).\
            select_related('page').defer('page__content')

    def get_map_title(self):
        d = {
            'page_tag_url': reverse('tags:global-tagged',
                                    kwargs={'slug': self.tag_slug}),
            'tag_name': escape(self.tag_slug)
        }
        return (
            _('Map for tag "<a href="%(page_tag_url)s">%(tag_name)s</a>"') % d
        )

    def get_context_data(self, **kwargs):
        context = super(GlobalMapForTag, self).get_context_data(**kwargs)
        context['map_title'] = self.get_map_title()
        return context


class MapObjectsForBounds(JSONResponseMixin, RegionMixin, BaseListView):
    model = MapData

    def get_queryset(self):
        queryset = MapData.objects.filter(region=self.get_region())
        # XXX TODO TEMPORARY HACK
        queryset = queryset.exclude(page__pagetagset__tags__slug='zipcode')
        queryset = queryset.exclude(
            page__pagetagset__tags__slug='supervisorialdistrict')
        bbox = self.request.GET.get('bbox', None)
        if bbox:
            bbox = Polygon.from_bbox([float(x) for x in bbox.split(',')])
            queryset = filter_by_bounds(queryset, bbox)
        zoom = self.request.GET.get('zoom', None)
        if zoom:
            # We order by -length so that the geometries are in that
            # order when rendered by OpenLayers. This creates the
            # correct stacking order.
            queryset = filter_by_zoom(queryset, int(zoom)).order_by('-length')
        return queryset.select_related('page')

    def get_context_data(self, **kwargs):
        objs = self.object_list.values('geom', 'page__name')
        region = self.get_region()
        map_objects = [
            (o['geom'].ewkt, o['page__name'], page_url(o['page__name'], region))
            for o in objs
        ]
        return map_objects


class OSMGeometryLookup(RegionMixin, JSONView):

    def get_context_data(self, **kwargs):
        display_name = self.request.GET.get('display_name')
        osm_id = int(self.request.GET.get('osm_id'))
        osm_type = self.request.GET.get('osm_type')
        osm_xml = get_osm_xml(
            osm_id, osm_type, display_name, self.get_region())
        return {
            'geom': osm_xml_to_geom(osm_xml, osm_type).ewkt,
            'tags': osm_xml_to_tags(osm_xml, osm_type)
        }


class MapVersionDetailView(MapDetailView):
    template_name = 'maps/mapdata_version_detail.html'
    context_object_name = 'mapdata'

    def get_object(self):
        region = self.get_region()
        # A dummy page object.
        page = Page(
            slug=slugify(self.kwargs['slug']),
            region=region
        )
        latest_page = page.versions.most_recent()
        # Need to set the pk on the dummy page for correct MapData lookup.
        page.pk = latest_page.id
        page.name = latest_page.name
        self.page = page

        mapdata = MapData(page=page, region=region)
        version = self.kwargs.get('version')
        date = self.kwargs.get('date')
        if version:
            return mapdata.versions.as_of(version=int(version))
        if date:
            return mapdata.versions.as_of(date=dateparser(date))

    def get_object_date(self):
        return self.object.version_info.date

    def get_context_data(self, **kwargs):
        context = super(MapVersionDetailView, self).get_context_data(**kwargs)
        context['show_revision'] = True
        return context


class MapUpdateView(PermissionRequiredMixin, CreateObjectMixin, RegionMixin, UpdateView):
    model = MapData
    form_class = MapForm
    # Tie map permissions to pages, for now.
    permission = 'pages.change_page'

    def get_object(self):
        page_slug = self.kwargs.get('slug')
        region = self.get_region()
        page = Page.objects.get(slug=slugify(page_slug), region=region)
        mapdatas = MapData.objects.filter(page=page, region=region)
        if mapdatas:
            return mapdatas[0]
        return MapData(page=page, region=region)

    def get_protected_object(self):
        return self.object.page

    def get_context_data(self, *args, **kwargs):
        context = super(MapUpdateView, self).get_context_data(*args, **kwargs)
        # Default to the region's defined map settings.
        # TODO: make this less hacky
        context['form'].fields['geom'].widget.options.update(
            map_options_for_region(self.get_region()))
        return context

    def get_success_url(self):
        return reverse('maps:show',
                       kwargs={'region': self.object.region.slug, 'slug': self.object.page.pretty_slug})


class MapCreateWithoutPageView(MapUpdateView):

    def _get_or_create_page(self):
        pagename = self.request.GET.get('pagename')
        region = self.get_region()
        has_page = Page.objects.filter(slug=slugify(pagename), region=region)
        if has_page:
            page = has_page[0]
        else:
            content = _('<p>What do you know about %s?</p>') % pagename
            page = Page(slug=slugify(pagename), name=pagename,
                        content=content, region=region)
        return page

    def get_object(self):
        page = self._get_or_create_page()
        region = self.get_region()
        if MapData.objects.filter(page=page, region=region).exists():
            return MapData.objects.get(page=page, region=region)
        return MapData(page=page, region=region)

    def form_valid(self, form):
        page = self._get_or_create_page()
        page.save(comment=form.get_save_comment())
        self.object.page = page
        return super(MapCreateWithoutPageView, self).form_valid(form)

    def success_msg(self):
        return (
            _('Map saved! You should probably go <a href="%s">edit the page that was created</a>, too.') %
            reverse('pages:edit', kwargs={
                    'region': self.get_region().slug, 'slug': self.object.page.name})
        )

    def get_context_data(self, *args, **kwargs):
        context = super(MapCreateWithoutPageView,
                        self).get_context_data(*args, **kwargs)
        # TODO: make this less hacky
        context['form'].fields['geom'].widget.options.update(
            {'permalink': True})
        return context

    def get_map(self):
        map_objects = self.get_map_objects()
        options = map_options_for_region(self.get_region())
        options.update({
            'dynamic': self.dynamic,
            'zoomToDataExtent': self.zoom_to_data,
            'permalink': self.permalink,
            'cluster': True
        })
        return InfoMap(map_objects, options=options)


class MapDeleteView(PermissionRequiredMixin, MapDetailView, DeleteView):
    model = MapData
    context_object_name = 'mapdata'
    # Tie map permissions to pages, for now.
    permission = 'pages.delete_page'

    def get_success_url(self):
        # Redirect back to the map.
        return reverse('maps:show',
                       kwargs={'region': self.get_region().slug, 'slug': self.kwargs.get('slug')})

    def get_protected_object(self):
        return self.object.page


class MapRevertView(MapVersionDetailView, RevertView):
    model = MapData
    context_object_name = 'mapdata'
    template_name = 'maps/mapdata_confirm_revert.html'
    # Tie map permissions to pages, for now.
    permission = 'pages.change_page'

    def get_success_url(self):
        # Redirect back to the map.
        return reverse('maps:show',
                       kwargs={'region': self.get_region().slug, 'slug': self.kwargs.get('slug')})

    def get_context_data(self, **kwargs):
        context = super(DetailView, self).get_context_data(**kwargs)

        options = map_options_for_region(self.get_region())
        context['show_revision'] = True
        context['map'] = InfoMap(
            [(self.object.geom, self.object.page.name)], options=options)
        context['date'] = self.object.version_info.date
        return context

    def get_protected_object(self):
        return self.object.page


class MapVersionsList(RegionMixin, VersionsList):

    def get_queryset(self):
        region = self.get_region()
        # A dummy page object.
        page = Page(slug=slugify(self.kwargs['slug']), region=region)
        latest_page = page.versions.most_recent()
        # Need to set the pk on the dummy page for correct MapData lookup.
        page.pk = latest_page.id
        page.name = latest_page.name

        self.mapdata = MapData(page=page, region=region)
        return self.mapdata.versions.all()

    def get_context_data(self, **kwargs):
        context = super(MapVersionsList, self).get_context_data(**kwargs)
        context['mapdata'] = self.mapdata
        return context


class MapCompareView(RegionMixin, diff.views.CompareView):
    model = MapData

    def get_object(self):
        region = self.get_region()
        # A dummy page object.
        page = Page(slug=slugify(self.kwargs['slug']), region=region)
        latest_page = page.versions.most_recent()
        # Need to set the pk on the dummy page for correct MapData lookup.
        page.pk = latest_page.id
        page.name = latest_page.name

        return MapData(page=page, region=region)

    def get_context_data(self, **kwargs):
        # Send this in directly because we've wrapped InfoMap.
        context = super(MapCompareView, self).get_context_data(**kwargs)
        # We subclassed olwidget.widget.InfoMap. We want to combine both
        # their media here to ensure we display more than one layer
        # correctly.
        context['map_diff_media'] = InfoMap([]).media + OLInfoMap([]).media
        return context


class MapNearbyView(RegionMixin, ListView):
    model = MapData
    template_name = 'maps/nearby_pages.html'
    context_object_name = 'nearby_maps'

    def get_queryset(self):
        if not self.request.GET.get('lat'):
            return None

        nearby_degrees = 0.3

        lat = float(self.request.GET.get('lat'))
        lng = float(self.request.GET.get('lng'))
        user_location = Point(lng, lat)

        near_user = user_location.buffer(nearby_degrees)

        points = MapData.objects.filter(points__contained=near_user).distance(
            user_location, field_name='points').order_by('distance')[:30]
        polys = MapData.objects.filter(polys__contained=near_user).distance(
            user_location, field_name='polys').order_by('distance')[:30]
        lines = MapData.objects.filter(lines__contained=near_user).distance(
            user_location, field_name='lines').order_by('distance')[:30]

        queryset = sorted(list(points) + list(polys) +
                          list(lines), key=attrgetter('distance'))[:30]
        return queryset

    def get_context_data(self, *args, **kwargs):
        from maps.widgets import InfoMap
        context = super(MapNearbyView, self).get_context_data(*args, **kwargs)
        qs = self.get_queryset()
        if qs is None:
            context['no_location'] = True
            qs = []
        map_objects = [(obj.geom, popup_html(obj)) for obj in qs]

        # Remove the PanZoom on normal page views.
        olwidget_options = copy.deepcopy(getattr(settings,
                                                 'OLWIDGET_DEFAULT_OPTIONS', {}))
        map_opts = olwidget_options.get('map_options', {})
        map_controls = map_opts.get('controls', [])
        if 'PanZoomBar' in map_controls:
            map_controls.remove('PanZoomBar')
        if 'PanZoom' in map_controls:
            map_controls.remove('PanZoom')
        if 'KeyboardDefaults' in map_controls:
            map_controls.remove('KeyboardDefaults')
        olwidget_options['map_options'] = map_opts
        olwidget_options['map_div_class'] = 'mapwidget small'
        context['map'] = InfoMap(
            map_objects,
            options=olwidget_options)
        return context
