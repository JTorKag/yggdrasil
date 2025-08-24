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
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.emojis_and_stickers = True

    return discordClient(
        intents=intents,
        db_instance=db_instance,
        bot_ready_signal=bot_ready_signal,
        config=config,
        nidhogg=nidhogg
    )

async def handle_terminal_input(db_instance, bot_ready_signal, shutdown_signal):
    """Handles terminal input commands."""
    print("[DEBUG] Terminal input handler starting...")
    print("[DEBUG] Waiting for bot to be ready...")
    await bot_ready_signal.wait()
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
    
    # Close the database connection
    await db_instance.close()
    print("DB connection closed.")
    
    # Stop the observer if it exists
    if observer:
        observer.stop()
        print("Stopped monitoring dom_data_folder.")
        observer.join()
    
    print("Goodbye.")



def is_wsl():
    try:
        # Check if /proc/version contains "microsoft" or "WSL"
        with open("/proc/version", "r") as f:
            version_info = f.read().lower()
            if "microsoft" in version_info or "wsl" in version_info:
                return True
    except FileNotFoundError:
        # If /proc/version doesn't exist, it's not a Linux system
        return False
    return False

async def main():
    """Main entry point for the application."""
    config = create_config()

    # If you need WSL specific configs setup here. 
    if is_wsl():
        os.environ["DOM6_CONF"] = config["dev_eviron"]
    else:
        os.environ["DOM6_CONF"] = config["dom_data_folder"]
    

    # Set up necessary permissions and configurations
    await bifrost.set_executable_permission(Path(config.get("dominions_folder")) / "dom6_amd64")
    observer = bifrost.initialize_dom_data_folder(config)

    # Initialize signals, bot, database, and TimerManager
    shutdown_signal = asyncio.Event()
    bot_ready_signal = asyncio.Event()
    db_instance = dbClient()
    await db_instance.connect()
    
    # Set up database tables immediately after connection
    await db_instance.setup_db()
    print("[DB] Database tables initialized")
    
    discordBot = initialize_bot(config, db_instance, bot_ready_signal)

    # Pass the shared db_instance to TimerManager
    timer_manager = TimerManager(
        db_instance=db_instance,
        config=config,
        nidhogg=nidhogg,
        discord_bot=discordBot  # Pass discord_bot instance
    )


    @discordBot.event
    async def on_disconnect():
        print("[INFO] Discord bot disconnected")
        # Note: Database connection will auto-recover due to retry mechanisms

    @discordBot.event
    async def on_ready():
        print(f"[INFO] Discord bot connected as {discordBot.user}")
        print(f"[INFO] Connected to guild: {discordBot.get_guild(config.get('guild_id'))}")
        
        # Sync Discord commands with timeout (set SKIP_SYNC=1 to skip)
        if not os.getenv('SKIP_SYNC'):
            print("Trying to sync discord bot commands")
            try:
                await asyncio.wait_for(
                    discordBot.tree.sync(guild=discord.Object(id=config.get('guild_id'))),
                    timeout=30.0  # 30 second timeout
                )
                print("Discord commands synced!")
            except asyncio.TimeoutError:
                print("Warning: Command sync timed out after 30 seconds, but continuing...")
            except Exception as e:
                print(f"Error syncing commands: {e}")
        else:
            print("Skipping command sync (SKIP_SYNC=1)")
        
        # Signal that bot is ready
        if bot_ready_signal:
            bot_ready_signal.set()
            print("[DEBUG] Bot ready signal set!")
        
    @discordBot.event
    async def on_resumed():
        print("[INFO] Discord bot session resumed")

    # Define API handler and start it concurrently
    api_handler = APIHandler(discord_bot=discordBot, config=config)

    # Create uvicorn server instance that we can shutdown gracefully
    import uvicorn
    uvicorn_config = uvicorn.Config(api_handler.app, host="127.0.0.1", port=8000, log_level="warning")
    uvicorn_server = uvicorn.Server(uvicorn_config)
    
    async def start_api_server():
        """
        Starts the API server using uvicorn's serve() method.
        """
        await uvicorn_server.serve()

    # Set up graceful shutdown on signals
    def handle_signal():
        print(f"\nReceived shutdown signal")
        shutdown_signal.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Run all components concurrently, including TimerManager
    tasks = [
        asyncio.create_task(discordBot.start(config.get("bot_token"))),
        asyncio.create_task(handle_terminal_input(db_instance, bot_ready_signal, shutdown_signal)),
        asyncio.create_task(start_api_server()),
        asyncio.create_task(timer_manager.start_timers()),
    ]
    
    # Wait for shutdown signal
    await shutdown_signal.wait()
    print("\nShutdown signal received, stopping all services...")
    
    # Gracefully shutdown each service instead of cancelling tasks
    print("[INFO] Shutting down API server...")
    uvicorn_server.should_exit = True
    await uvicorn_server.shutdown()
    
    print("[INFO] Shutting down Discord bot...")
    await discordBot.close()
    
    print("[INFO] Shutting down TimerManager...")
    await timer_manager.stop_timers()
    
    # Now wait for tasks to complete naturally
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Perform final cleanup
    await shutdown(discordBot, db_instance, observer, shutdown_signal, timer_manager)

    # Return instances for graceful shutdown in KeyboardInterrupt
    return discordBot, db_instance, observer, shutdown_signal, timer_manager


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt. Exiting.")
        loop = asyncio.new_event_loop()  # Create a new event loop
        asyncio.set_event_loop(loop)  # Set it as the current loop
        discordBot, db_instance, observer, shutdown_signal, timer_manager = loop.run_until_complete(main())
        loop.run_until_complete(shutdown(discordBot, db_instance, observer, shutdown_signal, timer_manager))
        sys.exit(0)
