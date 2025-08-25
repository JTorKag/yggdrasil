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
            bot = interaction.client  # Access the bot instance from the interaction
            command_name = interaction.command.name  # Get the name of the command being executed
            
            # Wait for bot to be fully ready before processing commands
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return

            # Get allowed bot-specific channels
            primary_bot_channel = list(map(int, config.get("primary_bot_channel", [])))
            allowed_channels = set(primary_bot_channel)

            if command_name == "delete-lobby":
                # Add inactive game channels for the delete-lobby command
                inactive_game_channels = [
                    game["channel_id"]
                    for game in await bot.db_instance.get_inactive_games()
                ]
                allowed_channels.update(inactive_game_channels)
            else:
                # Add active game channels for all other commands
                active_game_channels = await bot.db_instance.get_active_game_channels()
                allowed_channels.update(active_game_channels)

            # Check if the current channel is allowed
            if not allowed_channels or interaction.channel_id in allowed_channels:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the channel is not allowed
            await interaction.response.send_message("This command is not allowed in this channel.", ephemeral=True)
        return wrapper
    return decorator


def require_primary_bot_channel(config):
    """Decorator to restrict commands to the primary bot channel only (not game channels)."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client
            
            # Wait for bot to be fully ready before processing commands
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            # Get primary bot channel only (no game channels)
            primary_bot_channel = list(map(int, config.get("primary_bot_channel", [])))
            allowed_channels = set(primary_bot_channel)

            # Check if the current channel is the primary bot channel
            if interaction.channel_id in allowed_channels:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the channel is not the primary bot channel
            await interaction.response.send_message("This command can only be used in the main bot channel.", ephemeral=True)
        return wrapper
    return decorator


def require_game_channel(config):
    """Decorator to restrict commands to game channels only (not main bot channels)."""
    def decorator(command_func: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        @wraps(command_func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            bot = interaction.client  # Access the bot instance from the interaction
            command_name = interaction.command.name  # Get the name of the command being executed
            
            # Wait for bot to be fully ready before processing commands
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return

            # Get game channels only (no main bot channels)
            allowed_channels = set()

            if command_name == "delete-lobby":
                # Add inactive game channels for the delete-lobby command
                inactive_game_channels = [
                    game["channel_id"]
                    for game in await bot.db_instance.get_inactive_games()
                ]
                allowed_channels.update(inactive_game_channels)
                if config and config.get("debug", False):
                    print(f"[DECORATOR] {command_name} - inactive game channels: {inactive_game_channels}")
            else:
                # Add active game channels only
                active_game_channels = await bot.db_instance.get_active_game_channels()
                allowed_channels.update(active_game_channels)
                if config and config.get("debug", False):
                    print(f"[DECORATOR] {command_name} - active game channels: {active_game_channels}")

            if config and config.get("debug", False):
                print(f"[DECORATOR] {command_name} - current channel: {interaction.channel_id}")
                print(f"[DECORATOR] {command_name} - allowed channels: {allowed_channels}")

            # Check if the current channel is a game channel
            if interaction.channel_id in allowed_channels:
                if config and config.get("debug", False):
                    print(f"[DECORATOR] {command_name} - channel check PASSED")
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the channel is not a game channel
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
            
            # Wait for bot to be fully ready before processing commands
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            # Get the game admin role ID from the config
            admin_role_id = int(config.get("game_admin"))
            # Get the admin role from the guild
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not admin_role:
                # If the role doesn't exist, send an error message
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            # Check if the user has the admin role
            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the user lacks the role
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
            
            # Wait for bot to be fully ready before processing commands
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            # Get the game admin role ID from the config
            admin_role_id = int(config.get("game_admin"))
            # Get the admin role from the guild
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            if not admin_role:
                # If the role doesn't exist, send an error message
                await interaction.response.send_message(
                    "The game admin role is not configured or does not exist.", ephemeral=True
                )
                return

            # Get the game ID associated with the current channel
            game_id = await interaction.client.db_instance.get_game_id_by_channel(interaction.channel_id)
            if not game_id:
                # No game associated with the current channel
                await interaction.response.send_message("No game is associated with this channel.", ephemeral=True)
                return

            # Fetch game info
            game_info = await interaction.client.db_instance.get_game_info(game_id)
            if not game_info:
                # Game information is not found
                await interaction.response.send_message("Game information not found in the database.", ephemeral=True)
                return

            # Check if the user is the game owner (compare by username)
            game_owner = game_info.get("game_owner")
            if game_owner and interaction.user.name == game_owner:
                return await command_func(interaction, *args, **kwargs)

            # Check if the user has the admin role
            if admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the user is neither the game owner nor an admin
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
            
            # Wait for bot to be fully ready before processing commands
            if hasattr(bot, 'bot_ready_signal') and bot.bot_ready_signal and not bot.bot_ready_signal.is_set():
                await interaction.response.send_message("Bot is still starting up, please wait a moment...", ephemeral=True)
                return
                
            # Get the role IDs from the config
            host_role_id = int(config.get("game_host"))
            admin_role_id = int(config.get("game_admin"))

            # Get the roles from the guild
            host_role = discord.utils.get(interaction.guild.roles, id=host_role_id)
            admin_role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
            
            # Check if both roles are missing (configuration error)
            if not host_role and not admin_role:
                await interaction.response.send_message(
                    "Neither the game host nor game admin roles are configured or exist.", ephemeral=True
                )
                return

            # Check if the user has the host role (if it exists)
            if host_role and host_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Check if the user has the admin role (if it exists)
            if admin_role and admin_role in interaction.user.roles:
                return await command_func(interaction, *args, **kwargs)

            # Deny access if the user has neither the host role nor the admin role
            await interaction.response.send_message(
                "You don't have the required permissions to use this command. (Host or Admin role required)",
                ephemeral=True
            )
        
        return wrapper
    return decorator