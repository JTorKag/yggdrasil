#timer manager

import time 
import asyncio
import discord

class TimerManager:
    def __init__(self, db_instance, nidhogg, config, discord_bot):
        """
        Initialize TimerManager with the shared db_instance, nidhogg, config, and discord_bot.
        """
        self.db_instance = db_instance
        self.nidhogg = nidhogg
        self.config = config
        self.discord_bot = discord_bot  # Add discord_bot to TimerManager
        self.running = True
        self.error_logged = False

    async def start_timers(self):
        """
        Main loop to periodically update timers and handle resets at the start of new turns.
        """
        while self.running:
            try:
                # Fetch all active timers
                active_timers = await self.db_instance.get_active_timers()

                for timer in active_timers:
                    game_id = timer["game_id"]
                    remaining_time = timer["remaining_time"]

                    # Fetch game_running status for the game
                    game_info = await self.db_instance.get_game_info(game_id)
                    if not game_info or not game_info.get("game_running", False):
                        continue  # Skip this timer if the game is not running

                    # Decrement the remaining time
                    new_remaining_time = max(0, remaining_time - 1)

                    if new_remaining_time == 3600:  # Check if timer hits 1 hour
                        print(f"[DEBUG] Timer for game ID {game_id} hit 1 hour. Checking for unplayed nations.")
                        await self.alert_unplayed_nations(game_id, game_info)

                    if new_remaining_time == 0:
                        print(f"[DEBUG] Timer for game ID {game_id} reached 0. Forcing host.")
                        try:
                            # Force the game to host
                            await self.nidhogg.force_game_host(game_id, self.config, self.db_instance)

                            # Reset the timer for the new turn
                            await self.db_instance.reset_timer_for_new_turn(game_id)
                            print(f"[DEBUG] Timer for game ID {game_id} reset for the next turn.")
                        except Exception as e:
                            print(f"[ERROR] Failed to force host for game ID {game_id}: {e}")
                    else:
                        # Update the timer in the database
                        await self.db_instance.update_timer(game_id, new_remaining_time, True)

            except Exception as e:
                if not self.error_logged:
                    print(f"[ERROR] TimerManager encountered an issue: {e}")
                    self.error_logged = True

            # Wait 1 second between updates
            await asyncio.sleep(1)

    async def alert_unplayed_nations(self, game_id: int, game_info: dict):
        """
        Alerts the lobby if there are any nations left totally unplayed when the timer hits 1 hour.
        """
        try:
            raw_status = await self.nidhogg.query_game_status(game_id, self.db_instance)
            lines = raw_status.split("\n")

            # Extract unplayed nations
            unplayed_nations = []
            for line in lines[6:]:
                if "(-)" in line:  # Indicates unplayed nations
                    nation = line.split(":")[1].split(",")[0].strip()
                    unplayed_nations.append(nation)

            if unplayed_nations:
                channel_id = game_info.get("channel_id")
                if not channel_id:
                    print(f"[DEBUG] Game ID {game_id} has no associated channel ID.")
                    return

                # Fetch the Discord channel
                channel = self.discord_bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.discord_bot.fetch_channel(int(channel_id))

                # Prepare the embed with unplayed nations
                embed = discord.Embed(
                    title=f"⏳ Timer Warning for '{game_info['game_name']}'",
                    description=(
                        f"The timer is down to **1 hour**, and the following nations remain unplayed:\n\n"
                        f"{', '.join(unplayed_nations)}\n\n"
                        "Please take action to avoid being skipped!"
                    ),
                    color=discord.Color.orange()
                )
                embed.set_footer(text=f"Game ID: {game_id}")
                embed.timestamp = discord.utils.utcnow()

                # Send the embed message
                await channel.send(embed=embed)
                print(f"[DEBUG] Alert sent to game ID {game_id} for unplayed nations: {', '.join(unplayed_nations)}")
        except Exception as e:
            print(f"[ERROR] Failed to alert unplayed nations for game ID {game_id}: {e}")









    async def stop_timers(self):
        """
        Gracefully stop the timer loop.
        """
        print("[DEBUG] TimerManager stopping...")
        self.running = False