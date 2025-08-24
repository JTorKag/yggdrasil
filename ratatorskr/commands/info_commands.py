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
        name="game-info",
        description="Shows information about the current game.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    async def game_info_command(interaction: discord.Interaction):
        await interaction.response.send_message("Game info command - implementation needed", ephemeral=True)

    @bot.tree.command(
        name="get-version",
        description="Gets the current version of Dominions running on the server.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_bot_channel(bot.config)
    async def get_version_command(interaction: discord.Interaction):
        await interaction.response.send_message("Get version command - implementation needed", ephemeral=True)

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

            # Create an embed for better formatting
            embed = discord.Embed(
                title="Active Games on Server",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            for game in active_games:
                game_id = game['game_id']
                game_name = game['game_name']
                
                # Get timer information
                timer_info = await bot.db_instance.get_game_timer(game_id)
                timer_text = "No timer info"
                
                if timer_info:
                    remaining_time = timer_info.get('remaining_time', 0)
                    default_timer = timer_info.get('timer_default', 0) 
                    timer_running = timer_info.get('timer_running', False)
                    
                    # Format remaining time
                    remaining_text = descriptive_time_breakdown(remaining_time) if remaining_time > 0 else "Timer expired"
                    
                    # Format default timer
                    default_text = descriptive_time_breakdown(default_timer) if default_timer > 0 else "Not set"
                    
                    # Status
                    status = "Running" if timer_running else "⏸️ Paused"
                    
                    timer_text = f"**Current:** {remaining_text}\n**Default:** {default_text}\n**Status:** {status}"
                
                # Game info
                game_info_text = f"**Owner:** {game.get('game_owner', 'Unknown')}\n**Era:** {game.get('game_era', 'Unknown')}\n**Type:** {game.get('game_type', 'Unknown')}"
                
                # Add field for each game
                embed.add_field(
                    name=f"🎮 {game_name} (ID: {game_id})",
                    value=f"{game_info_text}\n\n**Timer Info:**\n{timer_text}",
                    inline=True
                )

            # Add footer with total count
            embed.set_footer(text=f"Total: {len(active_games)} active game(s)")

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    return [
        game_info_command,
        get_version_command,
        list_active_games_command
    ]