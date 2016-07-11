from dateutil.parser import parse as dateparser
import time
import urllib
import copy

from django.conf import settings
from django.views.generic.base import RedirectView
from django.contrib.auth.models import User
from django.template import Template
from django.template import RequestContext
from django.views.generic import (View, DetailView, ListView,
    FormView)
from django.http import (HttpResponseNotFound, HttpResponseRedirect,
                         HttpResponseBadRequest, HttpResponse, Http404)
from django import forms
from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape
from django.utils.http import urlquote
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from follow.models import Follow

from ckeditor.views import ck_upload_result
from versionutils import diff
from versionutils.versioning.views import UpdateView
from versionutils.versioning.views import VersionsList
from localwiki.utils.views import (Custom404Mixin, CreateObjectMixin,
    PermissionRequiredMixin, DeleteView, RevertView,
    CacheMixin, NeverCacheMixin)
from localwiki.utils.urlresolvers import reverse
from regions.models import Region
from regions.views import RegionMixin, region_404_response
from maps.widgets import InfoMap
from users.views import SetPermissionsView, AddContributorsMixin

from .models import slugify, clean_name, Page, PageFile, url_to_name
from .forms import PageForm, PageFileForm, _has_blacklist_title
from .utils import is_user_page
from .exceptions import PageExistsError


class BasePageDetailView(Custom404Mixin, AddContributorsMixin, RegionMixin, DetailView):
    model = Page
    context_object_name = 'page'

    def get_object(self):
        slug = self.kwargs.get('slug')
        return get_object_or_404(Page,
            slug=slugify(slug), region=self.get_region())

    def handler404(self, request, *args, **kwargs):
        name = url_to_name(kwargs['original_slug'])
        try:
            region = self.get_region(request=request, kwargs=kwargs)
        except Http404:
            return region_404_response(request, kwargs['region']) 
        slug = kwargs['slug']

        page_templates = Page.objects.filter(
                slug__startswith='templates/', region=region
            ).order_by('name')
        page = Page(name=name, slug=slug, region=region)
        return HttpResponseNotFound(
            render(request, 'pages/page_new.html',
                   {'page': page, 'page_templates': page_templates,
                    'region': region})
        )

    def get_context_data(self, **kwargs):
        from maps.widgets import map_options_for_region

        context = super(BasePageDetailView, self).get_context_data(**kwargs)
        context['region'] = self.object.region
        context['date'] = self.object.versions.most_recent().version_info.date
        if hasattr(self.object, 'mapdata'):
            # Remove the PanZoom on normal page views.
            olwidget_options = copy.deepcopy(getattr(settings,
                'OLWIDGET_DEFAULT_OPTIONS', {}))
            map_opts = olwidget_options.get('map_options', {})
            map_controls = map_opts.get('controls', [])
            if 'PanZoom' in map_controls:
                map_controls.remove('PanZoom')
            if 'PanZoomBar' in map_controls:
                map_controls.remove('PanZoomBar')
            if 'KeyboardDefaults' in map_controls:
                map_controls.remove('KeyboardDefaults')
            if 'Navigation' in map_controls:
                map_controls.remove('Navigation')
            olwidget_options['map_options'] = map_opts
            olwidget_options['map_div_class'] = 'mapwidget small'
            olwidget_options.update(map_options_for_region(self.object.region))
            context['map'] = InfoMap(
                [(self.object.mapdata.geom, self.object.name)],
                options=olwidget_options)
        return context


class PageDetailView(CacheMixin, BasePageDetailView):
    cache_keep_forever = True

    @staticmethod
    def get_cache_key(*args, **kwargs):
        from django.core.urlresolvers import get_urlconf
        from pages.models import name_to_url
        urlconf = get_urlconf() or settings.ROOT_URLCONF
        slug = kwargs.get('slug')
        region = CacheMixin.get_region_slug_param(*args, **kwargs)
        # Control characters and whitespace not allowed in memcached keys
        return '%s/%s/%s' % (urlconf, name_to_url(region), slugify(slug).replace(' ', '_'))


