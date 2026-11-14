from app.models.organization import Organization
from app.models.organization import OrganizationLLMSettings


def get_default_organization_llm_settings(
    organization: Organization,
) -> OrganizationLLMSettings | None:
    return organization.llm_settings.order_by("-is_default", "id").first()
