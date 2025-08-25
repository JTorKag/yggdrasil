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

        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found in the database.")
            return

        try:
            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            if nation_name not in valid_nations:
                await interaction.followup.send(f"{nation_name} is not a valid nation for this game.")
                return

            currently_owns = await bot.db_instance.check_player_nation(game_id, str(interaction.user.id), nation_name)
            if currently_owns:
                guild = interaction.guild
                role_name = f"{game_info['game_name']} player"
                role = discord.utils.get(guild.roles, name=role_name)

                if not role:
                    role = await guild.create_role(name=role_name)
                    print(f"\nRole '{role_name}' created successfully.")

                if role not in interaction.user.roles:
                    await interaction.user.add_roles(role)
                    print(f"Assigned role '{role_name}' to user {interaction.user.name}.")
                    await interaction.followup.send(f"You already own {nation_name}, but the role '{role_name}' has been assigned to you.")
                else:
                    await interaction.followup.send(f"You already own {nation_name} and have the role '{role_name}'.")

                return

            previously_owned = await bot.db_instance.check_player_previously_owned(game_id, str(interaction.user.id), nation_name)
            if previously_owned:
                player_has_nations = await bot.db_instance.player_has_claimed_nations(game_id, str(interaction.user.id))
                
                await bot.db_instance.reclaim_nation(game_id, str(interaction.user.id), nation_name)
                print(f"Player {interaction.user.name} reclaimed nation {nation_name} in game {game_id}.")
                
                chess_clock_time = 0
                chess_clock_active = game_info.get("chess_clock_active", False)
                if chess_clock_active and not player_has_nations:
                    chess_clock_time = game_info.get("chess_clock_starting_time", 0)
                    await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), chess_clock_time)

                guild = interaction.guild
                role_name = f"{game_info['game_name']} player"

                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    role = await guild.create_role(name=role_name)
                    print(f"Role '{role_name}' created successfully.")

                if role not in interaction.user.roles:
                    await interaction.user.add_roles(role)
                    print(f"Assigned role '{role_name}' to user {interaction.user.name}.")

                message = f"✅ **Welcome back!** You have **re-claimed** {nation_name} and have been assigned the role '{role_name}'."
                
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

            player_has_nations = await bot.db_instance.player_has_claimed_nations(game_id, str(interaction.user.id))
            
            chess_clock_time = 0
            chess_clock_active = game_info.get("chess_clock_active", False)
            if chess_clock_active and not player_has_nations:
                chess_clock_time = game_info.get("chess_clock_starting_time", 0)

            try:
                await bot.db_instance.add_player(game_id, str(interaction.user.id), nation_name, chess_clock_time)
                print(f"Added player {interaction.user.name} as {nation_name} in game {game_id}.")
            except Exception as e:
                await interaction.followup.send(f"Failed to add you as {nation_name} in the database: {e}")
                return

            guild = interaction.guild
            role_name = f"{game_info['game_name']} player"

            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                role = await guild.create_role(name=role_name)
                print(f"Role '{role_name}' created successfully.")

            await interaction.user.add_roles(role)
            print(f"Assigned role '{role_name}' to user {interaction.user.name}.")

            message = f"You have successfully claimed {nation_name} and have been assigned the role '{role_name}'."
            
            if chess_clock_active:
                starting_time = game_info.get("chess_clock_starting_time", 0)
                if starting_time > 0:
                    if game_info.get("game_type", "").lower() == "blitz":
                        time_display = f"{starting_time / 60:.1f} minutes"
                    else:
                        time_display = f"{starting_time / 3600:.1f} hours"
                    message += f"\n⏱️ You will receive {time_display} of chess clock time when the game starts."
            
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
            if guild:
                target_member = guild.get_member(int(target_player_id))
            
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
            
            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            embed = discord.Embed(title="Pretender Nations", color=discord.Color.blue())

            claimed_nations = await bot.db_instance.get_claimed_nations(game_id)
            for nation in valid_nations:
                claimants = claimed_nations.get(nation, [])
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
                    title="⚠️ Played But Not Finished",
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

    @claim_command.autocomplete("nation_name")
    async def autocomplete_nation(
        interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice]:
        """Autocomplete handler for the 'nation_name' argument."""
        try:
            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                return []

            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            filtered_nations = [nation for nation in valid_nations if current.lower() in nation.lower()]

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

    return [
        claim_command,
        unclaim_command,
        leave_game_command,
        pretenders_command,
        clear_claims_command,
        undone_command
    ]