class PageVersionDetailView(BasePageDetailView):
    template_name = 'pages/page_version_detail.html'

    def get_object(self):
        page = Page(slug=self.kwargs['slug'], region=self.get_region())
        version = self.kwargs.get('version')
        date = self.kwargs.get('date')
        if version:
            return page.versions.as_of(version=int(version))
        if date:
            return page.versions.as_of(date=dateparser(date))

    def get_context_data(self, **kwargs):
        # we don't want PageDetailView's context, skip to DetailView's
        context = super(DetailView, self).get_context_data(**kwargs)
        context['region'] = self.get_region()
        context['date'] = self.object.version_info.date
        context['show_revision'] = True
        return context


class PageUpdateView(PermissionRequiredMixin, CreateObjectMixin,
                     RegionMixin, UpdateView):
    model = Page
    form_class = PageForm
    permission = 'pages.change_page'

    def success_msg(self):
        # NOTE: This is eventually marked as safe when rendered in our
        # template.  So do *not* allow unescaped user input!
        #
        # XXX TODO: Refactor this into something more general + show this
        # message on other content types (maps, tags)
        default_message = '<div>%s</div>' % _('Thank you for your changes. '
                   'Your attention to detail is appreciated.')
        log_in_message = ''
        map_create_link = ''
        follow_message = ''
        share_message = ''

        if not self.request.user.is_authenticated():
            default_message = '<div>%s</div>' % (_('Changes saved! To use your name when editing, please '
                '<a href="%(login_url)s?next=%(current_path)s"><strong>log in</strong></a> or '
                '<a href="%(register_url)s?next=%(current_path)s"><strong>create an account</strong></a>.')
                % {'login_url': reverse('auth_login'),
                   'current_path' :self.request.path,
                   'register_url': reverse('registration_register')
                   }
                )
        if not hasattr(self.object, 'mapdata') and not is_user_page(self.object):
            slug = self.object.pretty_slug
            map_create_link = (_(
                '<p class="create_map"><a href="%s" class="button little map">'
                '<span class="text">Create a map</span></a> '
                'for this page?</p>') %
                reverse('maps:edit', kwargs={'region': self.object.region.slug, 'slug': slug})
            )

        if self.request.user.is_authenticated() and not map_create_link:
            if is_user_page(self.object):
                obj = User.objects.get(username__iexact=self.kwargs['original_slug'][6:])
                following = Follow.objects.filter(user=self.request.user, target_user=obj).exists()
            else:
                following = Follow.objects.filter(user=self.request.user, target_page=self.object).exists()
                obj = self.object

            # They're already auto-following their own user page
            own_user_page = slugify(self.object.name) == slugify('users/%s' % self.request.user.username)
            if not following and not own_user_page:
                t = Template("""
{% load follow_tags %}
{% load i18n %}
{% trans "page" as object_type %}
{% follow_form page %}
                """)
                c = RequestContext(self.request, {
                    'page': obj,
                    'follow_text': _("Follow this page"),
                })
                follow_message = '<div>%s</div>' % (_("%(follow_page_notice)s for updates!") % {'follow_page_notice': t.render(c)})

        if not map_create_link:
            # Translators: Keep under < 100 characters
            twitter_status = _("I just edited %(page)s on @localwiki! %(page_url)s") % {
                'page': self.object.name,
                'page_url': ('https://localwiki.org%s' % self.object.get_url_for_share(self.request)),
            }
            twitter_status = urllib.quote(twitter_status.encode('utf-8'))
            share_message = _("Tell the world about this page:")
            share_message = "%(share_message)s<div>%(fb_link)s %(twitter_link)s</div>" % {
                'share_message': share_message,
                'fb_link': ('<a target="_blank" class="button tiny" href="https://www.facebook.com/sharer/sharer.php?u=https://localwiki.org%s"></a>' %
                    self.object.get_url_for_share(self.request)),
                'twitter_link': ('<a target="_blank" class="button tiny" href="https://twitter.com/home?status=%s"></a>' % twitter_status)
            }
            share_message = '<div class="share_message">%s</div>' % share_message
            
            
        return '%s%s%s%s' % (default_message, map_create_link, follow_message, share_message)

    def get_success_url(self):
        region = self.get_region()
        return reverse('pages:show',
            kwargs={'region': region.slug, 'slug': self.object.pretty_slug})

    def form_valid(self, form):
        from tags.models import PageTagSet, Tag
        from tags.models import slugify as tag_slugify

        val = super(PageUpdateView, self).form_valid(form)

        if 'tag' in self.request.GET:
            # Add tag to page
            t = self.request.GET.get('tag')
            t = Tag.objects.get(slug=tag_slugify(t), region=self.object.region)
            if PageTagSet.objects.filter(page=self.object, region=self.object.region).exists():
                pts = self.object.pagetagset
            else:
                pts = PageTagSet(page=self.object, region=self.object.region)

            tag_name = Tag._meta.verbose_name.lower()
            pts.save(comment=_("added %(name)s %(added)s.") % {'name': tag_name, 'added': t})

            pts.tags.add(t)

        return val

    def create_object(self):
        pagename = clean_name(self.kwargs['original_slug'])
        content = _('<p>What do you know about %s?</p>') % pagename
        if 'template' in self.request.GET:
            try:
                p = Page.objects.get(
                        slug=self.request.GET['template'],
                        region=self.get_region())
                content = p.content
            except Page.DoesNotExist:
                pass
        return Page(name=url_to_name(self.kwargs['original_slug']),
                    content=content, region=self.get_region())


