#discord bot code


import discord
from discord import app_commands, Embed
from functools import wraps
from typing import Callable, Awaitable, List, Dict, Optional, Union
import asyncio
from bifrost import bifrost
from pathlib import Path

def require_active_channel(bot):
    """Decorator to restrict commands to active game channels or bot channels."""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Combine active game channels with bot_channels
        active_game_channels = await bot.db_instance.get_active_game_channels()
        allowed_channels = set(active_game_channels + bot.bot_channels)

        # If allowed_channels is empty, allow any channel
        if not allowed_channels or interaction.channel_id in allowed_channels:
            return True

        # Deny access if the channel is not allowed
        await interaction.response.send_message("This command is not allowed in this channel.", ephemeral=True)
        return False

    def wrapper(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)  # Preserves original function metadata, including type annotations
        async def wrapped(interaction: discord.Interaction, *args, **kwargs) -> None:
            if await predicate(interaction):
                return await command_func(interaction, *args, **kwargs)
        return wrapped

    return wrapper


def serverStatusJsonToDiscordFormatted(status_json):
    """Converts JSONifed discord information into formatted discord response"""
    # Start building the message
    message_parts = []
    
    # Add game info
    game_info = f"**Game Name:** {status_json.get('game_name')}\n"
    game_info += f"**Status:** {status_json.get('status')}\n"
    game_info += f"**Turn:** {status_json.get('turn')}\n"
    #This is dominions time, not ygg time
    #game_info += f"**Time Left:** {status_json.get('time_left')}\n"
    message_parts.append(game_info)
    
    # Add players info
    players_info = "**Players:**\n"
    for player in status_json.get('players', []):
        players_info += (f"Player {player['player_id']}: {player['nation']} ({player['nation_desc']}) - "
                         f"{player['status']}\n")
        
        # Check if message exceeds 1024 characters
        if len(players_info) > 1024:
            message_parts.append(players_info)
            players_info = ""  # Reset for next part if exceeds limit

    # Add any remaining players info
    if players_info:
        message_parts.append(players_info)

    # Join all parts into a single message
    formatted_message = "\n".join(message_parts)

    # Trim the message to 1024 characters if necessary
    return formatted_message[:1024]



