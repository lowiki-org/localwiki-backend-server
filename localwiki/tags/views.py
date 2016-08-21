import copy
from dateutil.parser import parse as dateparser

from localwiki.utils.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, Http404, HttpResponseNotFound
from django.utils.translation import ugettext as _
from django.template.context import RequestContext
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.gis.measure import D
from django.shortcuts import get_object_or_404, render
from django.db.models.aggregates import Count
from django.views.generic.list import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import FormView

from versionutils.versioning.views import VersionsList, UpdateView
from versionutils.diff.views import CompareView
from regions.models import Region
from regions.views import RegionMixin
from models import PageTagSet, Tag, slugify
from forms import PageTagSetForm, SingleTagForm
from pages.plugins import html_to_template_text
from pages.models import Page

from utils.views import CreateObjectMixin, PermissionRequiredMixin,\
    Custom404Mixin, RevertView, CacheMixin


class PageNotFoundMixin(Custom404Mixin):
    def handler404(self, request, *args, **kwargs):
        return HttpResponseRedirect(
            reverse('pages:show', kwargs={
                'slug': kwargs['slug'], 'region': kwargs['region']}))


class TagListView(RegionMixin, ListView):
    model = Tag

    def get_queryset(self):
        return super(TagListView, self).get_queryset().annotate(
                    num_pages=Count('pagetagset')).filter(num_pages__gt=0)


class TaggedList(CacheMixin, Custom404Mixin, RegionMixin, ListView):
    model = PageTagSet
    cache_keep_forever = True

    def get_queryset(self):
        self.tag_name = slugify(self.kwargs['slug'])
        try:
            region = self.get_region()
            self.tag = Tag.objects.get(
                slug=self.tag_name, region=region)
            self.tag_name = self.tag.name
            pts = PageTagSet.objects.filter(tags=self.tag, region=region).\
                select_related('page', 'region').defer('page__content')
            if not pts.exists():
                raise Http404
            return pts
        except Tag.DoesNotExist:
            self.tag = None
            raise Http404

    def get_map_objects(self):
        if not self.tag:
            return None
        # We re-use the MapForTag view's logic here to embed a mini-map on the
        # tags list page
        from maps.views import MapForTag
        map_view = MapForTag()
        map_view.request = self.request
        map_view.kwargs = dict(tag=self.tag.slug, region=self.get_region().slug)
        map_view.object_list = map_view.get_queryset()
        return map_view.get_map_objects()

    def get_nearby_tags(self):
        from maps.models import MapData

        region = self.get_region()
        center = region.regionsettings.region_center
        if center is None:
            self.nearby_pagetagset_list = []
            return []

        # __dwithin=(center, 0.5) means: all objects within
        # 1 degree of center. This is roughly 60 miles. This will vary slightly as we move around the earth,
        # but the complexity of fixing this here is too great. Not a huge deal
        # for this particular case. The real fix here is to:
        #
        #   1.) Use a geometry column instead of the default geography column type or
        #   2.) Figure out how to case to a geometry column for this query, or
        #   3.) Write a method that, given a point, finds the correct UTM_N projection,
        #       then projects the center point into that UTM_N, then buffers by meters
        #       around the point, and then finally does a __within= on the queryset. Whew.
        #
        nearby_pts = PageTagSet.objects.exclude(region=region).\
            exclude(region__regionsettings=None).exclude(region__regionsettings__region_center=None).\
            filter(region__regionsettings__region_center__dwithin=(center, 0.5))
        nearby_pts = nearby_pts.filter(tags__slug=self.tag.slug)
        nearby_pts = nearby_pts.select_related('page__mapdata')

        self.nearby_pagetagset_list = nearby_pts
        return nearby_pts

    def get_nearby_map_objects(self):
        from maps.models import MapData
        from maps.views import popup_html

        if getattr(self, 'nearby_pagetagset_list', None) is None:
            self.get_nearby_tags()

        pts = self.nearby_pagetagset_list
        if pts == [] or not pts.exists():
            return

        pts = pts.exclude(page__mapdata=None)
        ids = pts.values('page__id').distinct().order_by('page')
        maps = MapData.objects.exclude(region=self.get_region()).filter(page__id__in=ids)
        return [(obj.geom, popup_html(obj)) for obj in maps]

    def map_context(self, map_objects):
        from maps.widgets import InfoMap, map_options_for_region

        if map_objects:
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
            olwidget_options.update(map_options_for_region(self.get_region()))
            return InfoMap(
                map_objects,
                options=olwidget_options)

    def get_context_data(self, *args, **kwargs):
        context = super(TaggedList, self).get_context_data(*args, **kwargs)
        region = self.get_region()

        context['tag'] = self.tag
        context['tag_name'] = self.tag_name
        context['map'] = self.map_context(self.get_map_objects())

        # Grab nearby PageTagSets
        context['nearby_pagetagset_list'] = self.get_nearby_tags()
        context['nearby_map'] = self.map_context(self.get_nearby_map_objects())

        total_pts = PageTagSet.objects.filter(tags__slug=self.tag.slug).count()
        region_pts = PageTagSet.objects.filter(tags__slug=self.tag.slug, region=region).count()
        if total_pts > region_pts:
            context['more_tags'] = True
        else:
            context['more_tags'] = False

        if not region.regionsettings.is_meta_region and region.regionsettings.region_zoom_level is not None:
            zoom = region.regionsettings.region_zoom_level - 2 
            map_params = "#zoom=%s&lon=%s&lat=%s" % (zoom, region.regionsettings.region_center.x, region.regionsettings.region_center.y)
            context['map_params'] = map_params

        return context

    def handler404(self, request, *args, **kwargs):
        tag_name = slugify(kwargs['slug'])
        msg = (_('<p>No pages tagged "%s".</p>') % 
             tag_name)
        html = render_to_string('404.html', {'message': msg}, RequestContext(request))
        return HttpResponseNotFound(html)

    @staticmethod
    def get_cache_key(*args, **kwargs):
        from django.core.urlresolvers import get_urlconf
        from pages.models import name_to_url

        urlconf = get_urlconf() or settings.ROOT_URLCONF
        slug = kwargs.get('slug')
        region = CacheMixin.get_region_slug_param(*args, **kwargs)
        # Control characters and whitespace not allowed in memcached keys
        return 'tags:%s/%s/%s' % (urlconf, name_to_url(region), slugify(slug).replace(' ', '_'))


