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
                if db_instance and db_instance.connection:
                    async with db_instance.connection.cursor() as cursor:
                        await cursor.execute("SELECT COUNT(*) FROM games WHERE game_active = 1;")
                        active_game_count = (await cursor.fetchone())[0]
                        print(f"\nThere are currently {active_game_count} active games.")
                else:
                    print("\nDatabase connection is not open. Use the 'open_db' command first.")
            else:
                print(f"\nUnknown command: {user_input}")
        except EOFError:
            break

async def shutdown(discordBot, db_instance, observer, shutdown_signal):
    """Handles graceful shutdown of services."""
    print("\nShutting down gracefully.")
    await db_instance.close()
    print("\nDB connection closed.")
    if discordBot.is_ready():
        await discordBot.close()
        print("\nBot stopped.")
    if observer:
        observer.stop()
        print("\nStopped monitoring dom_data_folder.")
        observer.join()
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

    #only needed for wsl. remove in practice. 
    if is_wsl():
        os.environ["DOM6_CONF"] = "/home/jtorkag/.dominions6"
        print(f"DOM6_CONF set to: {os.environ['DOM6_CONF']}")
    


    # Set up necessary permissions and configurations
    bifrost.set_executable_permission(Path(config.get("dominions_folder")) / "dom6_amd64")
    observer = bifrost.initialize_dom_data_folder(config)

    # Initialize signals, bot, and database
    shutdown_signal = asyncio.Event()
    bot_ready_signal = asyncio.Event()
    db_instance = dbClient()
    await db_instance.connect()
    discordBot = initialize_bot(config, db_instance, bot_ready_signal)

    @discordBot.event
    async def on_disconnect():
        await db_instance.close()  # Close the connection on disconnect

    # Define API handler and start it concurrently
    api_handler = APIHandler(discordBot)

    async def start_api_server():
        """
        Starts the API server using uvicorn's serve() method.
        """
        import uvicorn
        config = uvicorn.Config(api_handler.app, host="127.0.0.1", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()


    # Set up graceful shutdown on signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(discordBot, db_instance, observer, shutdown_signal)))

    # Run all components concurrently
    await asyncio.gather(
        discordBot.start(config.get("bot_token")),
        handle_terminal_input(db_instance, bot_ready_signal, shutdown_signal),
        start_api_server(),
        shutdown_signal.wait()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt. Exiting.")
        loop = asyncio.new_event_loop()  # Create a new event loop
        asyncio.set_event_loop(loop)  # Set it as the current loop
        loop.run_until_complete(shutdown())
        sys.exit(0)
