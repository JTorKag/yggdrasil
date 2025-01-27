from pathlib import Path
import subprocess
import json
import re
import os
import stat
import threading
import asyncio
from bifrost import bifrost
import signal
import shlex

class nidhogg:
    # Load configuration and set Dominions folder path
    _config = bifrost.load_config()
    dominions_folder = Path(_config.get("dominions_folder"))

    @staticmethod
    def set_executable_permission(file_path: str):
        """
        Set executable permission for the specified file.

        Args:
            file_path (str): The path to the file.
        """
        try:
            # Get the current file permissions
            st = os.stat(file_path)
            
            # Set the executable bit for the owner, group, and others
            os.chmod(file_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            
            print(f"Executable permission set for: {file_path}")
        except Exception as e:
            print(f"Error setting executable permission for {file_path}: {e}")


    @staticmethod
    async def launch_game_lobby(game_id, db_instance):
        try:
            game_details = await db_instance.get_game_info(game_id=game_id)
            if not game_details:
                print(f"No game found with ID: {game_id}")
                return False

            # Extract values
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

            # Properly construct the --postexec command
            postexec_command = (
                f"curl -X POST \"http://127.0.0.1:8000/postexec_notify?game_id={game_id}\" "
                f"-H 'Content-Type: application/x-www-form-urlencoded'"
            )

            preexec_command = (
                f"curl -X POST \"http://127.0.0.1:8000/preexec_backup?game_id={game_id}\" "
                f"-H 'Content-Type: application/x-www-form-urlencoded'"
            )



            # Build the base command
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
                "--textonly"
            ]

            # Add thrones
            throne_counts = thrones.split(",")
            command.extend(["--thrones"] + throne_counts)

            # Add story events logic
            story_events_map = {0: "--nostoryevents", 1: "--storyevents", 2: "--allstoryevents"}
            if story_events in story_events_map:
                command.append(story_events_map[story_events])

            # Add AI behavior
            if no_going_ai == 1:
                command.append("--nonewai")

            # Add research randomness
            if research_random == 1:
                command.append("--norandres")

            # Add map logic
            if game_map in {"vanilla_10", "vanilla_15", "vanilla_20", "vanilla_25"}:
                command.extend(["--randmap", game_map.split("_")[1]])
            else:
                command.extend(["--mapfile", game_map])

            # Add team game logic
            if teamgame:
                command.append("--teamgame")

            command.append("--statfile")

            # Prepare the screen command
            screen_name = f"dom_{game_id}"
            screen_command = ["screen", "-dmS", screen_name] + command

            # Launch the screen session
            screen_process = subprocess.Popen(
                screen_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            print(f"Screen process launched with PID: {screen_process.pid}")
            #print(" ".join(screen_command))  # Debug output to verify command

            # Wait for the `dom6_amd64` process to start
            await asyncio.sleep(1)

            # Retrieve the PID of the `dom6_amd64` process
            try:
                result = subprocess.check_output(["screen", "-ls", screen_name]).decode("utf-8")
                actual_pid = None
                for line in result.splitlines():
                    if f"{screen_name}" in line:
                        actual_pid = int(line.split(".")[0].strip())
                        break

                if not actual_pid:
                    print(f"Failed to find process for screen session: {screen_name}")
                    return False

                print(f"Actual PID for game ID {game_id}: {actual_pid}")

                # Update the database with the correct PID
                await db_instance.update_process_pid(game_id, actual_pid)
                await db_instance.update_game_running(game_id, True)

                return True

            except subprocess.CalledProcessError as e:
                print(f"Error retrieving screen session: {e}")
                return False

        except Exception as e:
            print(f"Error launching game lobby: {e}")
            return False




    @staticmethod
    async def force_game_host(game_id: int, config: dict, db_instance):
        """
        Calls Bifrost's force_game_host to write the domcmd file.

        Args:
            game_id (int): The game ID.
            config (dict): Configuration containing 'dom_data_folder'.
            db_instance: Database instance for retrieving game details.

        Raises:
            Exception: If any error occurs during the execution.
        """
        try:
            await bifrost.force_game_host(game_id, config, db_instance)
            print(f"Force host operation completed for game ID {game_id}.")
        except Exception as e:
            print(f"Error in Nidhogg's force_game_host: {e}")
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
            # Fetch game details from the database
            game_details = await db_instance.get_game_info(game_id=game_id)
            if not game_details or "process_pid" not in game_details or not game_details["process_pid"]:
                raise ValueError(f"No running process found for game ID: {game_id}.")

            process_pid = game_details["process_pid"]

            # Attempt to kill the process
            os.kill(process_pid, signal.SIGTERM)  # Use SIGTERM to terminate the process
            print(f"Process with PID {process_pid} for game ID {game_id} has been killed.")

            # Update the database to reflect the game is no longer running
            await db_instance.update_game_running(game_id, False)
        except ProcessLookupError:
            raise ValueError(f"Process with PID {process_pid} not found.")
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
            # Run the executable with the version flag
            result = subprocess.run(
                [str(nidhogg.dominions_folder / "dom6_amd64"), "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check for errors in the command execution
            if result.returncode != 0:
                return f"Error fetching version: {result.stderr.strip()}"

            # Extract version number from the output
            version_match = re.search(r"version (\d+\.\d+)", result.stdout)
            if version_match:
                return version_match.group(1)  # Return the extracted version number
            else:
                return "Version information not found in output."

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
            # Fetch the game details to get the port
            game_details = await db_instance.get_game_info(game_id)
            if not game_details:
                raise ValueError(f"No game found with ID {game_id}.")

            game_port = game_details.get("game_port")
            if not game_port:
                raise ValueError(f"No port found for game ID {game_id}.")

            # Construct the query command
            command = [
                str(nidhogg.dominions_folder / "dom6_amd64"),
                "--tcpquery",
                "--ipadr", "localhost",
                "--port", str(game_port)
            ]

            #print({shlex.join(command)})

            # Execute the command and capture output
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check for errors
            if result.returncode != 0:
                raise RuntimeError(f"Query failed with error: {result.stderr.strip()}")

            # Return the response
            #print(f"Game query response: {result.stdout.strip()}")
            return result.stdout.strip()

        except Exception as e:
            print(f"Error querying game status: {e}")
            raise e



    ### Helpers
