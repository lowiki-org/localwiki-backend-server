from django.db import models

from localwiki.tags.models import Tag

class PageMigrateSource(models.Model):
    source_file = models.FileField(upload_to='uploads/import')
    tags = models.ManyToManyField(Tag)
    region = models.ForeignKey('regions.Region', null=True)
