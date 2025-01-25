from fastapi import FastAPI, Query

class APIHandler:
    def __init__(self, discord_bot):
        """
        Initialize the API with the required dependencies.
        
        Args:
            discord_bot: The Discord client instance.
        """
        self.discord_bot = discord_bot
        self.app = FastAPI()

        # Define the API endpoints
        @self.app.post("/send-message")
        async def send_message(
            game_id: int = Query(..., description="The ID of the game"),
            message: str = Query(..., description="The message to send")
        ):
            """
            Endpoint to send a message via the Discord bot.
            """
            try:
                response = await self.discord_bot.send_game_message(game_id, message)
                return response
            except Exception as e:
                return {"status": "error", "message": str(e)}

    def run(self, host="127.0.0.1", port=8000):
        """
        Run the FastAPI server.
        """
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)
