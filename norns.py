"""Timer management system for game monitoring and turn progression."""

import time 
import asyncio
import discord
import sqlite3
import aiosqlite

class TimerManager:
    def __init__(self, db_instance, nidhogg, config, discord_bot):
        """
        Initialize TimerManager with required dependencies for game monitoring and turn progression.

        Args:
            db_instance: Database client for game and timer data operations
            nidhogg: Game server management instance for hosting operations
            config: Configuration dictionary containing paths and settings
            discord_bot: Discord bot instance for sending notifications
        """
        self.db_instance = db_instance
        self.nidhogg = nidhogg
        self.config = config
        self.discord_bot = discord_bot
        self.running = True
        self.error_count = 0
        self.last_error_time = 0
        self.game_turns = {}

    async def start_timers(self):
        """
        Main loop to periodically update timers and handle resets at the start of new turns.
        
        Continuously monitors active games, checks for turn transitions from lobby to turn 1,
        decrements active timers, sends alerts at 1-hour mark, and forces hosting when timers
        reach zero. Includes error recovery for database connection issues and unexpected errors.
        
        The loop runs every second and handles:
        - Games needing turn monitoring (lobby → turn 1 transitions)
        - Active timer countdown and updates
        - Screen session health checks
        - Automatic game hosting when timers expire
        - Error recovery with exponential backoff
        """
        while self.running:
            try:
                games_needing_monitoring = await self.db_instance.get_games_needing_turn_monitoring()
                for game in games_needing_monitoring:
                    game_id = game["game_id"]
                    print(f"[DEBUG] Checking turn transition for game ID {game_id} (game_start_attempted=true, game_started=false)")
                    await self.check_turn_transition(game_id)

                active_timers = await self.db_instance.get_active_timers()

                for timer in active_timers:
                    game_id = timer["game_id"]
                    remaining_time = timer["remaining_time"]

                    game_info = await self.db_instance.get_game_info(game_id)
                    if not game_info or not game_info.get("game_running", False):
                        continue

                    await self.check_screen_session_alive(game_id, game_info)

                    new_remaining_time = max(0, remaining_time - 1)

                    if new_remaining_time == 3600:
                        print(f"[DEBUG] Timer for game ID {game_id} hit 1 hour. Checking for unplayed nations.")
                        await self.alert_unplayed_nations(game_id, game_info)

                    if new_remaining_time == 0:
                        print(f"[DEBUG] Timer for game ID {game_id} reached 0. Forcing host.")
                        try:
                            await self.nidhogg.force_game_host(game_id, self.config, self.db_instance)

                            await self.db_instance.reset_timer_for_new_turn(game_id, self.config)
                            print(f"[DEBUG] Timer for game ID {game_id} reset for the next turn.")
                        except Exception as e:
                            print(f"[ERROR] Failed to force host for game ID {game_id}: {e}")
                    else:
                        await self.db_instance.update_timer(game_id, new_remaining_time, True)

            except (aiosqlite.OperationalError, sqlite3.OperationalError) as e:
                current_time = time.time()
                if current_time - self.last_error_time > 60:
                    print(f"[ERROR] TimerManager database error: {e}")
                    print("[INFO] Attempting to recover database connection...")
                    self.last_error_time = current_time
                self.error_count += 1
                
                if self.error_count > 5:
                    sleep_time = min(30, 2 ** min(self.error_count - 5, 4))
                    print(f"[WARNING] Multiple database errors, sleeping for {sleep_time}s")
                    await asyncio.sleep(sleep_time)
                else:
                    await asyncio.sleep(5)
                continue
                
            except Exception as e:
                current_time = time.time()
                if current_time - self.last_error_time > 60:
                    print(f"[ERROR] TimerManager encountered unexpected error: {e}")
                    self.last_error_time = current_time
                self.error_count += 1
                await asyncio.sleep(5)
                continue
            
            if self.error_count > 0:
                self.error_count = 0
                print("[INFO] TimerManager recovered from errors")

            await asyncio.sleep(1)

    async def alert_unplayed_nations(self, game_id: int, game_info: dict):
        """
        Alerts the lobby if there are any nations left totally unplayed when the timer hits 1 hour.
        
        Queries the game status to identify unplayed nations (marked with "(-)") and sends
        a Discord embed warning to the game's channel. Only sends alerts if there are actually
        unplayed nations remaining.
        
        Args:
            game_id (int): The unique identifier for the game
            game_info (dict): Game information containing channel_id and game_name
            
        Note:
            Requires the game to have an associated Discord channel_id in game_info.
            Silently handles cases where no channel is found or Discord API fails.
        """
        try:
            raw_status = await self.nidhogg.query_game_status(game_id, self.db_instance)
            lines = raw_status.split("\n")

            unplayed_nations = []
            for line in lines[6:]:
                if "(-)" in line:
                    nation = line.split(":")[1].split(",")[0].strip()
                    unplayed_nations.append(nation)

            if unplayed_nations:
                channel_id = game_info.get("channel_id")
                if not channel_id:
                    print(f"[DEBUG] Game ID {game_id} has no associated channel ID.")
                    return

                channel = self.discord_bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.discord_bot.fetch_channel(int(channel_id))

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
        
        Monitors games that have been started but haven't reached turn 1 yet. Uses statusdump
        files to detect when a game transitions from lobby (turn -1) to turn 1 or beyond.
        Maintains internal state tracking to avoid duplicate notifications.
        
        Args:
            game_id: The unique identifier for the game to monitor
            
        Behavior:
            - Reads statusdump file via bifrost module
            - Compares current turn with last known turn for this game
            - Triggers game start notification on lobby → turn 1 transition
            - Handles cases where turn 1 was missed (current turn > 1)
            - Updates internal game_turns tracking dictionary
        """
        try:
            from bifrost import bifrost
            
            print(f"[DEBUG] Checking turn transition for game ID {game_id}")
            
            status_data = await bifrost.read_statusdump_file(game_id, self.db_instance, self.config)
            if not status_data:
                print(f"[DEBUG] No statusdump data for game ID {game_id}, likely still in lobby")
                return
            
            current_turn = status_data.get("turn", -1)
            last_known_turn = self.game_turns.get(game_id, -1)
            
            print(f"[DEBUG] Game ID {game_id}: current_turn={current_turn}, last_known_turn={last_known_turn}")
            
            if (last_known_turn == -1 and current_turn == 1) or (last_known_turn == -1 and current_turn >= 1):
                if current_turn == 1:
                    print(f"[DEBUG] Detected lobby → turn 1 transition for game ID {game_id}")
                else:
                    print(f"[DEBUG] Caught missed turn 1 transition for game ID {game_id} (current turn: {current_turn})")
                await self.handle_game_start_notification(game_id)
            else:
                print(f"[DEBUG] No transition detected for game ID {game_id}")
            
            self.game_turns[game_id] = current_turn
            
        except Exception as e:
            print(f"[ERROR] Error checking turn transition for game ID {game_id}: {e}")

    async def handle_game_start_notification(self, game_id):
        """
        Handle the notification when a game transitions from lobby to turn 1.
        This mimics the postexec notification but for the lobby → turn 1 case.
        
        Sends a Discord embed notification announcing the game has started, sets up the
        initial timer, marks the game as officially started in the database, and includes
        the next turn deadline with timestamp formatting.
        
        Args:
            game_id: The unique identifier for the game that just started
            
        Actions performed:
            - Retrieves game info and timer settings from database
            - Sets initial timer value and marks game as started
            - Calculates and formats next turn deadline
            - Sends Discord embed with role mention if configured
            - Updates database to reflect game_started=True status
        """
        try:
            game_info = await self.db_instance.get_game_info(game_id)
            if not game_info:
                print(f"[ERROR] Game ID {game_id} not found for start notification")
                return

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

            timer_info = await self.db_instance.get_game_timer(game_id)
            if timer_info:
                timer_default = timer_info["timer_default"]
                await self.db_instance.update_timer(game_id, timer_default, True)
                remaining_time = timer_default
            else:
                remaining_time = 3600

            await self.db_instance.set_game_started_value(game_id, True)
            print(f"[DEBUG] Game ID {game_id} marked as started (turn 1 reached). Both flags now true = monitoring complete.")

            from datetime import datetime, timedelta, timezone
            current_time = datetime.now(timezone.utc)
            future_time = current_time + timedelta(seconds=remaining_time)
            discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
            
            time_breakdown = self.discord_bot.descriptive_time_breakdown(remaining_time)

            associated_role_id = game_info.get("role_id")
            role_mention = ""
            if associated_role_id:
                role_mention = f"<@&{associated_role_id}>"

            import discord
            embed = discord.Embed(
                title="Game Started! - Turn 1",
                description=(
                    f"The game has begun! All nations have been set up.\n"
                    f"Next turn deadline:\n{discord_timestamp} in {time_breakdown}"
                ),
                color=discord.Color.green()
            )

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
        
        Uses subprocess to check if the game's screen session (dom_<game_id>) is running.
        If the session has died, updates the database to mark the game as not running,
        stops the timer, reads any error logs, and sends a death notification to Discord.
        
        Args:
            game_id: The unique identifier for the game
            game_info: Game information dictionary containing game metadata
            
        Error handling:
            - CalledProcessError indicates dead screen session
            - Reads dominions_error.log for crash details
            - Updates game_running=False and timer_running=False in database
            - Sends formatted Discord notification with error details
        """
        try:
            import subprocess
            from pathlib import Path
            
            screen_name = f"dom_{game_id}"
            
            try:
                subprocess.check_output(
                    ["screen", "-ls", screen_name],
                    stderr=subprocess.STDOUT,
                    timeout=5
                )
                
                return
                
            except subprocess.CalledProcessError:
                print(f"[ERROR] Screen session {screen_name} is dead for game ID {game_id}")
                
                await self.db_instance.update_game_running(game_id, False)
                await self.db_instance.set_timer_running(game_id, False)
                
                dom_data_folder = self.config.get("dom_data_folder", ".")
                game_name = game_info.get("game_name", "unknown")
                log_file = Path(dom_data_folder) / "savedgames" / game_name / "dominions_error.log"
                
                error_msg = await self.nidhogg._read_error_log(log_file)
                
                await self.send_game_death_notification(game_id, game_info, error_msg)
                
        except Exception as e:
            print(f"[ERROR] Error checking screen session for game ID {game_id}: {e}")

    async def send_game_death_notification(self, game_id, game_info, error_msg):
        """
        Send a Discord notification when a game dies unexpectedly.
        
        Sends a formatted Discord embed to the game's channel notifying players that
        the game process has died. Attempts to mention the game owner if they can be
        found in the guild membership.
        
        Args:
            game_id: The unique identifier for the dead game
            game_info (dict): Game information containing channel_id and game_owner
            error_msg (str): Error message from the game's error log
            
        Features:
            - Creates red-colored Discord embed with error details
            - Attempts to find and mention game owner by username
            - Gracefully handles missing channels or Discord API failures
            - Provides clear indication that game restart is required
        """
        try:
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

            game_owner = game_info.get("game_owner")
            owner_mention = ""
            if game_owner:
                try:
                    guild = channel.guild
                    owner_member = None
                    for member in guild.members:
                        if member.name == game_owner:
                            owner_member = member
                            break
                    
                    if owner_member:
                        owner_mention = owner_member.mention
                except:
                    pass

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

            if owner_mention:
                await channel.send(content=owner_mention, embed=embed)
            else:
                await channel.send(embed=embed)
            
            print(f"[DEBUG] Game death notification sent for game ID {game_id}")

        except Exception as e:
            print(f"[ERROR] Error sending game death notification for game ID {game_id}: {e}")