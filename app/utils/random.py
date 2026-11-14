from typing import Any

import shortuuid

_MAX_UUID_ATTEMPTS = 100


def populate_uuid(
    instance: Any,
    length: int,
    alphabet: str = "abcdefghjkmnpqrstuxyz23456789",
) -> None:
    if instance.uuid:
        return
    model = instance._meta.model
    short_uuid = shortuuid.ShortUUID(alphabet=alphabet)
    for _ in range(_MAX_UUID_ATTEMPTS):
        candidate = short_uuid.random(length=length)
        if not model.objects.filter(uuid=candidate).exists():  # noqa: SLF001
            instance.uuid = candidate
            return
    message = f"Could not allocate unique uuid after {_MAX_UUID_ATTEMPTS} attempts"
    raise RuntimeError(message)
