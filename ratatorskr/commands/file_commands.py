"""
File management commands - upload maps/mods, select maps/mods, etc.
"""

import discord
from bifrost import bifrost
from ..decorators import require_primary_bot_channel, require_game_host_or_admin


def register_file_commands(bot):
    """Register all file management commands to the bot's command tree."""
    
    @bot.tree.command(
        name="upload-map",
        description="Uploads a map file to the server.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    @require_game_host_or_admin(bot.config)
    async def upload_map_command(interaction: discord.Interaction, map_file: discord.Attachment):
        try:
            file_data = await map_file.read()
            result = await bifrost.handle_map_upload(file_data, map_file.filename, bot.config)
            
            if result["success"]:
                await interaction.response.send_message(
                    f"Map {map_file.filename} successfully uploaded and extracted."
                )
            else:
                await interaction.response.send_message(
                    f"Failed to upload and extract map: {result['error']}", ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)

    @bot.tree.command(
        name="upload-mod",
        description="Uploads a mod file to the server.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    @require_game_host_or_admin(bot.config)
    async def upload_mod_command(interaction: discord.Interaction, mod_file: discord.Attachment):
        try:
            file_data = await mod_file.read()
            result = await bifrost.handle_mod_upload(file_data, mod_file.filename, bot.config)
            
            if result["success"]:
                await interaction.response.send_message(
                    f"Mod {mod_file.filename} successfully uploaded and extracted."
                )
            else:
                await interaction.response.send_message(
                    f"Failed to upload and extract mod: {result['error']}", ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)

    return [
        upload_map_command,
        upload_mod_command
    ]