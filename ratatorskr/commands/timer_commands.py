"""
Timer-related commands - extending, setting, managing game timers.
"""

import discord
from datetime import datetime, timezone, timedelta
from bifrost import bifrost
from ..decorators import require_bot_channel, require_game_channel, require_game_owner_or_admin


def register_timer_commands(bot):
    """Register all timer-related commands to the bot's command tree."""
    
    def descriptive_time_breakdown(seconds: int) -> str:
        """Format a duration in seconds into a descriptive breakdown."""
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
    
    async def send_rollback_notification(game_id, game_info):
        """Send a Discord notification when a game is rolled back."""
        try:
            # Get the Discord channel
            channel_id = game_info.get("channel_id")
            if not channel_id:
                print(f"[ERROR] No channel ID found for rollback notification game ID {game_id}")
                return

            channel = bot.get_channel(int(channel_id))
            if not channel:
                channel = await bot.fetch_channel(int(channel_id))
            if not channel:
                print(f"[ERROR] Discord channel not found for rollback notification game ID {game_id}")
                return

            # Get timer info and reset it
            timer_info = await bot.db_instance.get_game_timer(game_id)
            if timer_info:
                timer_default = timer_info["timer_default"]
                await bot.db_instance.update_timer(game_id, timer_default, True)
                remaining_time = timer_default
            else:
                remaining_time = 3600  # Default 1 hour if no timer info

            # Calculate Discord timestamp
            current_time = datetime.now(timezone.utc)
            future_time = current_time + timedelta(seconds=remaining_time)
            discord_timestamp = f"<t:{int(future_time.timestamp())}:R>"
            
            # Send notification
            embed = discord.Embed(
                title=f"🔄 Game Rolled Back: {game_info['game_name']}",
                description=f"The game has been rolled back to the previous turn.\n\nNext turn: {discord_timestamp}",
                color=discord.Color.orange()
            )
            await channel.send(embed=embed)
            
        except Exception as e:
            print(f"[ERROR] Failed to send rollback notification for game {game_id}: {e}")
    
    @bot.tree.command(
        name="extend-timer",
        description="Extends the timer for the current turn.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def extend_timer_command(interaction: discord.Interaction, time_value: float):
        """Adjusts the timer for the current game by a specified amount (hours or minutes based on game type)."""
        await interaction.response.defer()

        # Get the game ID associated with the channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            # Fetch current timer info
            timer_info = await bot.db_instance.get_game_timer(game_id)
            if not timer_info:
                await interaction.followup.send("No timer information found for this game.")
                return

            # Fetch game info to get the game owner and determine game type
            game_info = await bot.db_instance.get_game_info(game_id)
            game_owner_id = game_info["game_owner"]

            # Check if the requester is an admin or the game owner
            admin_role_id = int(bot.config.get("game_admin"))
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            is_admin = admin_role in interaction.user.roles if admin_role else False
            is_owner = interaction.user.name == game_owner_id  # Fixed: compare usernames

            # Check if the requester is a player
            player_entry = await bot.db_instance.get_player_by_game_and_user(game_id, str(interaction.user.id))
            is_player = bool(player_entry)

            # Check if chess clock mode is active
            chess_clock_active = game_info.get("chess_clock_active", False)
            player_control_timers = game_info.get("player_control_timers", True)

            # Handle chess clock logic for players and admins who are also players
            used_chess_clock_time = False
            owner_exceeded_limit = False
            admin_exceeded_limit = False
            
            if chess_clock_active and time_value > 0:
                # Convert time_value to seconds for comparison (round to nearest second)
                if game_info.get("game_type", "").lower() == "blitz":
                    requested_seconds = round(time_value * 60)  # Minutes to seconds
                    time_unit = "minutes"
                else:
                    requested_seconds = round(time_value * 3600)  # Hours to seconds  
                    time_unit = "hours"
                
                if is_player or is_owner:
                    player_time_remaining = await bot.db_instance.get_player_chess_clock_time(game_id, str(interaction.user.id))
                    
                    if (is_owner or (is_admin and is_player)) and player_time_remaining < requested_seconds:
                        # Game owner or admin-player can extend past their limit - announce this
                        if is_owner:
                            owner_exceeded_limit = True
                        elif is_admin and is_player:
                            admin_exceeded_limit = True
                        
                        # Set their time to 0 (they've used all their time)
                        await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), 0)
                        used_chess_clock_time = True
                        
                    elif is_player and not is_owner and not is_admin and player_time_remaining < requested_seconds:
                        # Regular players (not owners or admins) cannot extend past their limit
                        if game_info.get("game_type", "").lower() == "blitz":
                            remaining_display = f"{player_time_remaining / 60:.1f} minutes"
                        else:
                            remaining_display = f"{player_time_remaining / 3600:.1f} hours"
                        
                        await interaction.followup.send(
                            f"❌ Insufficient chess clock time. You have {remaining_display} remaining, "
                            f"but tried to use {time_value:g} {time_unit}."
                        )
                        return
                    
                    else:
                        # Player/owner/admin has sufficient time - deduct normally
                        new_time_remaining = player_time_remaining - requested_seconds
                        await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), new_time_remaining)
                        used_chess_clock_time = True
                
                elif is_admin and not is_player:
                    # Admin extending a game they're not playing in - no chess clock impact
                    pass
                
            elif chess_clock_active and not is_player and not (is_owner or is_admin):
                # Chess clock mode but user is not a player/owner/admin
                await interaction.followup.send(
                    "You must be a player, game owner, or admin to extend the timer in chess clock mode."
                )
                return
                
            else:
                # Regular permission check (non-chess clock mode or owner/admin)
                if not player_control_timers:
                    # Only owner/admin can control timers
                    if not (is_owner or is_admin):
                        await interaction.followup.send(
                            "Only the game owner or an admin can extend/reduce timers in this game."
                        )
                        return
                else:
                    # Players can extend (positive values), only owner/admin can reduce (negative values)
                    if time_value < 0 and not (is_owner or is_admin):
                        await interaction.followup.send(
                            "Only the game owner or an admin can reduce the timer."
                        )
                        return
                    elif time_value >= 0 and not (is_owner or is_admin or is_player):
                        await interaction.followup.send(
                            "You must be a player, game owner, or admin to extend the timer."
                        )
                        return

            # Determine time unit and convert to seconds (round to nearest second)
            if game_info.get("game_type", "").lower() == "blitz":
                # Blitz games: treat input as minutes
                added_seconds = round(time_value * 60)
                time_unit = "minutes"
            else:
                # Normal games: treat input as hours
                added_seconds = round(time_value * 3600)
                time_unit = "hours"

            # If the requester is a player (even if they are also an admin or owner), update their extensions
            if is_player and time_value > 0:
                # Always store extensions in seconds regardless of game type
                await bot.db_instance.increment_player_extensions(game_id, str(interaction.user.id))

            # Calculate new remaining time
            new_remaining_time = max(0, timer_info["remaining_time"] + added_seconds)  # Prevent negative time

            # Update the timer
            await bot.db_instance.update_timer(game_id, new_remaining_time, timer_info["timer_running"])

            # Format time value nicely (remove .0 for whole numbers)
            formatted_time = f"{time_value:g}"
            
            # Create success message
            if time_value >= 0:
                message = f"Timer for game ID {game_id} has been extended by {formatted_time} {time_unit}."
                
                # Add chess clock info if applicable
                if used_chess_clock_time and not owner_exceeded_limit and not admin_exceeded_limit:
                    updated_time_remaining = await bot.db_instance.get_player_chess_clock_time(game_id, str(interaction.user.id))
                    if game_info.get("game_type", "").lower() == "blitz":
                        remaining_display = f"{updated_time_remaining / 60:.1f} minutes"
                    else:
                        remaining_display = f"{updated_time_remaining / 3600:.1f} hours"
                    message += f"\n⏱️ Your remaining chess clock time: {remaining_display}"
                
                # Add warning to message if owner/admin exceeded their limit
                if owner_exceeded_limit:
                    message += f"\n⚠️ **Game Owner extended beyond their chess clock limit.**"
                elif admin_exceeded_limit:
                    message += f"\n⚠️ **Admin extended beyond their chess clock limit.**"
                
                # Send public response (visible to everyone)
                await interaction.followup.send(message)
            else:
                await interaction.followup.send(
                    f"Timer for game ID {game_id} has been reduced by {abs(time_value):g} {time_unit}."
                )

        except Exception as e:
            await interaction.followup.send(f"Failed to adjust the timer: {e}")

    @bot.tree.command(
        name="set-default-timer",
        description="Sets the default timer for future turns.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def set_default_timer_command(interaction: discord.Interaction, time_value: float):
        """Changes the default timer for the current game."""
        await interaction.response.defer()

        # Get the game ID associated with the channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            # Get game info to check if it's a blitz game
            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Check if game type is blitz - if so, treat input as minutes instead of hours (round to nearest second)
            if game_info.get("game_type", "").lower() == "blitz":
                # Convert minutes to seconds
                new_default_timer = round(time_value * 60)
                time_unit = "minutes"
            else:
                # Convert hours to seconds
                new_default_timer = round(time_value * 3600)
                time_unit = "hours"

            # Update the timer_default in the database
            # Update the default timer using the database method
            await bot.db_instance.update_timer_default(game_id, new_default_timer)

            await interaction.followup.send(
                f"Default timer for game ID {game_id} has been updated to {time_value:g} {time_unit}."
            )
        except Exception as e:
            await interaction.followup.send(f"Failed to update default timer: {e}")

    @bot.tree.command(
        name="timer",
        description="Checks the time remaining on the current turn.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def timer_command(interaction: discord.Interaction):
        """Shows timer information for the current game."""
        await interaction.response.defer()

        # Get the game ID associated with the channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return

        # Check if game is started
        if not game_info['game_started'] or not game_info['game_running']:
            await interaction.followup.send("Game must be started and running to show timer information.")
            return

        try:
            # Get timer information
            timer_data = await bot.db_instance.get_game_timer(game_id)
            if not timer_data:
                await interaction.followup.send("Timer data not found for this game.")
                return

            remaining_time = timer_data["remaining_time"]
            timer_default = timer_data["timer_default"]
            timer_running = timer_data["timer_running"]

            # Convert seconds to readable format
            remaining_readable = descriptive_time_breakdown(remaining_time) if remaining_time else "Unknown"
            
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

    @bot.tree.command(
        name="roll-back",
        description="Rolls the game back to the previous turn.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def roll_back_command(interaction: discord.Interaction):
        """Rolls back the game associated with the current channel to the latest backup."""
        # Acknowledge interaction to prevent timeout
        await interaction.response.defer()

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        # Fetch game information
        game_info = await bot.db_instance.get_game_info(game_id)
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
                db_instance=bot.db_instance,
                config=bot.config
            )
            await interaction.followup.send(f"Game ID {game_id} ({game_info['game_name']}) has been successfully rolled back to the latest backup.")
            print(f"Game ID {game_id} ({game_info['game_name']}) successfully rolled back.")
            
            # Send rollback notification to game channel
            await send_rollback_notification(game_id, game_info)
        except FileNotFoundError as fnf_error:
            await interaction.followup.send(f"Failed to roll back: {fnf_error}")
            print(f"Error restoring game ID {game_id} ({game_info['game_name']}): {fnf_error}")
        except Exception as e:
            await interaction.followup.send(f"Failed to roll back: {e}")
            print(f"Unexpected error restoring game ID {game_id} ({game_info['game_name']}): {e}")

    @bot.tree.command(
        name="extensions-stats",
        description="Shows timer extension statistics for the current game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def extensions_stats_command(interaction: discord.Interaction):
        """Displays a summary of all players and their total extensions (hours or minutes based on game type)."""
        await interaction.response.defer()

        # Get the game ID associated with the channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            # Fetch game info to determine game type
            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            # Determine time unit based on game type
            is_blitz = game_info.get("game_type", "").lower() == "blitz"
            time_unit = "minutes" if is_blitz else "hours"
            time_divisor = 60 if is_blitz else 3600

            # Fetch all players and their extensions for the given game
            players_in_game = await bot.db_instance.get_players_in_game(game_id)
            
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

    return [
        extend_timer_command,
        set_default_timer_command,
        timer_command,
        roll_back_command,
        extensions_stats_command
    ]