class GlobalTaggedList(CacheMixin, ListView):
    model = PageTagSet
    template_name = 'tags/global_pagetagset_list.html'

    def get_queryset(self):
        self.tag_name = slugify(self.kwargs['slug'])
        return PageTagSet.objects.filter(tags__slug=self.tag_name).select_related('page', 'region').defer('page__content')

    def get_map_objects(self):
        if not self.tag_name:
            return None
        # We re-use the GlobalMapForTag view's logic here to embed a mini-map on the
        # tags list page
        from maps.views import GlobalMapForTag
        map_view = GlobalMapForTag()
        map_view.request = self.request
        map_view.kwargs = dict(tag=self.tag_name)
        map_view.object_list = map_view.get_queryset()
        return map_view.get_map_objects()

    def get_context_data(self, *args, **kwargs):
        from maps.widgets import InfoMap, map_options_for_region

        context = super(GlobalTaggedList, self).get_context_data(*args, **kwargs)
        context['tag_name'] = self.tag_name
        map_objects = self.get_map_objects()
        if map_objects:
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
            olwidget_options['cluster'] = True
            context['map'] = InfoMap(
                map_objects,
                options=olwidget_options)
        return context

    @staticmethod
    def get_cache_key(*args, **kwargs):
        from django.core.urlresolvers import get_urlconf
        from pages.models import name_to_url

        slug = kwargs.get('slug')
        # Control characters and whitespace not allowed in memcached keys
        return 'globaltags:%s' % slugify(slug).replace(' ', '_')


