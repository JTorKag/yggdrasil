"""
Admin-only commands - delete lobby, reset game state, etc.
"""

import discord
from ..decorators import require_bot_channel, require_game_channel, require_game_admin, require_game_owner_or_admin


def register_admin_commands(bot):
    """Register all admin-only commands to the bot's command tree."""
    
    @bot.tree.command(
        name="delete-lobby",
        description="Deletes the game lobby and associated role.",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_owner_or_admin(bot.config)
    async def delete_lobby_command(interaction: discord.Interaction, confirm_game_name: str):
        await interaction.response.defer()
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return
            
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return
            
        if game_info["game_active"]:
            await interaction.followup.send("The game is still active. Please end the game before deleting the lobby.")
            return

        if confirm_game_name != game_info["game_name"]:
            await interaction.followup.send(
                f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
            )
            return

        guild = interaction.guild
        role_id = game_info["role_id"]

        try:
            # Remove role from all members who have it, then delete the role
            if role_id:
                role = discord.utils.get(guild.roles, id=int(role_id))
                if role:
                    # Remove role from all members
                    for member in guild.members:
                        if role in member.roles:
                            try:
                                await member.remove_roles(role)
                                if bot.config and bot.config.get("debug", False):
                                    print(f"[DEBUG] Removed role {role.name} from {member.display_name}")
                            except Exception as e:
                                if bot.config and bot.config.get("debug", False):
                                    print(f"[DEBUG] Failed to remove role from {member.display_name}: {e}")
                    
                    # Delete the role
                    await role.delete()
                    if bot.config and bot.config.get("debug", False):
                        if bot.config and bot.config.get("debug", False):
                            print(f"[DEBUG] Deleted role {role.name}")

            # Keep player records for historical purposes - don't clear them
            
            # Delete timers for this game (no longer needed)
            try:
                async with bot.db_instance.connection.execute("DELETE FROM gameTimers WHERE game_id = ?", (game_id,)) as cursor:
                    await bot.db_instance.connection.commit()
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Deleted timers for game {game_id}")
            except Exception as e:
                if bot.config and bot.config.get("debug", False):
                    if bot.config and bot.config.get("debug", False):
                        print(f"[DEBUG] Failed to delete timers for game {game_id}: {e}")
            
            # Keep game record for historical purposes - don't delete it
            if bot.config and bot.config.get("debug", False):
                if bot.config and bot.config.get("debug", False):
                    print(f"[DEBUG] Preserving game {game_id} record for historical purposes")
            
            # Delete the Discord channel
            channel = interaction.channel
            await channel.delete()
            
        except Exception as e:
            await interaction.followup.send(f"Failed to delete lobby: {e}")

    @bot.tree.command(
        name="reset-game-started",
        description="Resets the game_started flag to allow retrying /start-game after failures (ADMIN ONLY).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_admin(bot.config)
    async def reset_game_started_command(interaction: discord.Interaction, confirm_game_name: str):
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
            
        if not game_info["game_started"]:
            await interaction.followup.send(f"Game '{game_info['game_name']}' is not marked as started - no reset needed.")
            return
            
        try:
            await bot.db_instance.set_game_started_value(game_id, False)
            await interaction.followup.send(
                f"✅ Game '{game_info['game_name']}' has been reset. The game_started flag is now False.\n"
                f"You can now retry `/start-game` to attempt starting the game again."
            )
            if bot.config and bot.config.get("debug", False):
                print(f"[ADMIN] Game ID {game_id} ({game_info['game_name']}) game_started flag reset by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"Failed to reset game_started flag: {e}")

    return [
        delete_lobby_command,
        reset_game_started_command
    ]