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
    """Decorator to restrict commands to bot-specific channels or channels linked to active games."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client  # Access the bot instance from the interaction
            # Combine active game channels with bot_channels
            active_game_channels = await bot.db_instance.get_active_game_channels()
            allowed_channels = set(active_game_channels + list(map(int, config.get("bot_channels", []))))

            # If allowed_channels is empty, allow any channel
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


    async def setup_hook(self):
        
        @self.tree.command(
            name="new-game",
            description="Creates a brand new game",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
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
                # Defer interaction to prevent timeout
                await interaction.response.defer(ephemeral=True)

                # Validate inputs
                era_map = {"Early": 1, "Middle": 2, "Late": 3}
                game_era_value = era_map[game_era]

                research_random_map = {"Even Spread": 1, "Random": 0}
                research_random_value = research_random_map[research_random]

                event_rarity_map = {"Common": 1, "Rare": 2}
                event_rarity_value = event_rarity_map[event_rarity]

                disicples_map = {"False": 0, "True": 1}
                disicples_value = disicples_map[disicples]

                story_events_map = {"None": 0, "Some": 1, "Full": 2}
                story_events_value = story_events_map[story_events]

                no_going_ai_map = {"True": 0, "False": 1}
                no_going_ai_value = no_going_ai_map[no_going_ai]

                thrones_value = ",".join(map(str, [lv1_thrones, lv2_thrones, lv3_thrones]))

                if points_to_win < 1 or points_to_win > lv1_thrones + lv2_thrones * 2 + lv3_thrones * 3:
                    await interaction.followup.send("Invalid points to win.")
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


                # Create a role for the game
                role_name = f"{game_name} player"
                guild = interaction.guild
                role = discord.utils.get(guild.roles, name=role_name)

                if not role:
                    role = await guild.create_role(name=role_name)
                    print(f"Role '{role_name}' created successfully.")

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
                        game_started=False,
                        game_mods="[]",
                        channel_id=new_channel_id,
                        role_id=role.id,  # Store the role ID
                        game_active=True,
                        process_pid=None,
                        game_owner=interaction.user.name,
                        creation_version=self.nidhogg.get_version()
                    )

                    await self.db_instance.create_timer(
                        game_id=new_game_id,
                        timer_default=86400,
                        timer_length=86400,
                        timer_running=False,
                        remaining_time=86400
                    )

                    await interaction.followup.send(f"Game '{game_name}' created successfully!")
                except ValueError as e:
                    await new_channel.delete()
                    await interaction.followup.send(str(e))
                except Exception as e:
                    await new_channel.delete()
                    await interaction.followup.send(f"Unexpected error: {e}")
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

        
        @new_game_command.autocomplete("no_going_ai")
        async def no_going_ai_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = ["False", "True"]
            matches = options if not current else [option for option in options if current.lower() in option.lower()]

            # Convert to app_commands.Choice objects
            suggestions = [app_commands.Choice(name=option, value=option) for option in matches]

            try:
                # Send the autocomplete suggestions
                await interaction.response.autocomplete(suggestions[:25])
            except Exception as e:
                print(f"Error sending autocomplete response: {e}")

        @new_game_command.autocomplete("disicples")
        async def disicples_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = ["False", "True"]
            matches = options if not current else [option for option in options if current.lower() in option.lower()]

            # Convert to app_commands.Choice objects
            suggestions = [app_commands.Choice(name=option, value=option) for option in matches]

            try:
                # Send the autocomplete suggestions
                await interaction.response.autocomplete(suggestions[:25])
            except Exception as e:
                print(f"Error sending autocomplete response: {e}")


        @new_game_command.autocomplete("story_events")
        async def story_events_autocomplete(interaction: discord.Interaction, current: str):
            # Provide predefined options
            options = ["None", "Some", "Full"]
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
        @require_bot_channel(self.config)
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
            success = await self.nidhogg.launch_game_lobby(game_id, self.db_instance)
            if success:
                await interaction.followup.send(f"Game lobby launched for game {game_info['game_name']} ID: {game_id}.")
            else:
                await interaction.followup.send(f"Failed to launch game lobby for game {game_info['game_name']} ID: {game_id}.")




        @self.tree.command(
            name="start_game",
            description="Starts a fresh game.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def start_game(interaction: discord.Interaction):
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer()
            print(f"\nTrying to start game in channel {interaction.channel}.")

            # Get the game ID associated with the channel
            game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
            
            # Reject if no game ID is found
            if game_id is None:
                await interaction.followup.send("No game lobby is associated with this channel.")
                return
            
            game_info = await self.db_instance.get_game_info(game_id)

            # Reject if the map is missing
            if not game_info["game_map"]:
                await interaction.followup.send("Map missing. Please use /select_map.")
                print(f"\nFailed to launch game. Map missing in {interaction.channel}.")
                return
            
            # Reject if the game is not running
            if not game_info["game_running"]:
                await interaction.followup.send("Game is not running. Please use /launch.")
                print(f"\nFailed to start game. Game not running in {interaction.channel}.")
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
                await interaction.followup.send(f"Game ID {game_id} has been successfully started. Please wait a few seconds.")
            except Exception as e:
                await interaction.followup.send(f"Failed to force the game to start: {e}")
                return
            
            # Set game started to true
            try:
                await self.db_instance.set_game_started_value(game_id, True)
                print(f"Game ID {game_id} has been marked as started.")
            except Exception as e:
                await interaction.followup.send(f"Failed to set game started state in the database: {e}")
                return



        @self.tree.command(
            name="restart_game_to_lobby",
            description="Restarts the game back to the lobby state.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def restart_game_to_lobby(interaction: discord.Interaction):
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
            
            success = await self.nidhogg.launch_game_lobby(game_id, self.db_instance)
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

            await interaction.followup.send(f"Game ID {game_id} has been successfully restarted back to the lobby.", ephemeral=True)

        

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
                nation_files = await bifrost.get_2h_files_by_game_id(game_id, self.db_instance, self.config)
                valid_nations = [os.path.splitext(os.path.basename(nation_file))[0] for nation_file in nation_files]

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

                # Retrieve the list of `.2h` files for the game
                files = await bifrost.get_2h_files_by_game_id(game_id, self.db_instance, self.config)
                valid_nations = [os.path.basename(file).replace(".2h", "") for file in files]

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
                
                # Get the `.2h` files
                nation_files = await bifrost.get_2h_files_by_game_id(game_id, self.db_instance, self.config)
                valid_nations = [os.path.splitext(os.path.basename(nation_file))[0] for nation_file in nation_files]

                # Get claimed nations
                claimed_nations = await self.db_instance.get_claimed_nations(game_id)

                # Build the response
                embed = discord.Embed(title="Pretender Nations", color=discord.Color.blue())
                #embed.add_field(name="Game ID", value=str(game_id), inline=False)

                for nation in valid_nations:
                    if nation in claimed_nations:
                        claimants = claimed_nations[nation]
                        resolved_claimants = []
                        for player_id in claimants:
                            user = interaction.guild.get_member(int(player_id)) or await interaction.client.fetch_user(int(player_id))
                            if user:
                                resolved_claimants.append(user.display_name)
                            else:
                                resolved_claimants.append(f"Unknown ({player_id})")  # Fallback if user not found

                        player_names = ", ".join(resolved_claimants)
                        embed.add_field(
                            name=nation,
                            value=f"Claimed by: {player_names}",
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





        # @self.tree.command(
        #     name="clear-claims",
        #     description="Clears all player claims for the current game.",
        #     guild=discord.Object(id=self.guild_id)
        # )
        # @require_bot_channel(self.config)
        # @require_game_admin(self.config)
        # async def clear_claims(interaction: discord.Interaction):
        #     """Clears all claims for a game and removes associated roles."""
        #     try:
        #         print("[DEBUG] clear-claims command invoked")  # Initial debug log

        #         # Defer response to prevent timeout
        #         await interaction.response.defer(ephemeral=True)
        #         print("[DEBUG] Interaction deferred")

        #         # Get the game ID associated with the current channel
        #         game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
        #         if not game_id:
        #             await interaction.followup.send("No game is associated with this channel.")
        #             print("[DEBUG] No game ID found for the channel")
        #             return
        #         print(f"[DEBUG] Retrieved game ID: {game_id}")

        #         # Get the associated role and game information
        #         game_info = await self.db_instance.get_game_info(game_id)
        #         if not game_info:
        #             await interaction.followup.send("Game information not found in the database.", ephemeral=True)
        #             print("[DEBUG] Game information not found in the database")
        #             return
        #         print(f"[DEBUG] Retrieved game information: {game_info}")

        #         role_id = game_info.get("role_id")
        #         if not role_id:
        #             await interaction.followup.send("No role is associated with this game.", ephemeral=True)
        #             print("[DEBUG] No role ID found for the game")
        #             return
        #         print(f"[DEBUG] Retrieved role ID: {role_id}")

        #         # Get guild and role information
        #         guild = interaction.guild
        #         if not guild:
        #             await interaction.followup.send("Unable to fetch guild information.", ephemeral=True)
        #             print("[DEBUG] Guild information not found")
        #             return

        #         role = discord.utils.get(guild.roles, id=int(role_id))
        #         if not role:
        #             await interaction.followup.send("The associated role does not exist.", ephemeral=True)
        #             print("[DEBUG] Role not found in the guild")
        #             return
        #         print(f"[DEBUG] Role found: {role.name}")

        #         # Fetch all players for the game
        #         players = await self.db_instance.get_players_by_game(game_id)
        #         if not players:
        #             await interaction.followup.send("No players found for this game.", ephemeral=True)
        #             print("[DEBUG] No players found for the game")
        #             return
        #         print(f"[DEBUG] Found {len(players)} players for the game")

        #         # Remove the role from all members with it
        #         for player in players:
        #             player_id = player["player_id"]
        #             member = guild.get_member(int(player_id))
        #             if member and role in member.roles:
        #                 try:
        #                     await member.remove_roles(role)
        #                     print(f"[DEBUG] Removed role from member: {member.name}")
        #                 except Exception as e:
        #                     print(f"[DEBUG] Failed to remove role from member {member.name}: {e}")

        #         # Clear claims from the database
        #         await self.db_instance.clear_players(game_id)
        #         print("[DEBUG] Cleared all player claims from the database")

        #         # Respond to the interaction
        #         await interaction.followup.send(f"All claims for game '{game_info['game_name']}' have been cleared.")
        #         print("[DEBUG] Interaction response sent")

        #     except Exception as e:
        #         # Handle unexpected exceptions
        #         print(f"[DEBUG] Error in clear-claims command: {e}")
        #         await interaction.followup.send(f"Failed to clear claims: {e}")









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
                await interaction.followup.send("Game information not found in the database.", ephemeral=True)
                return

            try:
                raw_status = await self.nidhogg.query_game_status(game_id, self.db_instance)
                timer_table = await self.db_instance.get_game_timer(game_id)

                # Parse the response
                lines = raw_status.split("\n")
                game_name = lines[2].split(":")[1].strip()
                turn = lines[4].split(":")[1].strip()
                #time_left = lines[5].split(":")[1].strip()
                time_left = timer_table["remaining_time"]
                if time_left is None:
                    raise ValueError("time_left cannot be None")

                #caluclate turn date

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
                    #description=f"**Name**: {game_name}\n**Turn**: {turn}\n**Time Left**: {time_left}\n**Turn",
                    description=f"Next turn:\n{discord_timestamp} in {descriptive_time_breakdown(time_left)}",
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
            name="force-host",
            description="Forces the game to start hosting immediately.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def force_host(interaction: discord.Interaction):
            """Forces the game associated with the current channel to start hosting."""
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

            # Check if the game is currently running
            if not game_info["game_running"]:
                await interaction.followup.send("The game is not currently running. Cannot force it to host.", ephemeral=True)
                return

            # Attempt to write the domcmd file to force hosting
            try:
                await bifrost.force_game_host(game_id, self.config, self.db_instance)
                await interaction.followup.send(f"Game ID {game_id} ({game_info['game_name']}) has been successfully forced to host.", ephemeral=True)
                print(f"Game ID {game_id} ({game_info['game_name']}) successfully forced to host.")
            except Exception as e:
                await interaction.followup.send(f"Failed to force the game to start: {e}", ephemeral=True)
                print(f"Error forcing game ID {game_id} ({game_info['game_name']}) to host: {e}")




        @self.tree.command(
            name="kill",
            description="Kills the game lobby process.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
        async def kill_game_lobby(interaction: discord.Interaction):
            # Acknowledge interaction to prevent timeout
            await interaction.response.defer(ephemeral=True)

            try:
                # Get the game ID from the channel ID
                game_id = await self.db_instance.get_game_id_by_channel(interaction.channel_id)
                if game_id is None:
                    await interaction.followup.send("No game lobby is associated with this channel.", ephemeral=True)
                    return

                # Delegate the killing of the process to nidhogg
                try:
                    await self.nidhogg.kill_game_lobby(game_id, self.db_instance)
                    await interaction.followup.send(f"Game lobby process for game ID: {game_id} has been killed.", ephemeral=True)
                except ValueError as ve:
                    await interaction.followup.send(str(ve), ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"An error occurred while attempting to kill the game lobby: {e}", ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)



        @self.tree.command(
            name="get_version",
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




        @self.tree.command(
            name="check-status",
            description="Checks server status",
            guild=discord.Object(id=self.guild_id) 
        )
        @require_bot_channel(self.config)
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
        @require_bot_channel(self.config)
        async def echo_command(interaction: discord.Interaction, echo_text:str, your_name:str):
            await interaction.response.send_message(echo_text + your_name)

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
        @require_bot_channel(self.config)
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
        @require_bot_channel(self.config)
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
        @require_bot_channel(self.config)
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
            name="list_active_games",
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




        @self.tree.command(
            name="dropdown_test",
            description="Test the generic dropdown menu.",
            guild=discord.Object(id=self.guild_id)
        )
        @require_bot_channel(self.config)
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
    