class PageTagSetUpdateView(PageNotFoundMixin, PermissionRequiredMixin,
                           RegionMixin, CreateObjectMixin, UpdateView):
    model = PageTagSet
    form_class = PageTagSetForm
    permission = 'pages.change_page'

    def tryTemplate(self, name):
        return Page.objects.get(slug=u"templates/%s" % name,
                                region=self.get_region())

    def renderTemplate(self, name, params):
        try:
            t = self.tryTemplate(name)
        except Page.DoesNotExist:
            return ""
        text = unicode(t.content)
        for param in params:
            text = text.replace(u"{{%s}}" % unicode(param.name), unicode(param.value))
        return text

    def form_valid(self, form):
        tag_slug = form.cleaned_data.get('tags').latest('slug').name
        page = form.instance.page
        # Don't check when tag_slug eqal to page_name or no data
        if tag_slug == page.name or len(tag_slug) == 0:
            return super(PageTagSetUpdateView, self).form_valid(form)

        # Check tag was also a template key
        try:
            tm = self.tryTemplate(tag_slug)
        except Page.DoesNotExist:
            tm = None
        if tm:
            context = page.content
            try:
                html = unicode(tm.content) + unicode(context)
                page.content = html
                logging.debug('tt %s', html)
                page.save()
            except:
                if settings.TEMPLATE_DEBUG:
                    raise

        return super(PageTagSetUpdateView, self).form_valid(form)

    def get_object(self):
        page_slug = self.kwargs.get('slug')
        region = self.get_region()
        page = get_object_or_404(Page, slug=page_slug, region=region)
        try:
            return PageTagSet.objects.get(page=page, region=region)
        except PageTagSet.DoesNotExist:
            return PageTagSet(page=page, region=region)

    def get_success_url(self):
        next = self.request.POST.get('next', None)
        if next:
            return next
        return reverse('pages:tags',
                       args = [self.kwargs.get('region'), self.kwargs.get('slug')])

    def get_context_data(self, *args, **kwargs):
        context = super(PageTagSetUpdateView, self).get_context_data(*args, **kwargs)
        context['region'] = self.get_region()

    def get_form_kwargs(self):
        kwargs = super(PageTagSetUpdateView, self).get_form_kwargs()
        # We need to pass the `region` to the PageTagSetForm.
        kwargs['region'] = self.get_region()
        return kwargs

    def get_protected_object(self):
        return self.object.page


class PageTagSetVersions(PageNotFoundMixin, RegionMixin, VersionsList):
    def get_queryset(self):
        page_slug = self.kwargs.get('slug')
        try:
            self.page = get_object_or_404(Page,
                slug=page_slug, region=self.get_region())
            return self.page.pagetagset.versions.all()
        except PageTagSet.DoesNotExist:
            return PageTagSet.versions.none()

    def get_context_data(self, **kwargs):
        context = super(PageTagSetVersions, self).get_context_data(**kwargs)
        context['page'] = self.page
        return context


class PageTagSetVersionDetailView(RegionMixin, DetailView):
    context_object_name = 'pagetagset'
    template_name = 'tags/pagetagset_version_detail.html'

    def get_object(self):
        page_slug = self.kwargs.get('slug')
        try:
            page = Page.objects.get(slug=page_slug, region=self.get_region())
            tags = page.pagetagset
            version = self.kwargs.get('version')
            date = self.kwargs.get('date')
            if version:
                return tags.versions.as_of(version=int(version))
            if date:
                return tags.versions.as_of(date=dateparser(date))
        except (Page.DoesNotExist, PageTagSet.DoesNotExist):
            return None

    def get_context_data(self, **kwargs):
        context = super(PageTagSetVersionDetailView, self).get_context_data(
            **kwargs)
        context['date'] = self.object.version_info.date
        context['show_revision'] = True
        return context


