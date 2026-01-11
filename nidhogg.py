
from pathlib import Path
import subprocess
import re
import os
import stat
import asyncio
import signal
import shlex
from bifrost import bifrost

class nidhogg:
    _config = bifrost.load_config()
    dominions_folder = Path(_config.get("dominions_folder"))

    @classmethod
    def update_config(cls, config):
        """Update the config and dominions_folder path."""
        cls._config = config
        cls.dominions_folder = Path(config.get("dominions_folder"))

    @staticmethod
    def set_executable_permission(file_path: str):
        """
        Set executable permission for the specified file.

        Args:
            file_path (str): The path to the file.
        """
        try:
            st = os.stat(file_path)
            
            os.chmod(file_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            
            print(f"Executable permission set for: {file_path}")
        except Exception as e:
            print(f"Error setting executable permission for {file_path}: {e}")


    @staticmethod
    async def launch_game_lobby(game_id, db_instance, config):
        try:
            game_details = await db_instance.get_game_info(game_id=game_id)
            if not game_details:
                print(f"No game found with ID: {game_id}")
                return False

            game_name = game_details["game_name"]
            game_port = game_details["game_port"]
            game_era = game_details["game_era"]
            game_map = game_details["game_map"]
            global_slots = game_details["global_slots"]
            eventrarity = game_details["eventrarity"]
            masterpass = game_details["masterpass"]
            requiredap = game_details["requiredap"]
            thrones = game_details["thrones"]
            story_events = game_details["story_events"]
            no_going_ai = game_details["no_going_ai"]
            research_random = game_details["research_random"]
            teamgame = game_details["teamgame"]

            # Extra game settings
            research_rate = game_details.get("research_rate")
            hall_of_fame = game_details.get("hall_of_fame")
            merc_slots = game_details.get("merc_slots")
            indie_str = game_details.get("indie_str")
            magicsites = game_details.get("magicsites")
            richness = game_details.get("richness")
            resources = game_details.get("resources")
            recruitment = game_details.get("recruitment")
            supplies = game_details.get("supplies")
            startprov = game_details.get("startprov")
            renaming = game_details.get("renaming")
            scoregraphs = game_details.get("scoregraphs")
            noartrest = game_details.get("noartrest")
            nolvl9rest = game_details.get("nolvl9rest")
            clustered = game_details.get("clustered")
            edgestart = game_details.get("edgestart")
            ai_level = game_details.get("ai_level")
            conqall = game_details.get("conqall")
            cataclysm = game_details.get("cataclysm")
            diplo = game_details.get("diplo")
            if game_details["game_mods"] and game_details["game_mods"] not in ["[]", "None", ""]:
                game_mods = game_details["game_mods"].split(",")
                game_mods = [mod.strip() for mod in game_mods if mod.strip() and mod.strip() not in ["[]", "None"]]
            else:
                game_mods = []

            postexec_command = (
                f"curl -X POST http://127.0.0.1:8000/postexec_notify?game_id={game_id}"
            )

            preexec_command = (
                f"curl -X POST http://127.0.0.1:8000/preexec_backup?game_id={game_id}"
            )



            command = [
                str(nidhogg.dominions_folder / "dom6_amd64"),
                "--tcpserver",
                "--ipadr", "localhost",
                "--newgame", game_name,
                "--port", str(game_port),
                "--era", str(game_era),
                "--globals", str(global_slots),
                "--eventrarity", str(eventrarity),
                "--masterpass", masterpass,
                "--requiredap", str(requiredap),
                "--renaming",
                "--noclientstart",
                "--preexec", preexec_command,
                "--postexec", postexec_command,
                "--textonly",
                "--statusdump"
            ]

            throne_counts = thrones.split(",")
            command.extend(["--thrones"] + throne_counts)

            story_events_map = {0: "--nostoryevents", 1: "--storyevents", 2: "--allstoryevents"}
            if story_events in story_events_map:
                command.append(story_events_map[story_events])

            if no_going_ai == 1:
                command.append("--nonewai")

            if research_random == 1:
                command.append("--norandres")

            if game_map in {"vanilla_10", "vanilla_15", "vanilla_20", "vanilla_25"}:
                command.extend(["--randmap", game_map.split("_")[1]])
            else:
                command.extend(["--mapfile", game_map])

            if game_mods:
                for mod in game_mods:
                    command.extend(["--enablemod", mod])

            if teamgame:
                command.append("--teamgame")

            # Add extra game settings if they exist in database
            if research_rate is not None:
                command.extend(["--research", str(research_rate)])

            if hall_of_fame is not None:
                command.extend(["--hofsize", str(hall_of_fame)])

            if merc_slots is not None:
                command.extend(["--mercsize", str(merc_slots)])

            if indie_str is not None:
                command.extend(["--indepstr", str(indie_str)])

            if magicsites is not None:
                command.extend(["--magicsites", str(magicsites)])

            if richness is not None:
                command.extend(["--richness", str(richness)])

            if resources is not None:
                command.extend(["--resources", str(resources)])

            if recruitment is not None:
                command.extend(["--recruitment", str(recruitment)])

            if supplies is not None:
                command.extend(["--supplies", str(supplies)])

            if startprov is not None:
                command.extend(["--startprov", str(startprov)])

            # Handle renaming setting
            if renaming == "False":
                command.append("--norenaming")
            # If renaming is True or None, use default --renaming (already added above)

            # Handle scoregraphs setting
            if scoregraphs == "Show Graphs":
                command.append("--scoregraphs")
            elif scoregraphs == "Hide Nations":
                command.append("--nonationinfo")
            # If scoregraphs is "Default" or None, use default behavior

            if noartrest == "True":
                command.append("--noartrest")

            if nolvl9rest == "True":
                command.append("--nolvl9rest")

            if clustered == "True":
                command.append("--clustered")

            if edgestart == "True":
                command.append("--edgestart")

            if ai_level is not None:
                command.extend(["--newailvl", str(ai_level)])

            if conqall == "True":
                command.append("--conqall")

            if cataclysm is not None:
                command.extend(["--cataclysm", str(cataclysm)])

            if diplo == "Disabled":
                command.append("--nodiplo")
            elif diplo == "Weak":
                command.append("--weakdiplo")
            # If diplo is "Binding" or None, use default behavior (no flag needed)

            command.append("--statfile")

            if not isinstance(game_id, int) or game_id <= 0:
                raise ValueError(f"Invalid game_id: {game_id}")
            
            screen_name = f"dom_{game_id}"
            screen_command = ["screen", "-dmS", screen_name] + command

            if config and config.get("debug", False):
                print(f"[DEBUG] Base command: {shlex.join(command)}")

            dom_data_folder = config.get("dom_data_folder", ".")
            savedgames_path = Path(dom_data_folder) / "savedgames" / game_name
            savedgames_path.mkdir(parents=True, exist_ok=True, mode=0o755)
            
            os.chmod(savedgames_path, 0o755)
            
            actual_perms = oct(savedgames_path.stat().st_mode)[-3:]
            if config and config.get("debug", False):
                print(f"[DEBUG] Created {savedgames_path} with permissions: {actual_perms}")
            
            log_file = savedgames_path / "dominions_error.log"
            
            screen_command_with_log = ["screen", "-dmS", screen_name, "-L", "-Logfile", str(log_file)] + command
            

            print(f"Lobby launched with logging: {shlex.join(screen_command_with_log)}")
            
            screen_process = subprocess.Popen(
                screen_command_with_log,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            print(f"Screen process launched with PID: {screen_process.pid}")
            print(f"Logging to: {log_file}")

            await asyncio.sleep(3)


            try:
                result = subprocess.check_output(
                    ["screen", "-ls", screen_name], 
                    timeout=10
                ).decode("utf-8")
                actual_pid = None
                for line in result.splitlines():
                    if f"{screen_name}" in line:
                        actual_pid = int(line.split(".")[0].strip())
                        break

                if not actual_pid:
                    error_msg = await nidhogg._read_error_log(log_file)
                    print(f"Failed to find process for screen session: {screen_name}")
                    print(f"Error log: {error_msg}")
                    raise RuntimeError(f"Game failed to start: {error_msg}")

                print(f"Actual PID for game ID {game_id}: {actual_pid}")

                await db_instance.update_process_pid(game_id, actual_pid)
                await db_instance.update_game_running(game_id, True)

                await asyncio.sleep(2)
                try:
                    os.kill(actual_pid, 0)
                except (ProcessLookupError, OSError):
                    error_msg = await nidhogg._read_error_log(log_file)
                    print(f"Process {actual_pid} died shortly after starting")
                    print(f"Error log: {error_msg}")
                    raise RuntimeError(f"Game failed to start: {error_msg}")

                return True

            except subprocess.CalledProcessError as e:
                print(f"Error retrieving screen session: {e}")
                return False
            except subprocess.TimeoutExpired:
                print(f"Timeout retrieving screen session for game {game_id}")
                return False

        except Exception as e:
            print(f"Error launching game lobby: {e}")
            return False




    @staticmethod
    async def force_game_host(game_id: int, config: dict, db_instance):
        """
        Writes a `domcmd` file to the live game folder to automatically start the game.
        Creates a backup before hosting, just like normal timer-based hosting.

        Args:
            game_id (int): The game ID.
            config (dict): Configuration containing 'dom_data_folder'.
            db_instance: Database instance for retrieving game details.

        Raises:
            Exception: If any error occurs during the execution.
        """
        try:
            # Create backup before hosting (same as normal turn progression)
            from bifrost import bifrost
            try:
                await bifrost.backup_saved_game_files(game_id, db_instance, config)
                print(f"Backup completed for force host of game ID {game_id}")
            except Exception as backup_error:
                print(f"Warning: Backup failed for force host of game ID {game_id}: {backup_error}")
                # Continue with force host even if backup fails

            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                raise ValueError("Configuration missing 'dom_data_folder'.")

            game_details = await db_instance.get_game_info(game_id)
            if not game_details:
                raise ValueError(f"No game found with ID {game_id}")

            savedgames_path = Path(dom_data_folder) / "savedgames" / game_details.get("game_name")

            if not savedgames_path.exists():
                raise FileNotFoundError(f"Savedgames directory not found for game ID {game_id} at {savedgames_path}.")

            png_files = list(savedgames_path.glob("*.png"))
            for png_file in png_files:
                try:
                    png_file.unlink()
                    if config and config.get("debug", False):
                        print(f"[DEBUG] Deleted statusdump PNG file: {png_file.name}")
                except Exception as e:
                    print(f"[WARNING] Could not delete PNG file {png_file.name}: {e}")
            
            if png_files:
                if config and config.get("debug", False):
                    print(f"[DEBUG] Cleaned up {len(png_files)} PNG files from statusdump")

            domcmd_path = savedgames_path / "domcmd"

            with open(domcmd_path, "w", encoding="utf-8") as domcmd_file:
                domcmd_file.write("settimeleft 5")

            print(f"Force host operation completed for game ID {game_id} at {domcmd_path}.")
            
            await asyncio.sleep(3)
            
            game_details = await db_instance.get_game_info(game_id)
            if game_details and game_details.get("process_pid"):
                try:
                    os.kill(game_details["process_pid"], 0)
                except (ProcessLookupError, OSError):
                    log_file = savedgames_path / "dominions_error.log"
                    error_msg = await nidhogg._read_error_log(log_file)
                    raise RuntimeError(f"Game process crashed during start: {error_msg}")
        except Exception as e:
            print(f"Error in force_game_host for game ID {game_id}: {e}")
            raise e



    @staticmethod
    async def kill_game_lobby(game_id, db_instance):
        """
        Kill the process for the specified game ID.

        Args:
            game_id (int): The ID of the game.
            db_instance: Database instance to fetch and update game details.
        """
        try:
            game_details = await db_instance.get_game_info(game_id=game_id)
            if not game_details or "process_pid" not in game_details or not game_details["process_pid"]:
                raise ValueError(f"No running process found for game ID: {game_id}.")

            process_pid = game_details["process_pid"]

            os.kill(process_pid, signal.SIGTERM)
            print(f"Process with PID {process_pid} for game ID {game_id} has been killed.")

            await db_instance.update_game_running(game_id, False)
        except ProcessLookupError:
            # Process already dead - update database state and continue
            print(f"Process with PID {process_pid} not found - already terminated.")
            await db_instance.update_game_running(game_id, False)
        except Exception as e:
            raise RuntimeError(f"Failed to kill process for game ID {game_id}: {e}")

    @staticmethod
    def get_version():
        """
        Get the version of the Dominions server executable.

        Returns:
            str: The version number (e.g., "6.25") if successful, or an error message otherwise.
        """
        try:
            result = subprocess.run(
                [str(nidhogg.dominions_folder / "dom6_amd64"), "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15
            )

            if result.returncode != 0:
                return f"Error fetching version: {result.stderr.strip()}"

            version_match = re.search(r"version (\d+\.\d+)", result.stdout)
            if version_match:
                return version_match.group(1)
            else:
                return "Version information not found in output."

        except subprocess.TimeoutExpired:
            return "Timeout while fetching version - Dominions executable may be unresponsive"
        except Exception as e:
            return f"Exception while fetching version: {e}"

    @staticmethod
    async def query_game_status(game_id: int, db_instance):
        """
        Query the status of a running game using the --tcpquery flag.

        Args:
            game_id (int): The ID of the game.
            db_instance: The database instance to fetch the game details.

        Returns:
            str: The raw response from the Dominions executable.
        """
        try:
            game_details = await db_instance.get_game_info(game_id)
            if not game_details:
                raise ValueError(f"No game found with ID {game_id}.")

            game_port = game_details.get("game_port")
            if not game_port:
                raise ValueError(f"No port found for game ID {game_id}.")

            command = [
                str(nidhogg.dominions_folder / "dom6_amd64"),
                "--tcpquery",
                "--ipadr", "localhost",
                "--port", str(game_port)
            ]


            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20
            )

            if result.returncode != 0:
                raise RuntimeError(f"Query failed with error: {result.stderr.strip()}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            error_msg = f"Timeout querying game {game_id} - Dominions process may be hanging"
            print(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            print(f"Error querying game status: {e}")
            raise e




    @staticmethod
    async def _read_error_log(log_file):
        """Read the error log and extract only meaningful error messages."""
        try:
            if not log_file.exists():
                return "No log file found"
            
            with open(log_file, "r") as f:
                lines = f.readlines()
                
            if not lines:
                return "Log file is empty"
                
            filtered_lines = []
            useless_patterns = [
                "Setup port",
                "seconds, open:",
                "kdialog: not found",
                "zenity: not found", 
                "Error: Can't open display:",
                "sh: 1:"
            ]
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                is_useless = any(pattern in line for pattern in useless_patterns)
                if is_useless:
                    continue
                    
                filtered_lines.append(line)
            
            error_indicators = [
                "Map specified by --mapfile was not found",
                "Can't find mod:",
                "Något gick fel!",
                "Error:",
                "Failed to",
                "Could not",
                "No such file or directory",
                "Permission denied"
            ]
            
            error_lines = []
            for line in reversed(filtered_lines):
                for indicator in error_indicators:
                    if indicator in line:
                        error_lines.append(line)
                        break
                        
            if error_lines:
                error_lines.reverse()
                return " | ".join(error_lines[-3:])
            elif filtered_lines:
                return " | ".join(filtered_lines[-3:])
            else:
                return "No meaningful errors found in log"
                
        except Exception as e:
            return f"Could not read log file: {e}"
