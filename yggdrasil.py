#where all the modules live to actually do stuff

import discord
from ratatorskr import discordClient
import nidhogg
from vedrfolnir import dbClient

#fill with your details here
with open("bot_token", 'r') as file:
    bot_token = file.read()
with open("guild_id", 'r') as file:
    guild_id = file.read()



intents = discord.Intents.default()
intents.message_content = True  #privliaged


db_instance = dbClient()  # Get the shared instance of dbClient
discordBot = discordClient(intents=intents, guild_id=guild_id,db_instance=db_instance)

@discordBot.event
async def on_disconnect():
    await discordBot.db_instance.close()  # Close the connection on disconnect

discordBot.run(bot_token)