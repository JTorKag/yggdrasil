"""
Utility functions for the Ratatorskr Discord bot.
"""


def serverStatusJsonToDiscordFormatted(status_json):
    """Converts JSONifed discord information into formatted discord response"""
    message_parts = []
    
    game_info = f"**Game Name:** {status_json.get('game_name')}\n"
    game_info += f"**Status:** {status_json.get('status')}\n"
    game_info += f"**Turn:** {status_json.get('turn')}\n"
    message_parts.append(game_info)
    
    players_info = "**Players:**\n"
    for player in status_json.get('players', []):
        players_info += (f"Player {player['player_id']}: {player['nation']} ({player['nation_desc']}) - "
                        f"{player['status']}\n")
        
        if len(players_info) > 1024:
            message_parts.append(players_info)
            players_info = ""

    if players_info:
        message_parts.append(players_info)

    formatted_message = "\n".join(message_parts)

    return formatted_message[:1024]


def descriptive_time_breakdown(seconds: int) -> str:
    """
    Format a duration in seconds into a descriptive breakdown.

    Args:
        seconds (int): The total duration in seconds.

    Returns:
        str: A descriptive breakdown of the duration.
    """
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return ", ".join(parts) if parts else "0 seconds"