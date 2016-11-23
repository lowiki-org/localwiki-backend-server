from django import forms
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from .models import PageMigrateSource, PageExport

EXPORT_TYPE_CHOICES = (
    ('csv', 'CSV'),
    # ('json', 'JSON'),
    ('txt', 'TXT'),
    ('kml', 'KML'),
)


class PageMigrateSourceForm(forms.ModelForm):

    class Meta:
        model = PageMigrateSource
        fields = ('source_file', 'tags')

    def __init__(self, *args, **kwargs):
        region = kwargs.pop('region', None)
        super(PageMigrateSourceForm, self).__init__(*args, **kwargs)

        from localwiki.tags.forms import TagSetField
        self.fields['tags'] = TagSetField(region=region, required=False)


class PageExportSourceForm(forms.Form):
    export_type = forms.ChoiceField(
        widget=forms.Select, choices=EXPORT_TYPE_CHOICES)

    def __init__(self, *args, **kwargs):
        region = kwargs.pop('region', None)
        super(PageExportSourceForm, self).__init__(*args, **kwargs)

        # from localwiki.pages.forms import Page
        # self.fields['tags'] = PageSetField(region=region, required=False)
