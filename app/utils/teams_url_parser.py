from urllib.parse import urlparse, parse_qs, unquote


def parse_teams_channel_url(url: str) -> dict:
    result = {
        "channel_name": None,
        "channel_id": None,
        "team_id": None,
        "tenant_id": None
    }

    try:
        parsed = urlparse(url)

        # Example path:
        # /l/channel/19%3Aabc123%40thread.tacv2/Risk%20Alerts

        path_parts = parsed.path.strip("/").split("/")

        if "channel" in path_parts:
            channel_index = path_parts.index("channel")

            if len(path_parts) > channel_index + 1:
                result["channel_id"] = unquote(
                    path_parts[channel_index + 1]
                )

            if len(path_parts) > channel_index + 2:
                result["channel_name"] = unquote(
                    path_parts[channel_index + 2]
                )

        # Query params
        query_params = parse_qs(parsed.query)

        # Microsoft Teams Copy Link usually uses groupId
        # groupId = Team ID
        if "groupId" in query_params:
            result["team_id"] = query_params["groupId"][0]

        if "tenantId" in query_params:
            result["tenant_id"] = query_params["tenantId"][0]

        return result

    except Exception:
        # Parsing failure should not block destination creation
        return result