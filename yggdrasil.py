import asyncio
import discord
from ratatorskr import discordClient
from nidhogg import nidhogg
from bifrost import bifrost
from vedrfolnir import dbClient
import signal
import sys
from pathlib import Path
from gjallarhorn import APIHandler
import os
from norns import TimerManager


def create_config():
    """Loads the configuration."""
    return bifrost.load_config()

def initialize_bot(config, db_instance, bot_ready_signal):
    """Initializes the Discord bot with required dependencies."""
    if config and config.get("debug", False):
        print("[MAIN] Initializing Discord bot...")
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.emojis_and_stickers = True
    if config and config.get("debug", False):
        print("[MAIN] Discord intents configured")

    bot = discordClient(
        intents=intents,
        db_instance=db_instance,
        bot_ready_signal=bot_ready_signal,
        config=config,
        nidhogg=nidhogg
    )
    if config and config.get("debug", False):
        print("[MAIN] Discord bot instance created")
    return bot

async def handle_terminal_input(db_instance, bot_ready_signal, shutdown_signal, config=None):
    """Handles terminal input commands."""
    if config and config.get("debug", False):
        print("[DEBUG] Terminal input handler starting...")
        print("[DEBUG] Waiting for bot to be ready...")
    await bot_ready_signal.wait()
    if config and config.get("debug", False):
        print("[DEBUG] Bot ready! Terminal input is now active. Type 'help' for commands.")
    while not shutdown_signal.is_set():
        try:
            user_input = await asyncio.to_thread(input, "\nEnter a command: ")
            if user_input.lower() == 'help':
                print(
                    "\nexit: Shuts down Ygg server"
                    "\nclose_db: Closes the database connection"
                    "\nopen_db: Reopens the database connection"
                    "\nactive_games: Displays the count of active games"
                )
            elif user_input.lower() == 'exit':
                shutdown_signal.set()
            elif user_input.lower() == 'close_db':
                print("\nClosing DB connection.")
                await db_instance.close()
                print("\nDB closed.")
            elif user_input.lower() == 'open_db':
                await db_instance.connect()
                print("\nDB instance reopened.")
            elif user_input.lower() == 'active_games':
                try:
                    active_game_count = await db_instance.get_active_games_count()
                    print(f"\nThere are currently {active_game_count} active games.")
                except Exception as e:
                    print(f"\nError getting active games count: {e}")
            else:
                print(f"\nUnknown command: {user_input}")
        except EOFError:
            break

async def shutdown(discordBot, db_instance, observer, shutdown_signal, timer_manager=None):
    """Handles final cleanup after services have been shut down."""
    print("[INFO] Performing final cleanup...")
    
    try:
        print("[INFO] Cleaning up running game screen sessions...")
        # Use the same nidhogg class that's used throughout the application
        active_games = await db_instance.get_active_games()
        if active_games:
            print(f"[INFO] Found {len(active_games)} active games to clean up")
            for game in active_games:
                game_id = game.get("game_id")
                game_name = game.get("game_name", f"game_{game_id}")
                
                try:
                    print(f"[DEBUG] Attempting to kill game {game_name} (ID: {game_id})")
                    await nidhogg.kill_game_lobby(game_id, db_instance)
                    print(f"[INFO] Successfully killed game {game_name} (ID: {game_id})")
                except Exception as e:
                    print(f"[ERROR] Failed to kill game {game_name}: {e}")
                    import traceback
                    print(f"[ERROR] Traceback: {traceback.format_exc()}")
        else:
            print("[INFO] No active games found to clean up")
    except Exception as e:
        print(f"[ERROR] Error during game cleanup: {e}")
    
    await db_instance.close()
    print("DB connection closed.")
    
    if observer:
        observer.stop()
        print("Stopped monitoring dom_data_folder.")
        observer.join()
    
    print("Goodbye.")



def is_wsl():
    try:
        with open("/proc/version", "r") as f:
            version_info = f.read().lower()
            if "microsoft" in version_info or "wsl" in version_info:
                return True
    except FileNotFoundError:
        return False
    return False

