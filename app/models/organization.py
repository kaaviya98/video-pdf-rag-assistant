from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django_multitenant.mixins import TenantModelMixin

from app.models.base import BaseModel
from app.models.base import OrganizationManager
from app.models.base import OrganizationModel
from app.models.fields import CreatedByField
from app.utils.random import populate_uuid

ORGANIZATION_UUID_LENGTH = 12


class OrganizationStatus(models.IntegerChoices):
    ACTIVE = 0
    SUSPENDED = 1
    BLOCKED = 2


class LLMProvider(models.IntegerChoices):
    OPENAI = 0, _("OpenAI")
    GOOGLE_GEMINI = 1, _("Google Gemini")


class StorageVendor(models.IntegerChoices):
    S3 = 0, _("Amazon S3")
    WASABI = 1, _("Wasabi")
    MINIO = 2, _("MinIO")


class Organization(BaseModel, TenantModelMixin):
    uuid = models.CharField(
        max_length=ORGANIZATION_UUID_LENGTH,
        editable=False,
        null=False,
        unique=True,
    )

    name = models.CharField(max_length=254)

    status = models.PositiveSmallIntegerField(
        _("Status"),
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.ACTIVE,
        db_index=True,
    )

    created_by = CreatedByField(
        related_name="created_organizations",
        help_text=_("User that created this organization."),
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="organizations",
        blank=True,
        help_text=_("Users belonging to this organization."),
    )
    limited_access_enabled = models.BooleanField(
        _("Enable limited access"),
        default=True,
    )
    storage_vendor = models.PositiveSmallIntegerField(
        choices=StorageVendor.choices,
        null=True,
        blank=True,
    )
    storage_endpoint = models.CharField(max_length=2048, null=True, blank=True)
    bucket_name = models.CharField(max_length=256, null=True, blank=True)
    storage_region = models.CharField(max_length=256, null=True, blank=True)
    storage_access_key_id = models.CharField(max_length=256, null=True, blank=True)
    storage_secret_access_key = models.CharField(
        max_length=256,
        null=True,
        blank=True,
    )
    storage_path_prefix = models.CharField(max_length=1024, null=True, blank=True)
    cdn_id = models.CharField(max_length=2048, null=True, blank=True)
    cdn_url = models.URLField(max_length=2048, null=True, blank=True)
    cdn_access_key_id = models.CharField(max_length=256, null=True, blank=True)
    cdn_secret_access_key = models.CharField(max_length=256, null=True, blank=True)
    cdn_public_key_id = models.CharField(max_length=256, null=True, blank=True)
    cdn_private_key = models.TextField(null=True, blank=True)

    tenant_id = "id"
    objects = OrganizationManager()

    def __str__(self) -> str:
        return self.name

    def is_member(self, user: AbstractUser) -> bool:
        return self.members.filter(pk=user.pk).exists()


class OrganizationLLMSettings(OrganizationModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="llm_settings",
    )
    provider = models.PositiveSmallIntegerField(
        _("Provider"),
        choices=LLMProvider.choices,
        default=LLMProvider.OPENAI,
        db_index=True,
    )
    model = models.CharField(
        _("Model"),
        max_length=128,
        help_text=_("Provider-specific model id (e.g. gpt-4o-mini, gemini-2.0-flash)."),
    )
    is_default = models.BooleanField(
        _("Default"),
        default=False,
        db_index=True,
        help_text=_(
            "When True, prefer this row for the organization's LLM calls.",
        ),
    )
    api_key = models.TextField(
        _("API key"),
        help_text=_(
            "Raw key for now; use encryption or a secrets backend in production.",
        ),
    )

    class Meta(OrganizationModel.Meta):
        abstract = False
        verbose_name = _("organization LLM settings")
        verbose_name_plural = _("organization LLM settings")

    def __str__(self) -> str:
        return f"{self.organization.name} ({self.get_provider_display()})"


@receiver(pre_save, sender=Organization)
def populate_organization_uuid(
    sender: type,
    instance: Organization,
    **kwargs: Any,
) -> None:
    populate_uuid(instance, length=ORGANIZATION_UUID_LENGTH)
