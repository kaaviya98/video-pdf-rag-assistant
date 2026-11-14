from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from app.models.base import BaseModel
from app.models.asset import Asset


class TranscriptLine(BaseModel):
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="transcript_lines",
    )

    line_number = models.PositiveIntegerField(
        help_text=_("Sequential line number within the transcript for this asset"),
    )

    start_sec = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        db_index=True,
        help_text=_("Start timestamp of the line in seconds"),
    )

    end_sec = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        db_index=True,
        help_text=_("End timestamp of the line in seconds"),
    )

    text = models.TextField(
        help_text=_("Transcript text for this line"),
    )

    class Meta:
        verbose_name = _("Transcript line")
        verbose_name_plural = _("Transcript lines")
        ordering = ("line_number",)
        indexes = [
            models.Index(
                fields=("asset", "start_sec", "end_sec"),
                name="transcript_asset_time_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "line_number"],
                condition=Q(deleted__isnull=True),
                name="uniq_transcriptline_asset_linenumber_not_deleted",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.asset_id} L{self.line_number}"
