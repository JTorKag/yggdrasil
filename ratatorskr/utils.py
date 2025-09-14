"""
Utility functions for the Ratatorskr Discord bot.
"""

import asyncio
import discord
from typing import List, Dict, Optional


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


# UI Components

async def create_dropdown(
        interaction: discord.Interaction,
        options: List[Dict[str, str]],
        prompt_type: str = "option",
        multi_select: bool = True,
        preselected_values: List[str] = None,
        timeout: int = 180) -> tuple[List[str], List[str], bool]:
        """Creates a dropdown menu with confirm button and returns the names, locations, and confirmation status of selected options."""
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
            return [], [], False

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

        class DropdownView(discord.ui.View):
            def __init__(self, prompt_type: str):
                super().__init__()
                self.dropdown = Dropdown(prompt_type)
                self.add_item(self.dropdown)
                self.selected_names = []
                self.selected_locations = []
                self.is_stopped = asyncio.Event()
                self.confirmed = False
                
                # Add confirm button
                confirm_button = discord.ui.Button(label="Confirm Selection", style=discord.ButtonStyle.green)
                confirm_button.callback = self.confirm_selection
                self.add_item(confirm_button)

            async def confirm_selection(self, interaction: discord.Interaction):
                # Update selections first
                self.selected_names = [o.label for o in self.dropdown.options if o.value in self.dropdown.values]
                self.selected_locations = [
                    v.split('/', 1)[-1] if prompt_type == "map" else v for v in self.dropdown.values
                ]
                
                self.confirmed = True
                await interaction.response.defer()
                self.stop()

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
                f"Select {prompt_type}{'s' if multi_select else ''} from the dropdown and click 'Confirm Selection' to apply changes:", 
                view=view, 
                ephemeral=True
            )
            await view.wait(timeout=timeout)
        except asyncio.TimeoutError:
            return [], [], False

        if view.confirmed:
            return view.selected_names, view.selected_locations, True
        else:
            return [], [], False


async def create_nations_dropdown(
        interaction: discord.Interaction,
        nations: List[str],
        preselected_nations: List[str] = None,
        debug: bool = False) -> List[str]:
    """Creates a paginated dropdown menu for nation selection and returns the selected nations."""
    
    if debug:
        print(f"[DEBUG] create_nations_dropdown called with {len(nations)} nations, {len(preselected_nations or [])} preselected")
    
    if not nations:
        await interaction.response.send_message("No nations available.", ephemeral=True)
        return []
    
    ITEMS_PER_PAGE = 25
    total_pages = (len(nations) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    preselected_set = set(preselected_nations or [])
    
    if debug:
        print(f"[DEBUG] create_nations_dropdown: {total_pages} pages, {len(preselected_set)} preselected nations")
    
    class NationDropdown(discord.ui.Select):
        def __init__(self, page_nations: List[str], page_num: int, total_pages: int):
            max_selectable = min(len(page_nations), ITEMS_PER_PAGE)
            super().__init__(
                placeholder=f"Choose nations to claim/unclaim... (Page {page_num + 1}/{total_pages})",
                min_values=0,
                max_values=max_selectable,
                options=[
                    discord.SelectOption(
                        label=nation,
                        value=nation,
                        default=nation in preselected_set
                    )
                    for nation in page_nations
                ],
            )

        async def callback(self, interaction: discord.Interaction):
            if not interaction.response.is_done():
                await interaction.response.defer()
            self.view.update_selection(self.values)

    class NationView(discord.ui.View):
        def __init__(self, nations: List[str], total_pages: int):
            super().__init__()
            self.nations = nations
            self.total_pages = total_pages
            self.current_page = 0
            self.selected_nations = set(preselected_nations or [])
            self.is_stopped = asyncio.Event()
            self.confirmed = False
            
            self.update_page()

        def update_selection(self, new_selections: List[str]):
            # Remove all nations from the current page from selection
            start_idx = self.current_page * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.nations))
            current_page_nations = set(self.nations[start_idx:end_idx])
            
            self.selected_nations = self.selected_nations - current_page_nations
            
            # Add newly selected nations
            self.selected_nations.update(new_selections)

        def update_page(self):
            self.clear_items()
            
            start_idx = self.current_page * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.nations))
            page_nations = self.nations[start_idx:end_idx]
            
            # Add dropdown
            dropdown = NationDropdown(page_nations, self.current_page, self.total_pages)
            self.add_item(dropdown)
            
            # Add navigation buttons
            if self.total_pages > 1:
                # Previous page button
                prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=self.current_page == 0)
                prev_button.callback = self.previous_page
                self.add_item(prev_button)
                
                # Next page button
                next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, disabled=self.current_page >= self.total_pages - 1)
                next_button.callback = self.next_page
                self.add_item(next_button)
            
            # Confirm button
            confirm_button = discord.ui.Button(label="Confirm Selection", style=discord.ButtonStyle.green)
            confirm_button.callback = self.confirm_selection
            self.add_item(confirm_button)

        async def previous_page(self, interaction: discord.Interaction):
            if self.current_page > 0:
                self.current_page -= 1
                self.update_page()
                await interaction.response.edit_message(view=self)

        async def next_page(self, interaction: discord.Interaction):
            if self.current_page < self.total_pages - 1:
                self.current_page += 1
                self.update_page()
                await interaction.response.edit_message(view=self)

        async def confirm_selection(self, interaction: discord.Interaction):
            self.confirmed = True
            await interaction.response.defer()
            self.stop()

        def stop(self):
            super().stop()
            self.is_stopped.set()

        async def wait(self, timeout=None):
            try:
                await asyncio.wait_for(self.is_stopped.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self.stop()
                raise

    view = NationView(nations, total_pages)
    
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    try:
        await interaction.followup.send(
            f"Select nations to claim/unclaim. Use the dropdown and navigation buttons to make your selection:", 
            view=view, 
            ephemeral=True
        )
        await view.wait(timeout=300)  # 5 minutes timeout for nation selection
    except asyncio.TimeoutError:
        await interaction.followup.send("You did not make a selection in time.", ephemeral=True)
        return []

    if view.confirmed:
        return list(view.selected_nations)
    else:
        return []