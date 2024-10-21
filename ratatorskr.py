#discord bot code


import discord
from discord import app_commands, Embed
import nidhogg

class discordClient(discord.Client):
    def __init__(self, *, intents, guild_id, db_instance):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_id = guild_id
        self.db_instance = db_instance


    async def setup_hook(self):
        
        @self.tree.command(
            name="new-game",
            description="Creates a brand new game",
            guild=discord.Object(id=self.guild_id)
        )
        async def new_game_command(interaction: discord.Interaction, supplied_name: str, supplied_era: int, supplied_map: str):

            if supplied_era < 1 or supplied_era > 3:
                await interaction.response.send_message("Era must be value 1, 2, or 3.")
                return
            if supplied_map != "DreamAtlas" and supplied_map != "Vanilla":
                await interaction.response.send_message(f"Pick something i'm using so far. DreamAtlas or Vanilla ENTRY: {supplied_map}")
                return

            try:

                new_game_id = await self.db_instance.create_game(game_name = supplied_name, game_port=None, game_era=supplied_era, game_map=supplied_map, 
                                                    started_status = False, timer_running = False, timer_default=1440, 
                                                    game_owner=interaction.user.name)
                await nidhogg.newGameLobby(new_game_id,self.db_instance)

                await interaction.response.send_message(f"Game '{supplied_name}' created successfully!")
            except  Exception as e:
                await interaction.response.send_message(f"An error occured while creating the game: {str(e)}")
        


        @self.tree.command(
            name="check-status",
            description="Checks server status",
            guild=discord.Object(id=self.guild_id) 
        )
        async def wake_command(interaction: discord.Interaction):
            response = nidhogg.serverStatusJsonToDiscordFormatted(nidhogg.getServerStatus())
            embedResponse = discord.Embed(title="Server Status", type="rich")
            embedResponse.add_field(name="", value=response, inline=True)
            await interaction.response.send_message(embed=embedResponse)
            print(f"{interaction.user} requested server status.")

        @self.tree.command(
            name="echo",
            description="Echos back text",
            guild=discord.Object(id=self.guild_id)
        )
        async def echo_command(interaction: discord.Interaction, echo_text:str, your_name:str):
            await interaction.response.send_message(echo_text + your_name)


        @self.tree.command(
            name="upload-map",
            description="Upload your map.",
            guild=discord.Object(id=self.guild_id) 
        )
        async def map_upload_command(interaction: discord.Interaction, file:discord.Attachment):
            await interaction.response.send_message("Uploading!")
            file_path = f"./{file.filename}" 
            await file.save(file_path)
            await interaction.response.send_message("Done uploading {file.filename}")
            print(f"{interaction.user} uploaded a map.")


    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        await self.db_instance.setup_db()

        try:
            await self.tree.sync(guild=discord.Object(id=self.guild_id))
            print("Commands synced!")
        except Exception as e:
            print(f"Error syncing commands: {e}")

    async def on_message(self, message):
        if message.author == self.user:
            return 
        print(f'Message from {message.author}: {message.content} in {message.channel}')
    
    