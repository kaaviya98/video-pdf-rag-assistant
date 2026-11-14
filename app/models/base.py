import uuid
from typing import Any
from typing import ClassVar

from django.db import models
from django_multitenant.mixins import TenantManagerMixin
from django_multitenant.mixins import TenantModelMixin
from django_multitenant.utils import get_current_tenant
from django_multitenant.utils import get_tenant_filters
from model_utils.models import TimeStampedModel
from safedelete.managers import SafeDeleteManager
from safedelete.models import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel
from simple_history.models import HistoricalRecords


class Manager(SafeDeleteManager):
    pass


class BaseModel(TimeStampedModel, SafeDeleteModel):
    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        abstract = True


class Model(BaseModel):
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        null=False,
    )

    objects = Manager()

    class Meta:
        abstract = True


class BaseModelWithHistory(BaseModel):
    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True


class OrganizationManager(Manager, TenantManagerMixin):
    def get_queryset(self) -> models.QuerySet:
        queryset = Manager.get_queryset(self)
        current_tenant = get_current_tenant()
        if current_tenant:
            kwargs = get_tenant_filters(self.model)
            return queryset.filter(**kwargs)  # type: ignore[no-any-return]
        return queryset  # type: ignore[no-any-return]


class OrganizationBaseModel(TenantModelMixin, models.Model):
    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="%(class)s",
        related_query_name="%(class)ss",
    )

    tenant_id = "organization_id"
    objects = OrganizationManager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.is_update():
            update_fields = kwargs.pop("update_fields", None)
            if update_fields:
                update_fields = self.remove_organization_from_update_fields(
                    update_fields,
                )
            else:
                update_fields = self.get_all_fields_without_organization()
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def is_update(self) -> bool:
        return not self._state.adding

    def remove_organization_from_update_fields(
        self,
        update_fields: list[str],
    ) -> list[str]:
        return [field for field in update_fields if field != "organization"]

    def get_all_fields_without_organization(self) -> list[str]:
        return [
            field.name
            for field in self._meta.concrete_fields
            if field.name != "organization"
            and not field.primary_key
            and not hasattr(field, "through")
        ]


class OrganizationScopedModel(OrganizationBaseModel, BaseModel):
    objects = OrganizationManager()  # type: ignore[misc]

    class Meta(OrganizationBaseModel.Meta):
        abstract = True


class OrganizationModel(OrganizationBaseModel, Model):
    objects = OrganizationManager()  # type: ignore[misc]

    class Meta(OrganizationBaseModel.Meta):
        abstract = True
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["organization", "uuid"],
                name="unique_%(class)s_organization_uuid",
            ),
        ]
