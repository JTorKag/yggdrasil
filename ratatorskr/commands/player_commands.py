"""
Player-related commands - claiming nations, managing pretenders, etc.
"""

import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
import asyncio
from bifrost import bifrost
from ..decorators import require_bot_channel, require_game_channel, require_game_owner_or_admin, require_game_admin
from ..utils import create_nations_dropdown


def register_player_commands(bot):
    """Register all player-related commands to the bot's command tree."""
    
# Removed local create_nations_dropdown - now using shared version from utils
    
    @bot.tree.command(
        name="claim",
        description="Claims/unclaims nations using a dropdown menu. Self-unclaiming only allowed before game starts.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def claim_command(interaction: discord.Interaction):
        """
        Allows a user to claim/unclaim nations using a dropdown menu.
        
        Players can claim multiple nations and unclaim themselves only if the game hasn't started yet.
        Once the game has started, only admins can unclaim players via the separate unclaim command.
        """
        if bot.config and bot.config.get("debug", False):
            print(f"[DEBUG] claim_command started for user {interaction.user.name} in channel {interaction.channel_id}")
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if bot.config and bot.config.get("debug", False):
            print(f"[DEBUG] claim_command got game_id: {game_id}")
            
        if not game_id:
            await interaction.response.send_message("No game is associated with this channel.", ephemeral=True)
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if bot.config and bot.config.get("debug", False):
            print(f"[DEBUG] claim_command got game_info: {bool(game_info)}")
            
        if not game_info:
            await interaction.response.send_message("Game information not found in the database.", ephemeral=True)
            return

        try:
            if bot.config and bot.config.get("debug", False):
                print(f"[DEBUG] claim_command calling bifrost.get_valid_nations_with_friendly_names for game {game_id}")

            nations_with_names = await bifrost.get_valid_nations_with_friendly_names(game_id, bot.config, bot.db_instance)
            if bot.config and bot.config.get("debug", False):
                print(f"[DEBUG] claim_command got {len(nations_with_names) if nations_with_names else 0} valid nations")

            if not nations_with_names:
                await interaction.response.send_message("No valid nations found for this game.", ephemeral=True)
                return

            # Extract just the nation files for validation logic
            valid_nations = [nation['nation_file'] for nation in nations_with_names]

            if bot.config and bot.config.get("debug", False):
                print(f"[DEBUG] claim_command getting current nations for player {interaction.user.id}")
            
            try:
                import asyncio
                # Add timeout to prevent hanging
                player_current_nations = await asyncio.wait_for(
                    bot.db_instance.get_claimed_nations_by_player(game_id, str(interaction.user.id)), 
                    timeout=10.0
                )
                
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] claim_command get_claimed_nations_by_player returned: {player_current_nations}")
                
                current_nation_names = player_current_nations if player_current_nations else []
                
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] claim_command player has {len(current_nation_names)} current nations: {current_nation_names}")
            except asyncio.TimeoutError:
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] claim_command timeout getting player nations")
                await interaction.response.send_message("Database query timeout. Please try again.", ephemeral=True)
                return
            except Exception as e:
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] claim_command error getting player nations: {e}")
                await interaction.response.send_message("Error retrieving your current nations.", ephemeral=True)
                return
                
            if bot.config and bot.config.get("debug", False):
                print(f"[DEBUG] claim_command calling create_nations_dropdown")

            selected_nations = await create_nations_dropdown(interaction, nations_with_names, current_nation_names, bot.config and bot.config.get("debug", False))

            if bot.config and bot.config.get("debug", False):
                print(f"[DEBUG] claim_command dropdown returned {len(selected_nations) if selected_nations else 0} selected nations: {selected_nations}")
                print(f"[DEBUG] current_nation_names: {current_nation_names}")
                print(f"[DEBUG] valid_nations: {valid_nations}")

            # Allow empty selection if player has current nations (means they want to unclaim all)
            if not selected_nations and not current_nation_names:
                await interaction.followup.send("No nations selected.", ephemeral=True)
                return

            results = []
            errors = []
            first_time_claiming = not await bot.db_instance.player_has_claimed_nations(game_id, str(interaction.user.id))
            
            chess_clock_active = game_info.get("chess_clock_active", False)
            chess_clock_time = 0
            if chess_clock_active and first_time_claiming:
                chess_clock_time = game_info.get("chess_clock_starting_time", 0)

            game_started = game_info.get("game_started", False)
            
            # Check for nations to unclaim (only allowed if game hasn't started)
            if not game_started:
                current_nations_set = set(current_nation_names)
                selected_nations_set = set(selected_nations)
                nations_to_unclaim = current_nations_set - selected_nations_set
                
                for nation_to_unclaim in nations_to_unclaim:
                    try:
                        await bot.db_instance.delete_player_nation(game_id, str(interaction.user.id), nation_to_unclaim)
                        results.append(f"❌ **{interaction.user.display_name}** unclaimed {nation_to_unclaim}")
                        if bot.config and bot.config.get("debug", False):
                            print(f"Player {interaction.user.name} unclaimed nation {nation_to_unclaim} in game {game_id}.")
                    except Exception as e:
                        errors.append(f"Failed to unclaim {nation_to_unclaim}: {e}")

            for nation_name in selected_nations:
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] Processing selected nation: {nation_name}")
                    print(f"[DEBUG] Is {nation_name} in valid_nations? {nation_name in valid_nations}")

                if nation_name not in valid_nations:
                    errors.append(f"{nation_name} is not a valid nation for this game.")
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Nation {nation_name} not found in valid_nations: {valid_nations}")
                    continue

                currently_owns = await bot.db_instance.check_player_nation(game_id, str(interaction.user.id), nation_name)
                if currently_owns:
                    continue

                previously_owned = await bot.db_instance.check_player_previously_owned(game_id, str(interaction.user.id), nation_name)
                
                try:
                    # Get the human-readable nation name from statusdump
                    human_nation_name = await bifrost.get_nation_name_from_statusdump(game_id, nation_name, bot.db_instance, bot.config)

                    if previously_owned:
                        await bot.db_instance.reclaim_nation(game_id, str(interaction.user.id), nation_name, human_nation_name)
                        results.append(f"✅ **{interaction.user.display_name}** re-claimed {nation_name}")
                        if bot.config and bot.config.get("debug", False):
                            print(f"Player {interaction.user.name} reclaimed nation {nation_name} in game {game_id}.")
                    else:
                        await bot.db_instance.add_player(game_id, str(interaction.user.id), nation_name, chess_clock_time, human_nation_name)
                        results.append(f"✅ **{interaction.user.display_name}** claimed {nation_name}")
                        if bot.config and bot.config.get("debug", False):
                            print(f"Added player {interaction.user.name} as {nation_name} in game {game_id}.")

                        chess_clock_time = 0
                        
                except Exception as e:
                    errors.append(f"Failed to claim {nation_name}: {e}")

            if first_time_claiming and chess_clock_active:
                starting_time = game_info.get("chess_clock_starting_time", 0)
                await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), starting_time)

            # Check if player should have role removed (no nations remaining)
            final_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, str(interaction.user.id))
            should_have_role = len(final_nations) > 0

            guild = interaction.guild
            role_name = f"{game_info['game_name']} player"
            role = discord.utils.get(guild.roles, name=role_name)

            if not role and should_have_role:
                role = await guild.create_role(name=role_name)
                if bot.config and bot.config.get("debug", False):
                    print(f"Role '{role_name}' created successfully.")

            # Handle role assignment/removal
            role_message = ""
            if should_have_role and role and role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                role_message = f"Role '{role_name}' assigned."
                if bot.config and bot.config.get("debug", False):
                    print(f"Assigned role '{role_name}' to user {interaction.user.name}.")
            elif not should_have_role and role and role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                role_message = f"Role '{role_name}' removed (no remaining nations)."
                if bot.config and bot.config.get("debug", False):
                    print(f"Removed role '{role_name}' from user {interaction.user.name}.")

            message_parts = []
            if results:
                message_parts.append("\n".join(results))
                if role_message:
                    message_parts.append(role_message)
                

            if errors:
                message_parts.append(f"\n**Errors:**\n" + "\n".join(errors))

            if message_parts:
                await interaction.followup.send("\n\n".join(message_parts))
            else:
                await interaction.followup.send("You already own all selected nations.")
                
        except Exception as e:
            await interaction.followup.send(f"Failed to process nation claims: {e}", ephemeral=True)

    @bot.tree.command(
        name="unclaim",
        description="[Admin/Owner] Completely removes a nation claim (deletes all records).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def unclaim_command(interaction: discord.Interaction, nation_name: str):
        """Allows game owner/admin to completely remove any nation claim."""
        await interaction.response.defer()

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        try:
            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
            player_ids = claimed_nations.get(nation_name, [])
            
            if not player_ids:
                await interaction.followup.send(f"Nation '{nation_name}' is not currently claimed by anyone.")
                return
            
            target_player_id = player_ids[0]
            
            rows_deleted = await bot.db_instance.delete_player_nation(game_id, target_player_id, nation_name)
            
            if rows_deleted == 0:
                await interaction.followup.send(f"No matching record found for nation '{nation_name}' and the target player.")
                return
            
            guild = interaction.guild
            target_member = None
            target_user = None
            
            if guild:
                target_member = guild.get_member(int(target_player_id))
            
            # If not found as member, try to fetch as user
            if not target_member:
                try:
                    target_user = await interaction.client.fetch_user(int(target_player_id))
                except:
                    target_user = None
            
            role_removed = False
            if target_member:
                game_name = game_info["game_name"]
                role_name = f"{game_name} player"
                role = discord.utils.get(guild.roles, name=role_name)
                
                if role and role in target_member.roles:
                    remaining_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, target_player_id)
                    
                    if not remaining_nations:
                        try:
                            await target_member.remove_roles(role)
                            role_removed = True
                        except discord.Forbidden:
                            pass
            
            # Resolve display name with fallbacks
            if target_member:
                target_display = target_member.display_name
            elif target_user:
                target_display = target_user.display_name
            else:
                target_display = f"Player ID {target_player_id}"
            message = f"✅ Nation '{nation_name}' has been **completely removed** from **{target_display}**."
            message += f"\n🗑️ All records (claim, extensions, chess clock time) have been deleted."
            
            if role_removed:
                message += f"\n🎭 Role '{role_name}' was also removed (no remaining nations)."
            
            await interaction.followup.send(message)
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred while unclaiming: {e}")

    @bot.tree.command(
        name="leave-game",
        description="Leave the game by unclaiming all your nations.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def leave_game_command(interaction: discord.Interaction):
        """Allows a player to leave the game by unclaiming all their nations."""
        await interaction.response.defer(ephemeral=True)

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        player_id = str(interaction.user.id)
        
        try:
            player_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, player_id)
            
            if not player_nations:
                await interaction.followup.send("You don't have any nations claimed in this game.", ephemeral=True)
                return
            
            unclaimed_nations = []
            for nation in player_nations:
                try:
                    await bot.db_instance.unclaim_nation(game_id, player_id, nation)
                    unclaimed_nations.append(nation)
                except Exception as e:
                    print(f"Error unclaiming {nation} for player {player_id}: {e}")
            
            guild = interaction.guild
            role_removed = False
            if guild:
                game_name = game_info["game_name"]
                role_name = f"{game_name} player"
                role = discord.utils.get(guild.roles, name=role_name)
                
                if role and role in interaction.user.roles:
                    try:
                        await interaction.user.remove_roles(role)
                        role_removed = True
                    except discord.Forbidden:
                        pass
            
            if unclaimed_nations:
                nations_text = ", ".join(unclaimed_nations)
                message = f"✅ You have left the game. Unclaimed nations: **{nations_text}**"
                
                if role_removed:
                    message += f"\n🔹 Role '{role_name}' has been removed."
                
                message += "\n\n📋 **Note**: Your play history is preserved in the game records."
            else:
                message = "❌ No nations were successfully unclaimed."
            
            await interaction.followup.send(message, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred while leaving the game: {e}", ephemeral=True)

    @bot.tree.command(
        name="pretenders",
        description="Shows all pretenders submitted for the game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def pretenders_command(interaction: discord.Interaction):
        """Lists all .2h files for a game and who has claimed each nation."""
        await interaction.response.defer()

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        print(f"Retrieved game ID: {game_id}")
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        try:
            print(f"Fetching pretenders for game ID: {game_id}")

            # Get nations with friendly names
            nations_with_names = await bifrost.get_valid_nations_with_friendly_names(game_id, bot.config, bot.db_instance)

            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)

            # Build description instead of fields to avoid 25-field limit
            description_lines = []
            claimed_count = 0
            unclaimed_count = 0

            for nation_info in nations_with_names:
                nation_file = nation_info['nation_file']
                nation_name = nation_info['nation_name']
                display_text = f"{nation_name} ({nation_file})" if nation_name != nation_file else nation_file

                claimants = claimed_nations.get(nation_file, [])
                if claimants:
                    resolved_claimants = []
                    for player_id in claimants:
                        user = interaction.guild.get_member(int(player_id)) or await interaction.client.fetch_user(int(player_id))
                        if user:
                            resolved_claimants.append(user.display_name)
                        else:
                            resolved_claimants.append(f"Unknown ({player_id})")
                    description_lines.append(f"**{display_text}**: {', '.join(resolved_claimants)}")
                    claimed_count += 1
                else:
                    description_lines.append(f"**{display_text}**: *Unclaimed*")
                    unclaimed_count += 1
            
            # Split into multiple embeds if description gets too long (Discord limit ~4096 chars)
            embeds = []
            current_embed_lines = []
            current_length = 0
            
            title = f"Pretender Nations ({claimed_count} claimed, {unclaimed_count} unclaimed)"
            
            for line in description_lines:
                line_length = len(line) + 1  # +1 for newline
                
                # If adding this line would exceed Discord's description limit, start new embed
                if current_length + line_length > 4000:  # Leave some buffer
                    embed = discord.Embed(
                        title=title if not embeds else f"{title} (continued)",
                        description="\n".join(current_embed_lines),
                        color=discord.Color.blue()
                    )
                    embeds.append(embed)
                    current_embed_lines = [line]
                    current_length = line_length
                else:
                    current_embed_lines.append(line)
                    current_length += line_length
            
            # Add the last embed
            if current_embed_lines:
                embed = discord.Embed(
                    title=title if not embeds else f"{title} (continued)",
                    description="\n".join(current_embed_lines),
                    color=discord.Color.blue()
                )
                embeds.append(embed)
            
            # Send all embeds
            if embeds:
                await interaction.followup.send(embeds=embeds)
            else:
                await interaction.followup.send("No nations found for this game.")

        except Exception as e:
            print(f"Error in pretenders command: {e}")
            await interaction.followup.send(f"Failed to retrieve pretender information: {e}")

    @bot.tree.command(
        name="clear-claims",
        description="Clears all claims in the game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def clear_claims_command(interaction: discord.Interaction):
        """Clears all claims and removes associated roles for the current game."""
        await interaction.response.defer()

        try:
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send("Game information not found.")
                return

            role_id = game_info.get("role_id")
            role = discord.utils.get(interaction.guild.roles, id=int(role_id))
            if not role:
                await interaction.followup.send("The associated role for this game does not exist.")
                return

            players = await bot.db_instance.get_players_in_game(game_id)
            if not players:
                await interaction.followup.send("No players are associated with this game.")
                return

            removed_members = []
            failed_members = []

            for player in players:
                player_id = player["player_id"]
                try:
                    member = interaction.guild.get_member(int(player_id)) or await interaction.guild.fetch_member(int(player_id))
                    if not member:
                        failed_members.append(player_id)
                        continue

                    if role in member.roles:
                        await member.remove_roles(role)
                        removed_members.append(member.display_name)
                except Exception as e:
                    print(f"Failed to remove role from player {player_id}: {e}")
                    failed_members.append(player_id)

            await bot.db_instance.clear_players(game_id)

            response = f"All claims for game '{game_info['game_name']}' have been cleared."
            if removed_members:
                response += f"\nRoles removed from: {', '.join(removed_members)}."
            if failed_members:
                response += f"\nFailed to process the following players: {', '.join(map(str, failed_members))}."

            await interaction.followup.send(response)

        except Exception as e:
            print(f"Error in clear_claims: {e}")
            await interaction.followup.send(f"An unexpected error occurred: {e}")

    @bot.tree.command(
        name="undone",
        description="Shows players that have not taken their turn yet.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def undone_command(interaction: discord.Interaction):
        """Returns current turn info"""
        await interaction.response.defer()

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        if not game_info["game_running"] or not game_info["game_started"]:
            await interaction.followup.send("This game is either not currently running or has not started. Turn information is unavailable.")
            return

        try:
            raw_status = await bot.nidhogg.query_game_status(game_id, bot.db_instance)
            timer_table = await bot.db_instance.get_game_timer(game_id)

            lines = raw_status.split("\n")
            game_name = lines[2].split(":")[1].strip()
            turn = lines[4].split(":")[1].strip()
            time_left = timer_table["remaining_time"]
            timer_running = timer_table["timer_running"]

            if time_left is None:
                raise ValueError("time_left cannot be None")

            timer_status = "Running" if timer_running else "Paused"

            current_time = datetime.now(timezone.utc)
            future_time = current_time + timedelta(seconds=time_left)
            discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"

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

            embeds = []

            game_info_embed = discord.Embed(
                title=f"Turn {turn}",
                description=(
                    f"Next turn:\n{discord_timestamp} in {descriptive_time_breakdown(time_left)}\n"
                    f"**Timer Status:** {timer_status}"
                ),
                color=discord.Color.blue()
            )
            embeds.append(game_info_embed)

            if played_nations:
                played_embed = discord.Embed(
                    title="✅ Played Nations",
                    description="\n".join(played_nations),
                    color=discord.Color.green()
                )
                embeds.append(played_embed)

            if played_but_not_finished:
                unfinished_embed = discord.Embed(
                    title="⚠️ Unfinished",
                    description="\n".join(played_but_not_finished),
                    color=discord.Color.gold()
                )
                embeds.append(unfinished_embed)

            if undone_nations:
                undone_embed = discord.Embed(
                    title="❌ Undone Nations",
                    description="\n".join(undone_nations),
                    color=discord.Color.red()
                )
                embeds.append(undone_embed)

            await interaction.followup.send(embeds=embeds)

        except Exception as e:
            await interaction.followup.send(f"Error querying turn for game id:{game_id}\n{str(e)}")


    @unclaim_command.autocomplete("nation_name")
    async def unclaim_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Autocomplete handler for the unclaim command 'nation_name' argument."""
        try:
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
            
            all_claimed_nations = list(claimed_nations.keys())

            filtered_nations = [nation for nation in all_claimed_nations if current.lower() in nation.lower()]

            return [app_commands.Choice(name=nation, value=nation) for nation in filtered_nations[:25]]

        except Exception as e:
            print(f"Error in unclaim autocomplete: {e}")
            return []

    @bot.tree.command(
        name="remove",
        description="[Admin/Owner] Removes pretender (.2h) files from unstarted game lobby.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def remove_command(interaction: discord.Interaction, nation_name: str):
        """Allows game owner/admin to remove pretender files from unstarted game lobbies."""
        await interaction.response.defer()

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        # Only allow in unstarted games
        if game_info.get("game_started", False):
            await interaction.followup.send("❌ Cannot remove pretender files after the game has started.")
            return

        try:
            from pathlib import Path
            
            # Get the savedgames path for this game
            dom_data_folder = bot.config.get("dom_data_folder", ".")
            game_name = game_info.get("game_name")
            if not game_name:
                await interaction.followup.send("Game name not found.")
                return
            
            savedgames_path = Path(dom_data_folder) / "savedgames" / game_name
            if not savedgames_path.exists():
                await interaction.followup.send(f"Savedgames directory not found: {savedgames_path}")
                return
            
            # Find the .2h file for this nation
            pretender_files = list(savedgames_path.glob(f"*{nation_name}*.2h"))
            
            if not pretender_files:
                await interaction.followup.send(f"No pretender file found for nation '{nation_name}'.")
                return
            
            # Remove all matching pretender files (in case there are multiple)
            removed_files = []
            for pretender_file in pretender_files:
                try:
                    pretender_file.unlink()
                    removed_files.append(pretender_file.name)
                    if bot.config and bot.config.get("debug", False):
                        print(f"Removed pretender file: {pretender_file}")
                except Exception as e:
                    await interaction.followup.send(f"Failed to remove {pretender_file.name}: {e}")
                    return
            
            if removed_files:
                files_list = "\n".join(f"• {filename}" for filename in removed_files)
                await interaction.followup.send(
                    f"✅ Successfully removed pretender file(s) for '{nation_name}':\n{files_list}"
                )
            else:
                await interaction.followup.send(f"No files were removed for '{nation_name}'.")
                
        except Exception as e:
            await interaction.followup.send(f"Error removing pretender files: {e}")

    @remove_command.autocomplete("nation_name")
    async def remove_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Autocomplete handler for the remove command 'nation_name' argument."""
        try:
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info or game_info.get("game_started", False):
                return []  # Don't show options if game has started
            
            from pathlib import Path
            
            # Get the savedgames path for this game
            dom_data_folder = bot.config.get("dom_data_folder", ".")
            game_name = game_info.get("game_name")
            if not game_name:
                return []
            
            savedgames_path = Path(dom_data_folder) / "savedgames" / game_name
            if not savedgames_path.exists():
                return []
            
            # Find all .2h files and extract nation names
            pretender_files = list(savedgames_path.glob("*.2h"))
            nations_with_files = []
            
            for pretender_file in pretender_files:
                # Extract nation name from filename (format is usually something like "Player_NationName.2h")
                filename = pretender_file.stem  # Remove .2h extension
                # Try to extract nation name - this might need adjustment based on your file naming convention
                if "_" in filename:
                    nation_name = filename.split("_", 1)[1]  # Take everything after first underscore
                else:
                    nation_name = filename  # Use whole filename if no underscore
                
                if nation_name not in nations_with_files:
                    nations_with_files.append(nation_name)
            
            # Filter based on what user is typing
            filtered_nations = [nation for nation in nations_with_files if current.lower() in nation.lower()]
            
            return [app_commands.Choice(name=nation, value=nation) for nation in filtered_nations[:25]]

        except Exception as e:
            if bot.config and bot.config.get("debug", False):
                print(f"Error in remove autocomplete: {e}")
            return []

    @bot.tree.command(
        name="get-turn-save",
        description="Get your .2h and .trn files for the current turn via DM.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def get_turn_save_command(interaction: discord.Interaction):
        """Sends the player's .2h and .trn files for the current turn via DM."""
        await interaction.response.defer(ephemeral=True)
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.", ephemeral=True)
            return
        
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.", ephemeral=True)
            return
        
        player_id = str(interaction.user.id)
        
        try:
            # Check if player has claimed nations in this game
            player_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, player_id)
            if not player_nations:
                await interaction.followup.send("You don't have any nations claimed in this game.", ephemeral=True)
                return
            
            # Use bifrost to create the save file
            temp_zip_path = await bifrost.create_player_turn_save(game_id, player_nations, bot.db_instance, bot.config)
            
            if not temp_zip_path:
                await interaction.followup.send("No save files found or error creating zip.", ephemeral=True)
                return
            
            # Get turn info for filename
            stats_data = await bifrost.read_stats_file(game_id, bot.db_instance, bot.config)
            turn_num = (stats_data.get("turn", 0) + 1) if stats_data else 0
            
            zip_filename = bifrost.get_turn_save_filename(game_info.get("game_name"), turn_num)
            
            try:
                # Send via DM
                try:
                    with open(temp_zip_path, 'rb') as f:
                        discord_file = discord.File(f, filename=zip_filename)
                        await interaction.user.send(
                            f"📁 **Save files for {game_info.get('game_name')} - Turn {turn_num}**\n"
                            f"Your .2h and .trn files are attached.",
                            file=discord_file
                        )
                    
                    await interaction.followup.send(
                        f"✅ Save files sent to your DMs! ({zip_filename})",
                        ephemeral=True
                    )
                    
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ Could not send DM. Please check your privacy settings allow DMs from server members.",
                        ephemeral=True
                    )
                
            finally:
                # Clean up temporary file
                try:
                    import os
                    os.unlink(temp_zip_path)
                except:
                    pass
                    
        except Exception as e:
            await interaction.followup.send(f"Error retrieving save files: {e}", ephemeral=True)

    @bot.tree.command(
        name="get-all-turn-save",
        description="Get all your .2h and .trn files from every turn via DM.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def get_all_turn_save_command(interaction: discord.Interaction):
        """Sends the player's .2h and .trn files from all turns via DM."""
        await interaction.response.defer(ephemeral=True)
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.", ephemeral=True)
            return
        
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.", ephemeral=True)
            return
        
        player_id = str(interaction.user.id)
        
        try:
            # Check if player has claimed nations in this game
            player_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, player_id)
            if not player_nations:
                await interaction.followup.send("You don't have any nations claimed in this game.", ephemeral=True)
                return
            
            # Use bifrost to create the all turns save file
            temp_zip_path = await bifrost.create_player_all_turns_save(game_id, player_nations, bot.db_instance, bot.config)
            
            if not temp_zip_path:
                await interaction.followup.send("No save files found or error creating zip.", ephemeral=True)
                return
            
            zip_filename = bifrost.get_all_turns_save_filename(game_info.get("game_name"))
            
            try:
                # Send via DM
                try:
                    with open(temp_zip_path, 'rb') as f:
                        discord_file = discord.File(f, filename=zip_filename)
                        await interaction.user.send(
                            f"📁 **All turn saves for {game_info.get('game_name')}**\n"
                            f"Your .2h and .trn files from all turns are attached.\n"
                            f"Files are organized by turn folders (turn_1, turn_2, etc.) with current turn in 'current' folder.",
                            file=discord_file
                        )
                    
                    await interaction.followup.send(
                        f"✅ All turn saves sent to your DMs! ({zip_filename})",
                        ephemeral=True
                    )
                    
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ Could not send DM. Please check your privacy settings allow DMs from server members.",
                        ephemeral=True
                    )
                
            finally:
                # Clean up temporary file
                try:
                    import os
                    os.unlink(temp_zip_path)
                except:
                    pass
                    
        except Exception as e:
            await interaction.followup.send(f"Error retrieving all turn saves: {e}", ephemeral=True)

    return [
        claim_command,
        unclaim_command,
        leave_game_command,
        pretenders_command,
        clear_claims_command,
        undone_command,
        remove_command,
        get_turn_save_command,
        get_all_turn_save_command
    ]