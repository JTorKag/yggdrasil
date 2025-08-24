"""
Admin-only commands - delete lobby, reset game state, etc.
"""

import discord
from ..decorators import require_bot_channel, require_game_channel, require_game_admin, require_game_owner_or_admin


def register_admin_commands(bot):
    """Register all admin-only commands to the bot's command tree."""
    
    @bot.tree.command(
        name="delete-lobby",
        description="Deletes a lobby.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def delete_lobby_command(interaction: discord.Interaction, game_id: int):
        await interaction.response.send_message("Delete lobby command - implementation needed", ephemeral=True)

    @bot.tree.command(
        name="reset-game-started",
        description="Resets the game started flag (admin only).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_admin(bot.config)
    async def reset_game_started_command(interaction: discord.Interaction):
        await interaction.response.send_message("Reset game started command - implementation needed", ephemeral=True)

    return [
        delete_lobby_command,
        reset_game_started_command
    ]