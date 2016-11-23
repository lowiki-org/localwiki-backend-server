# coding=utf-8
from django.views.generic import TemplateView
from django.contrib import messages
from django.utils.translation import ugettext as _
from django.http import HttpResponse
from localwiki.utils.urlresolvers import reverse

from localwiki.regions.views import RegionAdminRequired, RegionMixin, FormView
from localwiki.pages.models import Page
from localwiki.page_scores.models import PageScore
from localwiki.tags.models import Tag, PageTagSet
from localwiki.maps.models import MapData
from .forms import PageMigrateSourceForm, PageExportSourceForm
from .unicode_csv import UnicodeDictReader, UnicodeWriter

from django.contrib.gis.geos import GEOSGeometry

from zipfile import ZipFile
from fastkml import kml
from pygeoif import geometry
from html2text import html2text


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

        messages.add_message(self.request, messages.SUCCESS, _(
            u"File has been imported.  Total %(total)d records updated, including %(new)d new records.") % migrator.migration_result)

        return super(RegionPageMigrateView, self).form_valid(form)


class RegionPageExportView(RegionAdminRequired, RegionMixin, FormView):
    template_name = 'migrate/region_page_export.html'
    form_class = PageExportSourceForm

    def get_form_kwargs(self):
        kwargs = super(RegionPageExportView, self).get_form_kwargs()
        kwargs['region'] = self.get_region()
        return kwargs

    def get_success_url(self):
        return reverse('migrate:regions', kwargs={'region': self.get_region().slug})

    def form_valid(self, form):
        exporter = RegionExporter(
            region=self.get_region(),
            export_type=form['export_type'].value())
        exporter.export_to_file()

        messages.add_message(
            self.request, messages.SUCCESS, _(u"Export success."))

        if exporter.file_mime_type == 'text/csv':
            ext = 'csv'
        elif exporter.file_mime_type == 'application/json':
            ext = 'json'
        elif exporter.file_mime_type == 'application/vnd.google-earth.kml+xml':
            ext = 'kml'
        elif exporter.file_mime_type == 'text/plain':
            ext = 'txt'
        elif exporter.file_mime_type == 'application/zip':
            ext = 'zip'

        # Send file to user
        # response = HttpResponse(mimetype='application/force-download')
        response = HttpResponse(
            exporter.file, content_type=exporter.file_mime_type)
        response[
            'Content-Disposition'] = 'attachment; filename=export.%s' % ext
        response['X-Sendfile'] = 'export.%s' % ext

        # return super(RegionPageExportView, self).form_valid(form)
        return response


import mwparserfromhell


class PageTemplateMigrator():

    def __init__(self, region=None):
        self.region = region
        self.records = []
        self.param_keys = []
        self.template_page = None
        self.tags = []
        self.migration_result = {'total': 0, 'new': 0}

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
        self.param_keys = [unicode(t.name) for t in mwparserfromhell.parse(
            page.content).filter_templates()]

    def add_tag(self, tag):
        self.tags.append(tag)

    def get_name(self, rec):
        if u'名稱' in rec:
            return rec[u'名稱']
        elif u'機構名稱' in rec:
            return rec[u'機構名稱']
        else:
            return None

    def get_latitude(self, rec):
        if u'緯度' in rec:
            return rec[u'緯度']
        elif 'Y' in rec:
            return rec['Y']
        else:
            return None

    def get_longitude(self, rec):
        if u'經度' in rec:
            return rec[u'經度']
        elif 'X' in rec:
            return rec['X']
        else:
            return None

    def migrate(self):
        for rec in self.records:
            if self.get_name(rec) == None:
                continue
            self.migrate_record(rec)

    def migrate_record(self, record):
        slug = self.get_name(record)
        longitude = self.get_longitude(record)
        latitude = self.get_latitude(record)

        try:
            new_page = Page.objects.get(slug=slug, region=self.region)
        except Page.DoesNotExist:
            new_page = Page(name=slug, slug=slug, region=self.region)
            self.migration_result['new'] = self.migration_result['new'] + 1

        if self.template_page != None and len(self.param_keys) > 0:
            new_page.content = u'{{%s}}' % "|".join(
                [self.template_name] + [u'%s=%s' % (k, record[k]) for k in self.param_keys if k in record])
        new_page.save()

        if not PageScore.objects.filter(page=new_page).exists():
            score = PageScore(score=1, page=new_page,
                              page_content_length=len(new_page.content)).save()

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

        if longitude != None and latitude != None:
            try:
                mapdata = new_page.mapdata
            except MapData.DoesNotExist:
                mapdata = MapData(page=new_page, region=self.region)
            mapdata.points = GEOSGeometry(
                """MULTIPOINT (%s %s)""" % (longitude, latitude))
            mapdata.save()


class RegionExporter:

    def __init__(self, **kwargs):
        self.region = kwargs['region']
        self.export_type = kwargs['export_type']
        self.file = None
        self.file_mime_type = None

    def _get_export_pages(self):
        return self.region.page_set.exclude(slug__startswith='template')

    def export_to_file(self):
        if self.export_type == 'csv':
            self.exportCSV()
        elif self.export_type == 'json':
            self.exportJSON()
        elif self.export_type == 'txt':
            self.exportTXT()
        elif self.export_type == 'kml':
            self.exportKML()

    def exportTXT(self):
        for page in self._get_export_pages():
            with open('/tmp/%s.txt' % page.id, 'w') as f:
                f.write('## ')
                f.write(page.name.encode('utf-8'))
                f.write('\n\n')
                f.write(html2text(page.content).encode('utf-8'))
                f.close()
        with ZipFile('/tmp/export.zip', 'w') as zf:
            for page in self._get_export_pages():
                zf.write('/tmp/%s.txt' % page.id)
            zf.close()
        self.file = open('/tmp/export.zip', 'r')
        self.file_mime_type = 'application/zip'

    def exportJSON(self):
        pass

    def exportCSV(self):
        rows = []
        rows.append(['id', 'name', 'slug', 'tags',
                     'region', 'region_name', 'content'])
        for page in self._get_export_pages():
            rows.append([
                str(page.id),
                page.name,
                page.slug,
                " ".join([t.name for t in page.pagetagset.tags.all()]),
                self.region.slug,
                self.region.full_name,
                page.content])

        self.filename = '/tmp/export_file.csv'
        with open(self.filename, 'w') as f:
            writer = UnicodeWriter(f)
            writer.writerows(rows)
        self.file = open(self.filename, 'r')
        self.file_mime_type = 'text/csv'

    def exportKML(self):
        k = kml.KML()
        ns = '{http://www.opengis.net/kml/2.2}'
        d = kml.Document(ns, '0', 'Export', 'Exported from Lowiki')
        k.append(d)
        f = kml.Folder(ns, '1', 'Locations', 'Locations in Lowiki')
        d.append(f)
        for page in self._get_export_pages():
            try:
                p = kml.Placemark(ns, str(page.id),
                                  page.name, '')
                p.geometry = geometry.from_wkt(page.mapdata.geom.wkt)
                f.append(p)
            except:
                pass
        filename = '/tmp/export.kml'
        with open(filename, 'w') as f:
            f.write(k.to_string().encode('utf-8'))
            f.close()
        self.file = open(filename, 'r')
        self.file_mime_type = 'application/vnd.google-earth.kml+xml'
