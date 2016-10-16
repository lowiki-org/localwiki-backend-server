# encoding=utf-8
import copy
from PIL import Image
from cStringIO import StringIO

from django.views.generic import View
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.core.files.base import ContentFile
from django.conf import settings

from pages.models import Page
from pages.views import PageDetailView
from maps.models import MapData
from maps.widgets import Map, InfoLayer, InfoMap, map_options_for_region
from regions.views import RegionMixin, RegionAdminRequired, TemplateView, region_404_response
from regions.models import Region
from tags.models import Tag
from localwiki.utils.views import Custom404Mixin, CacheMixin

from .models import FrontPage


class FrontPageView(Custom404Mixin, TemplateView):
    template_name = 'frontpage/base.html'
    cache_timeout = 60 * 60  # 1 hr, and we invalidate after Front Page save
    layer_names = [ u'國道', u'省道', u'鄉道', u'鐵路', u'取水點', u'快速道路', u'指揮中心', u'消防單位', u'警察單位', u'醫療院所', u'高速鐵路', u'物資存備點', u'海嘯危險區域', u'直升機起降點', u'老人福利機構', u'適用地震災害', u'適用水災災害', u'適用海嘯災害', u'人車轉運集結點', u'室內避難收容所', u'室外避難收容所', u'救援器材放置點', u'通訊設備放置點', u'適用土石流災害', u'海嘯避難收容處所', u'身心障礙福利機構' ]

    def get(self, *args, **kwargs):
        # If there's no FrontPage defined, let's send the "Front Page" Page object.
        region = self.get_region()
        if not FrontPage.objects.filter(region=region).exists() or region.regionsettings.is_meta_region:
            page_view = PageDetailView()
            page_view.kwargs = {'slug': 'front page', 'region': self.get_region().slug}
            page_view.request = self.request
            return page_view.get(*args, **page_view.kwargs)
        return super(FrontPageView, self).get(*args, **kwargs)

    def get_map_objects(self):
        centroids = MapData.objects.filter(
            region=self.get_region()).centroid().values('centroid')
        return [(g['centroid'], '') for g in centroids]

    def get_map_objects_by_tag(self, tag_name):
        centroids = MapData.objects.filter(region=self.get_region()).filter(page__pagetagset__tags__name=tag_name).centroid().values('centroid')
        return [(g['centroid'], '') for g in centroids]

    def get_map(self, cover=False):
        olwidget_options = copy.deepcopy(getattr(settings,
            'OLWIDGET_DEFAULT_OPTIONS', {}))
        map_opts = olwidget_options.get('map_options', {})
        olwidget_options.update(map_options_for_region(self.get_region()))
        map_controls = map_opts.get('controls', [])
        if 'PanZoom' in map_controls:
            map_controls.remove('PanZoom')
        if 'PanZoomBar' in map_controls:
            map_controls.remove('PanZoomBar')
        if 'KeyboardDefaults' in map_controls:
            map_controls.remove('KeyboardDefaults')
        if 'Navigation' in map_controls:
            map_controls.remove('Navigation')
        if not cover:
            olwidget_options['map_div_class'] = 'mapwidget small'
        olwidget_options['map_options'] = map_opts
        olwidget_options['zoomToDataExtent'] = False
        olwidget_options['cluster'] = True
        if cover:
            return InfoMap([(self.get_region().geom, {
                'style': {
                    'fill_color': '#ffffff',
                    'stroke_color': '#fca92e',
                    'fill_opacity': '0',
                    'stroke_opacity': '1'
                },
                'html': '<p>' + self.get_region().full_name + '</p>'
            })], options=olwidget_options)
        else:
            map_objects = [InfoLayer(self.get_map_objects())]
            for layer_name in FrontPageView.layer_names:
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
            return Map(map_objects, options=olwidget_options)

    def get_categories_for_cards(self):
        names = [u'社區', u'避難收容處所', u'設備物資集結點', u'特殊需求機構', u'重要維生設施', u'緊急聯絡網']
        categories = []
        for name in names:
            if Tag.objects.filter(name=name).exists():
                categories.append({
                    'name': name,
                    'tag': Tag.objects.filter(name=name)[0]
                })
        return categories

    def get_pages_for_cards(self):
        categories = self.get_categories_for_cards()
        for category in categories:
            qs = Page.objects.filter(region=self.get_region(), pagetagset__tags__slug=category['name'])

            # Exclude meta stuff
            qs = qs.exclude(slug__startswith='templates/')
            qs = qs.exclude(slug='templates')
            qs = qs.exclude(slug='front page')

            # Exclude ones with empty scores
            qs = qs.exclude(score=None)

            qs = qs.defer('content').select_related('region').order_by('-score__score', '?')

            category['pages'] = qs
        return categories

    def get_context_data(self, *args, **kwargs):
        context = super(FrontPageView, self).get_context_data()

        context['frontpage'] = FrontPage.objects.get(region=self.get_region())
        context['no_index'] = self.get_region().is_empty
        context['map'] = self.get_map()
        context['cover_map'] = self.get_map(cover=True)
        context['pages_for_cards'] = self.get_pages_for_cards()
        if Page.objects.filter(name="Front Page", region=self.get_region()).exists():
            context['page'] = Page.objects.get(name="Front Page", region=self.get_region())
        else:
            context['page'] = Page(name="Front Page", region=self.get_region())
        return context

    def handler404(self, request, *args, **kwargs):
        return region_404_response(request, kwargs.get('region'))

    @staticmethod
    def get_cache_key(*args, **kwargs):
        from django.core.urlresolvers import get_urlconf
        urlconf = get_urlconf() or settings.ROOT_URLCONF
        region = CacheMixin.get_region_slug_param(*args, **kwargs)

        return '%s/%s/' % (urlconf, region)


