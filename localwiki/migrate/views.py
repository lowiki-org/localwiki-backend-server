# coding=utf-8
from django.views.generic import TemplateView
from django.contrib import messages
from django.utils.translation import ugettext as _
from localwiki.utils.urlresolvers import reverse

from localwiki.regions.views import RegionAdminRequired, RegionMixin, FormView
from localwiki.pages.models import Page
from localwiki.page_scores.models import PageScore
from localwiki.tags.models import Tag, PageTagSet
from localwiki.maps.models import MapData
from .forms import PageMigrateSourceForm
from .unicode_csv import UnicodeDictReader

from django.contrib.gis.geos import GEOSGeometry

class RegionPageMigrateView(RegionAdminRequired, RegionMixin, FormView):
    template_name = 'migrate/region_page_import.html'
    form_class = PageMigrateSourceForm

    def get_form_kwargs(self):
        kwargs = super(RegionPageMigrateView, self).get_form_kwargs()
        kwargs['region'] = self.get_region()
        return kwargs

    def get_success_url(self):
        return reverse('migrate:regions', kwargs={'region': self.get_region().slug})

    def form_valid(self, form):
        migrator = PageTemplateMigrator(region=self.get_region())
        if form['tags'].value():
            tag_slugs = form['tags'].value().split(', ')
            for template in migrator.get_templates():
                if template.name.replace(u'Templates/', u'') in tag_slugs:
                    migrator.set_template(template)
                    break
            tags = self.get_region().tag_set.filter(slug__in=tag_slugs)
            if tags.exists():
                for tag in tags:
                    migrator.add_tag(tag)
        records = UnicodeDictReader(form['source_file'].value())
        for rec in records:
            migrator.add_record(rec)
        migrator.migrate()

        messages.add_message(self.request, messages.SUCCESS, _(u"File has been imported.  Total %(total)d records updated, including %(new)d new records.") % migrator.migration_result)

        return super(RegionPageMigrateView, self).form_valid(form)


import mwparserfromhell

class PageTemplateMigrator():

    def __init__(self, region=None):
        self.region = region
        self.records = []
        self.param_keys = []
        self.template_page = None
        self.tags = []
        self.migration_result = { 'total': 0, 'new': 0 }

    def add_record(self, record):
        for k, v in record.iteritems():
            record[k] = v.replace('\n', '')
        self.records.append(record)

    def get_templates(self):
        return Page.objects.filter(
                slug__startswith='templates/', region=self.region
            )

    def set_template(self, page):
        self.template_page = page
        self.template_name = page.name.replace('Templates/', '')
        self.param_keys = [ unicode(t.name) for t in mwparserfromhell.parse(page.content).filter_templates() ]

    def add_tag(self, tag):
        self.tags.append(tag)

    def migrate(self):
        for rec in self.records:
            if u'名稱' not in rec:
                continue
            self.migrate_record(rec)

    def migrate_record(self, record):

        try:
            new_page = Page.objects.get(slug=record[u'名稱'], region=self.region)
        except Page.DoesNotExist:
            new_page = Page(name=record[u'名稱'], slug=record[u'名稱'], region=self.region)
            self.migration_result['new'] = self.migration_result['new'] + 1

        if self.template_page != None and len(self.param_keys) > 0:
            new_page.content = u'{{%s}}' % "|".join(
                    [self.template_name] + [ u'%s=%s' % (k, record[k]) for k in self.param_keys if k in record ])
        new_page.save()

        if not PageScore.objects.filter(page=new_page).exists():
            score = PageScore(score=1, page=new_page, page_content_length=len(new_page.content)).save()

        self.migration_result['total'] = self.migration_result['total'] + 1

        if len(self.tags) > 0:
            try:
                tagset = new_page.pagetagset
            except PageTagSet.DoesNotExist:
                tagset = PageTagSet(page=new_page, region=self.region)
                tagset.save()
            for tag in self.tags:
                if not tagset.tags.filter(pk=tag.pk).exists():
                    tagset.tags.add(tag)

        if u'經度' in record and u'緯度' in record:
            try:
                mapdata = new_page.mapdata
            except MapData.DoesNotExist:
                mapdata = MapData(page=new_page, region=self.region)
            mapdata.points = GEOSGeometry("""MULTIPOINT (%s %s)""" % (record[u'經度'], record[u'緯度']))
            mapdata.save()