async def main():
    """Main entry point for the application."""
    config = create_config()
    if config and config.get("debug", False):
        print("[MAIN] Starting application...")
    if config and config.get("debug", False):
        print("[MAIN] Configuration loaded")

    if is_wsl():
        if config and config.get("debug", False):
            print("[MAIN] WSL detected, using dev environment")
        os.environ["DOM6_CONF"] = config["dev_eviron"]
    else:
        if config and config.get("debug", False):
            print("[MAIN] Linux system, using production environment")
        os.environ["DOM6_CONF"] = config["dom_data_folder"]
    if config and config.get("debug", False):
        print("[MAIN] Environment variables set")
    

    if config and config.get("debug", False):
        print("[MAIN] Setting up file permissions...")
    await bifrost.set_executable_permission(Path(config.get("dominions_folder")) / "dom6_amd64")
    if config and config.get("debug", False):
        print("[MAIN] Initializing dom data folder monitoring...")
    observer = bifrost.initialize_dom_data_folder(config)
    if config and config.get("debug", False):
        print("[MAIN] File system monitoring configured")

    if config and config.get("debug", False):
        print("[MAIN] Creating event signals...")
    shutdown_signal = asyncio.Event()
    bot_ready_signal = asyncio.Event()
    if config and config.get("debug", False):
        print("[MAIN] Creating database instance...")
    db_instance = dbClient(config)
    if config and config.get("debug", False):
        print("[MAIN] Connecting to database...")
    await db_instance.connect()
    
    if config and config.get("debug", False):
        print("[MAIN] Setting up database tables...")
    await db_instance.setup_db()
    if config and config.get("debug", False):
        print("[DB] Database tables initialized")
    else:
        print("Database setup completed successfully.")
    
    if config and config.get("debug", False):
        print("[MAIN] Initializing Discord bot...")
    discordBot = initialize_bot(config, db_instance, bot_ready_signal)
    if config and config.get("debug", False):
        print("[MAIN] Discord bot initialized")

    if config and config.get("debug", False):
        print("[MAIN] Creating TimerManager...")
    timer_manager = TimerManager(
        db_instance=db_instance,
        config=config,
        nidhogg=nidhogg,
        discord_bot=discordBot
    )
    if config and config.get("debug", False):
        print("[MAIN] TimerManager created")


    @discordBot.event
    async def on_disconnect():
        print("[INFO] Discord bot disconnected")

    @discordBot.event
    async def on_ready():
        print(f"[INFO] Discord bot connected as {discordBot.user}")
        print(f"[INFO] Connected to guild: {discordBot.get_guild(config.get('guild_id'))}")
        
        # Commands are synced in setup_hook(), not here
        
        if bot_ready_signal:
            bot_ready_signal.set()
            if config and config.get("debug", False):
                print("[DEBUG] Bot ready signal set!")
        
    @discordBot.event
    async def on_resumed():
        print("[INFO] Discord bot session resumed")

    if config and config.get("debug", False):
        print("[MAIN] Creating API handler...")
    api_handler = APIHandler(discord_bot=discordBot, config=config)
    if config and config.get("debug", False):
        print("[MAIN] API handler created")

    if config and config.get("debug", False):
        print("[MAIN] Setting up uvicorn server...")
    import uvicorn
    uvicorn_config = uvicorn.Config(api_handler.app, host="127.0.0.1", port=8000, log_level="warning")
    uvicorn_server = uvicorn.Server(uvicorn_config)
    if config and config.get("debug", False):
        print("[MAIN] uvicorn server configured")
    
    async def start_api_server():
        """
        Starts the API server using uvicorn's serve() method.
        """
        await uvicorn_server.serve()

    if config and config.get("debug", False):
        print("[MAIN] Setting up signal handlers...")
    def handle_signal():
        print(f"\nReceived shutdown signal")
        shutdown_signal.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)
    if config and config.get("debug", False):
        print("[MAIN] Signal handlers configured")

    if config and config.get("debug", False):
        print("[MAIN] Creating tasks for all services...")
    tasks = [
        asyncio.create_task(discordBot.start(config.get("bot_token"))),
        asyncio.create_task(handle_terminal_input(db_instance, bot_ready_signal, shutdown_signal, config)),
        asyncio.create_task(start_api_server()),
        asyncio.create_task(timer_manager.start_timers()),
    ]
    if config and config.get("debug", False):
        print("[MAIN] All tasks created, starting services...")
    
    await shutdown_signal.wait()
    print("\nShutdown signal received, stopping all services...")
    
    print("[INFO] Shutting down API server...")
    uvicorn_server.should_exit = True
    await uvicorn_server.shutdown()
    
    print("[INFO] Sending shutdown notifications to active games...")
    try:
        active_games = await db_instance.get_active_games_with_channels()
        for game_info in active_games:
            try:
                channel_id = game_info.get("channel_id")
                game_name = game_info.get("game_name", "Unknown")
                game_owner = game_info.get("game_owner")
                
                if channel_id:
                    channel = discordBot.get_channel(int(channel_id))
                    if not channel:
                        channel = await discordBot.fetch_channel(int(channel_id))
                    
                    if channel:
                        message = f"🛑 **Service Maintenance** 🛑\n\nThe game service is being shut down for maintenance. "
                        message += f"**{game_name}** will be temporarily unavailable until the service is restarted."
                        
                        if game_owner:
                            try:
                                guild = channel.guild
                                owner_member = None
                                for member in guild.members:
                                    if member.name == game_owner:
                                        owner_member = member
                                        break
                                
                                if owner_member:
                                    message = f"{owner_member.mention}\n\n{message}"
                            except:
                                pass
                        
                        await channel.send(message)
                        print(f"[INFO] Sent shutdown notification to {game_name}")
                        
            except Exception as e:
                print(f"[ERROR] Failed to send shutdown notification for game {game_info.get('game_name', 'Unknown')}: {e}")
                
    except Exception as e:
        print(f"[ERROR] Error sending shutdown notifications: {e}")
    
    print("[INFO] Shutting down Discord bot...")
    await discordBot.close()
    
    print("[INFO] Shutting down TimerManager...")
    await timer_manager.stop_timers()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    
    await shutdown(discordBot, db_instance, observer, shutdown_signal, timer_manager)

    return discordBot, db_instance, observer, shutdown_signal, timer_manager


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt. Exiting.")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        discordBot, db_instance, observer, shutdown_signal, timer_manager = loop.run_until_complete(main())
        loop.run_until_complete(shutdown(discordBot, db_instance, observer, shutdown_signal, timer_manager))
        sys.exit(0)
