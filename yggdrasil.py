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
    await bot_ready_signal.wait()
    while not shutdown_signal.is_set():
        try:
            user_input = await asyncio.to_thread(input, "Enter a command:")
            if user_input.lower() == 'help':
                print("exit: Shutsdown ygg server\n"+
                      "close_db: Close the db file\n"+
                      "open_db: Opens closed db file.")
            elif user_input.lower() == 'exit':
                await shutdown()
            elif user_input.lower() == 'close_db':
                print("Closing DB connection.")
                await db_instance.close()
                print("DB closed.")
            elif user_input.lower() == 'open_db':
                db_instance = dbClient()
                print("DB instance reopened.")
            else:
                print(f"Unknown command: {user_input}")
        except EOFError:
            break

async def shutdown():
    print("Shutting down gracefully.")
    await db_instance.close()
    print("DB connection closed.")
    if discordBot.is_ready():
        await discordBot.close()
        print("Bot stopped.")
    if observer:
        observer.stop()
        print("Stopped monitoring dom_data_folder.")
        observer.join()
    shutdown_signal.set()
    print("Goodbye.")

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
