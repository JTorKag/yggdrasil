"""
Main Discord client for the Ratatorskr bot.
"""

import discord
from discord import app_commands
from .utils import descriptive_time_breakdown
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .commands import (
    game_management,
    timer_commands,
    player_commands,
    admin_commands,
    file_commands,
    info_commands
)


class discordClient(discord.Client):
    def __init__(self, *, intents, db_instance, bot_ready_signal, config: dict, nidhogg):
        if config and config.get("debug", False):
            print("[CLIENT] Initializing Discord client...")
        super().__init__(intents=intents)
        if config and config.get("debug", False):
            print("[CLIENT] Discord client base initialized")
        self.tree = app_commands.CommandTree(self)
        if config and config.get("debug", False):
            print("[CLIENT] Command tree created")
        self.guild_id = config["guild_id"]
        self.db_instance = db_instance
        self.bot_ready_signal = bot_ready_signal
        self.category_id = config["category_id"]
        self.bot_channels = list(map(int, config.get("primary_bot_channel", [])))
        self.config = config
        self.nidhogg = nidhogg
        if config and config.get("debug", False):
            print("[CLIENT] Discord client initialization complete")
   
    def descriptive_time_breakdown(self, seconds: int) -> str:
        """
        Format a duration in seconds into a descriptive breakdown.

        Args:
            seconds (int): The total duration in seconds.

        Returns:
            str: A descriptive breakdown of the duration.
        """
        return descriptive_time_breakdown(seconds)

    async def send_game_message(self, game_id: int, message: str):
        """
        Handles sending a message to the correct Discord channel based on the game ID.

        Args:
            game_id (int): The ID of the game.
            message (str): The message to send.

        Returns:
            dict: A response dictionary indicating success or failure.
        """
        try:
            channel_id = await self.db_instance.get_channel_id_by_game(game_id)
            print(f"Channel ID for game {game_id}: {channel_id}")
            if not channel_id:
                return {"status": "error", "message": "Invalid game ID or channel not found"}

            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if channel:
                await channel.send(message)
                return {"status": "success", "message": "Message sent"}
            else:
                return {"status": "error", "message": "Unable to find the channel"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def on_raw_reaction_add(self, payload):
        """
        Handles the addition of a reaction to a message. Pins the message if the 📌 emoji is used.
        """
        if payload.emoji.name == "📌":
            channel = self.get_channel(payload.channel_id) or await self.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            if not message.pinned:
                try:
                    await message.pin()
                except discord.Forbidden:
                    print(f"Permission denied to pin messages in channel {channel.name}.")
                except discord.HTTPException as e:
                    print(f"Failed to pin message: {e}")

    async def on_raw_reaction_remove(self, payload):
        """
        Handles the removal of a reaction from a message. Unpins the message if the 📌 emoji is removed.
        """
        if payload.emoji.name == "📌":
            channel = self.get_channel(payload.channel_id) or await self.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            if message.pinned:
                try:
                    await message.unpin()
                    print(f"Unpinned message: {message.content}")
                except discord.Forbidden:
                    print(f"Permission denied to unpin messages in channel {channel.name}.")
                except discord.HTTPException as e:
                    print(f"Failed to unpin message: {e}")

    async def setup_hook(self):
        """
        Register all commands from the various command modules.
        """
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Starting setup_hook...")
        
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Registering game management commands...")
        game_management.register_game_management_commands(self)
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Registering timer commands...")
        timer_commands.register_timer_commands(self)
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Registering player commands...")
        player_commands.register_player_commands(self)
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Registering admin commands...")
        admin_commands.register_admin_commands(self)
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Registering file commands...")
        file_commands.register_file_commands(self)
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Registering info commands...")
        info_commands.register_info_commands(self)
        if self.config and self.config.get("debug", False):
            print("[CLIENT] All commands registered")
        
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Syncing command tree with Discord...")
        await self.tree.sync(guild=discord.Object(id=self.guild_id))
        print("Commands synced!")
        
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Setting bot ready signal...")
        if self.bot_ready_signal:
            self.bot_ready_signal.set()
        if self.config and self.config.get("debug", False):
            print("[CLIENT] Setup hook complete!")