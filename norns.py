#timer manager

import time 
import asyncio
import discord
import sqlite3
import aiosqlite

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
        self.error_count = 0
        self.last_error_time = 0
        self.game_turns = {}  # Track last known turn for each game

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

                    # Only check for turn transitions on non-started games (lobby → turn 1 detection)
                    if not game_info.get("game_started", False):
                        await self.check_turn_transition(game_id)

                    # Check if screen session is still alive
                    await self.check_screen_session_alive(game_id, game_info)

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

            except (aiosqlite.OperationalError, sqlite3.OperationalError) as e:
                # Database connection issues - try to recover
                current_time = time.time()
                if current_time - self.last_error_time > 60:  # Log at most once per minute
                    print(f"[ERROR] TimerManager database error: {e}")
                    print("[INFO] Attempting to recover database connection...")
                    self.last_error_time = current_time
                self.error_count += 1
                
                # Exponential backoff for severe connection issues
                if self.error_count > 5:
                    sleep_time = min(30, 2 ** min(self.error_count - 5, 4))  # Cap at 30 seconds
                    print(f"[WARNING] Multiple database errors, sleeping for {sleep_time}s")
                    await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(5)  # Short delay before retry
                continue
                
            except Exception as e:
                # Other unexpected errors
                current_time = time.time()
                if current_time - self.last_error_time > 60:  # Log at most once per minute
                    print(f"[ERROR] TimerManager encountered unexpected error: {e}")
                    self.last_error_time = current_time
                self.error_count += 1
                await asyncio.sleep(5)
                continue
            
            # Reset error count on successful iteration
            if self.error_count > 0:
                self.error_count = 0
                print("[INFO] TimerManager recovered from errors")

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

    async def check_turn_transition(self, game_id):
        """
        Check for turn transitions using statusdump files.
        Detects lobby → turn 1 transitions and triggers notifications.
        """
        try:
            # Import bifrost here to avoid circular imports
            from bifrost import bifrost
            
            # Read the current turn from statusdump
            status_data = await bifrost.read_statusdump_file(game_id, self.db_instance, self.config)
            if not status_data:
                return  # No statusdump file yet, likely still in lobby
            
            current_turn = status_data.get("turn", -1)
            last_known_turn = self.game_turns.get(game_id, -1)
            
            # Detect transitions: either exact transition or missed transition
            if (last_known_turn == -1 and current_turn == 1) or (current_turn >= 1):
                if last_known_turn == -1 and current_turn == 1:
                    print(f"[DEBUG] Detected lobby → turn 1 transition for game ID {game_id}")
                else:
                    print(f"[DEBUG] Caught missed turn 1 transition for game ID {game_id} (current turn: {current_turn})")
                await self.handle_game_start_notification(game_id)
            
            # Update the last known turn
            self.game_turns[game_id] = current_turn
            
        except Exception as e:
            print(f"[ERROR] Error checking turn transition for game ID {game_id}: {e}")

    async def handle_game_start_notification(self, game_id):
        """
        Handle the notification when a game transitions from lobby to turn 1.
        This mimics the postexec notification but for the lobby → turn 1 case.
        """
        try:
            # Get game info
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                print(f"[ERROR] Game ID {game_id} not found for start notification")
                return

            # Get the Discord channel
            channel_id = game_info.get("channel_id")
            if not channel_id:
                print(f"[ERROR] No channel ID found for game ID {game_id}")
                return

            channel = self.discord_bot.get_channel(int(channel_id))
            if not channel:
                channel = await self.discord_bot.fetch_channel(int(channel_id))
            if not channel:
                print(f"[ERROR] Discord channel not found for game ID {game_id}")
                return

            # Get timer info and reset it
            timer_info = await self.db_instance.get_game_timer(game_id)
            if timer_info:
                timer_default = timer_info["timer_default"]
                await self.db_instance.update_timer(game_id, timer_default, True)
                remaining_time = timer_default
            else:
                remaining_time = 3600  # Default 1 hour if no timer info

            # Mark game as started (this is the true game start - lobby -> turn 1)
            await self.db_instance.set_game_started_value(game_id, True)
            print(f"[DEBUG] Game ID {game_id} marked as started (turn 1 reached)")

            # Calculate Discord timestamp
            from datetime import datetime, timedelta, timezone
            current_time = datetime.now(timezone.utc)
            future_time = current_time + timedelta(seconds=remaining_time)
            discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
            
            # Get time breakdown
            time_breakdown = self.discord_bot.descriptive_time_breakdown(remaining_time)

            # Get the associated role for pinging
            associated_role_id = game_info.get("role_id")
            role_mention = ""
            if associated_role_id:
                role_mention = f"<@&{associated_role_id}>"

            # Create embed for game start
            import discord
            embed = discord.Embed(
                title="Game Started! - Turn 1",
                description=(
                    f"The game has begun! All nations have been set up.\n"
                    f"Next turn deadline:\n{discord_timestamp} in {time_breakdown}"
                ),
                color=discord.Color.green()
            )

            # Send message with role ping
            if role_mention:
                await channel.send(content=role_mention, embed=embed)
            else:
                await channel.send(embed=embed)
            print(f"[DEBUG] Game start notification sent for game ID {game_id}")

        except Exception as e:
            print(f"[ERROR] Error sending game start notification for game ID {game_id}: {e}")

    async def check_screen_session_alive(self, game_id, game_info):
        """
        Check if the screen session for a game is still alive.
        If dead, notify Discord and update database.
        """
        try:
            import subprocess
            from pathlib import Path
            
            screen_name = f"dom_{game_id}"
            
            # Check if screen session exists
            try:
                result = subprocess.check_output(
                    ["screen", "-ls", screen_name],
                    stderr=subprocess.STDOUT,
                    timeout=5
                ).decode("utf-8")
                
                # If we get here, screen session exists
                return
                
            except subprocess.CalledProcessError:
                # Screen session doesn't exist - it died
                print(f"[ERROR] Screen session {screen_name} is dead for game ID {game_id}")
                
                # Update database to reflect game is no longer running
                await self.db_instance.update_game_running(game_id, False)
                await self.db_instance.set_timer_running(game_id, False)
                
                # Get error from log file
                dom_data_folder = self.config.get("dom_data_folder", ".")
                game_name = game_info.get("game_name", "unknown")
                log_file = Path(dom_data_folder) / "savedgames" / game_name / "dominions_error.log"
                
                # Import nidhogg to read error log
                error_msg = await self.nidhogg._read_error_log(log_file)
                
                # Send Discord notification
                await self.send_game_death_notification(game_id, game_info, error_msg)
                
        except Exception as e:
            print(f"[ERROR] Error checking screen session for game ID {game_id}: {e}")

    async def send_game_death_notification(self, game_id, game_info, error_msg):
        """
        Send a Discord notification when a game dies unexpectedly.
        """
        try:
            # Get the Discord channel
            channel_id = game_info.get("channel_id")
            if not channel_id:
                print(f"[ERROR] No channel ID found for dead game ID {game_id}")
                return

            channel = self.discord_bot.get_channel(int(channel_id))
            if not channel:
                channel = await self.discord_bot.fetch_channel(int(channel_id))
            if not channel:
                print(f"[ERROR] Discord channel not found for dead game ID {game_id}")
                return

            # Get the associated role for pinging
            associated_role_id = game_info.get("role_id")
            role_mention = ""
            if associated_role_id:
                role_mention = f"<@&{associated_role_id}>"

            # Create embed for game death
            import discord
            embed = discord.Embed(
                title="⚠️ Game Process Died",
                description=(
                    f"Game ID {game_id} has stopped running unexpectedly.\n"
                    f"**Error**: {error_msg}\n\n"
                    f"The game will need to be restarted."
                ),
                color=discord.Color.red()
            )

            # Send message with role ping
            if role_mention:
                await channel.send(content=role_mention, embed=embed)
            else:
                await channel.send(embed=embed)
            
            print(f"[DEBUG] Game death notification sent for game ID {game_id}")

        except Exception as e:
            print(f"[ERROR] Error sending game death notification for game ID {game_id}: {e}")