class discordClient(discord.Client):
    def __init__(self, *, intents, db_instance, bot_ready_signal,config:dict, nidhogg):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_id = config["guild_id"]
        self.db_instance = db_instance
        self.bot_ready_signal = bot_ready_signal
        self.category_id = config["category_id"]
        self.bot_channels = list(map(int, config.get("bot_channels", [])))
        self.config = config
        self.nidhogg = nidhogg

    async def setup_hook(self):
        
        @self.tree.command(
            name="new-game",
            description="Creates a brand new game",
            guild=discord.Object(id=self.guild_id)
        )
        @require_active_channel(self)
        async def new_game_command(
            interaction: discord.Interaction, 
            game_name: str, 
            game_era: str, 
            research_random: str, 
            global_slots: int, 
            event_rarity: str, 
            master_pass: str, 
            disicples: str, 
            story_events: str, 
            no_going_ai: str, 
            lv1_thrones: int, 
            lv2_thrones: int, 
            lv3_thrones: int, 
            points_to_win: int
        ):
            try:
                async def validate_choice(interaction, input_value, valid_map, field_name):
                    if input_value not in valid_map:
                        valid_options = ", ".join(valid_map.keys())
                        await interaction.response.send_message(
                            f"Invalid choice for {field_name}. Please choose from: {valid_options}.",
                            ephemeral=True
                        )
                        return None
                    return valid_map[input_value]

                # Defer interaction to prevent timeout
                await interaction.response.defer(ephemeral=True)

                # Validate inputs
                era_map = {"Early": 1, "Middle": 2, "Late": 3}
                game_era_value = await validate_choice(interaction, game_era, era_map, "game_era")

                research_random_map = {"Even Spread": 1, "Random": 0}
                research_random_value = await validate_choice(interaction, research_random, research_random_map, "research_random")

                event_rarity_map = {"Common": 1, "Rare": 2}
                event_rarity_value = await validate_choice(interaction, event_rarity, event_rarity_map, "event_rarity")

                disicples_map = {"False": 1, "True": 0}
                disicples_value = await validate_choice(interaction, disicples, disicples_map, "disicples")

                story_events_map = {"None": 0, "Some": 1, "Full": 2}
                story_events_value = await validate_choice(interaction, story_events, story_events_map, "story_events")

                no_going_ai_map = {"True": 0, "False": 1}
                no_going_ai_value = await validate_choice(interaction, no_going_ai, no_going_ai_map, "no_going_ai")

                thrones_value = ",".join(map(str, [lv1_thrones, lv2_thrones, lv3_thrones]))

                if not isinstance(points_to_win, int):
                    await interaction.followup.send("points_to_win must be an integer.")
                    return
                elif points_to_win < 1:
                    await interaction.followup.send("points_to_win must be at least 1.")
                    return
                elif points_to_win > lv1_thrones + lv2_thrones * 2 + lv3_thrones * 3:
                    await interaction.followup.send("points_to_win must be no more than total points available.")
                    return

                # Fetch guild and category
                guild = interaction.client.get_guild(self.guild_id)
                if not guild:
                    guild = await interaction.client.fetch_guild(self.guild_id)

                category = await guild.fetch_channel(self.category_id)
                if not category or not isinstance(category, discord.CategoryChannel):
                    await interaction.followup.send("Game lobby category not found or invalid.")
                    return

                # Create channel
                new_channel = await guild.create_text_channel(name=game_name, category=category)
                new_channel_id = new_channel.id

                # Database operations
                try:
                    new_game_id = await self.db_instance.create_game(
                        game_name=game_name,
                        game_era=game_era_value,
                        research_random=research_random_value,
                        global_slots=global_slots,
                        eventrarity=event_rarity_value,
                        masterpass=master_pass,
                        teamgame=disicples_value,
                        story_events=story_events_value,
                        no_going_ai=no_going_ai_value,
                        thrones=thrones_value,
                        requiredap=points_to_win,
                        game_map=None,
                        game_running=False,
                        game_mods="[]",
                        channel_id=new_channel_id,
                        game_active=True,
                        process_pid=None,
                        game_owner=interaction.user.name
                    )

                    await self.db_instance.create_timer(
                        game_id=new_game_id,
                        timer_default=1440,
                        timer_length=1440,
                        timer_running=False,
                        remaining_time=None
                    )

                    # Success response only sent here
                    await interaction.followup.send(f"Game '{game_name}' created successfully with channel '{new_channel.name}'!")

                except Exception as e:
                    # Rollback if database insertion fails
                    await new_channel.delete()
                    await interaction.followup.send(
                        f"An error occurred while creating the game in the database: {e}",
                        ephemeral=True
                    )

            except discord.Forbidden as e:
                await interaction.response.send_message(f"Permission error: {e}", ephemeral=True)
            except discord.HTTPException as e:
                await interaction.response.send_message(f"Failed to create channel: {e}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Unexpected error: {e}", ephemeral=True)





        @new_game_command.autocomplete("game_era")
        async def game_era_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = ["Early", "Middle", "Late"]
            matches = options if not current else [option for option in options if current.lower() in option.lower()]

            # Convert to app_commands.Choice objects
            suggestions = [app_commands.Choice(name=option, value=option) for option in matches]

            try:
                # Send the autocomplete suggestions
                await interaction.response.autocomplete(suggestions[:25])
            except Exception as e:
                print(f"Error sending autocomplete response: {e}")

        @new_game_command.autocomplete("research_random")
        async def research_random_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = ["Even Spread", "Random"]
            matches = options if not current else [option for option in options if current.lower() in option.lower()]

            # Convert to app_commands.Choice objects
            suggestions = [app_commands.Choice(name=option, value=option) for option in matches]

            try:
                # Send the autocomplete suggestions
                await interaction.response.autocomplete(suggestions[:25])
            except Exception as e:
                print(f"Error sending autocomplete response: {e}")

        @new_game_command.autocomplete("global_slots")
        async def global_slots_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = [5, 3, 4, 6, 7, 8, 9]
            if current.isdigit():
                current_int = int(current)
                matches = [option for option in options if option == current_int]
            else:
                matches = options

            # Convert to app_commands.Choice objects
            suggestions = [app_commands.Choice(name=option, value=option) for option in matches]

            try:
                # Send the autocomplete suggestions
                await interaction.response.autocomplete(suggestions[:25])
            except Exception as e:
                print(f"Error sending autocomplete response: {e}")

        @new_game_command.autocomplete("event_rarity")
        async def event_rarity_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = ["Common", "Rare"]
            matches = options if not current else [option for option in options if current.lower() in option.lower()]

            # Convert to app_commands.Choice objects
            suggestions = [app_commands.Choice(name=option, value=option) for option in matches]

            try:
                # Send the autocomplete suggestions
                await interaction.response.autocomplete(suggestions[:25])
            except Exception as e:
                print(f"Error sending autocomplete response: {e}")



        @self.tree.command(
                name="launch",
                description="Launches game lobby.",
                guild=discord.Object(id=self.guild_id)
        )
        @require_active_channel(self)
        async def launch_game_lobby(interaction: discord.Interaction):
            # id = interaction.channel
            # await interaction.response.send_message(f"Test method for startting game in channel {id}")
            print("\nTrying to launch game")
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            print(f"Launching game {game_id}")
            if game_id is None:
                await interaction.response.send_message("No game lobby is associated with this channel.")
                return
            await self.nidhogg.launchGameLobby(game_id, self.db_instance)
            #await self.db_instance.update_process_pid(game_id, pid)
            await interaction.response.send_message(f"Game lobby launched.")


        @self.tree.command(
            name="check-status",
            description="Checks server status",
            guild=discord.Object(id=self.guild_id) 
        )
        @require_active_channel(self)
        async def wake_command(interaction: discord.Interaction):
            response = serverStatusJsonToDiscordFormatted(self.nidhogg.getServerStatus())
            embedResponse = discord.Embed(title="Server Status", type="rich")
            embedResponse.add_field(name="", value=response, inline=True)
            await interaction.response.send_message(embed=embedResponse)
            print(f"{interaction.user} requested server status.")

        @self.tree.command(
            name="echo",
            description="Echos back text",
            guild=discord.Object(id=self.guild_id)
        )
        @require_active_channel(self)
        async def echo_command(interaction: discord.Interaction, echo_text:str, your_name:str):
            await interaction.response.send_message(echo_text + your_name)

        @self.tree.command(
            name="upload-map",
            description="Upload your map.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_active_channel(self)
        async def map_upload_command(interaction: discord.Interaction, file: discord.Attachment):
            try:
                # Read the file data as a binary blob
                file_data = await file.read()

                # Pass the file data, filename, and config to bifrost
                result = bifrost.handle_map_upload(file_data, file.filename, self.config)

                # Handle the result
                if result["success"]:
                    await interaction.response.send_message(
                        f"Map {file.filename} successfully uploaded and extracted."
                    )
                    print(f"Map uploaded by {interaction.user} and extracted to {result['extracted_path']}")
                else:
                    await interaction.response.send_message(
                        f"Failed to upload and extract map: {result['error']}", ephemeral=True
                    )
            except Exception as e:
                await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)
                print(f"Error during map upload by {interaction.user}: {e}")

        @self.tree.command(
            name="upload-mod",
            description="Upload your mod.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_active_channel(self)
        async def mod_upload_command(interaction: discord.Interaction, file: discord.Attachment):
            try:
                # Read the file data as a binary blob
                file_data = await file.read()

                # Pass the file data, filename, and config to bifrost
                result = bifrost.handle_mod_upload(file_data, file.filename, self.config)

                # Handle the result
                if result["success"]:
                    await interaction.response.send_message(
                        f"Mod {file.filename} successfully uploaded and extracted."
                    )
                    print(f"Mod uploaded by {interaction.user} and extracted to {result['extracted_path']}")
                else:
                    await interaction.response.send_message(
                        f"Failed to upload and extract mod: {result['error']}", ephemeral=True
                    )
            except Exception as e:
                await interaction.response.send_message(f"An unexpected error occurred: {e}", ephemeral=True)
                print(f"Error during mod upload by {interaction.user}: {e}")



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
                        min_values=1 if multi_select else 1,
                        max_values=len(options) if multi_select else 1,
                        options=[
                            discord.SelectOption(
                                label=option["name"],
                                value=option["location"],
                                description=option.get("yggdescr", None),
                                emoji=resolve_emoji(option.get("yggemoji")),
                                # Preselected values only apply for the relevant trimmed condition
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
                    # Process selected values: trim only if it's for maps
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




        @self.tree.command(
            name="select_mods",
            description="Select mods for game.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_active_channel(self)
        async def select_mods_dropdown(interaction: discord.Interaction):

            # Get the current game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel.id)
            if game_id is None:
                await interaction.response.send_message("This channel is not associated with any active game.", ephemeral=True)
                return

            # Fetch the preselected mods
            current_mods = await self.db_instance.get_mods(game_id)

            # Fetch available mods
            mods = bifrost.get_mods(config=self.config)

            # Preselect the current mods
            selected_mods, mods_locations = await create_dropdown(
                interaction, mods, "mod", multi_select=True, preselected_values=current_mods
            )

            if selected_mods:
                await self.db_instance.update_mods(game_id, mods_locations)
                await interaction.followup.send(f"You selected: {', '.join(selected_mods)}", ephemeral=True)
            else:
                await interaction.followup.send("No selection was made.", ephemeral=True)


        @self.tree.command(
            name="select_map",
            description="Select map for game.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_active_channel(self)
        async def select_map_dropdown(interaction: discord.Interaction):

            # Get the current game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel.id)
            if game_id is None:
                await interaction.response.send_message("This channel is not associated with any active game.", ephemeral=True)
                return

            # Fetch the preselected map
            current_map = await self.db_instance.get_map(game_id)

            # Fetch available maps
            maps = bifrost.get_maps(config=self.config)

            # Add default options
            default_maps = [
                {"name": "Vanilla Small 10", "location": "vanilla_10", "yggemoji":":dom6:", "yggdescr":"Small Lakes & One Cave"},
                {"name": "Vanilla Medium 15", "location": "vanilla_15", "yggemoji":":dom6:", "yggdescr":"Small Lakes & One Cave"},
                {"name": "Vanilla Large 20", "location": "vanilla_20", "yggemoji":":dom6:", "yggdescr":"Small Lakes & One Cave"},
                {"name": "Vanilla Enormous 25", "location": "vanilla_25", "yggemoji":":dom6:", "yggdescr":"Small Lakes & One Cave"}
            ]
            maps = default_maps + maps  # Prepend default maps; use `maps + default_maps` to append instead

            # Preselect the current map
            selected_map, map_location = await create_dropdown(
                interaction, maps, "map", multi_select=False, preselected_values=[current_map] if current_map else []
            )

            if selected_map:
                await self.db_instance.update_map(game_id, map_location[0])
                await interaction.followup.send(f"You selected: {', '.join(selected_map)}", ephemeral=True)
            else:
                await interaction.followup.send("No selection was made.", ephemeral=True)




        @self.tree.command(
            name="dropdown_test",
            description="Test the generic dropdown menu.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_active_channel(self)
        async def dropdown_test_command(interaction: discord.Interaction):

            options = [{'name': 'smackdown_ea1', 'location': 'smackdown_ea1/smackdown_ea1.map','yggemoji': 'DreamAtlas:', 'yggdescr': '"for winners only'},
                       {'name': 'teamstarttest', 'location': 'teamstarttest/teamstarttest.map', 'yggemoji': '::', 'yggdescr': ''},
                       {'name': 'Softball', 'location': 'Softball/Softball.map', 'yggemoji': '::', 'yggdescr': ''}]

            selected_names, selected_locations = await create_dropdown(interaction, options, "mod")

            if selected_names:
                await interaction.followup.send(f"You selected: {', '.join(selected_names)}", ephemeral=True)
            else:
                await interaction.followup.send("No selection was made.", ephemeral=True)









    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        await self.db_instance.setup_db()

        print("Trying to sync discord bot commands")

        try:
            await self.tree.sync(guild=discord.Object(id=self.guild_id))
            print("Discord commands synced!")
        except Exception as e:
            print(f"Error syncing commands: {e}")

        if self.bot_ready_signal:
            self.bot_ready_signal.set()

    async def on_message(self, message):
        if message.author == self.user:
            return 
        print(f'Message from {message.author}: {message.content} in {message.channel}')
    

