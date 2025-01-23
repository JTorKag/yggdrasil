#game manager code

import aiosqlite
import asyncio
import random

class dbClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(dbClient, cls).__new__(cls)
            cls._instance.connection = None
        return cls._instance

    async def connect(self, db_path='ygg.db'):
        """Connect to the database."""
        if self.connection is None:
            self.connection = await aiosqlite.connect(db_path)

    async def close(self):
        """Close the database connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None

    async def setup_db(self):
        """Create the DB file and initial tables if they don't exist."""
        await self.connect()  # Ensure the connection is established
        try:
            async with self.connection.cursor() as cursor:
                # Create tables
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_name TEXT NOT NULL,
                    game_port INTEGER,
                    game_era INTEGER,
                    game_map TEXT,
                    game_mods TEXT,
                    game_running BOOLEAN,
                    channel_id TEXT,
                    game_active BOOLEAN NOT NULL,
                    process_pid INTEGER,
                    game_owner TEXT
                )
                """)
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    game_id INTEGER,
                    player_id TEXT PRIMARY KEY,
                    nation TEXT,
                    turn_status TEXT,
                    FOREIGN KEY (game_id) REFERENCES games (game_id)
                )
                """)
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS gameTimers (
                    game_id INTEGER PRIMARY KEY,
                    timer_default INTEGER NOT NULL,
                    timer_length INTEGER NOT NULL,
                    timer_running BOOLEAN,
                    remaining_time INTEGER
                )
                """)
                await self.connection.commit()
            print("Database setup completed successfully.")
        except Exception as e:
            print(f"Error during database setup: {e}")

    async def create_game(self, game_name, game_port, game_era, game_map, game_mods, game_running, channel_id, game_active, process_pid, game_owner):
        """Insert a new game into the games table."""
        query = '''
        INSERT INTO games (game_name, game_port, game_era, game_map, game_mods, game_running, channel_id, game_active, process_pid, game_owner)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        '''
        if game_port is None:
            game_port = await self.assign_free_port()
        if game_map == "DreamAtlas":
            game_map = "Generated DA Map"
        
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_name, game_port, game_era, game_map, game_mods, game_running, channel_id, game_active, process_pid, game_owner ))
            await self.connection.commit()
            return cursor.lastrowid
            
    async def create_timer(self, game_id, timer_default, timer_length, timer_running, remaining_time):
        query = '''
        INSERT INTO gameTimers (game_id, timer_default, timer_length, timer_running, remaining_time)
        VALUES (?, ?, ?, ?, ?);
        '''

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_id, timer_default, timer_length, timer_running, remaining_time))
            await self.connection.commit()
            return cursor.lastrowid
        

    async def add_player(self, game_id, player_id, nation, turn_status):
        """Insert a new player into the players table."""
        query = '''
        INSERT INTO players (game_id, player_id, nation, turn_status)
        VALUES (?, ?, ?, ?);
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_id, player_id, nation, turn_status))
            await self.connection.commit()

    async def get_active_game_channels(self):
        """Retrieve channel IDs for all active games."""
        query = '''
        SELECT channel_id FROM games WHERE game_active = 1;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()
            # Extract channel_id from rows
            return [int(row[0]) for row in rows]

    async def update_process_pid(self, game_id, pid):
        query = """
        UPDATE games
        SET process_pid = ?
        WHERE game_id = ?
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (pid, game_id))
            await self.connection.commit()
            print(f"Updated process_pid to {pid} for game_id {game_id}")

    async def update_game_running(self, game_id, status):
        query = """
        UPDATE games
        SET game_running = ?
        WHERE game_id = ?
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (status, game_id))
            await self.connection.commit()
            print(f"Updated game_running to {status}")

    async def get_map(self, game_id):
        """Retrieve the map associated with a specific game."""
        query = '''
        SELECT game_map FROM games WHERE game_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_id,))
            result = await cursor.fetchone()
            return result[0] if result else None

    async def get_mods(self, game_id):
        """Retrieve the mods associated with a specific game."""
        query = '''
        SELECT game_mods FROM games WHERE game_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_id,))
            result = await cursor.fetchone()
            return result[0].split(',') if result and result[0] else []

    async def update_map(self, game_id, new_map):
        """Update the map associated with a specific game."""
        query = '''
        UPDATE games
        SET game_map = ?
        WHERE game_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (new_map, game_id))
            await self.connection.commit()
            print(f"Updated game_map to {new_map} for game_id {game_id}")

    async def update_mods(self, game_id, new_mods):
        """Update the mods associated with a specific game."""
        query = '''
        UPDATE games
        SET game_mods = ?
        WHERE game_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            # Store mods as a comma-separated string
            mods_str = ','.join(new_mods)
            await cursor.execute(query, (mods_str, game_id))
            await self.connection.commit()
            print(f"Updated game_mods to {new_mods} for game_id {game_id}")

    async def get_game_info(self, game_id):
        """Fetch all info about a specific game."""
        query = '''
        SELECT * FROM games WHERE game_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_id,))
            return await cursor.fetchone()

    async def get_players_in_game(self, game_id):
        """Fetch all players in a specific game."""
        query = '''
        SELECT * FROM players WHERE game_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (game_id,))
            return await cursor.fetchall()
    
    async def get_used_ports(self):
        """Get all currently used game ports from the database."""
        query = '''SELECT game_port FROM games;'''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()
            return [row[0] for row in rows if row[0] is not None]
        
    async def assign_free_port(self):
        used_ports = await self.get_used_ports()

        while True:
            random_port = random.randint(49152, 65535)
            if random_port not in used_ports:
                return random_port
            
    async def get_game_id_by_channel(self, channel_id: int) -> int | None:
        """Retrieve the game_id associated with a given channel_id from the games table."""
        query = '''
        SELECT game_id
        FROM games
        WHERE channel_id = ?;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, (channel_id,))
            result = await cursor.fetchone()
            return result[0] if result else None
