import enum
import logging

from sentry.incidents.models import IncidentStatus
from sentry.models import Integration
from sentry.shared_integrations.exceptions import ApiError

from .client import MsTeamsClient, MsTeamsPreInstallClient, get_token_data

MSTEAMS_MAX_ITERS = 100

logger = logging.getLogger("sentry.integrations.msteams")


# MS Teams will convert integers into strings in value inputs sent in adaptive
# cards, may as well just do that here first.
class ACTION_TYPE(str, enum.Enum):
    RESOLVE = "1"
    IGNORE = "2"
    ASSIGN = "3"
    UNRESOLVE = "4"
    UNASSIGN = "5"


def channel_filter(channel, name):
    # the general channel has no name in the list
    # retrieved from the REST API call
    if channel.get("name"):
        return name.lower() == channel.get("name").lower()
    else:
        return name.lower() == "general"


def get_user_conversation_id(integration: Integration, user_id: str) -> str:
    """
    Get the user_conversation_id even if `integration.metadata.tenant_id` is not set.
    """
    client = MsTeamsClient(integration)

    tenant_id = integration.metadata.get("tenant_id")

    if not tenant_id:
        # This is definitely an integration of `integration.metadata.installation_type` == `team`,
        # so use the `integration.external_id` (team_id) to get the tenant_id.
        members = client.get_member_list(integration.external_id).get("members")
        tenant_id = members[0].get("tenantId")

    conversation_id = client.get_user_conversation_id(user_id, tenant_id)

    return conversation_id


def get_channel_id(organization, integration_id, name):
    try:
        integration = Integration.objects.get(
            provider="msteams",
            organizationintegration__organization_id=organization.id,
            id=integration_id,
        )
    except Integration.DoesNotExist:
        return None

    team_id = integration.external_id
    client = MsTeamsClient(integration)

    # handle searching for channels first
    channel_list = client.get_channel_list(team_id)
    filtered_channels = list(filter(lambda x: channel_filter(x, name), channel_list))
    if len(filtered_channels) > 0:
        return filtered_channels[0].get("id")

    # handle searching for users
    members = client.get_member_list(team_id, None)
    for i in range(MSTEAMS_MAX_ITERS):
        member_list = members.get("members")
        continuation_token = members.get("continuationToken")

        filtered_members = list(
            filter(lambda x: x.get("name").lower() == name.lower(), member_list)
        )
        if len(filtered_members) > 0:
            # TODO: handle duplicate username case
            user_id = filtered_members[0].get("id")
            tenant_id = filtered_members[0].get("tenantId")
            return client.get_user_conversation_id(user_id, tenant_id)

        if not continuation_token:
            return None

        members = client.get_member_list(team_id, continuation_token)

    return None


def send_incident_alert_notification(action, incident, metric_value, new_status: IncidentStatus):
    from .card_builder import build_incident_attachment

    channel = action.target_identifier
    integration = action.integration
    attachment = build_incident_attachment(incident, new_status, metric_value)
    client = MsTeamsClient(integration)
    try:
        client.send_card(channel, attachment)
    except ApiError:
        logger.info("rule.fail.msteams_post", exc_info=True)


def get_preinstall_client(service_url):
    # may want try/catch here since this makes an external API call
    access_token = get_token_data()["access_token"]
    return MsTeamsPreInstallClient(access_token, service_url)
