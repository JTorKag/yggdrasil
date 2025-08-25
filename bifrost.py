
import os
import json
from typing import List, Optional
import stat
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import zipfile
from pathlib import Path
import shutil
import subprocess
import asyncio
from concurrent.futures import ThreadPoolExecutor

_CHMOD_EXECUTOR: ThreadPoolExecutor | None = None

def _get_executor() -> ThreadPoolExecutor:
    global _CHMOD_EXECUTOR
    if _CHMOD_EXECUTOR is None:
        _CHMOD_EXECUTOR = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
    return _CHMOD_EXECUTOR

def _shutdown_executor():
    """Shutdown the thread pool executor if it exists."""
    global _CHMOD_EXECUTOR
    if _CHMOD_EXECUTOR is not None:
        print("[bifrost] Shutting down thread pool executor...")
        _CHMOD_EXECUTOR.shutdown(wait=True)
        _CHMOD_EXECUTOR = None
        print("[bifrost] Thread pool executor shut down")


class bifrost:
    """A utility class for managing file I/O operations."""


    @staticmethod
    def load_config():
        """Loads the 'config.json' file as a JSON object with validation.

        Returns:
            dict: Parsed and validated JSON object from the config file.
            
        Raises:
            ValueError: If configuration is missing required fields or has invalid values.
            FileNotFoundError: If config file doesn't exist.
        """
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config = json.load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file {config_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error reading config file {config_path}: {e}")
        
        required_fields = {
            'bot_token': str,
            'guild_id': (int, str),
            'category_id': (int, str),
            'primary_bot_channel': list,
            'game_admin': (int, str),
            'game_host': (int, str),
            'max_active_games': int,
            'dom_data_folder': str,
            'backup_data_folder': str,
            'dominions_folder': str,
            'dev_eviron': str
        }
        
        optional_fields = {
            'server_host': str
        }
        
        discord_id_fields = {'guild_id', 'category_id', 'game_admin', 'game_host'}
        
        for field, expected_type in required_fields.items():
            if field not in config:
                raise ValueError(f"Missing required configuration field: {field}")
            
            if isinstance(expected_type, tuple):
                if not isinstance(config[field], expected_type):
                    type_names = [t.__name__ for t in expected_type]
                    raise ValueError(f"Configuration field '{field}' must be of type {' or '.join(type_names)}, got {type(config[field]).__name__}")
                
                if field in discord_id_fields and isinstance(config[field], str):
                    try:
                        config[field] = int(config[field])
                    except ValueError:
                        raise ValueError(f"Configuration field '{field}' contains invalid numeric value: {config[field]}")
            else:
                if not isinstance(config[field], expected_type):
                    raise ValueError(f"Configuration field '{field}' must be of type {expected_type.__name__}, got {type(config[field]).__name__}")
        
        for field, expected_type in optional_fields.items():
            if field in config and not isinstance(config[field], expected_type):
                raise ValueError(f"Configuration field '{field}' must be of type {expected_type.__name__}, got {type(config[field]).__name__}")
        
        path_fields = ['dom_data_folder', 'backup_data_folder', 'dominions_folder']
        for field in path_fields:
            path = Path(config[field])
            if not path.exists():
                print(f"Warning: Path does not exist: {config[field]} (will be created if needed)")
        
        dom_binary = Path(config['dominions_folder']) / 'dom6_amd64'
        if not dom_binary.exists():
            raise ValueError(f"Dominions binary not found: {dom_binary}")
        
        if not config['primary_bot_channel']:
            raise ValueError("primary_bot_channel cannot be empty")
        
        if config.get("debug", False):
            print("[CONFIG] Configuration validated successfully")
        return config
        
    @staticmethod
    def parse_ygg_metadata(file_path):
        """
        Parse a file to extract #yggemoji and #yggdescr metadata.

        Args:
            file_path (str): The path to the file to parse.

        Returns:
            dict: A dictionary containing 'yggemoji' and 'yggdescr' values, if found.
        """
        metadata = {
            "yggemoji": "::",
            "yggdescr": ""
        }

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = line.strip()
                    if line.startswith("#yggemoji"):
                        emoji = line[len("#yggemoji"):].strip().strip('"').strip("'")
                        metadata["yggemoji"] = f":{emoji}:" if emoji else "::"
                    elif line.startswith("#yggdescr"):
                        description = line[len("#yggdescr"):].strip().strip('"').strip("'")
                        metadata["yggdescr"] = description
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error parsing file {file_path}: {e}")

        return metadata


    @staticmethod
    async def get_2h_files_by_game_id(game_id: int, db_instance, config: dict) -> List[str]:
        """
        Retrieves all `.2h` files for a specific game by game_id.

        Args:
            game_id (int): The ID of the game.
            db_instance: The database instance for querying game details.
            config (dict): Configuration containing the path to dom_data_folder.

        Returns:
            List[str]: A list of paths to `.2h` files found for the game.
        """
        try:
            game_details = await db_instance.get_game_info(game_id)
            if not game_details:
                print(f"No game found with ID: {game_id}")
                return []

            game_name = game_details.get("game_name")
            if not game_name:
                print(f"Game name not found for ID: {game_id}")
                return []

            dom_data_folder = config.get("dom_data_folder", "")
            if not dom_data_folder:
                print("Error: 'dom_data_folder' not found in the config.")
                return []

            savedgames_folder = os.path.join(dom_data_folder, "savedgames", game_name)
            if not os.path.isdir(savedgames_folder):
                print(f"Savedgames folder for game '{game_name}' does not exist.")
                return []

            files = [
                os.path.join(savedgames_folder, f)
                for f in os.listdir(savedgames_folder)
                if os.path.isfile(os.path.join(savedgames_folder, f)) and f.endswith(".2h")
            ]

            return files

        except Exception as e:
            print(f"Error retrieving `.2h` files for game ID {game_id}: {e}")
            return []

    @staticmethod
    async def get_nations_with_2h_files(game_name: str, config: dict) -> List[str]:
        """
        Fetches a list of nations with .2h files for the given game.

        Args:
            game_name (str): The name of the game.
            config (dict): The configuration dictionary containing paths.

        Returns:
            List[str]: A list of nation names with .2h files (including any prefixes like 'early_').
        """
        try:
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                raise ValueError("dom_data_folder is not defined in the configuration.")

            game_folder = Path(dom_data_folder) / "savedgames" / game_name
            print(f"Looking for .2h files in: {game_folder}")

            if not game_folder.is_dir():
                print(f"Game folder does not exist: {game_folder}")
                return []

            return [
                file.stem
                for file in game_folder.glob("*.2h")
            ]
        except Exception as e:
            print(f"Error fetching nations with .2h files for {game_name}: {e}")
            return []


    @staticmethod
    async def backup_2h_files(game_id: int, game_name: str, config: dict):
        """
        Back up all .2h files from the savedgames directory into the backup_data_folder directory
        inside a subfolder named after the game_id, in a 'pretenders' subdirectory.

        Args:
            game_id (int): The game ID.
            game_name (str): The name of the game.
            config (dict): Configuration dictionary containing the 'dom_data_folder' and 'backup_data_folder' paths.

        Raises:
            Exception: If there's any issue during the backup process.
        """
        try:
            dom_data_folder = config.get("dom_data_folder")
            backup_data_folder = config.get("backup_data_folder")
            print(dom_data_folder)
            print(backup_data_folder)
            if not dom_data_folder or not backup_data_folder:
                raise ValueError("Configuration missing 'dom_data_folder' or 'backup_data_folder'.")

            savedgames_path = os.path.join(dom_data_folder, "savedgames", game_name)
            if not os.path.exists(savedgames_path):
                raise FileNotFoundError(f"Savedgames directory not found for game '{game_name}'.")

            backup_folder = os.path.join(backup_data_folder, str(game_id) , "pretenders")
            os.makedirs(backup_folder, exist_ok=True)

            for file_name in os.listdir(savedgames_path):
                if file_name.endswith(".2h"):
                    source_file = os.path.join(savedgames_path, file_name)
                    destination_file = os.path.join(backup_folder, file_name)
                    shutil.copy(source_file, destination_file)

        except Exception as e:
            print(f"Error during backup for game '{game_name}': {e}")
            raise e


    @staticmethod
    async def clear_folder(folder_path: Path):
        """ Clear all contents at folder path
        
        Args:
            folder_path (Path): Path object of folder.
        
        """
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
        except Exception as e:
            print(f"Error clearing folder'{folder_path}': {e}")
            raise e


    @staticmethod
    async def restore_2h_files(game_id: int, game_name: str, config: dict):
        """
        Restore all .2h files from the backup_data_folder directory (inside a 'pretenders' subdirectory)
        back to the savedgames directory.

        Args:
            game_id (int): The game ID.
            game_name (str): The name of the game.
            config (dict): Configuration dictionary containing the 'dom_data_folder' and 'backup_data_folder' paths.

        Raises:
            Exception: If there's any issue during the restore process.
        """
        try:
            dom_data_folder = config.get("dom_data_folder")
            backup_data_folder = config.get("backup_data_folder")

            if not dom_data_folder or not backup_data_folder:
                raise ValueError("Configuration missing 'dom_data_folder' or 'backup_data_folder'.")

            live_game_path = os.path.join(dom_data_folder, "savedgames", game_name)
            if not os.path.exists(live_game_path):
                os.makedirs(live_game_path, exist_ok=True)

            backup_folder = os.path.join(backup_data_folder, str(game_id), "pretenders")
            if not os.path.exists(backup_folder):
                raise FileNotFoundError(f"Backup directory not found for game ID {game_id}.")

            await bifrost.clear_folder(live_game_path)

            for file_name in os.listdir(backup_folder):
                if file_name.endswith(".2h"):
                    source_file = os.path.join(backup_folder, file_name)
                    destination_file = os.path.join(live_game_path, file_name)
                    shutil.copy(source_file, destination_file)

        except Exception as e:
            print(f"Error during restoration for game '{game_name}': {e}")
            raise e


    @staticmethod
    async def read_stats_file(game_id: int, db_instance, config:dict):
        """
        Reads the stats.txt file for a given game ID and extracts relevant information.

        Args:
            game_id (int): The ID of the game.
            db_instance: Database client instance to fetch game information.

        Returns:
            dict: A dictionary containing game name, turn number, and missing turns.

        Raises:
            FileNotFoundError: If the stats.txt file does not exist.
            ValueError: If the file format is invalid.
        """
        game_info = await db_instance.get_game_info(game_id)
        if not game_info:
            raise ValueError(f"Game with ID {game_id} not found.")

        game_name = game_info.get("game_name")
        savedgames_folder = os.path.join(config.get("dom_data_folder"), "savedgames", game_name)
        stats_file_path = os.path.join(savedgames_folder, "stats.txt")

        if not os.path.exists(stats_file_path):
            raise FileNotFoundError(f"stats.txt not found for game ID {game_id} at {stats_file_path}.")

        result = {
            "game_name": game_name,
            "turn": None,
            "missing_turns": []
        }

        try:
            with open(stats_file_path, "r") as stats_file:
                lines = stats_file.readlines()

            if lines:
                header_line = lines[0].strip()
                if header_line.startswith("Statistics for game"):
                    parts = header_line.split(" ")
                    result["turn"] = int(parts[-1])
                else:
                    raise ValueError("Invalid stats.txt header format.")

            for line in lines[1:]:
                if line.strip().endswith("didn't play this turn"):
                    player_name = line.strip().replace(" didn't play this turn", "")
                    result["missing_turns"].append(player_name)

            return result
        except Exception as e:
            raise ValueError(f"Error parsing stats.txt for game ID {game_id}: {e}")

    @staticmethod
    async def read_statusdump_file(game_id: int, db_instance, config: dict):
        """
        Reads the statusdump file for a given game ID and extracts turn information.
        Used primarily to detect the lobby → turn 1 transition.

        Args:
            game_id (int): The ID of the game.
            db_instance: Database client instance to fetch game information.
            config (dict): Configuration containing dom_data_folder.

        Returns:
            dict: A dictionary containing game name and turn number, or None if file doesn't exist.
        """
        try:
            game_info = await db_instance.get_game_info(game_id)
            if not game_info:
                return None

            game_name = game_info.get("game_name")
            savedgames_folder = os.path.join(config.get("dom_data_folder"), "savedgames", game_name)
            statusdump_file_path = os.path.join(savedgames_folder, "statusdump.txt")

            if not os.path.exists(statusdump_file_path):
                return None

            with open(statusdump_file_path, "r") as status_file:
                content = status_file.read().strip()
                
            lines = content.split('\n')
            turn_number = -1
            
            for line in lines:
                line = line.strip()
                if line.startswith("turn "):
                    parts = line.split(',')
                    if parts:
                        turn_part = parts[0].strip()
                        turn_str = turn_part.replace("turn ", "").strip()
                        turn_number = int(turn_str)
                        break

            return {
                "game_name": game_name,
                "turn": turn_number
            }
            
        except Exception as e:
            print(f"Error reading statusdump for game ID {game_id}: {e}")
            return None

    @staticmethod
    async def backup_saved_game_files(game_id: int, db_instance, config: dict):
        """
        Copies all files from a game's saved game folder to a backup folder,
        excluding files with .d6m and .map extensions. The backup folder is named after the current turn.

        Args:
            game_id (int): The ID of the game.
            db_instance: Database client instance to fetch game information.
            config (dict): The configuration dictionary containing paths.

        Raises:
            FileNotFoundError: If the saved game folder is not found.
            ValueError: If the turn number cannot be determined.
        """
        try:
            game_info = await db_instance.get_game_info(game_id)
            if not game_info:
                raise ValueError(f"Game with ID {game_id} not found.")

            game_name = game_info.get("game_name")
            savedgames_folder = Path(config.get("dom_data_folder")) / "savedgames" / game_name
            backup_folder = Path(config.get("backup_data_folder")) / str(game_id)

            if not savedgames_folder.exists():
                raise FileNotFoundError(f"Saved games folder not found for game ID {game_id} at {savedgames_folder}")

            stats_file = savedgames_folder / "stats.txt"
            if not stats_file.exists():
                print(f"stats.txt file not found for game ID {game_id} at {stats_file}. Skipping backup for this turn.")
                return

            turn_number = None
            with stats_file.open("r") as f:
                for line in f:
                    if line.startswith("Statistics for game"):
                        parts = line.split(" ")
                        turn_number = parts[-1].strip()
                        break

            if turn_number is None:
                raise ValueError(f"Turn number could not be determined from stats.txt for game ID {game_id}")

            turn_backup_folder = backup_folder / f"turn_{int(turn_number) + 1}"
            turn_backup_folder.mkdir(parents=True, exist_ok=True, mode=0o755)

            for file_path in savedgames_folder.iterdir():
                if file_path.is_file() and not file_path.suffix in [".d6m", ".map"]:
                    shutil.copy(file_path, turn_backup_folder / file_path.name)

            print(f"Backup for turn {turn_number} completed successfully in {turn_backup_folder}")

        except FileNotFoundError as e:
            print(f"Backup skipped: {e}")
        except Exception as e:
            print(f"Unexpected error during backup for game ID {game_id}: {e}")



    @staticmethod
    async def restore_saved_game_files(game_id: int, db_instance, config: dict):
        """
        Restores all files from the latest backup folder to the live saved game folder,
        excluding files with .d6m and .map extensions. The backup folder is determined
        based on the current turn. Deletes the backup folder for the restored turn.

        Args:
            game_id (int): The ID of the game.
            db_instance: Database client instance to fetch game information.
            config (dict): The configuration dictionary containing paths.

        Raises:
            FileNotFoundError: If the backup folder or saved games folder is not found.
            ValueError: If the turn number cannot be determined.
        """
        stats = await bifrost.read_stats_file(game_id, db_instance, config)
        turn_number = stats.get("turn")
        if turn_number is None:
            raise ValueError(f"Turn number could not be determined for game ID {game_id}.")

        game_name = stats["game_name"]
        savedgames_folder = Path(config.get("dom_data_folder")) / "savedgames" / game_name
        backup_folder = Path(config.get("backup_data_folder")) / str(game_id) / f"turn_{turn_number}"

        if not backup_folder.exists():
            raise FileNotFoundError(f"Backup folder not found for game ID {game_id} at {backup_folder}.")

        if not savedgames_folder.exists():
            raise FileNotFoundError(f"Saved games folder not found for game ID {game_id} at {savedgames_folder}.")

        for file_path in backup_folder.iterdir():
            if file_path.is_file() and not file_path.suffix in [".d6m", ".map"]:
                destination_path = savedgames_folder / file_path.name
                shutil.copy(file_path, destination_path)

        print(f"Restoration for game ID {game_id} (turn {turn_number}) completed. Deleting backup folder...")

        try:
            backup_data_folder = Path(config.get("backup_data_folder"))
            if not backup_folder.is_relative_to(backup_data_folder):
                raise ValueError(f"Backup folder path is outside expected directory: {backup_folder}")
            
            shutil.rmtree(backup_folder)
            print(f"Backup folder {backup_folder} deleted successfully.")
        except (OSError, ValueError) as e:
            raise RuntimeError(f"Failed to delete backup folder {backup_folder}: {e}")




    @staticmethod
    def get_mods(config):
        """
        Fetches mods from the dom_data_folder and returns an array of JSONs for a dropdown.

        Args:
            config (dict): Configuration JSON object containing the dom_data_folder path.

        Returns:
            list[dict]: Array of JSON objects for dropdown options.
        """
        mods = []

        dom_data_folder = config.get("dom_data_folder", "")
        if not dom_data_folder:
            print("Error: 'dom_data_folder' not found in the config.")
            return mods

        mods_folder = os.path.join(dom_data_folder, "mods")

        if not os.path.exists(mods_folder):
            os.makedirs(mods_folder, mode=0o755, exist_ok=True)
            print(f"[bifrost] Created missing mods folder: {mods_folder}")

        try:
            with os.scandir(mods_folder) as entries:
                for entry in entries:
                    if entry.is_dir():
                        dm_file_path = os.path.join(entry.path, f"{entry.name}.dm")

                        if os.path.isfile(dm_file_path):
                            metadata = bifrost.parse_ygg_metadata(dm_file_path)
                        else:
                            metadata = {"yggemoji": "::", "yggdescr": ""}

                        mod_json = {
                            "name": entry.name,
                            "location": f"{entry.name}/{entry.name}.dm",
                            "yggemoji": metadata.get("yggemoji", "::"),
                            "yggdescr": metadata.get("yggdescr", ""),
                        }
                        mods.append(mod_json)

        except Exception as e:
            print(f"Error reading mods folder: {e}")

        return mods

    @staticmethod
    def get_maps(config):
        """
        Fetches maps from the dom_data_folder and returns an array of JSONs for a dropdown.

        Args:
            config (dict): Configuration JSON object containing the dom_data_folder path.

        Returns:
            list[dict]: Array of JSON objects for dropdown options.
        """
        maps = []

        dom_data_folder = config.get("dom_data_folder", "")
        if not dom_data_folder:
            print("Error: 'dom_data_folder' not found in the config.")
            return maps

        maps_folder = os.path.join(dom_data_folder, "maps")

        if not os.path.exists(maps_folder):
            os.makedirs(maps_folder, mode=0o755, exist_ok=True)
            print(f"[bifrost] Created missing maps folder: {maps_folder}")

        try:
            with os.scandir(maps_folder) as entries:
                for entry in entries:
                    if entry.is_dir():
                        map_file_path = os.path.join(entry.path, f"{entry.name}.map")

                        if os.path.isfile(map_file_path):
                            metadata = bifrost.parse_ygg_metadata(map_file_path)
                        else:
                            metadata = {"yggemoji": "::", "yggdescr": ""}

                        map_json = {
                            "name": entry.name,
                            "location": f"{entry.name}/{entry.name}.map",
                            "yggemoji": metadata.get("yggemoji", "::"),
                            "yggdescr": metadata.get("yggdescr", ""),
                        }
                        maps.append(map_json)

        except Exception as e:
            print(f"Error reading maps folder: {e}")

        return maps


    @staticmethod
    def remove_execution_permission(path: str) -> None:
        """
        Clear all execute bits on *path*.  Does nothing if the file is already
        non-executable.  Safe to call from multiple threads.
        """
        try:
            st = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            return

        if stat.S_ISDIR(st.st_mode):
            return

        new_mode = st.st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if new_mode != st.st_mode:
            try:
                os.chmod(path, new_mode, follow_symlinks=False)
            except PermissionError as exc:
                print(f"[bifrost] chmod failed on {path}: {exc}")


    @staticmethod
    def remove_execution_permission_recursive(folder_path: str):
        """
        Remove execute permissions from files within *folder_path* and all
        sub-directories.  Logs a short summary at the end.
        """
        total_files = 0
        failed_items = []

        try:
            for root, dirs, files in os.walk(folder_path, topdown=False):
                for file_name in files:
                    fp = os.path.join(root, file_name)
                    try:
                        bifrost.remove_execution_permission(fp)
                        total_files += 1
                    except PermissionError:
                        failed_items.append(
                            {"type": "file", "path": fp, "error": "Permission denied"}
                        )
                    except Exception as exc:
                        failed_items.append(
                            {"type": "file", "path": fp, "error": str(exc)}
                        )

                for dir_name in dirs:
                    dp = os.path.join(root, dir_name)
                    try:
                        st = os.stat(dp)
                        os.chmod(dp, st.st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                    except PermissionError:
                        failed_items.append(
                            {"type": "directory", "path": dp, "error": "Permission denied"}
                        )
                    except Exception as exc:
                        failed_items.append(
                            {"type": "directory", "path": dp, "error": str(exc)}
                        )

            try:
                st = os.stat(folder_path)
                os.chmod(folder_path, st.st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            except PermissionError:
                failed_items.append(
                    {"type": "directory", "path": folder_path, "error": "Permission denied"}
                )
            except Exception as exc:
                failed_items.append(
                    {"type": "directory", "path": folder_path, "error": str(exc)}
                )

            print(f"[bifrost] chmod removed from {total_files} files")
            if failed_items:
                print("[bifrost] items that failed:")
                for item in failed_items:
                    print(f"  {item['type']}  {item['path']}: {item['error']}")
        except Exception as exc:
            print(f"[bifrost] Error processing folder {folder_path}: {exc}")




    @staticmethod
    def set_folder_no_exec(folder_path: str):
        """
        Prevent the folder and new contents from having executable permissions by default.

        Args:
            folder_path (str): The path to the folder.
        """
        try:
            bifrost.remove_execution_permission(folder_path)

            os.umask(0o111)
            print(f"Execution permissions restricted for: {folder_path}")
        except Exception as e:
            print(f"Error setting folder permissions for {folder_path}: {e}")

    class _PermissionHandler(FileSystemEventHandler):
        """
        Debounces *.2h* file events and runs remove_execution_permission()
        in a thread-pool so the asyncio loop never blocks.
        """
        _DEBOUNCE_SEC = 0.5

        def __init__(self, loop: asyncio.AbstractEventLoop):
            super().__init__()
            self._loop = loop
            self._pending: set[str] = set()
            self._flush_handle: asyncio.TimerHandle | None = None

        def on_created(self, event):
            if not event.is_directory and event.src_path.endswith(".2h"):
                self._queue(event.src_path)

        def on_modified(self, event):
            if not event.is_directory and event.src_path.endswith(".2h"):
                self._queue(event.src_path)

        def _queue(self, path: str):
            self._pending.add(path)
            if self._flush_handle is None:
                self._flush_handle = self._loop.call_later(
                    self._DEBOUNCE_SEC, self._flush
                )

        def _flush(self):
            paths = list(self._pending)
            self._pending.clear()
            self._flush_handle = None
            asyncio.ensure_future(self._chmod_paths(paths), loop=self._loop)

        async def _chmod_paths(self, paths: list[str]):
            print(f"[bifrost] Skipped chmod for {len(paths)} watched files")

    @staticmethod
    def watch_folder(folder_path: str,
                     *,
                     loop: asyncio.AbstractEventLoop | None = None):
        """
        Start a watchdog.Observer that strips execute bits from new or modified
        *.2h files in *folder_path* and its sub-directories.
        Returns the Observer so callers can stop/join it.
        """
        if loop is None:
            loop = asyncio.get_event_loop()

        observer = Observer()
        handler = bifrost._PermissionHandler(loop)
        observer.schedule(handler, folder_path, recursive=True)
        observer.start()
        print(f"[bifrost] Watching {folder_path} for *.2h changes…")
        return observer


    @staticmethod
    def initialize_dom_data_folder(config):
        """
        Initialize the dom_data_folder by removing execution permissions and setting up a watcher.

        Args:
            config (dict): The configuration dictionary containing 'dom_data_folder'.
        """
        dom_data_folder = config.get("dom_data_folder")
        if not dom_data_folder:
            print("Error: 'dom_data_folder' not found in the config.")
            return



        observer = bifrost.watch_folder(dom_data_folder)

        return observer

    @staticmethod
    async def handle_map_upload(file_data: bytes, filename: str, config: dict) -> dict:
        """
        Handles the upload and extraction of a map zip file from raw binary data.

        Args:
            file_data (bytes): The raw binary content of the zip file.
            filename (str): The name of the uploaded file.
            config (dict): Configuration JSON containing the dom_data_folder path.

        Returns:
            dict: A dictionary containing success status, extracted path, and error (if any).
        """
        try:
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                return {"success": False, "error": "Configuration error: dom_data_folder is not set."}

            maps_folder = Path(dom_data_folder) / "maps"
            maps_folder.mkdir(parents=True, exist_ok=True, mode=0o755)

            zip_file_path = maps_folder / filename
            if zip_file_path.exists():
                return {"success": False, "error": f"A file with the name '{filename}' already exists in the maps folder."}

            with open(zip_file_path, "wb") as f:
                f.write(file_data)
            print(f"Saved zip file to {zip_file_path}")

            extract_folder = maps_folder / zip_file_path.stem
            if extract_folder.exists():
                return {"success": False, "error": f"A folder named '{zip_file_path.stem}' already exists in the maps folder."}

            await bifrost.safe_extract_zip(str(zip_file_path), str(extract_folder))

            return {"success": True, "extracted_path": str(extract_folder)}

        except zipfile.BadZipFile:
            return {"success": False, "error": "The uploaded file is not a valid zip file."}
        except Exception as e:
            return {"success": False, "error": str(e)}
        

    @staticmethod
    async def handle_mod_upload(file_data: bytes, filename: str, config: dict) -> dict:
        """
        Handles the upload and extraction of a mod zip file from raw binary data.

        Args:
            file_data (bytes): The raw binary content of the zip file.
            filename (str): The name of the uploaded file.
            config (dict): Configuration JSON containing the dom_data_folder path.

        Returns:
            dict: A dictionary containing success status, extracted path, and error (if any).
        """
        try:
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                return {"success": False, "error": "Configuration error: dom_data_folder is not set."}

            mods_folder = Path(dom_data_folder) / "mods"
            mods_folder.mkdir(parents=True, exist_ok=True, mode=0o755)

            zip_file_path = mods_folder / filename
            if zip_file_path.exists():
                return {"success": False, "error": f"A file with the name '{filename}' already exists in the mods folder."}

            with open(zip_file_path, "wb") as f:
                f.write(file_data)
            print(f"Saved zip file to {zip_file_path}")

            extract_folder = mods_folder / zip_file_path.stem
            if extract_folder.exists():
                return {"success": False, "error": f"A folder named '{zip_file_path.stem}' already exists in the mods folder."}

            await bifrost.safe_extract_zip(str(zip_file_path), str(extract_folder))

            return {"success": True, "extracted_path": str(extract_folder)}

        except zipfile.BadZipFile:
            return {"success": False, "error": "The uploaded file is not a valid zip file."}
        except Exception as e:
            return {"success": False, "error": str(e)}



    @staticmethod
    async def safe_extract_zip(zip_path: str, extract_to: str):
        """
        Extract a zip file and ensure directories and files have proper permissions.
        """
        try:
            os.makedirs(extract_to, exist_ok=True)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(_get_executor(), os.chmod, extract_to, 0o755)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                extract_to_resolved = Path(extract_to).resolve()
                for member in zip_ref.namelist():
                    member_path = (extract_to_resolved / member).resolve()
                    
                    if not member_path.is_relative_to(extract_to_resolved):
                        raise ValueError(f"Unsafe path in ZIP file: {member} (resolves to {member_path})")
                    
                    if ".." in member or member.startswith("/") or ":" in member:
                        raise ValueError(f"Dangerous path in ZIP file: {member}")
                
                zip_ref.extractall(extract_to)
            print(f"Extracted {zip_path} to {extract_to}")


            print(f"[bifrost] Extracted {zip_path} without chmod operations")

            os.remove(zip_path)
            print(f"Deleted zip file: {zip_path}")

        except zipfile.BadZipFile:
            raise ValueError(f"{zip_path} is not a valid zip file.")
        except PermissionError as e:
            raise RuntimeError(f"Permission denied during extraction: {e}")
        except Exception as e:
            raise RuntimeError(f"Error extracting zip file {zip_path}: {e}")



    #     """
    #     Ensure the '/run/screen' directory exists and has correct permissions
    #     for 'screen' to operate without requiring sudo.
    #     """



    @staticmethod
    async def set_executable_permission(file_path: str):
        """
        Set executable permission for the specified file.

        Args:
            file_path (str): The path to the file.
        """
        try:
            st = os.stat(file_path)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                _get_executor(), 
                os.chmod, 
                file_path, 
                st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
            
            print(f"Executable permission set for: {file_path}")
        except Exception as e:
            print(f"Error setting executable permission for {file_path}: {e}")

    @staticmethod
    async def get_valid_nations_from_files(game_id: int, config: dict, db_instance):
        """Get valid nations from .2h files for a specific game."""
        try:
            game_info = await db_instance.get_game_info(game_id)
            if not game_info:
                return []
            
            game_name = game_info['game_name']
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                return []
            
            nation_files = await bifrost.get_2h_files_by_game_id(game_id, db_instance, config)
            valid_nations = [os.path.splitext(os.path.basename(nation_file))[0] for nation_file in nation_files]
            return valid_nations
            
        except Exception as e:
            print(f"Error getting valid nations from files: {e}")
            return []

    @staticmethod
    async def get_nations_from_2h_files(game_name: str, config: dict):
        """Get valid nations from .2h files by game name."""
        try:
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                return []
                
            savedgames_folder = os.path.join(dom_data_folder, "savedgames", game_name)
            if not os.path.isdir(savedgames_folder):
                return []
            
            files = [
                f for f in os.listdir(savedgames_folder)
                if os.path.isfile(os.path.join(savedgames_folder, f)) and f.endswith(".2h")
            ]
            
            valid_nations = [os.path.basename(file).replace(".2h", "") for file in files]
            return valid_nations
            
        except Exception as e:
            print(f"Error getting nations from 2h files: {e}")
            return []



    @staticmethod
    async def read_file(filepath: str) -> Optional[str]:
        """Reads the contents of a file asynchronously.

        Args:
            filepath (str): Path to the file to read.

        Returns:
            Optional[str]: The contents of the file, or None if an error occurs.
        """
        try:
            loop = asyncio.get_event_loop()
            def _read_file():
                with open(filepath, 'r', encoding='utf-8') as file:
                    return file.read()
            
            return await loop.run_in_executor(_get_executor(), _read_file)
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    @staticmethod
    async def write_file(filepath: str, content: str) -> bool:
        """Writes content to a file asynchronously.

        Args:
            filepath (str): Path to the file to write.
            content (str): Content to write to the file.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        try:
            loop = asyncio.get_event_loop()
            def _write_file():
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(content)
                return True
            
            return await loop.run_in_executor(_get_executor(), _write_file)
        except Exception as e:
            print(f"Error writing to file {filepath}: {e}")
            return False

    @staticmethod
    def list_files(directory: str, extension: Optional[str] = None) -> List[str]:
        """Lists all files in a directory, optionally filtered by extension.

        Args:
            directory (str): Path to the directory to list files from.
            extension (Optional[str]): File extension to filter by (e.g., ".txt").

        Returns:
            List[str]: A list of file paths.
        """
        try:
            files = [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
            if extension:
                files = [f for f in files if f.endswith(extension)]
            return files
        except Exception as e:
            print(f"Error listing files in directory {directory}: {e}")
            return []

    @staticmethod
    def create_directory(directory: str) -> bool:
        """Creates a directory if it does not already exist.

        Args:
            directory (str): Path to the directory to create.

        Returns:
            bool: True if the directory was created or already exists, False otherwise.
        """
        try:
            os.makedirs(directory, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating directory {directory}: {e}")
            return False

    @staticmethod
    def delete_file(filepath: str) -> bool:
        """Deletes a file.

        Args:
            filepath (str): Path to the file to delete.

        Returns:
            bool: True if the file was deleted, False otherwise.
        """
        try:
            os.remove(filepath)
            return True
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
            return False