class CoverUploadView(RegionMixin, RegionAdminRequired, View):
    def post(self, *args, **kwargs):

        photo = self.request.FILES.get('file')

        client_cover_w = int(float(self.request.POST.get('client_w')))
        client_cover_h = int(float(self.request.POST.get('client_h')))
        client_position_x = abs(int(float(self.request.POST.get('position_x'))))
        client_position_y = abs(int(float(self.request.POST.get('position_y'))))
        axis = self.request.POST.get('cover_position_axis')

        if client_cover_w <= 0 or client_cover_h <= 0:
            raise Exception

        im = Image.open(photo)
        exact_w, exact_h = im.size

        if axis == 'y':
            scale = (exact_w * 1.0)/ client_cover_w
            position_y = scale * client_position_y
            exact_cover_h = client_cover_h * scale

            left = 0
            upper = int(position_y)
            right = int(exact_w)
            lower = int(position_y + exact_cover_h)
            bbox = (left, upper, right, lower)
        else:
            scale = (exact_h * 1.0)/ client_cover_h
            position_x = scale * client_position_x
            exact_cover_w = client_cover_w * scale

            left = int(position_x)
            upper = 0
            right = int(position_x + exact_cover_w)
            lower = exact_h
            bbox = (left, upper, right, lower)

        cropped = im.crop(bbox)
        cropped_s = StringIO()
        cropped.save(cropped_s, "JPEG", quality=90)
        cropped_f = ContentFile(cropped_s.getvalue())

        frontpage = FrontPage.objects.get(region=self.get_region())
        frontpage.cover_photo_full = photo
        frontpage.cover_photo.save(photo.name, cropped_f)
        frontpage.cover_photo_crop_bbox_left = left
        frontpage.cover_photo_crop_bbox_upper = upper
        frontpage.cover_photo_crop_bbox_right = right
        frontpage.cover_photo_crop_bbox_lower = lower
        frontpage.save()

        messages.add_message(self.request, messages.SUCCESS, _("Cover photo updated!"))

        return HttpResponseRedirect(
            reverse('frontpage', kwargs={'region': self.get_region().slug}))
