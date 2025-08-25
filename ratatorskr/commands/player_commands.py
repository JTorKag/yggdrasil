"""
Player-related commands - claiming nations, managing pretenders, etc.
"""

import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import List
from bifrost import bifrost
from ..decorators import require_bot_channel, require_game_channel, require_game_owner_or_admin, require_game_admin


def register_player_commands(bot):
    """Register all player-related commands to the bot's command tree."""
    
    @bot.tree.command(
        name="claim",
        description="Claims a nation in the game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def claim_command(interaction: discord.Interaction, nation_name: str):
        """Allows a user to claim a nation in the game."""
        await interaction.response.defer()

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        # Get game information
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        # Get the 2h files and validate the claimed nation
        try:
            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            if nation_name not in valid_nations:
                await interaction.followup.send(f"{nation_name} is not a valid nation for this game.")
                return

            # Check if the player currently owns the nation
            currently_owns = await bot.db_instance.check_player_nation(game_id, str(interaction.user.id), nation_name)
            if currently_owns:
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

            # Check if the player previously owned this nation but left the game
            previously_owned = await bot.db_instance.check_player_previously_owned(game_id, str(interaction.user.id), nation_name)
            if previously_owned:
                # Check if player has any currently claimed nations (for chess clock logic)
                player_has_nations = await bot.db_instance.player_has_claimed_nations(game_id, str(interaction.user.id))
                
                # Re-claim the nation instead of creating a new record
                await bot.db_instance.reclaim_nation(game_id, str(interaction.user.id), nation_name)
                print(f"Player {interaction.user.name} reclaimed nation {nation_name} in game {game_id}.")
                
                # Initialize chess clock time if chess clock mode is active and they have no other nations
                chess_clock_time = 0
                chess_clock_active = game_info.get("chess_clock_active", False)
                if chess_clock_active and not player_has_nations:
                    chess_clock_time = game_info.get("chess_clock_starting_time", 0)
                    await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), chess_clock_time)

                # Create or fetch the role and assign it to the player
                guild = interaction.guild
                role_name = f"{game_info['game_name']} player"

                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    # Create the role
                    role = await guild.create_role(name=role_name)
                    print(f"Role '{role_name}' created successfully.")

                # Assign the role to the player if they don't already have it
                if role not in interaction.user.roles:
                    await interaction.user.add_roles(role)
                    print(f"Assigned role '{role_name}' to user {interaction.user.name}.")

                # Create success message
                message = f"✅ **Welcome back!** You have **re-claimed** {nation_name} and have been assigned the role '{role_name}'."
                
                # Add chess clock info if applicable
                if chess_clock_active and chess_clock_time > 0:
                    if game_info.get("game_type", "").lower() == "blitz":
                        time_display = f"{chess_clock_time / 60:.1f} minutes"
                    else:
                        time_display = f"{chess_clock_time / 3600:.1f} hours"
                    message += f"\n⏱️ Your chess clock time has been reset to {time_display}."
                elif chess_clock_active and player_has_nations:
                    message += f"\n⏱️ Chess clock time unchanged (you already have nations claimed)."
                
                await interaction.followup.send(message)
                return

            # Check if player already has claimed nations (for chess clock logic)
            player_has_nations = await bot.db_instance.player_has_claimed_nations(game_id, str(interaction.user.id))
            
            # Calculate chess clock time to initialize
            chess_clock_time = 0
            chess_clock_active = game_info.get("chess_clock_active", False)
            if chess_clock_active and not player_has_nations:
                # Only set starting time if this is their first nation in the game
                chess_clock_time = game_info.get("chess_clock_starting_time", 0)

            # Add player to the database
            try:
                await bot.db_instance.add_player(game_id, str(interaction.user.id), nation_name, chess_clock_time)
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

            # Create success message
            message = f"You have successfully claimed {nation_name} and have been assigned the role '{role_name}'."
            
            # Add chess clock info if applicable
            if chess_clock_active and chess_clock_time > 0:
                if game_info.get("game_type", "").lower() == "blitz":
                    time_display = f"{chess_clock_time / 60:.1f} minutes"
                else:
                    time_display = f"{chess_clock_time / 3600:.1f} hours"
                message += f"\n⏱️ You have been given {time_display} of chess clock time."
            elif chess_clock_active and player_has_nations:
                message += f"\n⏱️ Chess clock time unchanged (you already have nations claimed)."
            
            await interaction.followup.send(message)
        except Exception as e:
            await interaction.followup.send(f"Failed to claim the nation: {e}")

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

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        # Get game information
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        # Find who currently has this nation claimed
        try:
            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
            player_ids = claimed_nations.get(nation_name, [])
            
            if not player_ids:
                await interaction.followup.send(f"Nation '{nation_name}' is not currently claimed by anyone.")
                return
            
            # For simplicity, unclaim from the first player who has it
            # (In normal cases, there should only be one player per nation)
            target_player_id = player_ids[0]
            
            # Completely remove the nation entry from database
            rows_deleted = await bot.db_instance.delete_player_nation(game_id, target_player_id, nation_name)
            
            if rows_deleted == 0:
                await interaction.followup.send(f"No matching record found for nation '{nation_name}' and the target player.")
                return
            
            # Get the target player's Discord member object
            guild = interaction.guild
            target_member = None
            if guild:
                target_member = guild.get_member(int(target_player_id))
            
            # Remove role from the player if they exist and have no other claimed nations
            role_removed = False
            if target_member:
                game_name = game_info["game_name"]
                role_name = f"{game_name} player"
                role = discord.utils.get(guild.roles, name=role_name)
                
                if role and role in target_member.roles:
                    # Check if player has any other nations claimed in this game
                    remaining_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, target_player_id)
                    
                    if not remaining_nations:  # No other nations claimed
                        try:
                            await target_member.remove_roles(role)
                            role_removed = True
                        except discord.Forbidden:
                            pass  # Ignore permission errors for role removal
            
            # Create response message
            target_display = target_member.display_name if target_member else f"Player ID {target_player_id}"
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

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        # Get game information
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        player_id = str(interaction.user.id)
        
        try:
            # Get all nations this player currently has claimed
            player_nations = await bot.db_instance.get_claimed_nations_by_player(game_id, player_id)
            
            if not player_nations:
                await interaction.followup.send("You don't have any nations claimed in this game.", ephemeral=True)
                return
            
            # Unclaim all their nations
            unclaimed_nations = []
            for nation in player_nations:
                try:
                    await bot.db_instance.unclaim_nation(game_id, player_id, nation)
                    unclaimed_nations.append(nation)
                except Exception as e:
                    print(f"Error unclaiming {nation} for player {player_id}: {e}")
            
            # Remove the player role
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
                        pass  # Ignore permission errors
            
            # Create response message
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

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        print(f"Retrieved game ID: {game_id}")  # Debugging log
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        try:
            print(f"Fetching pretenders for game ID: {game_id}")
            
            # Get the valid nations
            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            # Build the response
            embed = discord.Embed(title="Pretender Nations", color=discord.Color.blue())

            # Get claimed nations
            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
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
            # Get the game ID and validate
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("No game is associated with this channel.")
                return

            game_info = await bot.db_instance.get_game_info(game_id)
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
            players = await bot.db_instance.get_players_in_game(game_id)
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
            await bot.db_instance.clear_players(game_id)

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

    @bot.tree.command(
        name="undone",
        description="Shows players that have not taken their turn yet.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def undone_command(interaction: discord.Interaction):
        """Returns current turn info"""
        await interaction.response.defer()

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        # Get game info
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        # Reject if the game is not running or not started
        if not game_info["game_running"] or not game_info["game_started"]:
            await interaction.followup.send("This game is either not currently running or has not started. Turn information is unavailable.")
            return

        try:
            raw_status = await bot.nidhogg.query_game_status(game_id, bot.db_instance)
            timer_table = await bot.db_instance.get_game_timer(game_id)

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

            # Create embeds
            embeds = []

            # Game Info embed
            game_info_embed = discord.Embed(
                title=f"Turn {turn}",
                description=(
                    f"Next turn:\n{discord_timestamp} in {descriptive_time_breakdown(time_left)}\n"
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

    @claim_command.autocomplete("nation_name")
    async def autocomplete_nation(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Autocomplete handler for the 'nation_name' argument."""
        try:
            # Get the game ID associated with the current channel
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            # Retrieve the list of valid nations for the game
            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            # Filter the nations by the current input
            filtered_nations = [nation for nation in valid_nations if current.lower() in nation.lower()]

            # Return the autocomplete choices (Discord limits to 25 items)
            return [app_commands.Choice(name=nation, value=nation) for nation in filtered_nations[:25]]

        except Exception as e:
            print(f"Error in claim autocomplete: {e}")
            return []

    @unclaim_command.autocomplete("nation_name")
    async def unclaim_autocomplete(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Autocomplete handler for the unclaim command 'nation_name' argument."""
        try:
            # Get the game ID associated with the current channel
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            # Get all currently claimed nations in the game
            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
            
            # Extract all nation names that are currently claimed
            all_claimed_nations = list(claimed_nations.keys())

            # Filter the nations based on the current input
            filtered_nations = [nation for nation in all_claimed_nations if current.lower() in nation.lower()]

            # Return the autocomplete choices (Discord limits to 25 items)
            return [app_commands.Choice(name=nation, value=nation) for nation in filtered_nations[:25]]

        except Exception as e:
            print(f"Error in unclaim autocomplete: {e}")
            return []

    return [
        claim_command,
        unclaim_command,
        leave_game_command,
        pretenders_command,
        clear_claims_command,
        undone_command
    ]