class PageDeleteView(PermissionRequiredMixin, RegionMixin, DeleteView):
    model = Page
    context_object_name = 'page'
    permission = 'pages.delete_page'

    def get_success_url(self):
        # Redirect back to the page.
        region = self.get_region()
        return reverse('pages:show',
            kwargs={'region': region.slug, 'slug': self.kwargs.get('original_slug')})


class PageRevertView(PermissionRequiredMixin, RegionMixin, RevertView):
    model = Page
    context_object_name = 'page'
    permission = 'pages.delete_page'

    def get_object(self):
        page = Page(slug=self.kwargs['slug'], region=self.get_region())
        return page.versions.as_of(version=int(self.kwargs['version']))

    def get_success_url(self):
        region = self.get_region()
        # Redirect back to the page.
        return reverse('pages:show',
            kwargs={'region': region.slug, 'slug': self.kwargs.get('original_slug')})


class PageVersionsList(RegionMixin, VersionsList):
    def get_queryset(self):
        p = Page(slug=self.kwargs['slug'], region=self.get_region())
        all_page_versions = p.versions.all().defer('content').select_related('history_user')
        # We set self.page to the most recent historical instance of the
        # page.
        if all_page_versions:
            self.page = all_page_versions[0]
        else:
            self.page = Page(slug=self.kwargs['slug'],
                             name=self.kwargs['original_slug'],
                             region=self.get_region())
        return all_page_versions

    def get_context_data(self, **kwargs):
        context = super(PageVersionsList, self).get_context_data(**kwargs)
        context['page'] = self.page
        return context


class PageFileListView(RegionMixin, ListView):
    context_object_name = "file_list"
    template_name = "pages/page_files.html"

    def get_queryset(self):
        return PageFile.objects.filter(
            slug__exact=self.kwargs['slug'], region=self.get_region())

    def get_context_data(self, **kwargs):
        context = super(PageFileListView, self).get_context_data(**kwargs)
        context['slug'] = self.kwargs['original_slug']
        context['region'] = self.get_region()
        return context


class PageFilebrowserView(NeverCacheMixin, PageFileListView):
    template_name = 'pages/cke_filebrowser.html'

    def get_context_data(self, **kwargs):
        context = super(PageFilebrowserView, self).get_context_data(**kwargs)
        _filter = self.kwargs.get('filter', 'files')
        if _filter == 'images':
            self.object_list = [f for f in self.object_list if f.is_image()]
            context['thumbnail'] = True
        return context


class PageFileView(RegionMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, slug, file, **kwargs):
        page_file = get_object_or_404(PageFile,
            slug__exact=slug, name__exact=file, region=self.get_region())
        return page_file.file.url


class PageFileVersionDetailView(RegionMixin, RedirectView):
    def get_redirect_url(self, slug, file, **kwargs):
        page_file = PageFile(slug=slug, name=file, region=self.get_region())
        version = self.kwargs.get('version')
        date = self.kwargs.get('date')

        if version:
            page_file = page_file.versions.as_of(version=int(version))
        if date:
            page_file = page_file.versions.as_of(date=dateparser(date))

        return page_file.file.url


class PageFileCompareView(RegionMixin, diff.views.CompareView):
    model = PageFile

    def get_object(self):
        return PageFile(
            slug=self.kwargs['slug'],
            name=self.kwargs['file'],
            region=self.get_region())

    def get_context_data(self, **kwargs):
        context = super(PageFileCompareView, self).get_context_data(**kwargs)
        context['slug'] = self.kwargs['original_slug']
        return context


