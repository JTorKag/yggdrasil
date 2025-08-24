# api 

from fastapi import FastAPI, Query, HTTPException
from bifrost import bifrost
from datetime import datetime, timedelta, timezone
import discord

class APIHandler:
    def __init__(self, discord_bot, config: dict):
        """
        Initialize the API with the required dependencies.
        
        Args:
            discord_bot: The Discord client instance.
            config: Configuration dictionary for the application.
        """
        self.discord_bot = discord_bot
        self.config = config

        self.app = FastAPI()


        @self.app.post("/preexec_backup")
        async def preexec_backup(game_id: int = Query(..., description="The ID of the game")):
            """
            API endpoint to back up the saved game files before the turn progresses.

            Args:
                game_id (int): The ID of the game.

            Returns:
                JSON response confirming the backup operation.
            """
            try:
                # Call the Bifrost method to perform the backup
                await bifrost.backup_saved_game_files(
                    game_id=game_id,
                    db_instance=self.discord_bot.db_instance,
                    config=self.config
                )

                return {"status": "success", "message": f"Backup completed for game ID {game_id}"}

            except FileNotFoundError as fnf_error:
                print(f"FileNotFoundError: {fnf_error}")
                raise HTTPException(status_code=404, detail=str(fnf_error))
            except ValueError as value_error:
                print(f"ValueError: {value_error}")
                raise HTTPException(status_code=400, detail=str(value_error))
            except Exception as e:
                print(f"Unexpected error in /preexec_backup: {e}")
                raise HTTPException(status_code=500, detail="An unexpected error occurred.")

        @self.app.post("/postexec_notify")
        async def postexec_notify(game_id: int = Query(..., description="The game ID for the completed turn")):
            """
            API endpoint to notify Discord when a game advances to the next turn, including an embed.
            """
            try:
                # Fetch game info
                game_info = await self.discord_bot.db_instance.get_game_info(game_id)
                if not game_info:
                    raise HTTPException(status_code=404, detail="Game ID not found.")

                # Extract channel ID
                channel_id = game_info.get("channel_id")
                if not channel_id:
                    raise HTTPException(status_code=404, detail="Channel ID not found for this game.")

                # Fetch the Discord channel
                channel = self.discord_bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.discord_bot.fetch_channel(int(channel_id))
                if not channel:
                    raise HTTPException(status_code=404, detail="Discord channel not found.")

                # Fetch timer info
                timer_info = await self.discord_bot.db_instance.get_game_timer(game_id)
                if not timer_info:
                    raise HTTPException(status_code=404, detail="Game timer information not found.")

                # Reset the timer to the default time
                try:
                    timer_default = timer_info["timer_default"]  # Fetch timer_default before resetting
                    await self.discord_bot.db_instance.update_timer(game_id, timer_default, True)
                    print(f"[DEBUG] Timer for game ID {game_id} reset to default: {timer_default} seconds.")
                except Exception as e:
                    print(f"[ERROR] Failed to reset timer for game ID {game_id}: {e}")
                    raise HTTPException(status_code=500, detail="Failed to reset the timer.")

                # Use the updated remaining time
                remaining_time = timer_default  # Since we just reset it, this is the new remaining time

                # Read stats.txt using bifrost
                try:
                    turn_stats = await bifrost.read_stats_file(game_id, self.discord_bot.db_instance, self.config)
                except FileNotFoundError:
                    print(f"stats.txt file not found for game ID {game_id}.")
                    raise HTTPException(status_code=404, detail="stats.txt not found. Cannot determine turn number.")
                except ValueError as e:
                    print(f"Error reading stats.txt for game ID {game_id}: {e}")
                    raise HTTPException(status_code=500, detail=str(e))

                # Extract the turn number and missing players
                turn = turn_stats.get("turn", 0) + 1  # Add +1 to account for the stats file being one turn behind
                missing_turns = turn_stats.get("missing_turns", [])

                # Calculate Discord timestamp
                current_time = datetime.now(timezone.utc)
                future_time = current_time + timedelta(seconds=remaining_time)
                discord_timestamp = f"<t:{int(future_time.timestamp())}:F>"

                # Use the descriptive_time_breakdown method from discord_bot
                time_breakdown = self.discord_bot.descriptive_time_breakdown(remaining_time)

                # Get the associated role for pinging
                associated_role_id = game_info.get("role_id")
                role_mention = ""
                if associated_role_id:
                    role_mention = f"<@&{associated_role_id}>"

                # Create the embed
                embed = discord.Embed(
                    title=f"Start of Turn {turn}",
                    description=(
                        f"Next turn:\n{discord_timestamp} in {time_breakdown}\n"
                        f"Players who missed turns:\n {', '.join(missing_turns) if missing_turns else 'None'}"
                    ),
                    color=discord.Color.blue()
                )

                # Send the message to the Discord channel with role ping
                if role_mention:
                    await channel.send(content=role_mention, embed=embed)
                else:
                    await channel.send(embed=embed)

                return {"status": "success", "message": f"Notification sent and timer reset for Turn {turn}."}

            except HTTPException as http_err:
                # Log HTTP-specific errors
                print(f"HTTP Exception: {http_err.detail}")
                raise http_err
            except Exception as e:
                # Log generic exceptions
                print(f"Unexpected error in /postexec_notify: {e}")
                raise HTTPException(status_code=500, detail="An unexpected error occurred.")





    def run(self, host="127.0.0.1", port=8000):
        """
        Run the FastAPI server.
        """
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)
