"""
Decorators for Discord command permission and channel restrictions.
"""

import discord
from functools import wraps
from typing import Callable, Awaitable


def require_bot_channel(config):
    """Decorator to restrict commands to bot-specific channels or channels linked to active or inactive games."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            command_name = interaction.command.name
            
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return

            primary_bot_channel = list(map(int, config.get("primary_bot_channel", [])))
            allowed_channels = set(primary_bot_channel)

            if command_name == "delete-lobby":
                inactive_game_channels = [
                    game["channel_id"]
                    for game in await bot.db_instance.get_inactive_games()
                ]
                allowed_channels.update(inactive_game_channels)
            else:
                active_game_channels = await bot.db_instance.get_active_game_channels()
                allowed_channels.update(active_game_channels)

            if not allowed_channels or interaction.channel_id in allowed_channels:
                return await command_func(interaction, *args, **kwargs)

            await interaction.response.send_message("This command is not allowed in this channel.", ephemeral=True)
        return wrapper
    return decorator


def require_primary_bot_channel(config):
    """Decorator to restrict commands to the primary bot channel only (not game channels)."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            primary_bot_channel = list(map(int, config.get("primary_bot_channel", [])))
            allowed_channels = set(primary_bot_channel)

            if interaction.channel_id in allowed_channels:
                return await command_func(interaction, *args, **kwargs)

            await interaction.response.send_message("This command can only be used in the main bot channel.", ephemeral=True)
        return wrapper
    return decorator


def require_game_channel(config):
    """Decorator to restrict commands to game channels only (not main bot channels)."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            command_name = interaction.command.name
            
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return

            allowed_channels = set()

            # Game commands should work in any active game channel
            active_game_channels = await bot.db_instance.get_active_game_channels()
            allowed_channels.update(active_game_channels)
            if config and config.get("debug", False):
                print(f"[DECORATOR] {command_name} - active game channels: {active_game_channels}")

            if config and config.get("debug", False):
                print(f"[DECORATOR] {command_name} - current channel: {interaction.channel_id}")
                print(f"[DECORATOR] {command_name} - allowed channels: {allowed_channels}")

            if interaction.channel_id in allowed_channels:
                if config and config.get("debug", False):
                    print(f"[DECORATOR] {command_name} - channel check PASSED")
                return await command_func(interaction, *args, **kwargs)

            if config and config.get("debug", False):
                print(f"[DECORATOR] {command_name} - channel check FAILED")
            await interaction.response.send_message("This command can only be used in game channels.", ephemeral=True)
        return wrapper
    return decorator


def require_game_admin(config):
    """Decorator to restrict commands to users with the game_admin role."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            admin_role_id = int(config.get("game_admin"))
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not admin_role:
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            await interaction.response.send_message(
                "You don't have the required permissions to use this command.", ephemeral=True
            )
        
        return wrapper
    return decorator


def require_game_owner_or_admin(config):
    """Decorator to restrict commands to the game owner or users with the game_admin role."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            admin_role_id = int(config.get("game_admin"))
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not admin_role:
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            game_id = await interaction.client.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                await interaction.response.send_message("No game is associated with this channel.", ephemeral=True)
                return

            game_info = await interaction.client.db_instance.get_game_info(game_id)
            if not game_info:
                await interaction.response.send_message("Game information not found in the database.", ephemeral=True)
                return

            game_owner = game_info.get("game_owner")
            if game_owner and interaction.user.name == game_owner:
                return await command_func(interaction, *args, **kwargs)

            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            await interaction.response.send_message(
                "You don't have the required permissions to use this command. (Owner or Admin role required)",
                ephemeral=True
            )
        
        return wrapper
    return decorator


def require_game_host_or_admin(config):
    """Decorator to restrict commands to users with the game_host role or game_admin role."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            host_role_id = int(config.get("game_host"))
            admin_role_id = int(config.get("game_admin"))

            host_role = discord.utils.get(interaction.guild.roles, id=host_role_id)
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not host_role and not admin_role:
                await interaction.response.send_message(
                    "Neither the game host nor game admin roles are configured or exist.", ephemeral=True
                )
                return

            if host_role and host_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            if admin_role and admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            await interaction.response.send_message(
                "You don't have the required permissions to use this command. (Host or Admin role required)",
                ephemeral=True
            )
        
        return wrapper
    return decorator