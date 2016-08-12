from django import forms
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from .models import PageMigrateSource

class PageMigrateSourceForm(forms.ModelForm):
    class Meta:
        model = PageMigrateSource
        fields = ('source_file', 'tags')

    def __init__(self, *args, **kwargs):
        region = kwargs.pop('region', None)
        super(PageMigrateSourceForm, self).__init__(*args, **kwargs)

        from localwiki.tags.forms import TagSetField
        self.fields['tags'] = TagSetField(region=region, required=False)
