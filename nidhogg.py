#dom binary interaction module

from pathlib import Path
import subprocess
import json
import re
import os
import stat
import threading
from bifrost import bifrost

# with open("config.json", 'r') as file:
#     config = json.load(file)
# dom_folder_path= Path(config["dominions_folder"])
# dom_data_folder_path = Path(config["dom_data_folder"])

config = bifrost.load_config()

dominions_folder = Path(config.get("dominions_folder"))



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

set_executable_permission(dominions_folder/ "dom6_amd64")

def getServerStatus():
    statusResult = subprocess.run(
    [str(dominions_folder/"dom6_amd64"),"-T", "--tcpquery", "--ipadr" , "45.79.83.4", "--port", "6006"],
            stdout=subprocess.PIPE,
            text=True,
            stderr=subprocess.DEVNULL)
    return dominions_to_json(statusResult.stdout)

async def launchGameLobby(game_id,db_instance):
    game_details = await db_instance.get_game_info(game_id=game_id)
    
    # Base command for launching the game
    command = [
        str(dominions_folder/"dom6_amd64"),
        "--tcpserver",
        "--ipadr", "localhost",
        "--port", str(game_details[2]),
        "--era", str(game_details[3]),
        "--newgame", str(game_details[1]),
        "--noclientstart"
    ]

    # Add specific parameters based on map type
    if game_details[4] == "Generated DA Map":
        command.extend(["--mapfile", "smackdown_ea1"])
    elif game_details[4] == "Vanilla":
        command.extend(["--randmap", "15"])
    else:
        print("Uploaded Maps not implemented yet")
        return None

    # Launch the process in a detached thread
    def launch_process():
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            print(f"Process launched with PID: {process.pid}")
            return process.pid
        except Exception as e:
            print(f"Failed to launch process: {e}")
            return None

    pid_container = []

    def thread_target():
        pid = launch_process()
        if pid is not None:
            pid_container.append(pid)

    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()
    thread.join()
    await db_instance.update_process_pid(game_id,int(pid_container[0]))
    await db_instance.update_game_running(game_id, 1)
    return

### Helpers

def dominions_to_json(log_string):
    dom_status_json = {}
    
    # Extract the general game info
    game_info_pattern = re.compile(r"Gamename:\s*(\S+)\nStatus:\s*(.+?)\nTurn:\s*(\d+)\nTime left:\s*(\d+ ms)")
    game_info_match = game_info_pattern.search(log_string)
    
    if game_info_match:
        dom_status_json['game_name'] = game_info_match.group(1)
        dom_status_json['status'] = game_info_match.group(2).strip()
        dom_status_json['turn'] = int(game_info_match.group(3))
        dom_status_json['time_left'] = game_info_match.group(4).strip()
    
    # Extract player info
    players = []
    player_info_pattern = re.compile(r"player (\d+): ([^,]+), ([^()]+) \(([^)]+)\)")
    for match in player_info_pattern.finditer(log_string):
        player = {
            "player_id": int(match.group(1)),
            "nation": match.group(2).strip(),
            "nation_desc": match.group(3).strip(),
            "status": match.group(4).strip()
        }
        players.append(player)
    
    dom_status_json['players'] = players
    
    return dom_status_json


