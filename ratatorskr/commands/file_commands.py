"""
File management commands - upload maps/mods, select maps/mods, etc.
"""

import asyncio
import discord
from typing import List, Dict, Optional
from bifrost import bifrost
from ..decorators import require_bot_channel, require_primary_bot_channel, require_game_channel, require_game_host_or_admin, require_game_owner_or_admin


def register_file_commands(bot):
    """Register all file management commands to the bot's command tree."""
    
    async def create_dropdown(
            interaction: discord.Interaction,
            options: List[Dict[str, str]],
            prompt_type: str = "option",
            multi_select: bool = True,
            preselected_values: List[str] = None) -> List[str]:
            """Creates a dropdown menu and returns the names and locations of selected options."""
            def resolve_emoji(emoji_code: str) -> Optional[discord.PartialEmoji]:
                """Resolves a custom emoji from its code."""
                if emoji_code and emoji_code.startswith(":") and emoji_code.endswith(":"):
                    emoji_name = emoji_code.strip(":")
                    for emoji in interaction.guild.emojis:
                        if emoji.name.lower() == emoji_name.lower():
                            return emoji
                    return None
                return emoji_code

            if not options:
                await interaction.response.send_message("No options available.", ephemeral=True)
                return [], []

            class Dropdown(discord.ui.Select):
                def __init__(self, prompt_type: str):
                    super().__init__(
                        placeholder=f"Choose {'one or more' if multi_select else 'one'} {prompt_type}{'s' if multi_select else ''}...",
                        min_values=0 if multi_select else 1,
                        max_values=len(options) if multi_select else 1,
                        options=[
                            discord.SelectOption(
                                label=option["name"],
                                value=option["location"],
                                description=option.get("yggdescr", None),
                                emoji=resolve_emoji(option.get("yggemoji")),
                                default=(
                                    option["location"].split('/', 1)[-1] in (preselected_values or [])
                                    if prompt_type == "map"
                                    else option["location"] in (preselected_values or [])
                                )
                            )
                            for option in options
                        ],
                    )

                async def callback(self, interaction: discord.Interaction):
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    self.view.selected_names = [o.label for o in self.options if o.value in self.values]
                    self.view.selected_locations = [
                        v.split('/', 1)[-1] if prompt_type == "map" else v for v in self.values
                    ]
                    self.view.stop()

            class DropdownView(discord.ui.View):
                def __init__(self, prompt_type: str):
                    super().__init__()
                    self.add_item(Dropdown(prompt_type))
                    self.selected_names = []
                    self.selected_locations = []
                    self.is_stopped = asyncio.Event()

                def stop(self):
                    super().stop()
                    self.is_stopped.set()

                async def wait(self, timeout=None):
                    try:
                        await asyncio.wait_for(self.is_stopped.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        self.stop()
                        raise

            view = DropdownView(prompt_type)
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            try:
                await interaction.followup.send(
                    f"Select {prompt_type}{'s' if multi_select else ''} from the dropdown:", 
                    view=view, 
                    ephemeral=True
                )
                await view.wait(timeout=180)
            except asyncio.TimeoutError:
                await interaction.followup.send("You did not make a selection in time.", ephemeral=True)
                return [], []

            return view.selected_names, view.selected_locations
    
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
        name="select-map",
        description="Select map for game.",
        guild=discord.Object(id=bot.guild_id),
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def select_map_command(interaction: discord.Interaction):
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel.id)
        if game_id is None:
            await interaction.response.send_message("This channel is not associated with any active game.", ephemeral=True)
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if game_info and game_info.get("game_started"):
            await interaction.response.send_message("The game has already started. You cannot change the map.", ephemeral=True)
            return

        current_map = await bot.db_instance.get_map(game_id)

        maps = bifrost.get_maps(config=bot.config)

        default_maps = [
            {"name": "Vanilla Small 10", "location": "vanilla_10", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
            {"name": "Vanilla Medium 15", "location": "vanilla_15", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
            {"name": "Vanilla Large 20", "location": "vanilla_20", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
            {"name": "Vanilla Enormous 25", "location": "vanilla_25", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
        ]
        maps = default_maps + maps

        selected_map, map_location = await create_dropdown(
            interaction, maps, "map", multi_select=False, preselected_values=[current_map] if current_map else []
        )

        if selected_map:
            await bot.db_instance.update_map(game_id, map_location[0])
            await interaction.followup.send(f"You selected: {', '.join(selected_map)}", ephemeral=True)
        else:
            await interaction.followup.send("No selection was made.", ephemeral=True)

    @bot.tree.command(
        name="select-mods",
        description="Select mods for game.",
        guild=discord.Object(id=bot.guild_id),
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def select_mods_command(interaction: discord.Interaction):
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel.id)
        if game_id is None:
            await interaction.response.send_message("This channel is not associated with any active game.", ephemeral=True)
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if game_info:
            if game_info.get("game_started"):
                await interaction.response.send_message("The game has already started. You cannot change the mods.", ephemeral=True)
                return
            if game_info.get("game_running"):
                await interaction.response.send_message("The game is currently running. You cannot change the mods.", ephemeral=True)
                return

        current_mods = await bot.db_instance.get_mods(game_id)

        mods = bifrost.get_mods(config=bot.config)

        selected_mods, mods_locations = await create_dropdown(
            interaction, mods, "mod", multi_select=True, preselected_values=current_mods
        )

        if selected_mods:
            await bot.db_instance.update_mods(game_id, mods_locations)
            await interaction.followup.send(f"You selected: {', '.join(selected_mods)}", ephemeral=True)
        else:
            await bot.db_instance.update_mods(game_id, [])
            await interaction.followup.send("No mods selected. All mods have been removed.", ephemeral=True)

    return [
        upload_map_command,
        upload_mod_command,
        select_map_command,
        select_mods_command
    ]