class PageFileRevertView(PermissionRequiredMixin, RegionMixin, RevertView):
    model = PageFile
    context_object_name = 'file'
    permission = 'pages.change_page'

    def get_object(self):
        _file = PageFile(slug=self.kwargs['slug'],
                        name=self.kwargs['file'],
                        region=self.get_region())
        return _file.versions.as_of(version=int(self.kwargs['version']))

    def get_protected_object(self):
        return Page.objects.get(slug=self.object.slug, region=self.get_region())

    def get_success_url(self):
        region = self.get_region()
        # Redirect back to the file info page.
        return reverse('pages:file-info', kwargs={
            'region': region.slug,
             'slug': self.kwargs['slug'],
             'file': self.kwargs['file']
        })


class PageFileInfo(RegionMixin, VersionsList):
    template_name_suffix = '_info'

    def get_queryset(self):
        all_file_versions = PageFile(
            slug=self.kwargs['slug'],
            name=self.kwargs['file'],
            region=self.get_region()
        ).versions.all()
        # We set self.file to the most recent historical instance of the
        # file.
        if all_file_versions:
            self.file = all_file_versions[0]
        else:
            self.file = PageFile(slug=self.kwargs['slug'],
                                 name=self.kwargs['file'],
                                 region=self.get_region())
        return all_file_versions

    def get_context_data(self, **kwargs):
        context = super(PageFileInfo, self).get_context_data(**kwargs)
        context['file'] = self.file
        context['form'] = PageFileForm()
        return context


class PageCompareView(CacheMixin, RegionMixin, diff.views.CompareView):
    model = Page
    cache_timeout = 60 * 60 * 4

    def get_object(self):
        ph = Page(slug=self.kwargs['slug'], region=self.get_region()).versions.most_recent()
        return ph.version_info._object

    def get_context_data(self, **kwargs):
        context = super(PageCompareView, self).get_context_data(**kwargs)
        context['page_diff'] = diff.diff(context['old'], context['new'])
        return context

    @staticmethod
    def get_cache_key(*args, **kwargs):
        from django.core.urlresolvers import get_urlconf
        from pages.models import name_to_url
        import urllib
        urlconf = get_urlconf() or settings.ROOT_URLCONF
        region = CacheMixin.get_region_slug_param(*args, **kwargs)
        slug = kwargs.get('slug')
        # Control characters and whitespace not allowed in memcached keys
        date1 = name_to_url(kwargs.get('date1', ''))
        date2 = name_to_url(kwargs.get('date2', ''))
        version1 = name_to_url(kwargs.get('version1', ''))
        version2 = name_to_url(kwargs.get('version2', ''))
        return 'diff:%s/%s/%s/%s/%s/%s/%s' % (urlconf, name_to_url(region), date1, date2, version1, version2, slugify(slug).replace(' ', '_'))


class PageCreateView(RegionMixin, RedirectView):
    """
    A convenience view that redirects either to the editor (for a new
    page) or to the page (if it already exists).
    """
    def get_redirect_url(self, **kwargs):
        pagename = self.request.GET.get('pagename', '')
        if not pagename.strip():
            # No page name provided, so let's return a useful error message.
            messages.add_message(self.request, messages.SUCCESS,
                _('You must provide a page name when creating a page.'))
            return reverse('haystack_search')

        slug = slugify(pagename)
        region = self.get_region()
        if Page.objects.filter(slug=slug, region=region).exists():
            return Page.objects.get(slug=slug, region=region).get_absolute_url()
        else:
            if self.request.GET.get('show_templates'):
                # Show them the 'empty page' page, which displays the list of
                # templates to create a page with.
                return reverse('pages:show', kwargs={'region': region.slug, 'slug': pagename})
            else:
                return reverse('pages:edit', kwargs={'region': region.slug, 'slug': pagename})


def _find_available_filename(filename, slug, region):
    """
    Returns a filename that isn't taken for the given page slug.
    """
    basename, ext = filename.rsplit(".", 1)
    suffix_count = 1
    while PageFile.objects.filter(name=filename, slug=slug,
                                  region=region).exists():
        suffix_count += 1
        filename = "%s %d.%s" % (basename, suffix_count, ext)
    return filename


