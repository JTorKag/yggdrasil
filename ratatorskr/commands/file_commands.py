"""
File management commands - upload maps/mods, select maps/mods, etc.
"""

import discord
from bifrost import bifrost
from ..decorators import require_primary_bot_channel, require_game_host_or_admin
from ..utils import create_dropdown


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

    @bot.tree.command(
        name="view-mods",
        description="View available mods (browse only, no selection applied).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    async def view_mods_command(interaction: discord.Interaction):
        try:
            mods = bifrost.get_mods(bot.config)
            
            if not mods:
                await interaction.response.send_message("No mods found in the mods folder.", ephemeral=True)
                return

            # Use the paginated dropdown for viewing only
            _, _, _ = await create_dropdown(
                interaction, mods, "mod", multi_select=True, preselected_values=[], timeout=300, view_only=True
            )

        except Exception as e:
            await interaction.response.send_message(f"An error occurred while fetching mods: {e}", ephemeral=True)

    @bot.tree.command(
        name="view-maps",
        description="View available maps (browse only, no selection applied).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    async def view_maps_command(interaction: discord.Interaction):
        try:
            maps = bifrost.get_maps(bot.config)
            
            if not maps:
                await interaction.response.send_message("No maps found in the maps folder.", ephemeral=True)
                return

            # Use the paginated dropdown for viewing only
            _, _, _ = await create_dropdown(
                interaction, maps, "map", multi_select=False, preselected_values=[], timeout=300, view_only=True
            )

        except Exception as e:
            await interaction.response.send_message(f"An error occurred while fetching maps: {e}", ephemeral=True)

    return [
        upload_map_command,
        upload_mod_command,
        view_mods_command,
        view_maps_command
    ]