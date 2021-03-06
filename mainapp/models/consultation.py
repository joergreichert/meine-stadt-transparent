from django.db import models

from .default_fields import DefaultFields
from .meeting import Meeting
from .organization import Organization
from .paper import Paper


class Consultation(DefaultFields):
    """
    See https://github.com/OParl/spec/issues/381 for why we need an extra consultation when there is agenda item
    """

    title = models.TextField(null=True, blank=True)
    meeting = models.ForeignKey(
        Meeting, null=True, blank=True, on_delete=models.CASCADE
    )
    paper = models.ForeignKey(Paper, null=True, blank=True, on_delete=models.CASCADE)
    authoritative = models.NullBooleanField(blank=True)
    organizations = models.ManyToManyField(Organization, blank=True)
    role = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return "{} {} {}".format(self.meeting, self.meeting.id, self.paper)

    def single_agenda_item(self):
        if self.agendaitem_set.count() == 1:
            return self.agendaitem_set.first()
