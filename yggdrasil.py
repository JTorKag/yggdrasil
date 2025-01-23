#where all the modules live to actually do stuff

import asyncio
import discord
from ratatorskr import discordClient
from nidhogg import nidhogg
from bifrost import bifrost
from vedrfolnir import dbClient
import signal
import sys
import json
from pathlib import Path

config = bifrost.load_config()

nidhogg.set_executable_permission(Path(config.get("dominions_folder"))/ "dom6_amd64")

observer = bifrost.initialize_dom_data_folder(config)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.emojis_and_stickers = True


shutdown_signal = asyncio.Event()
bot_ready_signal =asyncio.Event()

db_instance = dbClient()  # Get the shared instance of dbClient
discordBot = discordClient(intents=intents,
                           db_instance=db_instance,
                           bot_ready_signal=bot_ready_signal,
                           config=config,
                           nidhogg=nidhogg)


@discordBot.event
async def on_disconnect():
    await discordBot.db_instance.close()  # Close the connection on disconnect

async def run_discord_bot():
    try:
        await discordBot.start(config.get("bot_token"))
    except asyncio.CancelledError:
        pass
    finally:
        await discordBot.close()

async def handle_terminal_input():
    global db_instance  # Ensure we're referencing the global db_instance
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
                await shutdown()
            elif user_input.lower() == 'close_db':
                print("\nClosing DB connection.")
                await db_instance.close()
                print("\nDB closed.")
            elif user_input.lower() == 'open_db':
                db_instance = dbClient()
                await db_instance.connect()  # Re-establish the database connection
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



async def shutdown():
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

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
    await asyncio.gather(
        run_discord_bot(),
        handle_terminal_input(),
        shutdown_signal.wait()
    )

if __name__== "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt. Exiting.")
        loop = asyncio.new_event_loop()  # Create a new event loop
        asyncio.set_event_loop(loop)  # Set it as the current loop
        if not shutdown_signal.is_set():
           loop.run_until_complete(shutdown())
        sys.exit(0)
