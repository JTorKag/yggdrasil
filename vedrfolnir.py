import aiosqlite
import asyncio
import random
from typing import List, Dict
import sqlite3



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
            self.connection.row_factory = sqlite3.Row

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
                    research_rate INTEGER,
                    research_random BOOLEAN,
                    hall_of_fame INTEGER,
                    merc_slots INTEGER,
                    global_slots INTEGER,
                    indie_str INTEGER,
                    magicsites INTEGER,
                    eventrarity INTEGER,
                    richness INTEGER,
                    resources INTEGER,
                    recruitment INTEGER,
                    supplies INTEGER,
                    masterpass TEXT,
                    startprov INTEGER,
                    renaming BOOLEAN,
                    scoregraphs INTEGER,
                    noartrest BOOLEAN,
                    nolvl9rest BOOLEAN,
                    teamgame BOOLEAN,
                    clustered BOOLEAN,
                    edgestart BOOLEAN,
                    story_events INTEGER,
                    ai_level INTEGER,
                    no_going_ai BOOLEAN,
                    conqall BOOLEAN,
                    thrones TEXT,
                    requiredap INTEGER,
                    cataclysm INTSEGER,
                    game_running BOOLEAN,
                    game_started BOOLEAN DEFAULT 0,
                    channel_id TEXT,
                    role_id TEXT,
                    game_active BOOLEAN NOT NULL,
                    process_pid INTEGER,
                    game_owner TEXT,
                    creation_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    creation_version TEXT,
                    game_type TEXT,
                    game_winner INTEGER
                )
                """)
                await cursor.execute("""
                PRAGMA table_info(games)
                """)
                columns = [row[1] for row in await cursor.fetchall()]
                if "game_winner" not in columns:
                    await cursor.execute("ALTER TABLE games ADD COLUMN game_winner INTEGER DEFAULT NULL;")

                # Create the `players` table
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    game_id INTEGER,
                    player_id TEXT,
                    nation TEXT,
                    extensions INTEGER,
                    currently_claimed BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (player_id, nation),
                    FOREIGN KEY (game_id) REFERENCES games (game_id)
                )
                """)
                # Create the `gameTimers` table
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS gameTimers (
                    game_id INTEGER PRIMARY KEY,
                    timer_default INTEGER NOT NULL,
                    timer_running BOOLEAN,
                    remaining_time INTEGER,
                    FOREIGN KEY (game_id) REFERENCES games (game_id)
                )
                """)
                await self.connection.commit()
            print("Database setup completed successfully.")
        except Exception as e:
            print(f"Error during database setup: {e}")


    async def create_game(
        self,
        game_name: str,
        game_era: str,
        research_random: str,
        global_slots: int,
        eventrarity: str,
        masterpass: str,
        teamgame: str,
        story_events: str,
        no_going_ai: str,
        thrones: str,
        requiredap: int,
        role_id: int,
        creation_version: str,
        game_type: str,
        max_active_games: int,
        game_port: int = None,
        research_rate: int = None,
        hall_of_fame: int = None,
        merc_slots: int = None,
        indie_str: int = None,
        magicsites: int = None,
        richness: int = None,
        resources: int = None,
        recruitment: int = None,
        supplies: int = None,
        startprov: int = None,
        renaming: bool = None,
        scoregraphs: int = None,
        noartrest: bool = None,
        nolvl9rest: bool = None,
        clustered: bool = None,
        edgestart: bool = None,
        ai_level: int = None,
        conqall: bool = None,
        cataclysm: int = None,
        game_map: str = None,
        game_running: bool = False,
        game_mods: str = "[]",
        channel_id: str = None,
        game_active: bool = True,
        game_started: bool = False,
        process_pid: int = None,
        game_owner: str = None,
        game_winner: int = None,
        ):
        """Insert a new game into the games table, with a limit on active games."""

        # Check if the game name contains spaces
        if " " in game_name:
            raise Exception("Game name cannot contain spaces. Please use underscores or other characters instead.")

        # Check for duplicate active game names
        async with self.connection.cursor() as cursor:
            query = "SELECT COUNT(*) FROM games WHERE game_name = :game_name AND game_active = 1;"
            await cursor.execute(query, {"game_name": game_name})
            duplicate_count = (await cursor.fetchone())[0]

            if duplicate_count > 0:
                raise Exception(f"A game with the name '{game_name}' already exists and is active.")

        # Check the number of active games
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM games WHERE game_active = 1;")
            active_game_count = (await cursor.fetchone())[0]

            if active_game_count >= max_active_games:
                raise Exception(f"Cannot create a new game. The maximum number of active games ({max_active_games}) has been reached.")

        # Assign a free port if not provided
        if game_port is None:
            game_port = await self.assign_free_port()

        # Prepare query and parameters
        query = '''
        INSERT INTO games (
            game_name, game_port, game_era, game_map, game_mods, research_rate, research_random,
            hall_of_fame, merc_slots, global_slots, indie_str, magicsites, eventrarity, richness,
            resources, recruitment, supplies, masterpass, startprov, renaming, scoregraphs, noartrest,
            nolvl9rest, teamgame, clustered, edgestart, story_events, ai_level, no_going_ai, conqall, thrones,
            requiredap, cataclysm, game_running, channel_id, role_id, game_active, process_pid, game_owner,
            creation_date, creation_version, game_started, game_type, game_winner
        ) VALUES (
            :game_name, :game_port, :game_era, :game_map, :game_mods, :research_rate, :research_random,
            :hall_of_fame, :merc_slots, :global_slots, :indie_str, :magicsites, :eventrarity, :richness,
            :resources, :recruitment, :supplies, :masterpass, :startprov, :renaming, :scoregraphs, :noartrest,
            :nolvl9rest, :teamgame, :clustered, :edgestart, :story_events, :ai_level, :no_going_ai, :conqall, :thrones,
            :requiredap, :cataclysm, :game_running, :channel_id, :role_id, :game_active, :process_pid, :game_owner,
            CURRENT_TIMESTAMP, :creation_version, :game_started, :game_type, :game_winner
        );
        '''
        params = {
            "game_name": game_name,
            "game_port": game_port,
            "game_era": game_era,
            "game_map": game_map,
            "game_mods": game_mods,
            "research_rate": research_rate,
            "research_random": research_random,
            "hall_of_fame": hall_of_fame,
            "merc_slots": merc_slots,
            "global_slots": global_slots,
            "indie_str": indie_str,
            "magicsites": magicsites,
            "eventrarity": eventrarity,
            "richness": richness,
            "resources": resources,
            "recruitment": recruitment,
            "supplies": supplies,
            "masterpass": masterpass,
            "startprov": startprov,
            "renaming": renaming,
            "scoregraphs": scoregraphs,
            "noartrest": noartrest,
            "nolvl9rest": nolvl9rest,
            "teamgame": teamgame,
            "clustered": clustered,
            "edgestart": edgestart,
            "story_events": story_events,
            "ai_level": ai_level,
            "no_going_ai": no_going_ai,
            "conqall": conqall,
            "thrones": thrones,
            "requiredap": requiredap,
            "cataclysm": cataclysm,
            "game_type": game_type,
            "game_running": game_running,
            "channel_id": channel_id,
            "role_id": role_id,
            "game_active": game_active,
            "process_pid": process_pid,
            "game_owner": game_owner,
            "creation_version": creation_version,
            "game_started": game_started,
            "game_winner": game_winner  # Include game_winner here
        }



        # Insert the new game into the database
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            return cursor.lastrowid


    async def update_game_property(self, game_id: int, property_name: str, new_value: str | int):
        """
        Updates a specific property for a game in the database.

        Args:
            game_id (int): The ID of the game to update.
            property_name (str): The property to update.
            new_value (str | int): The new value for the property.

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        query = f"""
        UPDATE games
        SET {property_name} = :new_value
        WHERE game_id = :game_id
        """
        params = {"new_value": new_value, "game_id": game_id}

        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, params)
                await self.connection.commit()
                print(f"Updated {property_name} to {new_value} for game ID {game_id}")
                return True
        except Exception as e:
            print(f"Error updating {property_name} for game ID {game_id}: {e}")
            return False


    async def get_active_timers(self):
        """
        Fetch all games with active timers (timer_running = true).
        """
        query = """
        SELECT game_id, remaining_time, timer_default
        FROM gameTimers
        WHERE timer_running = true
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(query)
            return await cursor.fetchall()


    async def update_timer(self, game_id, remaining_time, timer_running):
        """
        Update the remaining time and running status of a timer.
        """
        query = """
        UPDATE gameTimers
        SET remaining_time = :remaining_time,
            timer_running = :timer_running
        WHERE game_id = :game_id
        """
        params = {
            "remaining_time": remaining_time,
            "timer_running": timer_running,
            "game_id": game_id,
        }
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()

    async def reset_timer_for_new_turn(self, game_id: int):
        """
        Reset the timer for a new turn:
        - Set remaining_time to timer_default.
        - Restart the timer.
        """
        query = """
        UPDATE gameTimers
        SET remaining_time = timer_default,
            timer_running = true
        WHERE game_id = :game_id
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_id": game_id})
            await self.connection.commit()


    async def get_active_games(self):
        """
        Fetch a list of active games from the database.

        Returns:
            list[dict]: A list of dictionaries, each containing details about an active game.
        """
        query = '''
        SELECT game_id, game_name, game_era, game_owner, creation_date, creation_version
        FROM games
        WHERE game_active = 1
        '''
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query)
                rows = await cursor.fetchall()

                # Get column names for better readability
                columns = [description[0] for description in cursor.description]

                # Convert rows to a list of dictionaries
                active_games = [dict(zip(columns, row)) for row in rows]

                return active_games
        except Exception as e:
            print(f"Error fetching active games: {e}")
            return []
        

    async def check_active_game_name_exists(self, game_name: str) -> bool:
        """
        Check if an active game with the same name already exists.

        Args:
            game_name (str): The name of the game to check.

        Returns:
            bool: True if an active game with the same name exists, False otherwise.
        """
        query = '''
        SELECT COUNT(*) FROM games WHERE game_name = :game_name AND game_active = 1;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_name": game_name})
            result = await cursor.fetchone()
            return result[0] > 0

    async def get_game_timer(self, game_id: int):
        """
        Fetch the timer details for the given game ID from the gameTimers table.

        Args:
            game_id (int): The ID of the game.

        Returns:
            dict: A dictionary containing the timer details (or None if not found).
        """
        query = """
        SELECT game_id, timer_default, timer_running, remaining_time
        FROM gameTimers
        WHERE game_id = :game_id
        """
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, {"game_id": game_id})
                row = await cursor.fetchone()

                if row:
                    # Map the row to a dictionary for easier access
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            print(f"Error retrieving timer for game ID {game_id}: {e}")
            return None




    async def set_game_started_value(self, game_id: int, started: bool):
        """
        Updates the game_started field in the database for a specific game.

        Args:
            game_id (int): The ID of the game to update.
            started (bool): The new value for the game_started field.

        Raises:
            Exception: If the update fails.
        """
        query = """
        UPDATE games
        SET game_started = :started
        WHERE game_id = :game_id;
        """
        params = {"started": started, "game_id": game_id}

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            print(f"Game ID {game_id} game_started set to {started}.")

    async def set_timer_running(self, game_id: int, running: bool):
        """
        Sets the timer_running value for a specific game ID.
        """
        query = """
        UPDATE gameTimers
        SET timer_running = :running
        WHERE game_id = :game_id
        """
        params = {"running": int(running), "game_id": game_id}
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, params)
                await self.connection.commit()
        except Exception as e:
            print(f"[ERROR] Failed to set timer_running for game ID {game_id}: {e}")


    async def create_timer(self, game_id: int, timer_default: int, timer_running: bool, remaining_time: int):
        """
        Create a timer entry in the database.
        """
        query = '''
        INSERT INTO gameTimers (game_id, timer_default, timer_running, remaining_time)
        VALUES (:game_id, :timer_default, :timer_running, :remaining_time)
        '''
        params = {
            "game_id": game_id,
            "timer_default": timer_default,
            "timer_running": timer_running,
            "remaining_time": remaining_time
        }

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            return cursor.lastrowid


    async def add_player(self, game_id, player_id, nation):
        """Insert or update a player in the players table."""
        query = '''
        INSERT INTO players (game_id, player_id, nation, extensions, currently_claimed)
        VALUES (:game_id, :player_id, :nation, :extensions, :currently_claimed)
        ON CONFLICT (player_id, nation) DO UPDATE SET currently_claimed = :currently_claimed;
        '''
        params = {
            "game_id": game_id,
            "player_id": player_id,
            "nation": nation,
            "extensions": 0,
            "currently_claimed": True
        }

        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, params)
                await self.connection.commit()
            print(f"Player {player_id} successfully added to game {game_id} as nation {nation}.")
        except Exception as e:
            print(f"Failed to add player {player_id} to game {game_id}: {e}")
            raise

    async def unclaim_nation(self, game_id, player_id, nation):
        """Unclaim a nation by setting currently_claimed to False."""
        query = '''
        UPDATE players
        SET currently_claimed = FALSE
        WHERE game_id = :game_id AND player_id = :player_id AND nation = :nation;
        '''
        params = {
            "game_id": game_id,
            "player_id": player_id,
            "nation": nation
        }

        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, params)
                await self.connection.commit()
            print(f"Player {player_id} successfully unclaimed nation {nation} in game {game_id}.")
        except Exception as e:
            print(f"Failed to unclaim nation {nation} for player {player_id} in game {game_id}: {e}")
            raise

    async def get_claimed_nations_by_player(self, game_id: int, player_id: str) -> List[str]:
        """
        Fetches the list of nations claimed by a player in a specific game.

        Args:
            game_id (int): The ID of the game.
            player_id (str): The ID of the player.

        Returns:
            List[str]: A list of nation names claimed by the player.
        """
        query = '''
        SELECT nation
        FROM players
        WHERE game_id = :game_id AND player_id = :player_id AND currently_claimed = 1;
        '''
        params = {"game_id": game_id, "player_id": player_id}
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
            return [row[0] for row in rows]  # Assuming rows are tuples
        except Exception as e:
            print(f"Error fetching claimed nations for player {player_id} in game {game_id}: {e}")
            return []


    async def get_claimed_nations(self, game_id: int) -> Dict[str, List[str]]:
        """
        Fetches all claimed nations and their associated player IDs for a specific game.

        Args:
            game_id (int): The ID of the game.

        Returns:
            Dict[str, List[str]]: A dictionary mapping each claimed nation to a list of player IDs.
        """
        query = '''
        SELECT nation, player_id
        FROM players
        WHERE game_id = :game_id AND currently_claimed = 1
        '''
        params = {"game_id": game_id}
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
            
            # Construct a dictionary: {nation: [player_id1, player_id2, ...]}
            claimed_nations = {}
            for nation, player_id in rows:
                if nation not in claimed_nations:
                    claimed_nations[nation] = []
                claimed_nations[nation].append(player_id)

            return claimed_nations
        except Exception as e:
            print(f"Error fetching claimed nations for game {game_id}: {e}")
            return {}






    async def clear_players(self, game_id: int):
        """Remove all player claims for a game."""
        query = '''
        DELETE FROM players
        WHERE game_id = :game_id
        '''
        params = {"game_id": game_id}
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()




    async def check_player_nation(self, game_id: int, player_id: str, nation: str) -> bool:
        """
        Check if a specific player already owns a nation in the specified game.

        Args:
            game_id (int): The ID of the game.
            player_id (str): The ID of the player.
            nation (str): The name of the nation.

        Returns:
            bool: True if the player already owns the nation, False otherwise.
        """
        query = '''
        SELECT 1 FROM players WHERE game_id = :game_id AND player_id = :player_id AND nation = :nation
        LIMIT 1;
        '''
        params = {
            "game_id": game_id,
            "player_id": player_id,
            "nation": nation
        }

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            result = await cursor.fetchone()
            return result is not None



    async def get_active_game_channels(self):
        """Retrieve channel IDs for all active games."""
        query = '''
        SELECT channel_id FROM games WHERE game_active = 1;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()
            return [int(row[0]) for row in rows]

    async def update_process_pid(self, game_id, pid):
        query = """
        UPDATE games
        SET process_pid = :process_pid
        WHERE game_id = :game_id
        """
        params = {"process_pid": pid, "game_id": game_id}

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            print(f"Updated process_pid to {pid} for game_id {game_id}")

    async def update_game_running(self, game_id, status):
        query = """
        UPDATE games
        SET game_running = :game_running
        WHERE game_id = :game_id
        """
        params = {"game_running": status, "game_id": game_id}

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            print(f"Updated game_running to {status}")


    async def get_map(self, game_id):
        """Retrieve the map associated with a specific game."""
        query = '''
        SELECT game_map FROM games WHERE game_id = :game_id;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_id": game_id})
            result = await cursor.fetchone()
            return result[0] if result else None

    async def get_mods(self, game_id):
        """Retrieve the mods associated with a specific game."""
        query = '''
        SELECT game_mods FROM games WHERE game_id = :game_id;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_id": game_id})
            result = await cursor.fetchone()
            return result[0].split(',') if result and result[0] else []

    async def update_map(self, game_id, new_map):
        """Update the map associated with a specific game."""
        query = '''
        UPDATE games
        SET game_map = :new_map
        WHERE game_id = :game_id;
        '''
        params = {"new_map": new_map, "game_id": game_id}

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            print(f"Updated game_map to {new_map} for game_id {game_id}")

    async def update_mods(self, game_id, new_mods):
        """Update the mods associated with a specific game."""
        query = '''
        UPDATE games
        SET game_mods = :game_mods
        WHERE game_id = :game_id;
        '''
        params = {"game_mods": ','.join(new_mods), "game_id": game_id}

        async with self.connection.cursor() as cursor:
            await cursor.execute(query, params)
            await self.connection.commit()
            print(f"Updated game_mods to {new_mods} for game_id {game_id}")
    
    async def get_game_info(self, game_id):
        """Fetch all info about a specific game."""
        query = '''
        SELECT * FROM games WHERE game_id = :game_id;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_id": game_id})
            row = await cursor.fetchone()
            if row:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            return None



    async def get_players_in_game(self, game_id):
        """Fetch all players in a specific game."""
        query = '''
        SELECT * FROM players WHERE game_id = :game_id;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_id": game_id})
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
            random_port = random.randint(49152, 55555)
            if random_port not in used_ports:
                return random_port

    async def get_game_id_by_channel(self, channel_id: int) -> int | None:
        """Retrieve the game_id associated with a given channel_id from the games table."""
        query = '''
        SELECT game_id
        FROM games
        WHERE channel_id = :channel_id;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"channel_id": channel_id})
            result = await cursor.fetchone()
            return result[0] if result else None
        
    async def get_channel_id_by_game(self, game_id: int) -> int | None:
        """
        Retrieves the channel ID associated with the given game ID.

        Args:
            game_id (int): The ID of the game.

        Returns:
            int | None: The channel ID if found, otherwise None.
        """
        query = '''
        SELECT channel_id
        FROM games
        WHERE game_id = :game_id;
        '''
        async with self.connection.cursor() as cursor:
            await cursor.execute(query, {"game_id": game_id})
            result = await cursor.fetchone()
            return result[0] if result else None