class UploadView(PermissionRequiredMixin, RegionMixin, View):
    http_method_names = ['get', 'post']
    permission = 'pages.change_page'

    def get(self, request, *args, **kwargs):
        # For GET, just return blank response. See issue #327.
        return HttpResponse('')

    def post(self, request, *args, **kwargs):
        slug = kwargs['slug']
        region = self.get_region()

        error = None
        file_form = PageFileForm(request.POST, request.FILES)

        uploaded = request.FILES['file']
        if 'file' in kwargs:
            # Replace existing file if exists
            try:
                file = PageFile.objects.get(
                    slug__exact=slug,
                    name__exact=kwargs['file'],
                    region=region
                )
                file.file = uploaded
            except PageFile.DoesNotExist:
                file = PageFile(
                    file=uploaded,
                    name=uploaded.name,
                    slug=slug,
                    region=region
                )
            file_form.instance = file
            if not file_form.is_valid():
                error = file_form.errors.values()[0]
            else:
                file_form.save()

            if error is not None:
                return HttpResponseBadRequest(error)
            return HttpResponseRedirect(
                reverse('pages:file-info',
                        kwargs={'region': region.slug, 'slug': slug, 'file': kwargs['file']}))

        # uploaded from ckeditor
        filename = _find_available_filename(uploaded.name, slug, region)
        relative_url = '_files/' + urlquote(filename)
        try:
            file = PageFile(file=uploaded, name=filename, slug=slug, region=region)
            file.save()
            return ck_upload_result(request, url=relative_url)
        except IntegrityError:
            error = _('A file with this name already exists')
        return ck_upload_result(request, url=relative_url, message=error)

    def get_protected_object(self):
        slug = slugify(self.kwargs['slug'])
        region = self.get_region()

        if Page.objects.filter(slug=slug, region=region).exists():
            return Page.objects.get(slug=slug, region=region)
        return Page(slug=slug, region=region)


class RenameForm(forms.Form):
    # Translators: This is for the page rename form.
    pagename = forms.CharField(max_length=255, label=ugettext_lazy("New page name"))
    comment = forms.CharField(max_length=150, required=False, label=ugettext_lazy("Comment"))

    def clean_pagename(self):
        name = self.cleaned_data['pagename']
        if _has_blacklist_title(name):
            raise forms.ValidationError()

        return name


class PageRenameView(PermissionRequiredMixin, RegionMixin, FormView):
    form_class = RenameForm
    template_name = 'pages/page_rename.html'
    permission = 'pages.change_page'

    def form_valid(self, form):
        region = self.get_region()
        try:
            p = Page.objects.get(
                slug=slugify(self.kwargs['slug']),
                region=region
            )
            self.new_pagename = form.cleaned_data['pagename']
            p.rename_to(self.new_pagename)
        except PageExistsError, s:
            messages.add_message(self.request, messages.SUCCESS, s)
            return HttpResponseRedirect(
                reverse('pages:show', kwargs={'region': region.slug, 'slug': p.slug}))

        return HttpResponseRedirect(self.get_success_url())

    def get_protected_objects(self):
        return [Page.objects.get(slug=slugify(self.kwargs['slug']), region=self.get_region())]

    def get_context_data(self, **kwargs):
        context = super(PageRenameView, self).get_context_data(**kwargs)
        context['page'] = Page.objects.get(slug=slugify(self.kwargs['slug']),
                                           region=self.get_region())
        return context

    def success_msg(self):
        # NOTE: This is eventually marked as safe when rendered in our
        # template.  So do *not* allow unescaped user input!
        return ('<div>' + _('Page renamed to "%s"') + '</div>') % escape(self.new_pagename)

    def get_success_url(self):
        region = self.get_region()
        messages.add_message(self.request, messages.SUCCESS,
            self.success_msg())
        # Redirect back to the page.
        return reverse('pages:show',
            kwargs={'region': region.slug, 'slug': self.new_pagename})


class MoveRegionForm(forms.Form):
    new_region = forms.CharField(max_length=255, label=ugettext_lazy("Move to region (short name)"))


