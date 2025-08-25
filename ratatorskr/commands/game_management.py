"""
Game management and control commands - creating, launching, editing, and controlling games.
"""

import asyncio
import discord
from discord import app_commands
from bifrost import bifrost
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ..decorators import require_bot_channel, require_primary_bot_channel, require_game_channel, require_game_host_or_admin, require_game_owner_or_admin, require_game_admin


def register_game_management_commands(bot):
    """Register all game management commands to the bot's command tree."""
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] Starting command registration...")
    
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] Registering new-game command...")
    @bot.tree.command(
        name="new-game",
        description="Creates a brand new game",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    @require_game_host_or_admin(bot.config)
    async def new_game_command(
        interaction: discord.Interaction,
        game_name: str,
        game_type: str,
        game_era: str,
        research_random: str,
        global_slots: int,
        event_rarity: str,
        disicples: str,
        story_events: str,
        no_going_ai: str,
        player_control_timers: str,
        default_timer: float,
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
            valid_game_types = ["Casual", "Blitz"]
            if game_type not in valid_game_types:
                await interaction.followup.send(f"Invalid game type. Choose from: {', '.join(valid_game_types)}", ephemeral=True)
                return

            era_map = {"Early": 1, "Middle": 2, "Late": 3}
            research_random_map = {"Even Spread": 1, "Random": 0}
            event_rarity_map = {"Common": 1, "Rare": 2}
            disicples_map = {"False": 0, "True": 1}
            story_events_map = {"None": 0, "Some": 1, "Full": 2}
            no_going_ai_map = {"True": 0, "False": 1}
            player_control_timers_map = {"True": 1, "False": 0}

            game_era_value = era_map[game_era]
            research_random_value = research_random_map[research_random]
            event_rarity_value = event_rarity_map[event_rarity]
            disicples_value = disicples_map[disicples]
            story_events_value = story_events_map[story_events]
            no_going_ai_value = no_going_ai_map[no_going_ai]
            player_control_timers_value = player_control_timers_map[player_control_timers]

            thrones_value = ",".join(map(str, [lv1_thrones, lv2_thrones, lv3_thrones]))

            if points_to_win < 1 or points_to_win > lv1_thrones + lv2_thrones * 2 + lv3_thrones * 3:
                await interaction.followup.send("Invalid points to win.", ephemeral=True)
                return

            # Calculate timer value based on game type (blitz vs normal, round to nearest second)
            if game_type.lower() == "blitz":
                timer_seconds = round(default_timer * 60)  # Minutes for blitz games
            else:
                timer_seconds = round(default_timer * 3600)  # Hours for normal games

            # Fetch guild and category
            guild = interaction.client.get_guild(bot.guild_id)
            if not guild:
                guild = await interaction.client.fetch_guild(bot.guild_id)

            category = await guild.fetch_channel(bot.category_id)
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
                new_game_id = await bot.db_instance.create_game(
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
                    creation_version=bot.nidhogg.get_version(),
                    max_active_games = bot.config["max_active_games"],
                    player_control_timers=bool(player_control_timers_value)
                )

                # Create the timer for the new game
                await bot.db_instance.create_timer(
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

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] new-game command function defined, adding autocomplete...")
    @new_game_command.autocomplete("game_type")
    async def game_type_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Casual", "Blitz"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] game_type autocomplete added")
    @new_game_command.autocomplete("game_era")
    async def game_era_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Early", "Middle", "Late"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] game_era autocomplete added")
    @new_game_command.autocomplete("research_random")
    async def research_random_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Even Spread", "Random"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] research_random autocomplete added")
    @new_game_command.autocomplete("event_rarity")
    async def event_rarity_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Common", "Rare"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] event_rarity autocomplete added")
    @new_game_command.autocomplete("disicples")
    async def disicples_autocomplete(interaction: discord.Interaction, current: str):
        options = ["False", "True"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] disicples autocomplete added")
    @new_game_command.autocomplete("story_events")
    async def story_events_autocomplete(interaction: discord.Interaction, current: str):
        options = ["None", "Some", "Full"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] story_events autocomplete added")
    @new_game_command.autocomplete("no_going_ai")
    async def no_going_ai_autocomplete(interaction: discord.Interaction, current: str):
        options = ["False", "True"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]
    
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] no_going_ai autocomplete added")
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
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] global_slots autocomplete added")
    @new_game_command.autocomplete("player_control_timers")
    async def player_control_timers_autocomplete(interaction: discord.Interaction, current: str):
        # Simple static choices without any filtering or complex logic
        return [
            app_commands.Choice(name="True", value="True"),
            app_commands.Choice(name="False", value="False")
        ]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] player_control_timers autocomplete added")
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] new-game command registered successfully")
    
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] Registering edit-game command...")
    @bot.tree.command(
        name="edit-game", 
        description="Edits a game",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
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
        player_control_timers: str,
        default_timer: float,
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
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("This channel is not associated with an active game.", ephemeral=True)
                return

            # Fetch game details
            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send(f"No game found with ID {game_id}.", ephemeral=True)
                return

            # Reject edits if the game has already started
            if game_info["game_started"]:
                await interaction.followup.send(f"Cannot edit game properties. The game in this channel has already started.", ephemeral=True)
                return

            # Validation logic for fields
            valid_game_types = ["Casual", "Blitz"]
            if game_type not in valid_game_types:
                await interaction.followup.send("Invalid value for game_type. Allowed values: Casual, Blitz.", ephemeral=True)
                return

            era_map = {"Early": 1, "Middle": 2, "Late": 3}
            if game_era not in era_map:
                await interaction.followup.send("Invalid value for game_era. Allowed values: Early, Middle, Late.", ephemeral=True)
                return
            game_era_value = era_map[game_era]
            
            player_control_timers_map = {"True": 1, "False": 0}
            if player_control_timers not in player_control_timers_map:
                await interaction.followup.send("Invalid value for player_control_timers. Allowed values: True, False.", ephemeral=True)
                return
            player_control_timers_value = player_control_timers_map[player_control_timers]

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

            # Calculate timer value based on game type (blitz vs normal, round to nearest second)
            if game_type.lower() == "blitz":
                timer_seconds = round(default_timer * 60)  # Minutes for blitz games
            else:
                timer_seconds = round(default_timer * 3600)  # Hours for normal games

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
                "requiredap": points_to_win,
                "player_control_timers": bool(player_control_timers_value)
            }

            for property_name, new_value in updates.items():
                await bot.db_instance.update_game_property(game_id, property_name, new_value)

            # Update the timer default value
            await bot.db_instance.update_timer_default(game_id, timer_seconds)

            await interaction.followup.send(f"Successfully updated the game in this channel.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @edit_game_command.autocomplete("game_type")
    async def edit_game_type_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Casual", "Blitz"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("game_era")
    async def edit_game_era_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Early", "Middle", "Late"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("research_random")
    async def edit_research_random_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Even Spread", "Random"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("global_slots")
    async def edit_global_slots_autocomplete(interaction: discord.Interaction, current: str):
        options = [5, 3, 4, 6, 7, 8, 9]
        matches = [str(option) for option in options if current.isdigit() and current in str(option)]
        if not matches:
            matches = [str(option) for option in options]
        return [app_commands.Choice(name=match, value=int(match)) for match in matches]

    @edit_game_command.autocomplete("event_rarity")
    async def edit_event_rarity_autocomplete(interaction: discord.Interaction, current: str):
        options = ["Common", "Rare"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("disicples")
    async def edit_disicples_autocomplete(interaction: discord.Interaction, current: str):
        options = ["False", "True"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("story_events")
    async def edit_story_events_autocomplete(interaction: discord.Interaction, current: str):
        options = ["None", "Some", "Full"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("no_going_ai")
    async def edit_no_going_ai_autocomplete(interaction: discord.Interaction, current: str):
        options = ["False", "True"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @edit_game_command.autocomplete("player_control_timers")
    async def edit_player_control_timers_autocomplete(interaction: discord.Interaction, current: str):
        options = ["True", "False"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] edit-game command registered successfully")
    
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] Registering launch command...")
    @bot.tree.command(
        name="launch",
        description="Launches game lobby.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def launch_command(interaction: discord.Interaction):
        # Acknowledge interaction to prevent timeout
        await interaction.response.defer()  # Ensure the initial defer is also ephemeral
        print(f"\nTrying to launch game in channel {interaction.channel}.")
        # Get the game ID and game info
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return
        game_info = await bot.db_instance.get_game_info(game_id)
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
        success = await bot.nidhogg.launch_game_lobby(game_id, bot.db_instance, bot.config)
        if success:
            await interaction.followup.send(f"Game lobby launched for game {game_info['game_name']} ID: {game_id}.")
        else:
            await interaction.followup.send(f"Failed to launch game lobby for game {game_info['game_name']} ID: {game_id}.")

    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] launch command registered successfully")
    
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] Registering start-game command...")
    @bot.tree.command(
        name="start-game",
        description="Forces a game to generate a new turn at any time.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def start_game_command(interaction: discord.Interaction):
        # Acknowledge interaction to prevent timeout
        await interaction.response.defer()
        print(f"\nTrying to start game in channel {interaction.channel}.")

        # Get the game ID associated with the channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)

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
            nations_with_2h_files = await bifrost.get_nations_with_2h_files(game_info["game_name"], bot.config)
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
            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
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
            await bifrost.backup_2h_files(game_id, game_info["game_name"], config=bot.config)
            print(f"Backup completed for game ID {game_id}.")
        except Exception as e:
            await interaction.followup.send(f"Failed to backup game files: {e}")
            return

        # Set game_start_attempted flag to begin monitoring for turn 1 transition
        await bot.db_instance.set_game_start_attempted(game_id, True)
        if bot.config and bot.config.get("debug", False):
            if bot.config and bot.config.get("debug", False):
                print(f"[DEBUG] Set game_start_attempted=True for game ID {game_id}")

        # Initialize chess clock times for all players when start-game is used
        chess_clock_active = game_info.get("chess_clock_active", False)
        if chess_clock_active:
            starting_time = game_info.get("chess_clock_starting_time", 0)
            if starting_time > 0:
                try:
                    async with bot.db_instance.connection.execute(
                        "UPDATE players SET chess_clock_time_remaining = ? WHERE game_id = ? AND chess_clock_time_remaining = 0",
                        (starting_time, game_id)
                    ) as cursor:
                        await bot.db_instance.connection.commit()
                        updated_count = cursor.rowcount
                        if bot.config and bot.config.get("debug", False):
                            if bot.config and bot.config.get("debug", False):
                                print(f"[DEBUG] Initialized chess clock for {updated_count} players with {starting_time} seconds")
                except Exception as e:
                    print(f"[ERROR] Failed to initialize chess clock times: {e}")

        # Use Nidhogg to force host via domcmd
        try:
            await bot.nidhogg.force_game_host(game_id, bot.config, bot.db_instance)
            await bot.nidhogg.force_game_host(game_id, bot.config, bot.db_instance)
            await interaction.followup.send(f"Game start command has been executed for game ID {game_id}. Please wait until turn 1 notice before joining game.")
        except Exception as e:
            await interaction.followup.send(f"Failed to force the game to start: {e}")
            return

        # NOTE: game_started and timer will be set to True when turn 1 notification is sent (actual game start)

    @bot.tree.command(
        name="restart-game-to-lobby",
        description="Restarts the game back to the lobby state.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def restart_game_to_lobby_command(interaction: discord.Interaction, confirm_game_name: str):
        """Restarts the game associated with the current channel back to the lobby state."""
        # Acknowledge interaction to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.", ephemeral=True)
            return

        # Fetch game information
        game_info = await bot.db_instance.get_game_info(game_id)
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
            await bot.nidhogg.kill_game_lobby(game_id, bot.db_instance)
            print(f"Game process for game ID {game_id} has been killed.")
        except Exception as e:
            await interaction.followup.send(f"Failed to kill the game process: {e}", ephemeral=True)
            return

        # Restore .2h files from the backup
        try:
            await bifrost.restore_2h_files(game_id, game_info["game_name"], config=bot.config)
            print(f"Backup files restored for game ID {game_id}.")
        except Exception as e:
            await interaction.followup.send(f"Failed to restore game files: {e}", ephemeral=True)
            return
        
        await asyncio.sleep(5)
        success = await bot.nidhogg.launch_game_lobby(game_id, bot.db_instance, bot.config)
        if success:
            await interaction.followup.send(f"Game lobby launched for game ID: {game_id}.")
        else:
            await interaction.followup.send(f"Failed to launch game lobby for game ID: {game_id}.")

        # Reset both game_started and game_start_attempted fields in the database
        try:
            await bot.db_instance.set_game_started_value(game_id, False)
            await bot.db_instance.set_game_start_attempted(game_id, False)
            print(f"Game ID {game_id} has been reset to the lobby state (both flags set to false).")
        except Exception as e:
            await interaction.followup.send(f"Failed to reset game to lobby state in the database: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"Game ID {game_id} has been successfully restarted back to the lobby.")

    # Game Control Commands
    @bot.tree.command(
        name="pause",
        description="Toggles the game timer pause state.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def pause_command(interaction: discord.Interaction):
        await interaction.response.defer()
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return
        
        # Get current timer state from gameTimers table
        timer_info = await bot.db_instance.get_timer_info(game_id)
        if not timer_info:
            await interaction.followup.send("No timer found for this game.")
            return
            
        current_running = timer_info.get('timer_running', False)
        new_running = not current_running
        
        success = await bot.db_instance.set_timer_running(game_id, new_running)
        if success:
            state = "unpaused" if new_running else "paused"
            await interaction.followup.send(f"Game timer has been {state}.")
        else:
            await interaction.followup.send("Failed to change the game timer state.")

    @bot.tree.command(
        name="end-game",
        description="Ends the game but keeps the lobby active.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def end_game_command(interaction: discord.Interaction, game_winner: str, confirm_game_name: str):
        await interaction.response.defer()
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return

        if confirm_game_name != game_info["game_name"]:
            await interaction.followup.send(
                f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
            )
            return
        
        try:
            # Try to kill the game process, but don't fail if it's already dead
            try:
                await bot.nidhogg.kill_game_lobby(game_id, bot.db_instance)
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Successfully killed game process for game {game_id}")
            except Exception as kill_error:
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Failed to kill game process (likely already dead): {kill_error}")
                # Continue anyway - the game process might already be dead
            
            await bot.db_instance.update_game_running(game_id, False)
            await bot.db_instance.set_timer_running(game_id, False)
            await bot.db_instance.update_game_property(game_id, "game_active", False)
            
            if game_winner == "-666":
                winner_text = "Everybody Lost"
                winner_value = -666
            else:
                winner_value = int(game_winner)
                try:
                    user = interaction.guild.get_member(winner_value) or await interaction.client.fetch_user(winner_value)
                    winner_text = user.display_name if user else f"Player {game_winner}"
                except:
                    winner_text = f"Player {game_winner}"
            
            import aiosqlite
            query = "UPDATE games SET game_winner = ? WHERE game_id = ?"
            async with bot.db_instance.connection.execute(query, (winner_value, game_id)) as cursor:
                await bot.db_instance.connection.commit()
            
            await interaction.followup.send(f"Game {game_info['game_name']} has been successfully ended. Winner: {winner_text}.")
        except Exception as e:
            await interaction.followup.send(f"Failed to end the game: {e}")

    @end_game_command.autocomplete("game_winner")
    async def game_winner_autocomplete(interaction: discord.Interaction, current: str):
        try:
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            choices = [discord.app_commands.Choice(name="Everybody Lost", value="-666")]
            
            try:
                players = await bot.db_instance.get_players_in_game(game_id)
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Autocomplete found {len(players) if players else 0} players for game {game_id}")
                    if players:
                        if bot.config and bot.config.get("debug", False):
                            print(f"[DEBUG] Players: {players}")
                
                seen_players = set()
                for player in players:
                    player_id = player["player_id"]
                    nation_name = player["nation"]
                    if bot.config and bot.config.get("debug", False):
                        if bot.config and bot.config.get("debug", False):
                            print(f"[DEBUG] Processing player {player_id} with nation {nation_name}")
                    
                    if player_id in seen_players:
                        if bot.config and bot.config.get("debug", False):
                            if bot.config and bot.config.get("debug", False):
                                print(f"[DEBUG] Skipping duplicate player {player_id}")
                        continue
                    
                    seen_players.add(player_id)
                    try:
                        user = interaction.guild.get_member(int(player_id)) or await interaction.client.fetch_user(int(player_id))
                        if user:
                            choice_name = f"{user.display_name}"
                            choices.append(discord.app_commands.Choice(name=choice_name, value=player_id))
                            if bot.config and bot.config.get("debug", False):
                                if bot.config and bot.config.get("debug", False):
                                    print(f"[DEBUG] Added choice: {choice_name} with value: {player_id}")
                        else:
                            choice_name = f"Unknown ({player_id})"
                            choices.append(discord.app_commands.Choice(name=choice_name, value=player_id))
                            if bot.config and bot.config.get("debug", False):
                                if bot.config and bot.config.get("debug", False):
                                    print(f"[DEBUG] Added unknown choice: {choice_name} with value: {player_id}")
                    except ValueError as e:
                        if bot.config and bot.config.get("debug", False):
                            if bot.config and bot.config.get("debug", False):
                                print(f"[DEBUG] ValueError processing player {player_id}: {e}")
                        continue
                    except Exception as e:
                        if bot.config and bot.config.get("debug", False):
                            if bot.config and bot.config.get("debug", False):
                                print(f"[DEBUG] Exception adding choice for player {player_id}: {e}")
                        continue
            except Exception as e:
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Exception in autocomplete: {e}")
                pass

            if current:
                choices = [choice for choice in choices if current.lower() in choice.name.lower()]
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Filtered choices for '{current}': {len(choices)} choices")
            
            if bot.config and bot.config.get("debug", False):
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] Returning {len(choices)} choices: {[choice.name for choice in choices]}")
            
            return choices[:25]
        except Exception:
            return []

    @bot.tree.command(
        name="kill",
        description="Kills the game process.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def kill_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.", ephemeral=True)
            return
        
        try:
            await bot.nidhogg.kill_game_lobby(game_id, bot.db_instance)
            await interaction.followup.send(f"Game process for ID {game_id} has been killed.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to kill game process: {e}", ephemeral=True)

    @bot.tree.command(
        name="force-host",
        description="Forces the game to host the next turn immediately.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def force_host_command(interaction: discord.Interaction):
        await interaction.response.defer()
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return
        
        try:
            await bot.nidhogg.force_game_host(game_id, bot.config, bot.db_instance)
            await interaction.followup.send(f"Game ID {game_id} has been forced to host.")
        except Exception as e:
            await interaction.followup.send(f"Failed to force host: {e}")

    @bot.tree.command(
        name="player-extension-rules",
        description="Toggle whether players can extend timers or only owner/admin can.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def player_extension_rules_command(interaction: discord.Interaction, allow_players: str):
        """Toggle the player_control_timers setting for the current game."""
        await interaction.response.defer()
        
        # Get the game ID associated with the channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return
        
        # Get current game info
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return
        
        # Check if chess clock is active
        chess_clock_active = game_info.get("chess_clock_active", False)
        if chess_clock_active and not allow_players:
            await interaction.followup.send(
                "❌ Cannot disable player timer control while chess clock mode is active.\n"
                "Chess clock mode requires players to be able to extend timers."
            )
            return
        
        try:
            # Convert string to boolean using mapping
            allow_players_map = {"True": 1, "False": 0}
            if allow_players not in allow_players_map:
                await interaction.followup.send("Invalid value for allow_players. Allowed values: True, False.")
                return
            allow_players_value = bool(allow_players_map[allow_players])
            
            # Update the setting
            await bot.db_instance.update_game_property(game_id, "player_control_timers", allow_players_value)
            
            status_text = "can extend timers" if allow_players_value else "cannot extend timers (only owner/admin)"
            game_name = game_info.get("game_name", f"Game ID {game_id}")
            
            await interaction.followup.send(
                f"✅ Timer rules updated for **{game_name}**:\n"
                f"Players {status_text}."
            )
            
        except Exception as e:
            await interaction.followup.send(f"Failed to update timer rules: {e}")

    @player_extension_rules_command.autocomplete("allow_players")
    async def allow_players_autocomplete(interaction: discord.Interaction, current: str):
        options = ["True", "False"]
        matches = [option for option in options if current.lower() in option.lower()]
        return [app_commands.Choice(name=match, value=match) for match in matches]

    @bot.tree.command(
        name="chess-clock-setup", 
        description="Set up chess clock mode (or disable by setting both values to 0).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def chess_clock_setup_command(interaction: discord.Interaction, starting_time: float, per_turn_bonus: float):
        """Set up or disable chess clock mode for the current game.
        
        Enables chess clock mode with specified starting time and per-turn bonus.
        To disable chess clock mode, set both starting_time and per_turn_bonus to 0.
        
        Requirements for enabling:
        - Game must not have started yet
        - Player control timers must be enabled
        - Starting time must be positive, per-turn bonus cannot be negative
        
        Time units are based on game type:
        - Blitz games: values are in minutes, converted to seconds internally
        - Normal games: values are in hours, converted to seconds internally
        
        When enabled, players receive their starting time allocation when they claim nations.
        """
        await interaction.response.defer()
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return
        
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return
        
        if starting_time == 0 and per_turn_bonus == 0:
            try:
                await bot.db_instance.update_game_property(game_id, "chess_clock_active", False)
                await bot.db_instance.update_game_property(game_id, "chess_clock_starting_time", 0)
                await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", 0)
                
                game_name = game_info.get("game_name", f"Game ID {game_id}")
                await interaction.followup.send(
                    f"✅ **Chess clock disabled** for **{game_name}**\n"
                    f"Timer extensions now follow the existing player extension rules."
                )
                return
            except Exception as e:
                await interaction.followup.send(f"Failed to disable chess clock: {e}")
                return
        
        player_control_timers = game_info.get("player_control_timers", True)
        if not player_control_timers:
            await interaction.followup.send(
                "❌ Chess clock mode requires 'player control timers' to be enabled.\n"
                "Use `/player-extension-rules allow_players:True` first."
            )
            return
        
        chess_clock_active = game_info.get("chess_clock_active", False)
        game_started = game_info.get("game_started", False)
        
        # Handle lobby games (not started) - use original simple logic
        if not game_started:
            if starting_time == 0 and per_turn_bonus == 0:
                try:
                    await bot.db_instance.update_game_property(game_id, "chess_clock_active", False)
                    await bot.db_instance.update_game_property(game_id, "chess_clock_starting_time", 0)
                    await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", 0)
                    
                    game_name = game_info.get("game_name", f"Game ID {game_id}")
                    await interaction.followup.send(
                        f"✅ **Chess clock disabled** for **{game_name}**\n"
                        f"Timer extensions now follow the existing player extension rules."
                    )
                    return
                except Exception as e:
                    await interaction.followup.send(f"Failed to disable chess clock: {e}")
                    return
            
            # Original lobby logic - normal validation and setup
            if starting_time <= 0 or per_turn_bonus < 0:
                await interaction.followup.send("❌ Starting time must be positive and per-turn bonus cannot be negative.")
                return
            
            try:
                game_type = game_info.get("game_type", "").lower()
                if game_type == "blitz":
                    starting_seconds = round(starting_time * 60)
                    per_turn_seconds = round(per_turn_bonus * 60)
                    time_unit = "minutes"
                else:
                    starting_seconds = round(starting_time * 3600)
                    per_turn_seconds = round(per_turn_bonus * 3600)
                    time_unit = "hours"
                
                await bot.db_instance.update_game_property(game_id, "chess_clock_active", True)
                await bot.db_instance.update_game_property(game_id, "chess_clock_starting_time", starting_seconds)
                await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", per_turn_seconds)
                
                game_name = game_info.get("game_name", f"Game ID {game_id}")
                
                await interaction.followup.send(
                    f"✅ Chess clock mode enabled for **{game_name}**:\n"
                    f"• Starting time: {starting_time:g} {time_unit}\n"
                    f"• Per-turn bonus: {per_turn_bonus:g} {time_unit}\n\n"
                    f"Players will receive their starting time when the game starts."
                )
                return
                
            except Exception as e:
                await interaction.followup.send(f"Failed to set up chess clock: {e}")
                return
        
        # For started games, check admin permissions when enabling chess clock
        if game_started and not chess_clock_active:
            admin_role_id = int(bot.config.get("game_admin"))
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            is_admin = admin_role and admin_role in interaction.user.roles
            
            if not is_admin:
                await interaction.followup.send("❌ Cannot enable chess clock mode after the game has started. (Admin-only capability)")
                return
        
        # Handle started games with special logic
        if game_started:
            # Check if this is disabling chess clock (both values are 0)
            if starting_time == 0 and per_turn_bonus == 0:
                try:
                    await bot.db_instance.update_game_property(game_id, "chess_clock_active", False)
                    await bot.db_instance.update_game_property(game_id, "chess_clock_starting_time", 0)
                    await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", 0)
                    
                    game_name = game_info.get("game_name", f"Game ID {game_id}")
                    await interaction.followup.send(
                        f"✅ **Chess clock disabled** for **{game_name}**\n"
                        f"Timer extensions now follow the existing player extension rules."
                    )
                    return
                except Exception as e:
                    await interaction.followup.send(f"Failed to disable chess clock: {e}")
                    return
            
            try:
                game_type = game_info.get("game_type", "").lower()
                if game_type == "blitz":
                    per_turn_seconds = round(per_turn_bonus * 60)
                    time_unit = "minutes"
                else:
                    per_turn_seconds = round(per_turn_bonus * 3600)
                    time_unit = "hours"
                
                game_name = game_info.get("game_name", f"Game ID {game_id}")
                
                if chess_clock_active:
                    # Chess clock is already running - only update per-turn bonus, ignore starting_time
                    await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", per_turn_seconds)
                    
                    await interaction.followup.send(
                        f"✅ Chess clock per-turn bonus updated for **{game_name}**:\n"
                        f"• New per-turn bonus: {per_turn_bonus:g} {time_unit}\n\n"
                        f"Player time banks unchanged. Starting time value ignored."
                    )
                else:
                    # Chess clock is not setup - enable it with proper time allocation (admin-only)
                    if game_type == "blitz":
                        starting_seconds = round(starting_time * 60) if starting_time > 0 else 0
                    else:
                        starting_seconds = round(starting_time * 3600) if starting_time > 0 else 0
                    
                    await bot.db_instance.update_game_property(game_id, "chess_clock_active", True)
                    await bot.db_instance.update_game_property(game_id, "chess_clock_starting_time", starting_seconds)
                    await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", per_turn_seconds)
                    
                    # Handle player time allocation
                    players = await bot.db_instance.get_players_in_game(game_id)
                    
                    if starting_time > 0:
                        # Set all players to starting_time value
                        for player_data in players:
                            if player_data.get('currently_claimed', False):
                                await bot.db_instance.update_player_chess_clock_time(
                                    game_id, 
                                    player_data['player_id'], 
                                    starting_seconds
                                )
                        allocation_msg = f"All players set to {starting_time:g} {time_unit}"
                    else:
                        # starting_time is 0 - preserve existing times or set to 0 if none
                        for player_data in players:
                            if player_data.get('currently_claimed', False):
                                current_time = player_data.get('chess_clock_time_remaining')
                                if current_time is None:  # Only set to 0 if no previous record exists
                                    await bot.db_instance.update_player_chess_clock_time(
                                        game_id, 
                                        player_data['player_id'], 
                                        0
                                    )
                                # If current_time exists (even if it's 0), preserve it
                        allocation_msg = "Existing time banks preserved"
                    
                    await interaction.followup.send(
                        f"✅ Chess clock enabled for **{game_name}**:\n"
                        f"• Per-turn bonus: {per_turn_bonus:g} {time_unit}\n"
                        f"• {allocation_msg}\n\n"
                        f"Chess clock is now active for this game."
                    )
                return
                
            except Exception as e:
                await interaction.followup.send(f"Failed to update chess clock: {e}")
                return
        
        if starting_time <= 0 or per_turn_bonus < 0:
            await interaction.followup.send("❌ Starting time must be positive and per-turn bonus cannot be negative.")
            return
        
        try:
            game_type = game_info.get("game_type", "").lower()
            if game_type == "blitz":
                starting_seconds = round(starting_time * 60)
                per_turn_seconds = round(per_turn_bonus * 60)
                time_unit = "minutes"
            else:
                starting_seconds = round(starting_time * 3600)
                per_turn_seconds = round(per_turn_bonus * 3600)
                time_unit = "hours"
            
            await bot.db_instance.update_game_property(game_id, "chess_clock_active", True)
            await bot.db_instance.update_game_property(game_id, "chess_clock_starting_time", starting_seconds)
            await bot.db_instance.update_game_property(game_id, "chess_clock_per_turn_time", per_turn_seconds)
            
            game_name = game_info.get("game_name", f"Game ID {game_id}")
            
            await interaction.followup.send(
                f"✅ Chess clock mode enabled for **{game_name}**:\n"
                f"• Starting time: {starting_time:g} {time_unit}\n"
                f"• Per-turn bonus: {per_turn_bonus:g} {time_unit}\n\n"
                f"Players will receive their starting time when the game starts."
            )
            
        except Exception as e:
            await interaction.followup.send(f"Failed to set up chess clock: {e}")

    # Add autocomplete functions for the commands that need them
    # These will need to be implemented based on the original logic
    
    if bot.config and bot.config.get("debug", False):
        print("[GAME_MGMT] All commands registered, returning command list...")
    return [
        new_game_command,
        edit_game_command, 
        launch_command,
        start_game_command,
        restart_game_to_lobby_command,
        pause_command,
        end_game_command,
        kill_command,
        force_host_command,
        player_extension_rules_command,
        chess_clock_setup_command
    ]