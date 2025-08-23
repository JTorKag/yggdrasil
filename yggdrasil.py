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
    await bot_ready_signal.wait()
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
    """Handles graceful shutdown of services."""
    print("\nShutting down gracefully.")
    
    # Stop the timer manager if it exists
    if timer_manager:
        await timer_manager.stop_timers()
        print("\nTimerManager stopped.")
    
    # Close the database connection
    await db_instance.close()
    print("\nDB connection closed.")
    
    # Shut down the Discord bot
    if discordBot.is_ready():
        await discordBot.close()
        print("\nBot stopped.")
    
    # Stop the observer if it exists
    if observer:
        observer.stop()
        print("\nStopped monitoring dom_data_folder.")
        observer.join()
    
    # Shutdown thread pool executors
    bifrost._shutdown_executor()
    
    # Set the shutdown signal
    shutdown_signal.set()
    print("\nGoodbye.")



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
        print(f"[INFO] Discord bot reconnected as {discordBot.user}")
        print(f"[INFO] Connected to guild: {discordBot.get_guild(config.get('guild_id'))}")
        
    @discordBot.event
    async def on_resumed():
        print("[INFO] Discord bot session resumed")

    # Define API handler and start it concurrently
    api_handler = APIHandler(discord_bot=discordBot, config=config)

    async def start_api_server():
        """
        Starts the API server using uvicorn's serve() method.
        """
        import uvicorn
        uvicorn_config = uvicorn.Config(api_handler.app, host="127.0.0.1", port=8000, log_level="info")
        server = uvicorn.Server(uvicorn_config)
        await server.serve()

    # Set up graceful shutdown on signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(
                shutdown(discordBot, db_instance, observer, shutdown_signal, timer_manager)
            )
        )

    # Run all components concurrently, including TimerManager
    await asyncio.gather(
        discordBot.start(config.get("bot_token")),
        handle_terminal_input(db_instance, bot_ready_signal, shutdown_signal),
        start_api_server(),
        timer_manager.start_timers(),  # Start the TimerManager loop
        shutdown_signal.wait()
    )

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
