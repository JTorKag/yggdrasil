"""
Information commands - game info, version, list games, etc.
"""

import discord
from datetime import datetime, timezone, timedelta
from ..decorators import require_bot_channel, require_primary_bot_channel, require_game_channel
from ..utils import descriptive_time_breakdown


def register_info_commands(bot):
    """Register all information commands to the bot's command tree."""

    @bot.tree.command(
        name="help",
        description="Get help with Yggdrasil commands and documentation.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_bot_channel(bot.config)
    async def help_command(interaction: discord.Interaction):
        """Provides a link to the command documentation on GitHub."""
        embed = discord.Embed(
            title="📚 Yggdrasil Help",
            description=(
                "For a complete list of available commands and their usage, "
                "please visit the Yggdrasil documentation on GitHub."
            ),
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Command Documentation",
            value="[View Discord Slash Commands](https://github.com/JTorKag/yggdrasil?tab=readme-ov-file#discord-slash-commands)",
            inline=False
        )

        embed.add_field(
            name="Full Repository",
            value="[Yggdrasil GitHub Repository](https://github.com/JTorKag/yggdrasil)",
            inline=False
        )

        embed.set_footer(text="All commands and documentation are maintained in the GitHub repository.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="game-info",
        description="Fetches and displays details about the game in this channel.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def game_info_command(interaction: discord.Interaction):
        """
        Fetch and display details about the game in the current channel in a single embed.
        """
        try:
            await interaction.response.defer()

            game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.followup.send("This channel is not associated with an active game.")
                return

            game_info = await bot.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.followup.send(f"No game found with ID {game_id}.")
                return

            server_host = bot.config.get("server_host", "Unknown")

            story_events_map = {0: "None", 1: "Some", 2: "Full"}
            story_events_value = story_events_map.get(game_info["story_events"], "Unknown")

            era_map = {1: "Early", 2: "Middle", 3: "Late"}
            game_era_value = era_map.get(game_info["game_era"], "Unknown")

            embed = discord.Embed(
                title=f"Game Info: {game_info['game_name']}",
                description=f"Details for game ID **{game_id}**",
                color=discord.Color.green(),
            )

            current_turn = "Unknown"
            try:
                from bifrost import bifrost
                stats_data = await bifrost.read_stats_file(game_id, bot.db_instance, bot.config)
                if stats_data:
                    turn_num = stats_data.get("turn", -1)
                    if turn_num == -1:
                        current_turn = "Lobby"
                    else:
                        current_turn = f"Turn {turn_num + 1}"
            except Exception:
                current_turn = "Unknown"

            embed.add_field(
                name="🎯 Current Turn",
                value=current_turn,
                inline=False,
            )

            try:
                timer_data = await bot.db_instance.get_game_timer(game_id)
                player_control_timers = game_info.get('player_control_timers', True)
                chess_clock_active = game_info.get('chess_clock_active', False)
                
                if timer_data:
                    remaining_time = timer_data["remaining_time"]
                    timer_default = timer_data["timer_default"]
                    timer_running = timer_data["timer_running"]
                    
                    remaining_readable = descriptive_time_breakdown(remaining_time) if remaining_time else "Unknown"
                    
                    if game_info.get("game_type", "").lower() == "blitz":
                        default_readable = f"{timer_default / 60:.1f} minutes" if timer_default else "Unknown"
                    else:
                        hours = timer_default / 3600 if timer_default else 0
                        if hours == int(hours):
                            default_readable = f"{int(hours)} hours" if timer_default else "Unknown"
                        else:
                            default_readable = f"{hours:.1f} hours" if timer_default else "Unknown"
                    
                    timer_status = "🟢 Running" if timer_running else "🔴 Paused"
                    extension_rule = "✅ Players can extend timers" if player_control_timers else "❌ Only owner/admin can extend timers"
                    
                    timer_value = (
                        f"**Timer Remaining**: {remaining_readable}\n"
                        f"**Timer Status**: {timer_status}\n"
                        f"**Default Timer**: {default_readable}\n"
                        f"**Extension Rules**: {extension_rule}"
                    )
                    
                    if chess_clock_active:
                        starting_time = game_info.get('chess_clock_starting_time', 0)
                        per_turn_time = game_info.get('chess_clock_per_turn_time', 0)
                        
                        game_type = game_info.get('game_type', '').lower()
                        if game_type == 'blitz':
                            starting_display = f"{starting_time / 60:.1f} minutes"
                            per_turn_display = f"{per_turn_time / 60:.1f} minutes"
                        else:
                            starting_display = f"{starting_time / 3600:.1f} hours"
                            per_turn_display = f"{per_turn_time / 3600:.1f} hours"
                        
                        timer_value += (
                            f"\n\n**♟️ Chess Clock**: ✅ Active\n"
                            f"**Starting Time**: {starting_display}\n"
                            f"**Per-Turn Bonus**: {per_turn_display}"
                        )
                    
                    embed.add_field(
                        name="⏰ Timer Status",
                        value=timer_value,
                        inline=False,
                    )
                else:
                    extension_rule = "✅ Players can extend timers" if player_control_timers else "❌ Only owner/admin can extend timers"
                    timer_value = f"No timer configured\n**Extension Rules**: {extension_rule}"
                    
                    if chess_clock_active:
                        starting_time = game_info.get('chess_clock_starting_time', 0)
                        per_turn_time = game_info.get('chess_clock_per_turn_time', 0)
                        
                        game_type = game_info.get('game_type', '').lower()
                        if game_type == 'blitz':
                            starting_display = f"{starting_time / 60:.1f} minutes"
                            per_turn_display = f"{per_turn_time / 60:.1f} minutes"
                        else:
                            starting_display = f"{starting_time / 3600:.1f} hours"
                            per_turn_display = f"{per_turn_time / 3600:.1f} hours"
                        
                        timer_value += (
                            f"\n\n**♟️ Chess Clock**: ✅ Active\n"
                            f"**Starting Time**: {starting_display}\n"
                            f"**Per-Turn Bonus**: {per_turn_display}"
                        )
                    
                    embed.add_field(
                        name="⏰ Timer Status",
                        value=timer_value,
                        inline=False,
                    )
            except Exception as e:
                extension_rule = "✅ Players can extend timers" if game_info.get('player_control_timers', True) else "❌ Only owner/admin can extend timers"
                embed.add_field(
                    name="⏰ Timer Status",
                    value=f"Error fetching timer data\n**Extension Rules**: {extension_rule}",
                    inline=False,
                )

            # Extract just the .dm filenames from mods (everything after the last /)
            mods_raw = game_info['game_mods']
            if mods_raw and mods_raw != "None":
                # Split by comma, extract filename after /, rejoin
                mod_list = [mod.strip() for mod in mods_raw.split(',')]
                mod_names = [mod.split('/')[-1] if '/' in mod else mod for mod in mod_list]
                mods_display = ', '.join(mod_names)
            else:
                mods_display = game_info['game_mods']

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
                    f"🔧 **Mods**: {mods_display}\n"
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
                    f"**Story Events**: {story_events_value}\n"
                    f"**No Going AI**: {'True' if game_info['no_going_ai'] else 'False'}\n"
                    f"**Team Game**: {'True' if game_info['teamgame'] else 'False'}\n"
                    f"**Clustered Starts**: {'True' if game_info['clustered'] else 'False'}\n"
                    f"**Edge Starts**: {'True' if game_info['edgestart'] else 'False'}\n"
                    f"**No Artifact Restrictions**: {'True' if game_info['noartrest'] else 'False'}\n"
                    f"**No Level 9 Restrictions**: {'True' if game_info['nolvl9rest'] else 'False'}\n"
                    f"**Diplomacy**: {game_info.get('diplo', 'Disabled')}\n"
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

            embed.add_field(
                name="Game State",
                value=(
                    f"**Game Running**: {'True' if game_info['game_running'] else 'False'}\n"
                    f"**Game Started**: {'True' if game_info['game_started'] else 'False'}\n"
                    f"**Game Active**: {'True' if game_info['game_active'] else 'False'}"
                ),
                inline=False,
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")

    @bot.tree.command(
        name="get-version",
        description="Gets the current version of Dominions running on the server.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_bot_channel(bot.config)
    async def get_version_command(interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            version_info = bot.nidhogg.get_version()
            
            await interaction.followup.send(f"Dominions Server Version: `{version_info}`", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error fetching version: {e}", ephemeral=True)

    @bot.tree.command(
        name="list-active-games",
        description="Lists all active games on the server.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    async def list_active_games_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            active_games = await bot.db_instance.get_active_games()
            if not active_games:
                await interaction.followup.send("There are currently no active games.", ephemeral=True)
                return

            embed = discord.Embed(
                title="Active Games on Server",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            for game in active_games:
                game_id = game['game_id']
                game_name = game['game_name']
                
                timer_info = await bot.db_instance.get_game_timer(game_id)
                timer_text = "No timer info"
                
                if timer_info:
                    remaining_time = timer_info.get('remaining_time', 0)
                    default_timer = timer_info.get('timer_default', 0) 
                    timer_running = timer_info.get('timer_running', False)
                    
                    remaining_text = descriptive_time_breakdown(remaining_time) if remaining_time > 0 else "Timer expired"
                    
                    default_text = descriptive_time_breakdown(default_timer) if default_timer > 0 else "Not set"
                    
                    status = "Running" if timer_running else "⏸️ Paused"
                    
                    timer_text = f"**Current:** {remaining_text}\n**Default:** {default_text}\n**Status:** {status}"
                
                game_info_text = f"**Owner:** {game.get('game_owner', 'Unknown')}\n**Era:** {game.get('game_era', 'Unknown')}\n**Type:** {game.get('game_type', 'Unknown')}"
                
                embed.add_field(
                    name=f"🎮 {game_name} (ID: {game_id})",
                    value=f"{game_info_text}\n\n**Timer Info:**\n{timer_text}",
                    inline=True
                )

            embed.set_footer(text=f"Total: {len(active_games)} active game(s)")

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    return [
        help_command,
        game_info_command,
        get_version_command,
        list_active_games_command
    ]