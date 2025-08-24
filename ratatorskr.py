#discord bot code


import discord
from discord import app_commands, Embed, Color
from functools import wraps
from typing import Callable, Awaitable, List, Dict, Optional, Union
import asyncio
from bifrost import bifrost
from pathlib import Path
from datetime import datetime, timedelta, timezone
import os

def require_bot_channel(config):
    """Decorator to restrict commands to bot-specific channels or channels linked to active or inactive games."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client  # Access the bot instance from the interaction
            command_name = interaction.command.name  # Get the name of the command being executed

            # Get allowed bot-specific channels
            bot_channels = list(map(int, config.get("bot_channels", [])))
            allowed_channels = set(bot_channels)

            if command_name == "delete-lobby":
                # Add inactive game channels for the delete-lobby command
                inactive_game_channels = [
                    game["channel_id"]
                    for game in await bot.db_instance.get_inactive_games()
                ]
                allowed_channels.update(inactive_game_channels)
            else:
                # Add active game channels for all other commands
                active_game_channels = await bot.db_instance.get_active_game_channels()
                allowed_channels.update(active_game_channels)

            # Check if the current channel is allowed
            if not allowed_channels or interaction.channel_id in allowed_channels:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the channel is not allowed
            await interaction.response.send_message("This command is not allowed in this channel.", ephemeral=True)
        return wrapper
    return decorator



def require_game_admin(config):
    """Decorator to restrict commands to users with the game_admin role."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            # Get the game admin role ID from the config
            admin_role_id = int(config.get("game_admin"))
            # Get the admin role from the guild
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not admin_role:
                # If the role doesn't exist, send an error message
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            # Check if the user has the admin role
            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the user lacks the role
            await interaction.response.send_message(
                "You don't have the required permissions to use this command.", ephemeral=True
            )
        
        return wrapper
    return decorator

