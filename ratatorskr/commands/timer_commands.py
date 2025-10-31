"""
Timer-related commands - extending, setting, managing game timers.
"""

import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
from bifrost import bifrost
from ..decorators import require_bot_channel, require_game_channel, require_game_owner_or_admin, require_game_admin


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

            timer_info = await bot.db_instance.get_game_timer(game_id)
            if timer_info:
                timer_default = timer_info["timer_default"]
                await bot.db_instance.update_timer(game_id, timer_default, True)
                remaining_time = timer_default
            else:
                remaining_time = 3600

            current_time = datetime.now(timezone.utc)
            future_time = current_time + timedelta(seconds=remaining_time)
            discord_timestamp = f"<t:{int(future_time.timestamp())}:R>"
            
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

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            timer_info = await bot.db_instance.get_game_timer(game_id)
            if not timer_info:
                await interaction.followup.send("No timer information found for this game.")
                return

            game_info = await bot.db_instance.get_game_info(game_id)
            game_owner_id = game_info["game_owner"]

            admin_role_id = int(bot.config.get("game_admin"))
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            is_admin = admin_role in interaction.user.roles if admin_role else False
            is_owner = interaction.user.name == game_owner_id

            player_entry = await bot.db_instance.get_player_by_game_and_user(game_id, str(interaction.user.id))
            is_player = bool(player_entry)

            chess_clock_active = game_info.get("chess_clock_active", False)
            player_control_timers = game_info.get("player_control_timers", True)

            used_chess_clock_time = False
            owner_exceeded_limit = False
            admin_exceeded_limit = False
            
            if chess_clock_active and time_value > 0:
                if game_info.get("game_type", "").lower() == "blitz":
                    requested_seconds = round(time_value * 60)
                    time_unit = "minutes"
                else:
                    requested_seconds = round(time_value * 3600)
                    time_unit = "hours"
                
                if is_player or is_owner:
                    player_time_remaining = await bot.db_instance.get_player_chess_clock_time(game_id, str(interaction.user.id))
                    
                    if (is_owner or (is_admin and is_player)) and player_time_remaining < requested_seconds:
                        if is_owner:
                            owner_exceeded_limit = True
                        elif is_admin and is_player:
                            admin_exceeded_limit = True
                        
                        await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), 0)
                        used_chess_clock_time = True
                        
                    elif is_player and not is_owner and not is_admin and player_time_remaining < requested_seconds:
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
                        new_time_remaining = player_time_remaining - requested_seconds
                        await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), new_time_remaining)
                        used_chess_clock_time = True
                
                elif is_admin and not is_player:
                    pass
                
            elif chess_clock_active and not is_player and not (is_owner or is_admin):
                await interaction.followup.send(
                    "You must be a player, game owner, or admin to extend the timer in chess clock mode."
                )
                return
                
            else:
                if not player_control_timers:
                    if not (is_owner or is_admin):
                        await interaction.followup.send(
                            "Only the game owner or an admin can extend/reduce timers in this game."
                        )
                        return
                else:
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

            if game_info.get("game_type", "").lower() == "blitz":
                added_seconds = round(time_value * 60)
                time_unit = "minutes"
            else:
                added_seconds = round(time_value * 3600)
                time_unit = "hours"

            if is_player and time_value > 0:
                await bot.db_instance.increment_player_extensions(game_id, str(interaction.user.id), added_seconds)

            new_remaining_time = max(0, timer_info["remaining_time"] + added_seconds)

            await bot.db_instance.update_timer(game_id, new_remaining_time, timer_info["timer_running"])

            formatted_time = f"{time_value:g}"

            # Format the exact time remaining using descriptive_time_breakdown
            remaining_readable = descriptive_time_breakdown(new_remaining_time)

            # Calculate the Discord timestamp for next turn
            if new_remaining_time and timer_info["timer_running"]:
                from datetime import datetime, timezone, timedelta
                current_time = datetime.now(timezone.utc)
                future_time = current_time + timedelta(seconds=new_remaining_time)
                discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
                next_turn_text = f"**Next Turn**: {discord_timestamp}"
            else:
                next_turn_text = "**Next Turn**: Timer is paused"

            if time_value >= 0:
                embed = discord.Embed(
                    title="⏰ Timer Extended",
                    description=f"Timer extended by **{formatted_time} {time_unit}**",
                    color=discord.Color.green()
                )

                embed.add_field(
                    name="Time Remaining",
                    value=remaining_readable,
                    inline=False
                )

                if new_remaining_time and timer_info["timer_running"]:
                    current_time = datetime.now(timezone.utc)
                    future_time = current_time + timedelta(seconds=new_remaining_time)
                    discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
                    embed.add_field(
                        name="Next Turn",
                        value=discord_timestamp,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Next Turn",
                        value="Timer is paused",
                        inline=False
                    )

                if used_chess_clock_time and not owner_exceeded_limit and not admin_exceeded_limit:
                    updated_time_remaining = await bot.db_instance.get_player_chess_clock_time(game_id, str(interaction.user.id))
                    if game_info.get("game_type", "").lower() == "blitz":
                        remaining_display = f"{updated_time_remaining / 60:.1f} minutes"
                    else:
                        remaining_display = f"{updated_time_remaining / 3600:.1f} hours"
                    embed.add_field(
                        name="♟️ Your Chess Clock Time",
                        value=remaining_display,
                        inline=False
                    )

                footer_text = f"Game ID: {game_id}"
                if owner_exceeded_limit:
                    footer_text = "⚠️ Game Owner extended beyond their chess clock limit"
                elif admin_exceeded_limit:
                    footer_text = "⚠️ Admin extended beyond their chess clock limit"

                embed.set_footer(text=footer_text)

                await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="⏰ Timer Reduced",
                    description=f"Timer reduced by **{abs(time_value):g} {time_unit}**",
                    color=discord.Color.orange()
                )

                embed.add_field(
                    name="Time Remaining",
                    value=remaining_readable,
                    inline=False
                )

                if new_remaining_time and timer_info["timer_running"]:
                    current_time = datetime.now(timezone.utc)
                    future_time = current_time + timedelta(seconds=new_remaining_time)
                    discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
                    embed.add_field(
                        name="Next Turn",
                        value=discord_timestamp,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="Next Turn",
                        value="Timer is paused",
                        inline=False
                    )

                embed.set_footer(text=f"Game ID: {game_id}")

                await interaction.followup.send(embed=embed)

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

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            if game_info.get("game_type", "").lower() == "blitz":
                new_default_timer = round(time_value * 60)
                time_unit = "minutes"
            else:
                new_default_timer = round(time_value * 3600)
                time_unit = "hours"

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

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return

        if not game_info['game_started'] or not game_info['game_running']:
            await interaction.followup.send("Game must be started and running to show timer information.")
            return

        try:
            timer_data = await bot.db_instance.get_game_timer(game_id)
            if not timer_data:
                await interaction.followup.send("Timer data not found for this game.")
                return

            remaining_time = timer_data["remaining_time"]
            timer_default = timer_data["timer_default"]
            timer_running = timer_data["timer_running"]

            remaining_readable = descriptive_time_breakdown(remaining_time) if remaining_time else "Unknown"
            
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

            if remaining_time and timer_running:
                current_time = datetime.now(timezone.utc)
                future_time = current_time + timedelta(seconds=remaining_time)
                discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
                next_turn_text = f"**Next Turn**: {discord_timestamp}"
            else:
                next_turn_text = "**Next Turn**: Timer is paused"

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
            
            chess_clock_active = game_info.get('chess_clock_active', False)
            if chess_clock_active:
                try:
                    players = await bot.db_instance.get_currently_claimed_players(game_id)
                    per_turn_bonus = game_info.get('chess_clock_per_turn_time', 0)
                    
                    if players:
                        if game_info.get("game_type", "").lower() == "blitz":
                            bonus_display = f"{per_turn_bonus / 60:.1f} minutes"
                            time_unit = "min"
                        else:
                            bonus_display = f"{per_turn_bonus / 3600:.1f} hours"
                            time_unit = "hr"
                        
                        clock_info = []
                        seen_players = {}
                        
                        for player in players:
                            player_id = player["player_id"]
                            nation_name = player.get("nation", "Unknown")
                            
                            try:
                                if player_id not in seen_players:
                                    try:
                                        if getattr(bot, 'config', {}).get("debug", False):
                                            print(f"[TIMER DEBUG] Trying to resolve player_id: {player_id} (type: {type(player_id)})")
                                        
                                        user = interaction.guild.get_member(int(player_id))
                                        if user:
                                            display_name = user.display_name
                                            if getattr(bot, 'config', {}).get("debug", False):
                                                print(f"[TIMER DEBUG] Found guild member: {display_name}")
                                        else:
                                            user = bot.get_user(int(player_id))
                                            if user:
                                                display_name = user.name
                                                if getattr(bot, 'config', {}).get("debug", False):
                                                    print(f"[TIMER DEBUG] Found user via client: {display_name}")
                                            else:
                                                try:
                                                    user = await bot.fetch_user(int(player_id))
                                                    if user:
                                                        display_name = user.name
                                                        if getattr(bot, 'config', {}).get("debug", False):
                                                            print(f"[TIMER DEBUG] Found user via fetch: {display_name}")
                                                    else:
                                                        display_name = f"User {player_id}"
                                                        if getattr(bot, 'config', {}).get("debug", False):
                                                            print(f"[TIMER DEBUG] Could not find user via fetch, using fallback: {display_name}")
                                                except Exception as fetch_error:
                                                    display_name = f"User {player_id}"
                                                    if getattr(bot, 'config', {}).get("debug", False):
                                                        print(f"[TIMER DEBUG] Fetch user failed: {fetch_error}")
                                    except (ValueError, AttributeError) as e:
                                        display_name = f"User {player_id}"
                                        if getattr(bot, 'config', {}).get("debug", False):
                                            print(f"[TIMER DEBUG] Exception resolving user: {e}")
                                    
                                    player_nations = [p for p in players if p["player_id"] == player_id]
                                    max_clock_time = 0
                                    nations_list = []
                                    
                                    for nation_record in player_nations:
                                        nation = nation_record.get("nation", "Unknown")
                                        nations_list.append(nation)
                                        clock_time = nation_record.get("chess_clock_time_remaining", 0)
                                        if clock_time and clock_time > max_clock_time:
                                            max_clock_time = clock_time
                                    
                                    if max_clock_time >= 0:
                                        if game_info.get("game_type", "").lower() == "blitz":
                                            time_display = f"{max_clock_time / 60:.1f}{time_unit}"
                                        else:
                                            time_display = f"{max_clock_time / 3600:.1f}{time_unit}"
                                        
                                        nations_str = ", ".join(nations_list)
                                        clock_info.append(f"**{display_name}** ({nations_str}): {time_display}")
                                    else:
                                        nations_str = ", ".join(nations_list)
                                        clock_info.append(f"**{display_name}** ({nations_str}): No data")
                                    
                                    seen_players[player_id] = True
                                    
                            except Exception as e:
                                if getattr(bot, 'config', {}).get("debug", False):
                                    print(f"[TIMER] Error processing player {player_id}: {e}")
                                if player_id not in seen_players:
                                    clock_info.append(f"**Unknown** ({nation_name}): Error")
                                    seen_players[player_id] = True
                        
                        chess_clock_text = "\n".join(clock_info) if clock_info else "No player data available"
                        chess_clock_text += f"\n\n**Per-Turn Bonus**: +{bonus_display}"
                        
                        embed.add_field(
                            name="♟️ Chess Clock - All Players",
                            value=chess_clock_text,
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="♟️ Chess Clock Active",
                            value=f"No players found\n**Per-Turn Bonus**: +{bonus_display}",
                            inline=False
                        )
                except Exception as e:
                    if getattr(bot, 'config', {}).get("debug", False):
                        print(f"[TIMER] Error retrieving chess clock info: {e}")
                    embed.add_field(
                        name="♟️ Chess Clock Active",
                        value="Could not retrieve chess clock information",
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
        await interaction.response.defer()

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        if game_info["game_running"]:
            await interaction.followup.send("The game is currently running. Please stop the game first.")
            return

        try:
            await bifrost.restore_saved_game_files(
                game_id=game_id,
                db_instance=bot.db_instance,
                config=bot.config
            )
            await interaction.followup.send(f"Game ID {game_id} ({game_info['game_name']}) has been successfully rolled back to the latest backup.")
            print(f"Game ID {game_id} ({game_info['game_name']}) successfully rolled back.")
            
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

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            is_blitz = game_info.get("game_type", "").lower() == "blitz"
            time_unit = "minutes" if is_blitz else "hours"
            time_divisor = 60 if is_blitz else 3600

            players_in_game = await bot.db_instance.get_players_in_game(game_id)
            
            if not players_in_game:
                await interaction.followup.send("No players found for this game.")
                return

            embed = discord.Embed(
                title="Extension Stats",
                description=f"Extension statistics for game ID: {game_id}",
                color=discord.Color.green()
            )

            guild = interaction.guild
            for player in players_in_game:
                player_id = player['player_id']
                extensions = player['extensions']
                user = guild.get_member(int(player_id)) or await interaction.client.fetch_user(int(player_id))
                display_name = user.display_name if user else f"Unknown (ID: {player_id})"

                extensions_in_time_unit = (extensions or 0) // time_divisor

                embed.add_field(
                    name=display_name,
                    value=f"Total Extensions: {extensions_in_time_unit} {time_unit}",
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"Failed to retrieve extension stats: {e}")

    @bot.tree.command(
        name="adjust-chess-clock",
        description="Admin only: Adjust chess clock time for a player in the current game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_admin(bot.config)
    async def adjust_chess_clock_command(interaction: discord.Interaction, player: str, time_value: float):
        """Adds or removes chess clock time for a player (hours or minutes based on game type)."""
        await interaction.response.defer()

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return

        try:
            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            if not game_info.get('chess_clock_active', False):
                await interaction.followup.send("Chess clock is not active for this game.")
                return

            player_entry = await bot.db_instance.get_player_by_game_and_user(game_id, player)
            if not player_entry:
                await interaction.followup.send("Selected player is not in this game.")
                return

            current_time = await bot.db_instance.get_player_chess_clock_time(game_id, player)

            if game_info.get("game_type", "").lower() == "blitz":
                adjustment_seconds = round(time_value * 60)
                time_unit = "minutes"
            else:
                adjustment_seconds = round(time_value * 3600)
                time_unit = "hours"

            new_time = max(0, current_time + adjustment_seconds)

            await bot.db_instance.update_player_chess_clock_time(game_id, player, new_time)

            formatted_adjustment = f"{abs(time_value):g} {time_unit}"
            action = "added to" if time_value >= 0 else "removed from"

            if game_info.get("game_type", "").lower() == "blitz":
                new_time_display = f"{new_time / 60:.1f} minutes"
            else:
                new_time_display = f"{new_time / 3600:.1f} hours"

            # Get player display name
            try:
                user = interaction.guild.get_member(int(player)) or await bot.fetch_user(int(player))
                player_name = user.display_name if hasattr(user, 'display_name') else user.name
            except:
                player_name = f"Player {player}"

            await interaction.followup.send(
                f"⏱️ Chess clock adjusted: {formatted_adjustment} {action} {player_name}'s timer.\n"
                f"Their new chess clock time: {new_time_display}"
            )

        except Exception as e:
            await interaction.followup.send(f"Failed to adjust chess clock: {e}")

    @adjust_chess_clock_command.autocomplete("player")
    async def player_autocomplete(interaction: discord.Interaction, current: str):
        try:
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            players = await bot.db_instance.get_players_in_game(game_id)
            if not players:
                return []

            choices = []
            seen_players = set()

            for player in players:
                player_id = player["player_id"]
                if player_id in seen_players:
                    continue
                seen_players.add(player_id)

                try:
                    user = interaction.guild.get_member(int(player_id))
                    if not user:
                        user = await bot.fetch_user(int(player_id))

                    if user:
                        display_name = user.display_name if hasattr(user, 'display_name') else user.name
                        # Get all nations for this player
                        player_nations = [p["nation"] for p in players if p["player_id"] == player_id]
                        nations_str = ", ".join(player_nations) if player_nations else "Unknown"

                        choice_name = f"{display_name} ({nations_str})"
                        if current.lower() in choice_name.lower():
                            choices.append(app_commands.Choice(name=choice_name[:100], value=player_id))
                except Exception as e:
                    if bot.config and bot.config.get("debug", False):
                        print(f"[AUTOCOMPLETE] Error processing player {player_id}: {e}")

            return choices[:25]  # Discord limits to 25 choices

        except Exception as e:
            if bot.config and bot.config.get("debug", False):
                print(f"[AUTOCOMPLETE] Error in player autocomplete: {e}")
            return []

    return [
        extend_timer_command,
        set_default_timer_command,
        timer_command,
        roll_back_command,
        extensions_stats_command,
        adjust_chess_clock_command
    ]