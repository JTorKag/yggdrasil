"""
Player-related commands - claiming nations, managing pretenders, etc.
"""

import discord
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

        # Get the 2h files and validate the claimed nation
        try:
            valid_nations = await bifrost.get_valid_nations_from_files(game_id, bot.config, bot.db_instance)

            if nation_name not in valid_nations:
                await interaction.followup.send(f"{nation_name} is not a valid nation for this game.")
                return

            # Check if the player already owns the nation
            already_exists = await bot.db_instance.check_player_nation(game_id, str(interaction.user.id), nation_name)
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
                await bot.db_instance.add_player(game_id, str(interaction.user.id), nation_name)
                print(f"Added player {interaction.user.name} as {nation_name} in game {game_id}.")
            except Exception as e:
                await interaction.followup.send(f"Failed to add you as {nation_name} in the database: {e}")
                return

            # Initialize chess clock time if chess clock mode is active
            chess_clock_active = game_info.get("chess_clock_active", False)
            if chess_clock_active:
                starting_time = game_info.get("chess_clock_starting_time", 0)
                await bot.db_instance.update_player_chess_clock_time(game_id, str(interaction.user.id), starting_time)

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
            if chess_clock_active and starting_time > 0:
                if game_info.get("game_type", "").lower() == "blitz":
                    time_display = f"{starting_time / 60:.1f} minutes"
                else:
                    time_display = f"{starting_time / 3600:.1f} hours"
                message += f"\n⏱️ You have been given {time_display} of chess clock time."
            
            await interaction.followup.send(message)
        except Exception as e:
            await interaction.followup.send(f"Failed to claim the nation: {e}")

    @bot.tree.command(
        name="unclaim",
        description="Unclaims your nation in the game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def unclaim_command(interaction: discord.Interaction, nation_name: str):
        """Allows a player to unclaim a nation."""
        await interaction.response.defer()

        # Get the game ID associated with the current channel
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game is associated with this channel.")
            return

        # Get game information
        game_info = await bot.db_instance.get_game_info(game_id)
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
            await bot.db_instance.unclaim_nation(game_id, str(interaction.user.id), nation_name)
            await interaction.followup.send(f"Role '{role_name}' has been removed from you, and nation '{nation_name}' has been unclaimed.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to remove this role.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred while removing the role: {e}", ephemeral=True)

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

    return [
        claim_command,
        unclaim_command,
        pretenders_command,
        clear_claims_command,
        undone_command
    ]