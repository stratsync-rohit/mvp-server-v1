from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.dependencies import (
    get_slack_destination_service,
    get_teams_channel_service,
)

from app.services.slack_destination_service import (
    SlackDestinationService,
)

from app.services.teams_channel_service import (
    TeamsChannelService,
)


router = APIRouter(
    prefix="/api/clients",
    tags=["Destinations"],
)


# =========================================================
# GET UNIFIED CLIENT DESTINATIONS
# =========================================================

@router.get(
    "/{client_id}/destinations",
    status_code=status.HTTP_200_OK,
)
async def get_client_destinations(
    client_id: str,
    teams_service: TeamsChannelService = Depends(
        get_teams_channel_service
    ),
    slack_service: SlackDestinationService = Depends(
        get_slack_destination_service
    ),
):
    """
    Return all active Teams and Slack destinations
    configured for a client.

    Sensitive fields such as webhook URLs and channel
    links are intentionally not returned.
    """

    try:
        # -------------------------------------------------
        # Load Teams destinations
        # -------------------------------------------------

        teams_channels = await teams_service.get_channels_by_client(
            client_id
        )

        # -------------------------------------------------
        # Load Slack destinations
        # -------------------------------------------------

        slack_destinations = await slack_service.get_destinations_by_client(
            client_id
        )

        destinations = []

        # -------------------------------------------------
        # Normalize Teams destinations
        # -------------------------------------------------

        for channel in teams_channels:

            if not channel.get("is_active", True):
                continue

            destinations.append(
                {
                    "destination_id": str(
                        channel["_id"]
                    ),
                    "client_id": str(
                        channel["client_id"]
                    ),
                    "platform": "teams",
                    "member_name": channel.get(
                        "member_name"
                    ),
                    "team_name": channel.get(
                        "team_name"
                    ),
                    "channel_name": channel.get(
                        "channel_name"
                    ),
                    "is_active": True,
                }
            )

        # -------------------------------------------------
        # Normalize Slack destinations
        # -------------------------------------------------

        for destination in slack_destinations:

            if not destination.get("is_active", True):
                continue

            destinations.append(
                {
                    "destination_id": str(
                        destination["_id"]
                    ),
                    "client_id": str(
                        destination["client_id"]
                    ),
                    "platform": "slack",
                    "member_name": destination.get(
                        "member_name"
                    ),
                    "workspace_domain": destination.get(
                        "workspace_domain"
                    ),
                    "channel_name": destination.get(
                        "channel_name"
                    ),
                    "is_active": True,
                }
            )

        # -------------------------------------------------
        # Response
        # -------------------------------------------------

        return {
            "success": True,
            "data": destinations,
            "count": len(destinations),
        }

    except (ValueError, LookupError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch client destinations",
        ) from exc