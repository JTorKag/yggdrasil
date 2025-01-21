#where all the modules live to actually do stuff

import asyncio
import discord
from ratatorskr import discordClient
import nidhogg
from vedrfolnir import dbClient
import signal
import sys
import json


with open("config.json", 'r') as file:
    config = json.load(file)

bot_token = config["bot_token"]
guild_id = config["guild_id"]
category_id = config["category_id"]
bot_channels = list(map(int, config["bot_channels"]))


intents = discord.Intents.default()
intents.message_content = True  #privliaged
intents.guilds = True

shutdown_signal = asyncio.Event()
bot_ready_signal =asyncio.Event()

db_instance = dbClient()  # Get the shared instance of dbClient
discordBot = discordClient(intents=intents, guild_id=guild_id,db_instance=db_instance, bot_ready_signal=bot_ready_signal, category_id=category_id,bot_channels=bot_channels)


@discordBot.event
async def on_disconnect():
    await discordBot.db_instance.close()  # Close the connection on disconnect

async def run_discord_bot():
    try:
        await discordBot.start(bot_token)
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