def require_game_owner_or_admin(config):
    """Decorator to restrict commands to the game owner or users with the game_admin role."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            # Get the game admin role ID from the config
            admin_role_id = int(config.get("game_admin"))
            # Get the admin role from the guild
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not admin_role:
                # If the role doesn't exist, send an error message
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            # Get the game ID associated with the current channel
            game_id = await interaction.client.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                # No game associated with the current channel
                await interaction.response.send_message("No game is associated with this channel.", ephemeral=True)
                return

            # Fetch game info
            game_info = await interaction.client.db_instance.get_game_info(game_id)
            if not game_info:
                # Game information is not found
                await interaction.response.send_message("Game information not found in the database.", ephemeral=True)
                return

            # Check if the user is the game owner
            if str(interaction.user.id) == game_info.get("game_owner"):
                return await command_func(interaction, *args, **kwargs)

            # Check if the user has the admin role
            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the user is neither the game owner nor an admin
            await interaction.response.send_message(
                "You don't have the required permissions to use this command. (Owner or Admin role required)",
                ephemeral=True
            )
        
        return wrapper
    return decorator

def require_game_host_or_admin(config):
    """Decorator to restrict commands to users with the game_host role or game_admin role."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            # Get the role IDs from the config
            host_role_id = int(config.get("game_host"))
            admin_role_id = int(config.get("game_admin"))

            # Get the roles from the guild
            host_role = discord.utils.get(interaction.guild.roles, id=host_role_id)
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not host_role:
                # If the host role doesn't exist, send an error message
                await interaction.response.send_message(
                    "The game host role is not configured or does not exist.", ephemeral=True
                )
                return

            if not admin_role:
                # If the admin role doesn't exist, send an error message
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            # Check if the user has the host role
            if host_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Check if the user has the admin role (admin bypass)
            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the user has neither the host role nor the admin role
            await interaction.response.send_message(
                "You don't have the required permissions to use this command. (Host or Admin role required)",
                ephemeral=True
            )
        
        return wrapper
    return decorator





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
   
    def descriptive_time_breakdown(self, seconds: int) -> str:
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


    async def send_game_message(self, game_id: int, message: str):
        """
        Handles sending a message to the correct Discord channel based on the game ID.

        Args:
            game_id (int): The ID of the game.
            message (str): The message to send.

        Returns:
            dict: A response dictionary indicating success or failure.
        """
        try:
            # Retrieve the channel_id based on the game_id
            channel_id = await self.db_instance.get_channel_id_by_game(game_id)
            print(f"Channel ID for game {game_id}: {channel_id}")
            if not channel_id:
                return {"status": "error", "message": "Invalid game ID or channel not found"}

            # Fetch the channel and send the message
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if channel:
                await channel.send(message)
                return {"status": "success", "message": "Message sent"}
            else:
                return {"status": "error", "message": "Unable to find the channel"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


    async def on_raw_reaction_add(self, payload):
        """
        Handles the addition of a reaction to a message. Pins the message if the 📌 emoji is used.
        """
        if payload.emoji.name == "📌":
            # Fetch the channel and message
            channel = self.get_channel(payload.channel_id) or await self.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            # Check if the message is already pinned
            if not message.pinned:
                try:
                    await message.pin()
                    #print(f"Pinned message: {message.content}")
                except discord.Forbidden:
                    print(f"Permission denied to pin messages in channel {channel.name}.")
                except discord.HTTPException as e:
                    print(f"Failed to pin message: {e}")


    async def on_raw_reaction_remove(self, payload):
        """
        Handles the removal of a reaction from a message. Unpins the message if the 📌 emoji is removed.
        """
        if payload.emoji.name == "📌":
            # Fetch the channel and message
            channel = self.get_channel(payload.channel_id) or await self.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            # Check if the message is currently pinned
            if message.pinned:
                try:
                    # Unpin the message
                    await message.unpin()
                    print(f"Unpinned message: {message.content}")
                except discord.Forbidden:
                    print(f"Permission denied to unpin messages in channel {channel.name}.")
                except discord.HTTPException as e:
                    print(f"Failed to unpin message: {e}")



    async def setup_hook(self):
        
        @self.tree.command(
            name="new-game",
            description="Creates a brand new game",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_host_or_admin(self.config)
        async def new_game_command(
            interaction: discord.Interaction,
            game_name: str,
            game_type: str,
            default_timer: float,
            game_era: str,
            research_random: str,
            global_slots: int,
            event_rarity: str,
            disicples: str,
            story_events: str,
            no_going_ai: str,
            master_pass: str,
            lv1_thrones: int,
            lv2_thrones: int,
            lv3_thrones: int,
            points_to_win: int
        ):
            try:
                # Defer interaction to prevent timeout
                await interaction.response.defer(ephemeral=True)

                # Validate inputs
                valid_game_types = ["Serious", "Casual", "Blitz"]
                if game_type not in valid_game_types:
                    await interaction.followup.send(f"Invalid game type. Choose from: {', '.join(valid_game_types)}", ephemeral=True)
                    return

                era_map = {"Early": 1, "Middle": 2, "Late": 3}
                research_random_map = {"Even Spread": 1, "Random": 0}
                event_rarity_map = {"Common": 1, "Rare": 2}
                disicples_map = {"False": 0, "True": 1}
                story_events_map = {"None": 0, "Some": 1, "Full": 2}
                no_going_ai_map = {"True": 0, "False": 1}

                game_era_value = era_map[game_era]
                research_random_value = research_random_map[research_random]
                event_rarity_value = event_rarity_map[event_rarity]
                disicples_value = disicples_map[disicples]
                story_events_value = story_events_map[story_events]
                no_going_ai_value = no_going_ai_map[no_going_ai]

                thrones_value = ",".join(map(str, [lv1_thrones, lv2_thrones, lv3_thrones]))

                if points_to_win < 1 or points_to_win > lv1_thrones + lv2_thrones * 2 + lv3_thrones * 3:
                    await interaction.followup.send("Invalid points to win.", ephemeral=True)
                    return

                # Calculate timer value based on game type (blitz vs normal)
                if game_type.lower() == "blitz":
                    timer_seconds = int(default_timer * 60)  # Minutes for blitz games
                    timer_unit = "minutes"
                else:
                    timer_seconds = int(default_timer * 3600)  # Hours for normal games  
                    timer_unit = "hours"

                # Fetch guild and category
                guild = interaction.client.get_guild(self.guild_id)
                if not guild:
                    guild = await interaction.client.fetch_guild(self.guild_id)

                category = await guild.fetch_channel(self.category_id)
                if not category or not isinstance(category, discord.CategoryChannel):
                    await interaction.followup.send("Game lobby category not found or invalid.", ephemeral=True)
                    return

                # Create channel
                new_channel = await guild.create_text_channel(name=game_name, category=category)

                # Set permissions for @everyone role
                everyone_role = guild.default_role
                permissions = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )
                await new_channel.set_permissions(everyone_role, overwrite=permissions)

                # Create a role for the game
                role_name = f"{game_name} player"
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    role = await guild.create_role(name=role_name)

                # Database operations
                try:
                    # Create the game
                    new_game_id = await self.db_instance.create_game(
                        game_name=game_name,
                        game_type=game_type,
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
                        game_running=False,
                        game_started=False,
                        channel_id=new_channel.id,
                        role_id=role.id,
                        game_owner=interaction.user.name,
                        creation_version=self.nidhogg.get_version(),
                        max_active_games = self.config["max_active_games"]
                    )

                    # Create the timer for the new game
                    await self.db_instance.create_timer(
                        game_id=new_game_id,
                        timer_default=timer_seconds,  # Based on default_timer parameter and game type
                        timer_running=False,  # Not running initially
                        remaining_time=timer_seconds  # Full remaining time initially
                    )

                    await interaction.followup.send(f"Game '{game_name}' created successfully!", ephemeral=True)

                except Exception as e:
                    # Cleanup if any exception occurs
                    await new_channel.delete()
                    await interaction.followup.send(f"Unexpected error: {e}", ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)




        @new_game_command.autocomplete("game_type")
        async def game_type_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Casual", "Serious", "Blitz"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]

        @new_game_command.autocomplete("game_era")
        async def game_era_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Early", "Middle", "Late"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]

        @new_game_command.autocomplete("research_random")
        async def research_random_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Even Spread", "Random"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]

        @new_game_command.autocomplete("event_rarity")
        async def event_rarity_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Common", "Rare"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]

        @new_game_command.autocomplete("disicples")
        async def disicples_autocomplete(interaction: discord.Interaction, current: str):
            options = ["False", "True"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]

        @new_game_command.autocomplete("story_events")
        async def story_events_autocomplete(interaction: discord.Interaction, current: str):
            options = ["None", "Some", "Full"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]

        @new_game_command.autocomplete("no_going_ai")
        async def no_going_ai_autocomplete(interaction: discord.Interaction, current: str):
            options = ["False", "True"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [app_commands.Choice(name=match, value=match) for match in matches]
        @new_game_command.autocomplete("global_slots")
        async def global_slots_autocomplete(interaction: discord.Interaction, current: str):
            # Predefined options for global slots
            options = [5, 3, 7, 9, 11, 13, 15]

            # Filter options based on the current input
            matches = [str(option) for option in options if current.isdigit() and current in str(option)]

            # If no input yet or input doesn't match a specific number, show all options
            if not current.isdigit():
                matches = [str(option) for option in options]

            # Convert matches to app_commands.Choice objects
            return [discord.app_commands.Choice(name=match, value=int(match)) for match in matches]





        @self.tree.command(
            name="edit-game",
            description="Edits all properties of an existing game.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def edit_game_command(
            interaction: discord.Interaction,
            game_type: str,
            game_era: str,
            research_random: str,
            global_slots: int,
            event_rarity: str,
            disicples: str,
            story_events: str,
            no_going_ai: str,
            master_pass: str,
            lv1_thrones: int,
            lv2_thrones: int,
            lv3_thrones: int,
            points_to_win: int
        ):
            """
            Fully edits all properties of an existing game. All fields are required.
            """
            try:
                # Defer interaction to prevent timeout
                await interaction.response.defer(ephemeral=True)

                # Get the game ID from the channel ID
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if not game_id:
                    await interaction.followup.send("This channel is not associated with an active game.", ephemeral=True)
                    return

                # Fetch game details
                game_info = await self.db_instance.get_game_info(game_id)
                if not game_info:
                    await interaction.followup.send(f"No game found with ID {game_id}.", ephemeral=True)
                    return

                # Reject edits if the game has already started
                if game_info["game_started"]:
                    await interaction.followup.send(f"Cannot edit game properties. The game in this channel has already started.", ephemeral=True)
                    return

                # Validation logic for fields
                valid_game_types = ["Serious", "Casual", "Blitz"]
                if game_type not in valid_game_types:
                    await interaction.followup.send("Invalid value for game_type. Allowed values: Serious, Casual, Blitz.", ephemeral=True)
                    return

                era_map = {"Early": 1, "Middle": 2, "Late": 3}
                if game_era not in era_map:
                    await interaction.followup.send("Invalid value for game_era. Allowed values: Early, Middle, Late.", ephemeral=True)
                    return
                game_era_value = era_map[game_era]

                research_random_map = {"Even Spread": 1, "Random": 0}
                if research_random not in research_random_map:
                    await interaction.followup.send("Invalid value for research_random. Allowed values: Even Spread, Random.", ephemeral=True)
                    return
                research_random_value = research_random_map[research_random]

                if global_slots not in [3, 4, 5, 6, 7, 8, 9]:
                    await interaction.followup.send("Invalid value for global_slots. Allowed values: 3, 4, 5, 6, 7, 8, 9.", ephemeral=True)
                    return

                event_rarity_map = {"Common": 1, "Rare": 2}
                if event_rarity not in event_rarity_map:
                    await interaction.followup.send("Invalid value for event_rarity. Allowed values: Common, Rare.", ephemeral=True)
                    return
                event_rarity_value = event_rarity_map[event_rarity]

                disicples_map = {"False": 0, "True": 1}
                if disicples not in disicples_map:
                    await interaction.followup.send("Invalid value for disicples. Allowed values: False, True.", ephemeral=True)
                    return
                disicples_value = disicples_map[disicples]

                story_events_map = {"None": 0, "Some": 1, "Full": 2}
                if story_events not in story_events_map:
                    await interaction.followup.send("Invalid value for story_events. Allowed values: None, Some, Full.", ephemeral=True)
                    return
                story_events_value = story_events_map[story_events]

                no_going_ai_map = {"True": 0, "False": 1}
                if no_going_ai not in no_going_ai_map:
                    await interaction.followup.send("Invalid value for no_going_ai. Allowed values: True, False.", ephemeral=True)
                    return
                no_going_ai_value = no_going_ai_map[no_going_ai]

                max_points = lv1_thrones + lv2_thrones * 2 + lv3_thrones * 3
                if points_to_win < 1 or points_to_win > max_points:
                    await interaction.followup.send(f"Invalid points_to_win. Must be between 1 and {max_points}.", ephemeral=True)
                    return

                thrones_value = f"{lv1_thrones},{lv2_thrones},{lv3_thrones}"

                # Update the database
                updates = {
                    "game_type": game_type,
                    "game_era": game_era_value,
                    "research_random": research_random_value,
                    "global_slots": global_slots,
                    "eventrarity": event_rarity_value,
                    "teamgame": disicples_value,
                    "story_events": story_events_value,
                    "no_going_ai": no_going_ai_value,
                    "masterpass": master_pass,
                    "thrones": thrones_value,
                    "requiredap": points_to_win
                }

                for property_name, new_value in updates.items():
                    await self.db_instance.update_game_property(game_id, property_name, new_value)

                await interaction.followup.send(f"Successfully updated the game in this channel.", ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)



        

        @edit_game_command.autocomplete("game_type")
        async def game_type_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Serious", "Casual", "Blitz"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]


        @edit_game_command.autocomplete("game_era")
        async def game_era_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Early", "Middle", "Late"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]


        @edit_game_command.autocomplete("research_random")
        async def research_random_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Even Spread", "Random"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]

        @edit_game_command.autocomplete("global_slots")
        async def global_slots_autocomplete(interaction: discord.Interaction, current: str):
            options = [5, 3, 4, 6, 7, 8, 9]
            matches = [str(option) for option in options if current.isdigit() and current in str(option)]
            if not matches:
                matches = [str(option) for option in options]
            return [discord.app_commands.Choice(name=match, value=int(match)) for match in matches]


        @edit_game_command.autocomplete("event_rarity")
        async def event_rarity_autocomplete(interaction: discord.Interaction, current: str):
            options = ["Common", "Rare"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]


        @edit_game_command.autocomplete("disicples")
        async def disicples_autocomplete(interaction: discord.Interaction, current: str):
            options = ["False", "True"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]


        @edit_game_command.autocomplete("story_events")
        async def story_events_autocomplete(interaction: discord.Interaction, current: str):
            options = ["None", "Some", "Full"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]


        @edit_game_command.autocomplete("no_going_ai")
        async def no_going_ai_autocomplete(interaction: discord.Interaction, current: str):
            options = ["False", "True"]
            matches = [option for option in options if current.lower() in option.lower()]
            return [discord.app_commands.Choice(name=match, value=match) for match in matches]





        @self.tree.command(
            name="launch",
            description="Launches game lobby.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def launch_game_lobby(interaction: discord.Interaction):
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer()  # Ensure the initial defer is also ephemeral
            print(f"\nTrying to launch game in channel {interaction.channel}.")

            # Get the game ID and game info
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Check if the game is active
            if not game_info["game_active"]:
                await interaction.followup.send("This game is not marked as active and cannot be launched.")
                print(f"\nFailed to launch game. Game {game_id} is inactive.")
                return

            # Check if the game map is set
            if not game_info["game_map"]:
                await interaction.followup.send("Map missing. Please use /select_map.")
                print(f"\nFailed to launch game. Map missing in {interaction.channel}.")
                return  # Exit the function early since the map is missing

            print(f"Launching game {game_id}")

            # Attempt to launch the game lobby
            success = await self.nidhogg.launch_game_lobby(game_id, self.db_instance, self.config)
            if success:
                await interaction.followup.send(f"Game lobby launched for game {game_info['game_name']} ID: {game_id}.")
            else:
                await interaction.followup.send(f"Failed to launch game lobby for game {game_info['game_name']} ID: {game_id}.")




        @self.tree.command(
            name="start-game",
            description="Starts a fresh game.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def start_game(interaction: discord.Interaction):
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer()
            print(f"\nTrying to start game in channel {interaction.channel}.")

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            game_info = await self.db_instance.get_game_info(game_id)

            # Reject if the game is already started
            if game_info["game_started"]:
                await interaction.followup.send(
                    f"The game '{game_info['game_name']}' has already been started. You cannot start it again."
                )
                print(f"\nFailed to start game. Game '{game_info['game_name']}' is already started.")
                return

            # Reject if the map is missing
            if not game_info["game_map"]:
                await interaction.followup.send("Map missing. Please use /select_map.")
                print(f"\nFailed to start game. Map missing in {interaction.channel}.")
                return

            # Reject if the game is not running
            if not game_info["game_running"]:
                await interaction.followup.send("Game is not running. Please use /launch.")
                print(f"\nFailed to start game. Game not running in {interaction.channel}.")
                return

            # Step 1: Fetch nations with submitted pretenders (.2h files)
            try:
                nations_with_2h_files = await bifrost.get_nations_with_2h_files(game_info["game_name"], self.config)
                print(f"Found nations with .2h files: {nations_with_2h_files}")  # Debug output
                if not nations_with_2h_files:
                    await interaction.followup.send(
                        "No pretenders have been submitted. Ensure at least one pretender is submitted before starting the game."
                    )
                    print(f"\nFailed to start game. No .2h files found in {interaction.channel}.")
                    return
            except Exception as e:
                await interaction.followup.send(f"Error checking pretender submission status: {e}")
                return

            # Step 2: Fetch claimed nations from the database
            try:
                claimed_nations = await self.db_instance.get_claimed_nations(game_id)
                print(f"Claimed nations: {claimed_nations}")  # Debug output
            except Exception as e:
                await interaction.followup.send(f"Error fetching claimed nations: {e}")
                return

            # Step 3: Verify claimants for submitted pretenders
            unclaimed_pretenders = [
                nation for nation in nations_with_2h_files if nation not in claimed_nations
            ]
            if unclaimed_pretenders:
                await interaction.followup.send(
                    f"The following nations have submitted pretenders but are unclaimed: {', '.join(unclaimed_pretenders)}. "
                    "Ensure all nations with pretenders are claimed before starting the game."
                )
                print(f"\nFailed to start game. Unclaimed pretenders in {interaction.channel}: {unclaimed_pretenders}")
                return

            print(f"Starting game {game_id}")

            # Call Bifrost to backup the .2h files
            try:
                await bifrost.backup_2h_files(game_id, game_info["game_name"], config=self.config)
                print(f"Backup completed for game ID {game_id}.")
            except Exception as e:
                await interaction.followup.send(f"Failed to backup game files: {e}")
                return

            # Use Nidhogg to force host via domcmd
            try:
                await self.nidhogg.force_game_host(game_id, self.config, self.db_instance)
                await self.nidhogg.force_game_host(game_id, self.config, self.db_instance)
                await interaction.followup.send(f"Game start command has been executed for game ID {game_id}. Please wait until turn 1 notice before joining game.")
            except Exception as e:
                await interaction.followup.send(f"Failed to force the game to start: {e}")
                return

            # NOTE: game_started and timer will be set to True when turn 1 notification is sent (actual game start)



        @self.tree.command(
            name="extend-timer",
            description="Adjusts the timer (hours for normal games, minutes for blitz games).",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def extend_timer(interaction: discord.Interaction, time_value: float):
            """Adjusts the timer for the current game by a specified amount (hours or minutes based on game type)."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            try:
                # Fetch current timer info
                timer_info = await self.db_instance.get_game_timer(game_id)
                if not timer_info:
                    await interaction.followup.send("No timer information found for this game.")
                    return

                # Fetch game info to get the game owner and determine game type
                game_info = await self.db_instance.get_game_info(game_id)
                game_owner_id = game_info["game_owner"]

                # Check if the requester is an admin or the game owner
                admin_role_id = int(self.config.get("game_admin"))
                admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
                is_admin = admin_role in interaction.user.roles if admin_role else False
                is_owner = str(interaction.user.id) == game_owner_id

                # Disallow negative values for non-admins and non-owners
                if time_value < 0 and not (is_owner or is_admin):
                    await interaction.followup.send(
                        "Only the game owner or an admin can reduce the timer."
                    )
                    return

                # Check if the requester is a player
                player_entry = await self.db_instance.get_player_by_game_and_user(game_id, str(interaction.user.id))
                is_player = bool(player_entry)

                # Determine time unit and convert to seconds
                if game_info.get("game_type", "").lower() == "blitz":
                    # Blitz games: treat input as minutes
                    added_seconds = int(time_value * 60)
                    time_unit = "minutes"
                else:
                    # Normal games: treat input as hours
                    added_seconds = int(time_value * 3600)
                    time_unit = "hours"

                # If the requester is a player (even if they are also an admin or owner), update their extensions
                if is_player and time_value > 0:
                    # Always store extensions in seconds regardless of game type
                    await self.db_instance.increment_player_extensions(game_id, str(interaction.user.id))

                # Calculate new remaining time
                new_remaining_time = max(0, timer_info["remaining_time"] + added_seconds)  # Prevent negative time

                # Update the timer
                await self.db_instance.update_timer(game_id, new_remaining_time, timer_info["timer_running"])

                # Format time value nicely (remove .0 for whole numbers)
                formatted_time = f"{time_value:g}"
                
                if time_value >= 0:
                    await interaction.followup.send(
                        f"Timer for game ID {game_id} has been extended by {formatted_time} {time_unit}."
                    )
                else:
                    await interaction.followup.send(
                        f"Timer for game ID {game_id} has been reduced by {abs(time_value):g} {time_unit}."
                    )

            except Exception as e:
                await interaction.followup.send(f"Failed to adjust the timer: {e}")



        @self.tree.command(
            name="extensions-stats",
            description="Shows all players in the game and their total extension amounts.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def extensions_stats(interaction: discord.Interaction):
            """Displays a summary of all players and their total extensions (hours or minutes based on game type)."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            try:
                # Fetch game info to determine game type
                game_info = await self.db_instance.get_game_info(game_id)
                if not game_info:
                    await interaction.followup.send("Game information not found.")
                    return

                # Determine time unit based on game type
                is_blitz = game_info.get("game_type", "").lower() == "blitz"
                time_unit = "minutes" if is_blitz else "hours"
                time_divisor = 60 if is_blitz else 3600

                # Fetch all players and their extensions for the given game
                players_in_game = await self.db_instance.get_players_in_game(game_id)
                
                if not players_in_game:
                    await interaction.followup.send("No players found for this game.")
                    return

                # Prepare the embed
                embed = discord.Embed(
                    title="Extension Stats",
                    description=f"Extension statistics for game ID: {game_id}",
                    color=discord.Color.green()
                )

                guild = interaction.guild
                for player in players_in_game:
                    player_id = player['player_id']
                    extensions = player['extensions']
                    # Resolve the player's Discord username
                    member = guild.get_member(int(player_id))
                    display_name = member.display_name if member else f"Unknown (ID: {player_id})"

                    # Convert extensions (in seconds) to appropriate time unit
                    extensions_in_time_unit = (extensions or 0) // time_divisor

                    # Add the player and their extensions to the embed
                    embed.add_field(
                        name=display_name,
                        value=f"Total Extensions: {extensions_in_time_unit} {time_unit}",
                        inline=False
                    )

                # Send the embed
                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"Failed to retrieve extension stats: {e}")




        @self.tree.command(
            name="set-default-timer",
            description="Changes the default timer for the game (hours for normal games, minutes for blitz).",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def set_default_timer(interaction: discord.Interaction, time_value: float):
            """Changes the default timer for the current game."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            try:
                # Get game info to check if it's a blitz game
                game_info = await self.db_instance.get_game_info(game_id)
                if not game_info:
                    await interaction.followup.send("Game information not found.")
                    return

                # Check if game type is blitz - if so, treat input as minutes instead of hours
                if game_info.get("game_type", "").lower() == "blitz":
                    # Convert minutes to seconds
                    new_default_timer = int(time_value * 60)
                    time_unit = "minutes"
                else:
                    # Convert hours to seconds
                    new_default_timer = int(time_value * 3600)
                    time_unit = "hours"

                # Update the timer_default in the database
                # Update the default timer using the database method
                await self.db_instance.update_timer_default(game_id, new_default_timer)

                await interaction.followup.send(
                    f"Default timer for game ID {game_id} has been updated to {time_value:g} {time_unit}."
                )
            except Exception as e:
                await interaction.followup.send(f"Failed to update default timer: {e}")

        @self.tree.command(
            name="pause",
            description="Toggles the timer for the current game between paused and running.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def toggle_timer(interaction: discord.Interaction):
            """Toggles the timer for the current game between paused and running."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return
            
            # Fetch game details
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send(f"No game found with ID {game_id}.")
                return

            try:
                # Fetch the current timer status
                timer_info = await self.db_instance.get_game_timer(game_id)
                if not timer_info:
                    await interaction.followup.send("No timer information found for this game.")
                    return
                


                current_state = timer_info["timer_running"]

                # Toggle the timer state
                new_state = not current_state
                await self.db_instance.set_timer_running(game_id, new_state)

                if new_state:
                    await interaction.followup.send(f"Timer for game {game_info['game_name']} ID {game_id} has been unpaused.")
                else:
                    await interaction.followup.send(f"Timer for game {game_info['game_name']} ID {game_id} has been paused.")
            except Exception as e:
                await interaction.followup.send(f"Failed to toggle timer: {e}")







        @self.tree.command(
            name="game-info",
            description="Fetches and displays details about the game in this channel.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def game_info_command(interaction: discord.Interaction):
            """
            Fetch and display details about the game in the current channel in a single embed.
            """
            try:
                # Defer interaction to prevent timeout
                await interaction.response.defer()

                # Get the game ID from the channel ID
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if not game_id:
                    await interaction.followup.send("This channel is not associated with an active game.")
                    return

                # Fetch game details
                game_info = await self.db_instance.get_game_info(game_id)
                if not game_info:
                    await interaction.followup.send(f"No game found with ID {game_id}.")
                    return

                # Get the host address from the config file
                server_host = self.config.get("server_host", "Unknown")

                # Map story events and game era to human-readable values
                story_events_map = {0: "None", 1: "Some", 2: "Full"}
                story_events_value = story_events_map.get(game_info["story_events"], "Unknown")

                era_map = {1: "Early", 2: "Middle", 3: "Late"}
                game_era_value = era_map.get(game_info["game_era"], "Unknown")

                # Create an embed to display the game details
                embed = discord.Embed(
                    title=f"Game Info: {game_info['game_name']}",
                    description=f"Details for game ID **{game_id}**",
                    color=discord.Color.green(),
                )

                # Get timer information if game is started - add as first field
                if game_info['game_started'] and game_info['game_running']:
                    try:
                        timer_data = await self.db_instance.get_game_timer(game_id)
                        if timer_data:
                            remaining_time = timer_data["remaining_time"]
                            timer_default = timer_data["timer_default"]
                            timer_running = timer_data["timer_running"]
                            
                            # Convert seconds to readable format
                            remaining_readable = self.descriptive_time_breakdown(remaining_time) if remaining_time else "Unknown"
                            
                            # Check if it's a blitz game for default timer display
                            if game_info.get("game_type", "").lower() == "blitz":
                                default_readable = f"{timer_default // 60} minutes" if timer_default else "Unknown"
                            else:
                                default_readable = f"{timer_default // 3600} hours" if timer_default else "Unknown"
                            
                            timer_status = "Running" if timer_running else "Paused"
                            
                            embed.add_field(
                                name="⏰ Timer Status",
                                value=(
                                    f"**Timer Remaining**: {remaining_readable}\n"
                                    f"**Timer Status**: {timer_status}\n"
                                    f"**Default Timer**: {default_readable}"
                                ),
                                inline=False,
                            )
                    except Exception as e:
                        embed.add_field(
                            name="⏰ Timer Status",
                            value="Error fetching timer data",
                            inline=False,
                        )

                story_events_map = {0: "None", 1: "Some", 2: "Full"}
                
                # Format and group details for the embed
                embed.add_field(
                    name="Basic Information",
                    value=(
                        f"**Game Name**: {game_info['game_name']}\n"
                        f"**Game Type**: {game_info['game_type']}\n"
                        f"**Game Era**: {game_era_value}\n"
                        f"🔌 **Game Port**: {game_info['game_port']}\n"
                        f"🌐 **Host Address**: {server_host}\n"
                        f"**Game Owner**: {game_info['game_owner']}\n"
                        f"**Version**: {game_info['creation_version']}\n"
                        f"**Creation Date**: {game_info['creation_date']}\n"
                        f"🔧 **Mods**: {game_info['game_mods']}\n"
                        f"🗺 **Map**: {game_info['game_map']}\n"
                    ),
                    inline=False,
                )

                embed.add_field(
                    name="Settings",
                    value=(
                        f"**Global Slots**: {game_info['global_slots']}\n"
                        f"**Research Random**: {'True' if game_info['research_random'] else 'False'}\n"
                        f"**Event Rarity**: {game_info['eventrarity']}\n"
                        f"**Story Events**: {story_events_map[game_info['story_events']]}\n"
                        f"**No Going AI**: {'True' if game_info['no_going_ai'] else 'False'}\n"
                        f"**Team Game**: {'True' if game_info['teamgame'] else 'False'}\n"
                        f"**Clustered Starts**: {'True' if game_info['clustered'] else 'False'}\n"
                        f"**Edge Starts**: {'True' if game_info['edgestart'] else 'False'}\n"
                        f"**No Artifact Restrictions**: {'True' if game_info['noartrest'] else 'False'}\n"
                        f"**No Level 9 Restrictions**: {'True' if game_info['nolvl9rest'] else 'False'}\n"
                    ),
                    inline=False,
                )

                embed.add_field(
                    name="Gameplay Details",
                    value=(
                        f"**Indie Strength**: {game_info['indie_str'] or 'Default'}\n"
                        f"**Magic Sites**: {game_info['magicsites'] or 'Default'}\n"
                        f"**Richness**: {game_info['richness'] or 'Default'}\n"
                        f"**Resources**: {game_info['resources'] or 'Default'}\n"
                        f"**Recruitment**: {game_info['recruitment'] or 'Default'}\n"
                        f"**Supplies**: {game_info['supplies'] or 'Default'}\n"
                        f"**Points to Win**: {game_info['requiredap']}\n"
                        f"**Thrones**: {game_info['thrones']}\n"
                    ),
                    inline=False,
                )

                # Get timer information if game is started
                timer_info_text = ""
                if game_info['game_started'] and game_info['game_running']:
                    try:
                        timer_data = await self.db_instance.get_game_timer(game_id)
                        if timer_data:
                            remaining_time = timer_data["remaining_time"]
                            timer_default = timer_data["timer_default"]
                            timer_running = timer_data["timer_running"]
                            
                            # Convert seconds to readable format
                            remaining_readable = self.descriptive_time_breakdown(remaining_time) if remaining_time else "Unknown"
                            
                            # Check if it's a blitz game for default timer display
                            if game_info.get("game_type", "").lower() == "blitz":
                                default_readable = f"{timer_default // 60} minutes" if timer_default else "Unknown"
                            else:
                                default_readable = f"{timer_default // 3600} hours" if timer_default else "Unknown"
                            
                            timer_status = "Running" if timer_running else "Paused"
                            timer_info_text = (
                                f"**Timer Remaining**: {remaining_readable}\n"
                                f"**Timer Status**: {timer_status}\n"
                                f"**Default Timer**: {default_readable}\n"
                            )
                    except Exception as e:
                        timer_info_text = f"**Timer Info**: Error fetching timer data\n"
                
                embed.add_field(
                    name="Game State",
                    value=(
                        f"**Game Running**: {'True' if game_info['game_running'] else 'False'}\n"
                        f"**Game Started**: {'True' if game_info['game_started'] else 'False'}\n"
                        f"**Game Active**: {'True' if game_info['game_active'] else 'False'}\n"
                        f"{timer_info_text}"
                    ),
                    inline=False,
                )

                # Send the embed
                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")








        @self.tree.command(
            name="restart-game-to-lobby",
            description="Restarts the game back to the lobby state.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def restart_game_to_lobby(interaction: discord.Interaction, confirm_game_name:str):
            """Restarts the game associated with the current channel back to the lobby state."""
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer(ephemeral=True)

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.", ephemeral=True)
                return

            # Fetch game information
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found in the database.", ephemeral=True)
                return
            

            # Validate the confirm_game_name
            if confirm_game_name != game_info["game_name"]:
                await interaction.followup.send(
                    f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
                )
                return

            # Check if the game has started
            if not game_info["game_started"]:
                await interaction.followup.send("The game has not been started. Cannot restart to lobby.", ephemeral=True)
                return

            # Kill the game
            try:
                await self.nidhogg.kill_game_lobby(game_id, self.db_instance)
                print(f"Game process for game ID {game_id} has been killed.")
            except Exception as e:
                await interaction.followup.send(f"Failed to kill the game process: {e}", ephemeral=True)
                return

            # Restore .2h files from the backup
            try:
                await bifrost.restore_2h_files(game_id, game_info["game_name"], config=self.config)
                print(f"Backup files restored for game ID {game_id}.")
            except Exception as e:
                await interaction.followup.send(f"Failed to restore game files: {e}", ephemeral=True)
                return
            
            await asyncio.sleep(5)
            success = await self.nidhogg.launch_game_lobby(game_id, self.db_instance, self.config)
            if success:
                await interaction.followup.send(f"Game lobby launched for game ID: {game_id}.")
            else:
                await interaction.followup.send(f"Failed to launch game lobby for game ID: {game_id}.")

            # Reset the `game_started` field in the database
            try:
                await self.db_instance.set_game_started_value(game_id, False)
                print(f"Game ID {game_id} has been reset to the lobby state.")
            except Exception as e:
                await interaction.followup.send(f"Failed to reset game to lobby state in the database: {e}", ephemeral=True)
                return

            await interaction.followup.send(f"Game ID {game_id} has been successfully restarted back to the lobby.")

        

        @self.tree.command(
            name="claim",
            description="Claim ownership of a nation.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def claim(interaction: discord.Interaction, nation_name: str):
            """Allows a user to claim a nation in the game."""
            await interaction.response.defer(ephemeral=True)

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            # Get game information
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found in the database.")
                return

            # Get the 2h files and validate the claimed nation
            try:
                valid_nations = await bifrost.get_valid_nations_from_files(game_id, self.config, self.db_instance)

                if nation_name not in valid_nations:
                    await interaction.followup.send(f"{nation_name} is not a valid nation for this game.")
                    return

                # Check if the player already owns the nation
                already_exists = await self.db_instance.check_player_nation(game_id, str(interaction.user.id), nation_name)
                if already_exists:
                    # Fetch the role
                    guild = interaction.guild
                    role_name = f"{game_info['game_name']} player"
                    role = discord.utils.get(guild.roles, name=role_name)

                    if not role:
                        # Create the role if it doesn't exist
                        role = await guild.create_role(name=role_name)
                        print(f"\nRole '{role_name}' created successfully.")

                    # Assign the role to the player if they don't already have it
                    if role not in interaction.user.roles:
                        await interaction.user.add_roles(role)
                        print(f"Assigned role '{role_name}' to user {interaction.user.name}.")
                        await interaction.followup.send(f"You already own {nation_name}, but the role '{role_name}' has been assigned to you.")
                    else:
                        await interaction.followup.send(f"You already own {nation_name} and have the role '{role_name}'.")

                    return

                # Add player to the database
                try:
                    await self.db_instance.add_player(game_id, str(interaction.user.id), nation_name)
                    print(f"Added player {interaction.user.name} as {nation_name} in game {game_id}.")
                except Exception as e:
                    await interaction.followup.send(f"Failed to add you as {nation_name} in the database: {e}")
                    return

                # Create or fetch the role and assign it to the player
                guild = interaction.guild
                role_name = f"{game_info['game_name']} player"

                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    # Create the role
                    role = await guild.create_role(name=role_name)
                    print(f"Role '{role_name}' created successfully.")

                # Assign the role to the player
                await interaction.user.add_roles(role)
                print(f"Assigned role '{role_name}' to user {interaction.user.name}.")

                await interaction.followup.send(f"You have successfully claimed {nation_name} and have been assigned the role '{role_name}'.")
            except Exception as e:
                await interaction.followup.send(f"Failed to claim the nation: {e}")
        @claim.autocomplete("nation_name")
        async def autocomplete_nation(
            interaction: discord.Interaction, current: str
        ) -> List[discord.app_commands.Choice]:
            """Autocomplete handler for the 'nation' argument."""
            try:
                # Get the game ID associated with the current channel
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if not game_id:
                    return []

                # Retrieve the list of valid nations for the game
                valid_nations = await bifrost.get_valid_nations_from_files(game_id, self.config, self.db_instance)

                # Filter the nations by the current input
                filtered_nations = [nation for nation in valid_nations if current.lower() in nation.lower()]

                # Return as autocomplete choices
                return [discord.app_commands.Choice(name=nation, value=nation) for nation in filtered_nations]

            except Exception as e:
                print(f"Error in autocomplete for nations: {e}")
                return []

        @self.tree.command(
            name="unclaim",
            description="Unclaim a nation and remove your game role.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def unclaim(interaction: discord.Interaction, nation_name: str):
            """Allows a player to unclaim a nation."""
            await interaction.response.defer()

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            # Get game information
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found in the database.", ephemeral=True)
                return

            game_name = game_info["game_name"]
            role_name = f"{game_name} player"

            # Check if the user has the role
            guild = interaction.guild
            if not guild:
                await interaction.followup.send("Unable to fetch guild information.", ephemeral=True)
                return

            member = interaction.user
            role = discord.utils.get(guild.roles, name=role_name)

            if not role or role not in member.roles:
                await interaction.followup.send(f"You do not have the role '{role_name}' to unclaim.", ephemeral=True)
                return

            # Remove the role from the user
            try:
                await member.remove_roles(role)
                await self.db_instance.unclaim_nation(game_id, str(interaction.user.id), nation_name)
                await interaction.followup.send(f"Role '{role_name}' has been removed from you, and nation '{nation_name}' has been unclaimed.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send("I don't have permission to remove this role.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"An error occurred while removing the role: {e}", ephemeral=True)

        # Autocomplete for unclaim
        @unclaim.autocomplete("nation_name")
        async def unclaim_autocomplete(interaction: discord.Interaction, current: str) -> List[discord.app_commands.Choice]:
            """Autocomplete handler for the 'nation_name' argument."""
            try:
                # Get the game ID associated with the current channel
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if not game_id:
                    return []

                # Fetch nations claimed by the user in the current game
                claimed_nations = await self.db_instance.get_claimed_nations_by_player(game_id, str(interaction.user.id))
                if not claimed_nations:
                    return []

                # Filter the nations based on the current input
                filtered_nations = [nation for nation in claimed_nations if current.lower() in nation.lower()]

                # Return the autocomplete choices
                return [discord.app_commands.Choice(name=nation, value=nation) for nation in filtered_nations]

            except Exception as e:
                print(f"Error in unclaim autocomplete: {e}")
                return []



                
        @self.tree.command(
            name="pretenders",
            description="Lists all submitted pretenders and shows who has claimed each nation.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def pretenders(interaction: discord.Interaction):
            """Lists all .2h files for a game and who has claimed each nation."""
            await interaction.response.defer()

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            print(f"Retrieved game ID: {game_id}")  # Debugging log
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            try:
                print(f"Fetching pretenders for game ID: {game_id}")
                
                # Get the valid nations
                valid_nations = await bifrost.get_valid_nations_from_files(game_id, self.config, self.db_instance)

                # Build the response
                embed = discord.Embed(title="Pretender Nations", color=discord.Color.blue())

                # Get claimed nations
                claimed_nations = await self.db_instance.get_claimed_nations(game_id)
                for nation in valid_nations:
                    claimants = claimed_nations.get(nation, [])  # Get the list of player IDs for the nation
                    if claimants:
                        resolved_claimants = []
                        for player_id in claimants:
                            user = interaction.guild.get_member(int(player_id)) or await interaction.client.fetch_user(int(player_id))
                            if user:
                                resolved_claimants.append(user.display_name)
                            else:
                                resolved_claimants.append(f"Unknown ({player_id})")
                        embed.add_field(
                            name=nation,
                            value=f"Claimed by: {', '.join(resolved_claimants)}",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name=nation,
                            value="Unclaimed",
                            inline=False
                        )



                await interaction.followup.send(embed=embed)

            except Exception as e:
                print(f"Error in pretenders command: {e}")
                await interaction.followup.send(f"Failed to retrieve pretender information: {e}")



        @self.tree.command(
            name="clear-claims",
            description="Clears all player claims and roles from the current game.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_admin(self.config)
        async def clear_claims(interaction: discord.Interaction):
            """Clears all claims and removes associated roles for the current game."""
            await interaction.response.defer()

            try:
                # Get the game ID and validate
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if not game_id:
                    await interaction.followup.send("No game is associated with this channel.")
                    return

                game_info = await self.db_instance.get_game_info(game_id)
                if not game_info:
                    await interaction.followup.send("Game information not found.")
                    return

                # Retrieve the role associated with the game
                role_id = game_info.get("role_id")
                role = discord.utils.get(interaction.guild.roles, id=int(role_id))
                if not role:
                    await interaction.followup.send("The associated role for this game does not exist.")
                    return

                # Fetch all players in the game
                players = await self.db_instance.get_players_in_game(game_id)
                if not players:
                    await interaction.followup.send("No players are associated with this game.")
                    return

                removed_members = []
                failed_members = []

                for player in players:
                    player_id = player["player_id"]
                    try:
                        # Retrieve the member from the guild
                        member = interaction.guild.get_member(int(player_id)) or await interaction.guild.fetch_member(int(player_id))
                        if not member:
                            failed_members.append(player_id)
                            continue

                        # Remove the role if the member has it
                        if role in member.roles:
                            await member.remove_roles(role)
                            removed_members.append(member.display_name)
                    except Exception as e:
                        print(f"Failed to remove role from player {player_id}: {e}")
                        failed_members.append(player_id)

                # Clear claims from the database
                await self.db_instance.clear_players(game_id)

                # Prepare response message
                response = f"All claims for game '{game_info['game_name']}' have been cleared."
                if removed_members:
                    response += f"\nRoles removed from: {', '.join(removed_members)}."
                if failed_members:
                    response += f"\nFailed to process the following players: {', '.join(map(str, failed_members))}."

                await interaction.followup.send(response)

            except Exception as e:
                print(f"Error in clear_claims: {e}")
                await interaction.followup.send(f"An unexpected error occurred: {e}")




        @self.tree.command(
            name="undone",
            description="Returns current turn status",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def undone_check(interaction: discord.Interaction):
            """Returns current turn info"""

            await interaction.response.defer()

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            # Get game info
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found in the database.")
                return

            # Reject if the game is not running or not started
            if not game_info["game_running"] or not game_info["game_started"]:
                await interaction.followup.send("This game is either not currently running or has not started. Turn information is unavailable.")
                return

            try:
                raw_status = await self.nidhogg.query_game_status(game_id, self.db_instance)
                timer_table = await self.db_instance.get_game_timer(game_id)

                # Parse the response
                lines = raw_status.split("\n")
                game_name = lines[2].split(":")[1].strip()
                turn = lines[4].split(":")[1].strip()
                time_left = timer_table["remaining_time"]
                timer_running = timer_table["timer_running"]

                if time_left is None:
                    raise ValueError("time_left cannot be None")

                # Determine timer status
                timer_status = "Running" if timer_running else "Paused"

                # Calculate turn end time
                current_time = datetime.now(timezone.utc)
                future_time = current_time + timedelta(seconds=time_left)
                discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"

                played_nations = []
                played_but_not_finished = []
                undone_nations = []

                for line in lines[6:]:
                    if "played, but not finished" in line:
                        nation = line.split(":")[1].split(",")[0].strip()
                        played_but_not_finished.append(nation)
                    elif "played" in line:
                        nation = line.split(":")[1].split(",")[0].strip()
                        played_nations.append(nation)
                    elif "(-)" in line:
                        nation = line.split(":")[1].split(",")[0].strip()
                        undone_nations.append(nation)

                # Create embeds
                embeds = []

                # Game Info embed
                game_info_embed = discord.Embed(
                    title=f"Turn {turn}",
                    description=(
                        f"Next turn:\n{discord_timestamp} in {self.descriptive_time_breakdown(time_left)}\n"
                        f"**Timer Status:** {timer_status}"
                    ),
                    color=discord.Color.blue()
                )
                embeds.append(game_info_embed)

                # Played Nations embed
                if played_nations:
                    played_embed = discord.Embed(
                        title="✅ Played Nations",
                        description="\n".join(played_nations),
                        color=discord.Color.green()
                    )
                    embeds.append(played_embed)

                # Played But Not Finished embed
                if played_but_not_finished:
                    unfinished_embed = discord.Embed(
                        title="⚠️ Played But Not Finished",
                        description="\n".join(played_but_not_finished),
                        color=discord.Color.gold()
                    )
                    embeds.append(unfinished_embed)

                # Undone Nations embed
                if undone_nations:
                    undone_embed = discord.Embed(
                        title="❌ Undone Nations",
                        description="\n".join(undone_nations),
                        color=discord.Color.red()
                    )
                    embeds.append(undone_embed)

                # Send all embeds in one response
                await interaction.followup.send(embeds=embeds)

            except Exception as e:
                await interaction.followup.send(f"Error querying turn for game id:{game_id}\n{str(e)}")




        @self.tree.command(
            name="end-game",
            description="Ends the game but keeps the lobby active.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def end_game(interaction: discord.Interaction, game_winner: int, confirm_game_name: str):
            """Ends the game but keeps the lobby active."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Validate the confirm_game_name
            if confirm_game_name != game_info["game_name"]:
                await interaction.followup.send(
                    f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
                )
                return

            # Reject if the game is currently running
            if game_info["game_running"]:
                await interaction.followup.send("You cannot end a game while it is currently running.")
                return

            # Set the game to inactive and update the winner
            try:
                async with self.db_instance.connection.cursor() as cursor:
                    query = """
                    UPDATE games
                    SET game_active = 0, game_winner = :game_winner
                    WHERE game_id = :game_id
                    """
                    params = {"game_winner": game_winner, "game_id": game_id}
                    await cursor.execute(query, params)
                    await self.db_instance.connection.commit()

                winner_text = "Everybody Lost" if game_winner == -666 else f"Player {game_winner}"
                await interaction.followup.send(f"Game {game_info['game_name']} has been successfully ended. Winner: {winner_text}.")
            except Exception as e:
                await interaction.followup.send(f"Failed to end the game: {e}")




        @self.tree.command(
            name="delete-lobby",
            description="Deletes the game lobby and associated role.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def delete_lobby(interaction: discord.Interaction, confirm_game_name: str):
            """Deletes the game lobby and associated role."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Check if the game is still active
            if game_info["game_active"]:
                await interaction.followup.send("The game is still active. Please end the game before deleting the lobby.")
                return

            # Validate the confirm_game_name
            if confirm_game_name != game_info["game_name"]:
                await interaction.followup.send(
                    f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
                )
                return

            guild = interaction.guild
            role_id = game_info["role_id"]

            try:
                # Remove the role from all members
                if role_id:
                    role = discord.utils.get(guild.roles, id=int(role_id))
                    if role:
                        for member in guild.members:
                            if role in member.roles:
                                await member.remove_roles(role)

                        # Delete the role
                        await role.delete()
                        print(f"Deleted role: {role.name}")

                # Delete the lobby channel
                channel = interaction.channel
                await channel.delete()
                print(f"Deleted channel: {channel.name}")

                await interaction.followup.send(f"Lobby {channel.name} and associated role have been deleted.")
            except Exception as e:
                await interaction.followup.send(f"Failed to delete lobby: {e}")

        @self.tree.command(
            name="reset-game-started",
            description="Resets the game_started flag to allow retrying /start-game after failures (ADMIN ONLY).",
            guild=discord.Object(id=self.guild_id),
        )
        @require_bot_channel(self.config)
        @require_game_admin(self.config)
        async def reset_game_started(interaction: discord.Interaction, confirm_game_name: str):
            """Resets the game_started flag to False so /start-game can be retried after failures."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return

            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Validate the confirm_game_name
            if confirm_game_name != game_info["game_name"]:
                await interaction.followup.send(
                    f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
                )
                return

            # Check if the game is actually marked as started
            if not game_info["game_started"]:
                await interaction.followup.send(f"Game '{game_info['game_name']}' is not marked as started - no reset needed.")
                return

            # Reset the game_started flag
            try:
                await self.db_instance.set_game_started_value(game_id, False)
                await interaction.followup.send(
                    f"✅ Game '{game_info['game_name']}' has been reset. The game_started flag is now False.\n"
                    f"You can now retry `/start-game` to attempt starting the game again."
                )
                print(f"[ADMIN] Game ID {game_id} ({game_info['game_name']}) game_started flag reset by {interaction.user}")
            except Exception as e:
                await interaction.followup.send(f"Failed to reset game_started flag: {e}")

        @self.tree.command(
            name="timer",
            description="Shows current timer status and remaining time for the game.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_bot_channel(self.config)
        async def timer_command(interaction: discord.Interaction):
            """Shows timer information for the current game."""
            await interaction.response.defer()

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Check if game is started
            if not game_info['game_started'] or not game_info['game_running']:
                await interaction.followup.send("Game must be started and running to show timer information.")
                return

            try:
                # Get timer information
                timer_data = await self.db_instance.get_game_timer(game_id)
                if not timer_data:
                    await interaction.followup.send("Timer data not found for this game.")
                    return

                remaining_time = timer_data["remaining_time"]
                timer_default = timer_data["timer_default"]
                timer_running = timer_data["timer_running"]

                # Convert seconds to readable format
                remaining_readable = self.descriptive_time_breakdown(remaining_time) if remaining_time else "Unknown"
                
                # Check if it's a blitz game for default timer display
                if game_info.get("game_type", "").lower() == "blitz":
                    default_readable = f"{timer_default / 60:.1f} minutes" if timer_default else "Unknown"
                    timer_unit = "minutes"
                else:
                    hours = timer_default / 3600 if timer_default else 0
                    if hours == int(hours):
                        default_readable = f"{int(hours)} hours" if timer_default else "Unknown"
                    else:
                        default_readable = f"{hours:.1f} hours" if timer_default else "Unknown"
                    timer_unit = "hours"

                timer_status = "🟢 Running" if timer_running else "🔴 Paused"

                # Calculate when timer will end
                from datetime import datetime, timezone, timedelta
                if remaining_time and timer_running:
                    current_time = datetime.now(timezone.utc)
                    future_time = current_time + timedelta(seconds=remaining_time)
                    discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
                    next_turn_text = f"**Next Turn**: {discord_timestamp}"
                else:
                    next_turn_text = "**Next Turn**: Timer is paused"

                # Create embed
                embed = discord.Embed(
                    title=f"⏰ Timer Status: {game_info['game_name']}",
                    color=discord.Color.green() if timer_running else discord.Color.red()
                )

                embed.add_field(
                    name="Current Timer",
                    value=(
                        f"**Time Remaining**: {remaining_readable}\n"
                        f"**Status**: {timer_status}\n"
                        f"{next_turn_text}"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Timer Settings",
                    value=(
                        f"**Default Timer**: {default_readable}\n"
                        f"**Timer Type**: {timer_unit.title()} per turn"
                    ),
                    inline=False
                )

                embed.set_footer(text=f"Game ID: {game_id}")

                await interaction.followup.send(embed=embed)

            except Exception as e:
                await interaction.followup.send(f"Error fetching timer information: {e}")

        @end_game.autocomplete("game_winner")
        async def game_winner_autocomplete(interaction: discord.Interaction, current: str):
            """Autocomplete options for game winner."""
            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            # Fetch players for the game
            try:
                # Fetch players for the game using the database method
                players_in_game = await self.db_instance.get_players_in_game(game_id)

                # Map player_id to usernames
                guild = interaction.guild
                options = []
                for player in players_in_game:
                    player_id = player['player_id']
                    member = guild.get_member(int(player_id))
                    if member:
                        display_name = member.display_name
                        options.append(app_commands.Choice(name=f"{display_name} (ID: {player_id})", value=int(player_id)))

                # Add "Everybody Lost" as an additional option
                options.append(app_commands.Choice(name="Everybody Lost", value=-666))

                # Filter options by the current input
                if current:
                    options = [option for option in options if current.lower() in option.name.lower()]

                return options[:25]  # Limit to 25 options as per Discord's limit
            except Exception as e:
                print(f"Error fetching autocomplete options for game_winner: {e}")
                return []










        @self.tree.command(
            name="roll-back",
            description="Roll back the game to the latest backup.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def roll_back(interaction: discord.Interaction):
            """Rolls back the game associated with the current channel to the latest backup."""
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer()

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            # Fetch game information
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found in the database.")
                return

            # Check if the game is currently running
            if game_info["game_running"]:
                await interaction.followup.send("The game is currently running. Please stop the game first.")
                return

            # Attempt to restore the saved game files
            try:
                await bifrost.restore_saved_game_files(
                    game_id=game_id,
                    db_instance=self.db_instance,
                    config=self.config
                )
                await interaction.followup.send(f"Game ID {game_id} ({game_info['game_name']}) has been successfully rolled back to the latest backup.")
                print(f"Game ID {game_id} ({game_info['game_name']}) successfully rolled back.")
            except FileNotFoundError as fnf_error:
                await interaction.followup.send(f"Failed to roll back: {fnf_error}")
                print(f"Error restoring game ID {game_id} ({game_info['game_name']}): {fnf_error}")
            except Exception as e:
                await interaction.followup.send(f"Failed to roll back: {e}")
                print(f"Unexpected error restoring game ID {game_id} ({game_info['game_name']}): {e}")



        @self.tree.command(
            name="force-host",
            description="Forces the game to start hosting immediately.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def force_host(interaction: discord.Interaction):
            """Forces the game associated with the current channel to start hosting."""
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer()

            # Get the game ID associated with the current channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            # Fetch game information
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found in the database.")
                return

            # Check if the game is currently running
            if not game_info["game_running"]:
                await interaction.followup.send("The game is not currently running. Cannot force it to host.")
                return

            # Attempt to write the domcmd file to force hosting
            try:
                await self.nidhogg.force_game_host(game_id, self.config, self.db_instance)
                await interaction.followup.send(f"Game ID {game_id} ({game_info['game_name']}) has been successfully forced to host. Please wait while turn proceeses.")
                print(f"Game ID {game_id} ({game_info['game_name']}) successfully forced to host.")
            except Exception as e:
                await interaction.followup.send(f"Failed to force host: {e}")
                print(f"Error forcing game ID {game_id} ({game_info['game_name']}) to host: {e}")




        @self.tree.command(
            name="kill",
            description="Kills the game lobby process.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        @require_game_owner_or_admin(self.config)
        async def kill_game_lobby(interaction: discord.Interaction):
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer()

            try:
                # Get the game ID from the channel ID
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if game_id is None:
                    await interaction.followup.send("No game lobby is associated with this channel.")
                    return

                # Delegate the killing of the process to nidhogg
                try:
                    await self.nidhogg.kill_game_lobby(game_id, self.db_instance)
                    await interaction.followup.send(f"Game lobby process for game ID: {game_id} has been killed.")
                except ValueError as ve:
                    await interaction.followup.send(str(ve))
                except Exception as e:
                    await interaction.followup.send(f"An error occurred while attempting to kill the game lobby: {e}")

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}")



        @self.tree.command(
            name="get-version",
            description="Fetches the version of the Dominions server executable.",
            guild=discord.Object(id=self.guild_id)  # Replace with your actual guild ID
        )
        async def get_version(interaction: discord.Interaction):
            """
            Fetch the version of the Dominions server executable and return it.
            """
            try:
                # Acknowledge the interaction to prevent timeout
                await interaction.response.defer(ephemeral=True)

                # Fetch the version information
                version_info = self.nidhogg.get_version()

                # Send the version information as a follow-up response
                await interaction.followup.send(f"Dominions Server Version: `{version_info}`", ephemeral=True)
            except Exception as e:
                # Handle any exceptions and respond with an error message
                await interaction.followup.send(f"Error fetching version: {e}", ephemeral=True)


        # @self.tree.command(
        #     name="echo",
        #     description="Echos back text",
        #     guild=discord.Object(id=self.guild_id)
        # )
        # @require_bot_channel(self.config)
        # async def echo_command(interaction: discord.Interaction, echo_text:str, your_name:str):
        #     await interaction.response.send_message(echo_text + your_name)

        @self.tree.command(
            name="upload-map",
            description="Upload your map.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def map_upload_command(interaction: discord.Interaction, file: discord.Attachment):
            try:
                # Read the file data as a binary blob
                file_data = await file.read()

                # Pass the file data, filename, and config to bifrost
                result = await bifrost.handle_map_upload(file_data, file.filename, self.config)

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
        @require_bot_channel(self.config)
        async def mod_upload_command(interaction: discord.Interaction, file: discord.Attachment):
            try:
                # Read the file data as a binary blob
                file_data = await file.read()

                # Pass the file data, filename, and config to bifrost
                result = await bifrost.handle_mod_upload(file_data, file.filename, self.config)

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
                        min_values=0 if multi_select else 1,  # Allow zero selection if multi_select is True
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
            name="select-mods",
            description="Select mods for game.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_bot_channel(self.config)
        async def select_mods_dropdown(interaction: discord.Interaction):

            # Get the current game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel.id)
            if game_id is None:
                await interaction.response.send_message("This channel is not associated with any active game.", ephemeral=True)
                return

            # Check if the game has already started or is running
            game_info = await self.db_instance.get_game_info(game_id)
            if game_info:
                if game_info.get("game_started"):
                    await interaction.response.send_message("The game has already started. You cannot change the mods.", ephemeral=True)
                    return
                if game_info.get("game_running"):
                    await interaction.response.send_message("The game is currently running. You cannot change the mods.", ephemeral=True)
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
                # Update mods with the selected ones
                await self.db_instance.update_mods(game_id, mods_locations)
                await interaction.followup.send(f"You selected: {', '.join(selected_mods)}", ephemeral=True)
            else:
                # Clear all mods if no selection was made
                await self.db_instance.update_mods(game_id, [])
                await interaction.followup.send("No mods selected. All mods have been removed.", ephemeral=True)





        @self.tree.command(
            name="select-map",
            description="Select map for game.",
            guild=discord.Object(id=self.guild_id),
        )
        @require_bot_channel(self.config)
        async def select_map_dropdown(interaction: discord.Interaction):

            # Get the current game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel.id)
            if game_id is None:
                await interaction.response.send_message("This channel is not associated with any active game.", ephemeral=True)
                return

            # Check if the game has already started
            game_info = await self.db_instance.get_game_info(game_id)
            if game_info and game_info.get("game_started"):
                await interaction.response.send_message("The game has already started. You cannot change the map.", ephemeral=True)
                return

            # Fetch the preselected map
            current_map = await self.db_instance.get_map(game_id)

            # Fetch available maps
            maps = bifrost.get_maps(config=self.config)

            # Add default options
            default_maps = [
                {"name": "Vanilla Small 10", "location": "vanilla_10", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
                {"name": "Vanilla Medium 15", "location": "vanilla_15", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
                {"name": "Vanilla Large 20", "location": "vanilla_20", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
                {"name": "Vanilla Enormous 25", "location": "vanilla_25", "yggemoji": ":dom6:", "yggdescr": "Small Lakes & One Cave"},
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
            name="list-active-games",
            description="Lists all active games.",
            guild=discord.Object(id=self.guild_id)  # Replace with your actual guild ID
        )
        @require_bot_channel(self.config)
        async def list_active_games(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)  # Acknowledge the interaction

            try:
                active_games = await self.db_instance.get_active_games()

                if not active_games:
                    await interaction.followup.send("There are currently no active games.", ephemeral=True)
                    return

                # Format the list of active games
                game_list = "\n".join(
                    f"- **{game['game_name']}** (ID: {game['game_id']}, Era: {game['game_era']}, Owner: {game['game_owner']}, "
                    f"Created: {game['creation_date']}, Version: {game['creation_version']})"
                    for game in active_games
                )

                # Send the active game list
                await interaction.followup.send(f"**Active Games:**\n{game_list}", ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)




    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        print("Trying to sync discord bot commands")

        try:
            await self.tree.sync(guild=discord.Object(id=self.guild_id))
            print("Discord commands synced!")
        except Exception as e:
            print(f"Error syncing commands: {e}")

        if self.bot_ready_signal:
            self.bot_ready_signal.set()

    # async def on_message(self, message):
    #     if message.author == self.user:
    #         return 
    #     print(f'Message from {message.author}: {message.content} in {message.channel}')
    

