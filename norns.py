"""Timer management system for game monitoring and turn progression."""

import time
import asyncio
import discord
import sqlite3
import aiosqlite
from bifrost import bifrost

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
            loop_start = time.time()

            try:
                games_needing_monitoring = await self.db_instance.get_games_needing_turn_monitoring()
                for game in games_needing_monitoring:
                    game_id = game["game_id"]
                    if self.config and self.config.get("debug", False):
                        print(f"[DEBUG] Checking turn transition for game ID {game_id} (game_start_attempted=true, game_started=false)")
                    await self.check_turn_transition(game_id)

                # Check all running games for crashes (including lobby games without timers)
                running_games = await self.db_instance.get_running_games()
                for game in running_games:
                    game_id = game["game_id"]
                    await self.check_screen_session_alive(game_id, game)

                active_timers = await self.db_instance.get_active_timers()

                for timer in active_timers:
                    game_id = timer["game_id"]
                    remaining_time = timer["remaining_time"]

                    game_info = await self.db_instance.get_game_info(game_id)
                    if not game_info or not game_info.get("game_running", False):
                        continue

                    # Screen session already checked above, skip duplicate check

                    new_remaining_time = max(0, remaining_time - 1)

                    if new_remaining_time == 3600:
                        if self.config and self.config.get("debug", False):
                            print(f"[DEBUG] Timer for game ID {game_id} hit 1 hour. Sending timer warning.")
                        await self.send_timer_warning(game_id, game_info)

                    if new_remaining_time == 0:
                        if self.config and self.config.get("debug", False):
                            print(f"[DEBUG] Timer for game ID {game_id} reached 0. Forcing host.")
                        try:
                            await self.nidhogg.force_game_host(game_id, self.config, self.db_instance)

                            await self.db_instance.reset_timer_for_new_turn(game_id, self.config)
                            if self.config and self.config.get("debug", False):
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

            # Sleep for remainder of 1 second interval to eliminate timing drift
            elapsed = time.time() - loop_start
            sleep_time = max(0, 1.0 - elapsed)
            await asyncio.sleep(sleep_time)

    async def send_timer_warning(self, game_id: int, game_info: dict):
        """
        Sends a timer warning when the timer hits 1 hour remaining.

        Includes the full undone information showing which nations haven't submitted.

        Args:
            game_id (int): The unique identifier for the game
            game_info (dict): Game information containing channel_id and game_name

        Note:
            Requires the game to have an associated Discord channel_id in game_info.
            Silently handles cases where no channel is found or Discord API fails.
        """
        try:
            channel_id = game_info.get("channel_id")
            if not channel_id:
                if self.config and self.config.get("debug", False):
                    print(f"[DEBUG] Game ID {game_id} has no associated channel ID.")
                return

            channel = self.discord_bot.get_channel(int(channel_id))
            if not channel:
                channel = await self.discord_bot.fetch_channel(int(channel_id))

            embeds = []

            # Main warning embed
            warning_embed = discord.Embed(
                title=f"⏳ Timer Warning for '{game_info['game_name']}'",
                description=(
                    f"⏰ **1 hour remaining** until the timer expires!\n\n"
                    f"Make sure to finalize your turns to avoid being skipped."
                ),
                color=discord.Color.orange()
            )
            warning_embed.set_footer(text=f"Game ID: {game_id}")
            warning_embed.timestamp = discord.utils.utcnow()
            embeds.append(warning_embed)

            # Try to get undone information
            try:
                # Parse statusdump file using bifrost (same as /undone command)
                statusdump_data = await bifrost.parse_statusdump_for_turn_status(game_id, self.db_instance, self.config)

                if not statusdump_data:
                    raise ValueError("Statusdump data not available")

                turn = statusdump_data["turn"]
                nations_data = statusdump_data["nations"]

                timer_table = await self.db_instance.get_game_timer(game_id)
                time_left = timer_table["remaining_time"] if timer_table else 3600
                timer_running = timer_table["timer_running"] if timer_table else True

                # Helper function for time breakdown
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

                # Add timer info embed like /undone does
                from datetime import datetime, timezone, timedelta
                current_time = datetime.now(timezone.utc)
                future_time = current_time + timedelta(seconds=time_left)
                discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"
                timer_status = "Running" if timer_running else "Paused"

                game_info_embed = discord.Embed(
                    title=f"Turn {turn}",
                    description=(
                        f"Next turn:\n{discord_timestamp} in {descriptive_time_breakdown(time_left)}\n"
                        f"**Timer Status:** {timer_status}"
                    ),
                    color=discord.Color.blue()
                )
                embeds.append(game_info_embed)

                # Categorize nations based on statusdump data
                # Filter out nations eliminated in prior turns (player_status == -1)
                played_nations = []
                played_but_not_finished = []
                undone_nations = []

                for nation in nations_data:
                    # Skip nations eliminated in prior turns
                    if nation["player_status"] == -1:
                        continue

                    nation_name = nation["nation_name"]
                    player_status = nation["player_status"]
                    turn_status = nation["turn_status"]

                    # AI-controlled nations (player_status == 2) are always treated as done
                    if player_status == 2:
                        played_nations.append(f"{nation_name} - AI")
                        continue

                    # For human players (player_status == 1) and eliminated this turn (player_status == -2)
                    if turn_status == 2:
                        # Turn submitted
                        played_nations.append(nation_name)
                    elif turn_status == 1:
                        # Turn played but not finished
                        played_but_not_finished.append(nation_name)
                    elif turn_status == 0:
                        # No activity (undone)
                        undone_nations.append(nation_name)

                # Add the same embeds as /undone command
                if played_nations:
                    played_embed = discord.Embed(
                        title="✅ Played Nations",
                        description="\n".join(played_nations),
                        color=discord.Color.green()
                    )
                    embeds.append(played_embed)

                if played_but_not_finished:
                    unfinished_embed = discord.Embed(
                        title="⚠️ Unfinished",
                        description="\n".join(played_but_not_finished),
                        color=discord.Color.gold()
                    )
                    embeds.append(unfinished_embed)

                if undone_nations:
                    undone_embed = discord.Embed(
                        title="❌ Undone Nations",
                        description="\n".join(undone_nations),
                        color=discord.Color.red()
                    )
                    embeds.append(undone_embed)

                # Check if we should shame a single remaining player
                from ratatorskr.commands.meme_commands import should_shame_player, generate_skeletor_image
                should_shame, player_name, nation = await should_shame_player(
                    self.discord_bot, game_id, undone_nations, played_but_not_finished
                )

            except Exception as status_error:
                # If we can't get the status, just send the warning without undone info
                if self.config and self.config.get("debug", False):
                    print(f"[DEBUG] Failed to get undone status for timer warning: {status_error}")
                should_shame = False
                player_name = None

            # Check if there's an associated role to ping
            associated_role_id = game_info.get("role_id")
            if associated_role_id:
                role_mention = f"<@&{associated_role_id}>"
                await channel.send(content=role_mention, embeds=embeds)
            else:
                await channel.send(embeds=embeds)

            # Send Skeletor shame image after embeds if applicable
            if should_shame and player_name:
                try:
                    # Generate Skeletor shame image
                    skeletor_buffer = generate_skeletor_image(player_name)
                    skeletor_file = discord.File(skeletor_buffer, filename="skeletor_shame.png")
                    await channel.send(file=skeletor_file)
                except Exception as shame_error:
                    if self.config and self.config.get("debug", False):
                        print(f"[DEBUG] Error generating Skeletor shame image: {shame_error}")
            if self.config and self.config.get("debug", False):
                print(f"[DEBUG] Timer warning sent to game ID {game_id}")
        except Exception as e:
            print(f"[ERROR] Failed to send timer warning for game ID {game_id}: {e}")









    async def stop_timers(self):
        """
        Gracefully stop the timer loop.
        """
        if self.config and self.config.get("debug", False):
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
            if self.config and self.config.get("debug", False):
                print(f"[DEBUG] Checking turn transition for game ID {game_id}")
            
            status_data = await bifrost.read_statusdump_file(game_id, self.db_instance, self.config)
            if not status_data:
                if self.config and self.config.get("debug", False):
                    print(f"[DEBUG] No statusdump data for game ID {game_id}, likely still in lobby")
                return
            
            current_turn = status_data.get("turn", -1)
            last_known_turn = self.game_turns.get(game_id, -1)
            
            if self.config and self.config.get("debug", False):
                print(f"[DEBUG] Game ID {game_id}: current_turn={current_turn}, last_known_turn={last_known_turn}")
            
            if (last_known_turn == -1 and current_turn == 1) or (last_known_turn == -1 and current_turn >= 1):
                if current_turn == 1:
                    if self.config and self.config.get("debug", False):
                        print(f"[DEBUG] Detected lobby → turn 1 transition for game ID {game_id}")
                else:
                    if self.config and self.config.get("debug", False):
                        print(f"[DEBUG] Caught missed turn 1 transition for game ID {game_id} (current turn: {current_turn})")
                await self.handle_game_start_notification(game_id)
            else:
                if self.config and self.config.get("debug", False):
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
            if self.config and self.config.get("debug", False):
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

            embed = discord.Embed(
                title="Game Started! - Turn 1",
                description=(
                    f"The game has begun! Good luck, have fun!\n"
                    f"Next turn deadline:\n{discord_timestamp} in {time_breakdown}"
                ),
                color=discord.Color.green()
            )

            if role_mention:
                await channel.send(content=role_mention, embed=embed)
            else:
                await channel.send(embed=embed)
            if self.config and self.config.get("debug", False):
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
            
            if self.config and self.config.get("debug", False):
                print(f"[DEBUG] Game death notification sent for game ID {game_id}")

        except Exception as e:
            print(f"[ERROR] Error sending game death notification for game ID {game_id}: {e}")