class PageTagSetCompareView(RegionMixin, CompareView):
    model = PageTagSet

    def get_object(self):
        page_slug = self.kwargs.get('slug')
        page = Page.objects.get(slug=page_slug, region=self.get_region())
        return page.pagetagset

    def get_context_data(self, **kwargs):
        context = super(PageTagSetCompareView, self).get_context_data(**kwargs)
        context['slug'] = self.kwargs['original_slug']
        return context


class PageTagSetRevertView(PermissionRequiredMixin, RegionMixin, RevertView):
    model = PageTagSet
    context_object_name = 'pagetagset'
    permission = 'pages.change_page'

    def get_object(self):
        page_slug = self.kwargs.get('slug')
        page = Page.objects.get(slug=page_slug, region=self.get_region())
        version_num = int(self.kwargs['version'])
        return page.pagetagset.versions.as_of(version=version_num)

    def get_protected_object(self):
        return self.object.page

    def get_success_url(self):
        # Redirect back to the file info page.
        return reverse('pages:tags-history',
            args=[self.kwargs['region'], self.kwargs['slug']])


class AddSingleTagView(PermissionRequiredMixin, RegionMixin, CreateObjectMixin, FormView):
    """
    A convenience view that's used with the "add a new page to tag list" button.
    """
    form_class = SingleTagForm
    permission = 'pages.change_page'

    def form_valid(self, form):
        tag_slug = form.cleaned_data['tag_slug']
        page_name = form.cleaned_data['page_name']

        if not self.object:
            # Page doesn't exist yet, so let's redirect to page creation screen
            Page(name=page_name, region=self.get_region())
            url = reverse('pages:edit', kwargs={'slug': page_name, 'region': self.get_region()})
            return HttpResponseRedirect('%s?tag=%s' % (url, tag_slug))

        t = Tag.objects.get(slug=tag_slug, region=self.get_region())
        pts = PageTagSet.objects.filter(page=self.object, region=self.get_region())
        if pts.exists():
            pts = pts[0]
        else:
            pts = PageTagSet(page=self.object, region=self.get_region())

        tag_name = Tag._meta.verbose_name.lower()
        pts.save(comment=_("added %(name)s %(added)s.") % {'name': tag_name, 'added': tag_slug})

        if pts.tags and t not in pts.tags.all():
            pts.tags.add(t)

        return super(AddSingleTagView, self).form_valid(form)

    def get_object(self):
        from pages.models import slugify
        p = Page.objects.filter(slug=slugify(self.request.POST['page_name']), region=self.get_region())
        if p.exists():
            return p[0]

    def get_success_url(self):
        return self.request.POST.get('next')


def suggest_tags(request):
    """
    Simple tag suggest.
    """
    def _make_unique(l):
        d = {}
        ll = []
        for m in l:
            if m['slug'] in d:
                continue
            ll.append(m) 
            d[m['slug']] = True
        return ll

    # XXX TODO: Break this out when doing the API work.
    import json

    term = request.GET.get('term', None)
    if not term:
        return HttpResponse('')
    region_id = request.GET.get('region_id', None)
    if region_id is not None:
        results = Tag.objects.filter(
            slug__startswith=slugify(term),
            region__id=int(region_id)).exclude(pagetagset=None)

        if len(results) < 5:
            # Set a sane limit before adding
            results = results.values('slug').distinct().values('slug', 'name').order_by('slug')[:20]
            global_results = Tag.objects.filter(
                slug__startswith=slugify(term)).exclude(pagetagset=None).values('slug').distinct().values('slug', 'name').order_by('slug')[:20]
            results = _make_unique(list(results) + list(global_results))[:20]
        else:
            results = results.values('slug').distinct().values('slug', 'name').order_by('slug')[:20]

    else:
        results = Tag.objects.filter(
            slug__startswith=slugify(term)).exclude(pagetagset=None).values('slug').distinct().values('slug', 'name').order_by('slug')[:20]

    results = [t['name'] for t in results]
    return HttpResponse(json.dumps(results))
