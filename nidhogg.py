#dom binary interaction module

from pathlib import Path
import subprocess
import json
import re

dom_folder_path = Path.home() / "dominions6"

def getServerStatus():
    statusResult = subprocess.run(
    [str(dom_folder_path / "dom6_amd64" ),"-T", "--tcpquery", "--ipadr" , "45.79.83.4", "--port", "6006"],
            stdout=subprocess.PIPE,
            text=True,
            stderr=subprocess.DEVNULL)
    return dominions_to_json(statusResult.stdout)

async def newGameLobby(game_id,db_instance):
    game_details = await db_instance.get_game_info(game_id = game_id)

    if game_details[4] == "Generated DA Map":
        subprocess.Popen(
            [str(dom_folder_path / "dom6_amd64"), "--tcpserver", "--ipadr", "localhost", "--port", str(game_details[2]), "--era", str(game_details[3]), "--mapfile", "smackdown_ea1", "--newgame", str(game_details[1]), "--noclientstart" ]
        )
        return
    elif game_details[4] == "Vanilla":
        subprocess.Popen(
            [str(dom_folder_path / "dom6_amd64"), "--tcpserver", "--ipadr", "localhost", "--port", str(game_details[2]), "--era", str(game_details[3]), "--randmap", "15", "--newgame", str(game_details[1]), "--noclientstart" ]
        )
        return
    else:
        print("Uploaded Maps not implemnted yet")
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

def serverStatusJsonToDiscordFormatted(status_json):
    # Start building the message
    message_parts = []
    
    # Add game info
    game_info = f"**Game Name:** {status_json.get('game_name')}\n"
    game_info += f"**Status:** {status_json.get('status')}\n"
    game_info += f"**Turn:** {status_json.get('turn')}\n"
    #This is dominions time, not ygg time
    #game_info += f"**Time Left:** {status_json.get('time_left')}\n"
    message_parts.append(game_info)
    
    # Add players info
    players_info = "**Players:**\n"
    for player in status_json.get('players', []):
        players_info += (f"Player {player['player_id']}: {player['nation']} ({player['nation_desc']}) - "
                         f"{player['status']}\n")
        
        # Check if message exceeds 1024 characters
        if len(players_info) > 1024:
            message_parts.append(players_info)
            players_info = ""  # Reset for next part if exceeds limit

    # Add any remaining players info
    if players_info:
        message_parts.append(players_info)

    # Join all parts into a single message
    formatted_message = "\n".join(message_parts)

    # Trim the message to 1024 characters if necessary
    return formatted_message[:1024]
