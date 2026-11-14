# mypy: disable-error-code="var-annotated"
import uuid

from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from model_utils.fields import MonitorField
from model_utils.fields import StatusField

from app.models.base import OrganizationScopedModel
from app.models.fields import CreatedByField


class AssetFileType(models.IntegerChoices):
    PDF = 0, _("PDF Document")
    VIDEO = 1, _("Video")
    AUDIO = 2, _("Audio")
    POWERPOINT = 3, _("PowerPoint")
    WORD = 4, _("Word Document")


class AssetProcessingStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")


class Asset(OrganizationScopedModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="assets",
        null=True,
        blank=True,
    )

    created_by = CreatedByField()

    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Optional title for the asset"),
    )

    file_url = models.URLField(
        max_length=2000,
        null=True,
        blank=True,
        editable=False,
        help_text=_("URL to the uploaded file"),
    )

    captions_url = models.URLField(
        max_length=2000,
        null=True,
        blank=True,
        help_text=_("URL to the captions file (videos only)"),
    )

    file_type = models.PositiveSmallIntegerField(
        choices=AssetFileType.choices,
        default=AssetFileType.PDF,
        help_text=_("Type of the uploaded file"),
    )

    processing_status = StatusField(
        choices_name="STATUS_CHOICES",
        default=AssetProcessingStatus.PENDING,
        help_text=_("Current processing state of the asset"),
    )

    processing_started_at = MonitorField(
        monitor="processing_status",
        when=[AssetProcessingStatus.PROCESSING],
    )

    processing_completed_at = MonitorField(
        monitor="processing_status",
        when=[AssetProcessingStatus.COMPLETED, AssetProcessingStatus.FAILED],
    )

    processing_error = models.TextField(
        blank=True,
        default="",
        help_text=_("Error message, if asset processing failed"),
    )

    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("ID of the processing task from celery"),
    )

    total_chunks = models.PositiveIntegerField(
        default=0,
        help_text=_("Total number of file chunks (if uploaded in parts)"),
    )

    total_pages = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Total number of pages in the document"),
    )

    scope_key = models.CharField(
        max_length=255,
        db_index=True,
        help_text=_("Tenant identifier for data isolation"),
    )



    ai_outputs_folder_url = models.URLField(
        max_length=2000,
        null=True,
        blank=True,
        help_text=_(
            "Folder/container URL where AI-generated outputs for this asset are uploaded "
            "(e.g. notes, chapters, summaries); provided by the third party when creating the asset.",
        ),
    )

    notes_upload_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text=_(
            "Path (or key) where notes and related AI outputs are uploaded for this asset."
        ),
    )

    STATUS_CHOICES = AssetProcessingStatus

    class Meta(OrganizationScopedModel.Meta):
        abstract = False
        verbose_name = _("Asset")
        verbose_name_plural = _("Assets")
        ordering = ["-created"]  # noqa: RUF012
        get_latest_by = "created"
        indexes = [  # noqa: RUF012
            models.Index(fields=["created"]),
        ]

    def __str__(self) -> str:
        return self.title or f"Asset {str(self.id)[:8]}"

    @property
    def is_processed(self) -> bool:
        return bool(self.processing_status == self.STATUS_CHOICES.COMPLETED)

    @property
    def is_processing(self) -> bool:
        return bool(self.processing_status == self.STATUS_CHOICES.PROCESSING)

    def mark_as_processing(self) -> None:
        self.processing_status = self.STATUS_CHOICES.PROCESSING
        self.processing_started_at = now()
        self.save(update_fields=["processing_status", "processing_started_at"])

    def mark_as_completed(self) -> None:
        self.processing_status = self.STATUS_CHOICES.COMPLETED
        self.save()

    def mark_as_failed(self, error: str) -> None:
        self.processing_status = self.STATUS_CHOICES.FAILED
        self.processing_error = error
        self.save()

    def update_total_chunks(self, total_chunks: int) -> None:
        self.total_chunks = total_chunks
        self.save(update_fields=["total_chunks"])

    def update_total_pages(self, total_pages: int) -> None:
        if not self.total_pages and total_pages > 0:
            self.total_pages = total_pages
            self.save(update_fields=["total_pages"])

    def update_notes_upload_path(self, storage_key: str) -> None:
        if self.notes_upload_path != storage_key:
            self.notes_upload_path = storage_key
            self.save(update_fields=["notes_upload_path"])
