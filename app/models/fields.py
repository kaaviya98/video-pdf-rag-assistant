from django.conf import settings
from django.db import models


class CreatedByField(models.ForeignKey):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("to", settings.AUTH_USER_MODEL)
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("on_delete", models.SET_NULL)
        super().__init__(*args, **kwargs)