class PageMoveRegionView(PermissionRequiredMixin, RegionMixin, FormView):
    form_class = MoveRegionForm
    template_name = 'pages/page_move_region.html'
    permission = 'is_staff'

    def get_object(self):
        page_slug = slugify(self.kwargs['slug'])
        self.page = Page.objects.get(slug=page_slug, region=self.get_region())
        return self.page

    def form_valid(self, form):
        from regions.utils import move_to_region

        self.page = self.get_object()
        self.new_region_slug = form.cleaned_data['new_region']
        self.new_region = Region.objects.get(slug__iexact=self.new_region_slug)

        move_to_region(self.new_region, pages=[self.page]) 
        return HttpResponseRedirect(self.get_success_url())

    def success_msg(self):
        # NOTE: This is eventually marked as safe when rendered in our
        # template.  So do *not* allow unescaped user input!
        return ('<div>' + _('Page moved to <a href="%(page_url)s">%(page_name)s</a> on <a href="%(region_url)s">%(region_slug)s</a>') + '</div>') % {
            'page_url': self.page.get_absolute_url(),
            'page_name': self.page.name,
            'region_url': self.new_region.get_absolute_url(),
            'region_slug': self.new_region_slug,
        }

    def get_success_url(self):
        region = self.get_region()
        messages.add_message(self.request, messages.SUCCESS,
            self.success_msg())
        # Redirect back to the (now empty) page on the old region.
        return reverse('pages:show',
            kwargs={'region': region.slug, 'slug': self.page.pretty_slug})

    def get_context_data(self, *args, **kwargs):
        context = super(PageMoveRegionView, self).get_context_data(*args, **kwargs)
        context['page'] = self.page
        return context


class PagePermissionsView(SetPermissionsView):
    template_name = 'pages/page_permissions.html'

    def get_object(self):
        return Page.objects.get(slug=self.kwargs.get('slug'), region=self.get_region())

    def get_success_url(self):
        return reverse('pages:show', kwargs={
            'slug':self.get_object().slug, 'region': self.get_region().slug
        })

    def get_context_data(self, *args, **kwargs):
        context = super(PagePermissionsView, self).get_context_data(*args, **kwargs)
        context['page'] = self.get_object()
        return context


class PageRandomView(RegionMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        pgs_in_region = Page.objects.filter(region=self.get_region())
        return pgs_in_region.order_by('?')[0].get_absolute_url()


class PageContentInUsersNamespaceView(PageDetailView):
    def get_object(self):
        region = self.get_region()
        return get_object_or_404(Page,
            slug=slugify(self.kwargs['slug']), region=region)

    def get_region(self, *args, **kwargs):
        if not hasattr(self, 'kwargs'):
            self.kwargs = kwargs['kwargs']

        if self.kwargs['slug'].startswith('users/'):
            username = self.kwargs['slug'].split('/')[1]
        else:
            username = self.kwargs['slug'].split('/')[0]
            self.kwargs['slug'] = 'users/%s' % self.kwargs['slug']
            self.kwargs['original_slug'] = 'Users/%s' % self.kwargs['original_slug']

        user_pagename = 'Users/%s' % username
        user_pages = Page.objects.filter(slug=slugify(user_pagename))
        if user_pages:
            # Just pick the first one
            return user_pages[0].region
        else:
            # Pick the region the user most recently edited in
            if Page.versions.filter(version_info__user__username__iexact=username):
                return Page.versions.filter(version_info__user__username__iexact=username)[0].region
            return Http404

    def handler404(self, request, *args, **kwargs):
        kwargs['slug'] = 'users/%s' % kwargs['slug']
        kwargs['original_slug'] = 'Users/%s' % kwargs['original_slug']

        return super(PageContentInUsersNamespaceView, self).handler404(request, *args, **kwargs)

    @staticmethod
    def get_cache_key(*args, **kwargs):
        if not 'region' in kwargs:
            kwargs['region'] = 'users'
        return PageDetailView.get_cache_key(*args, **kwargs)


def suggest(request, *args, **kwargs):
    """
    Simple page suggest.
    """
    # XXX TODO: Break this out when doing the API work.
    from haystack.query import SearchQuerySet 
    import json

    term = request.GET.get('term', None)
    if 'region_id' in request.GET:
        region_id = int(request.GET.get('region_id'))
    else:
        region_id = None
    if not term:
        return HttpResponse('')

    if region_id is not None:
        results = SearchQuerySet().models(Page).autocomplete(name_auto=term).filter_and(region_id=region_id)
    else:
        results = SearchQuerySet().models(Page).autocomplete(name_auto=term)

    # Set a sane limit
    results = results[:20]

    results = [{'value': p.name, 'region': p.object.region.slug, 'url': p.object.get_absolute_url()} for p in results]
    return HttpResponse(json.dumps(results))
