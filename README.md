
# **Yggdrasil**

Yggdrasil is a comprehensive Discord bot and automated game server management system designed specifically for hosting Dominions 6 multiplayer games. Named after the Norse world tree, this system serves as the central hub connecting players, game servers, file management, timers, and notifications in a seamless automated workflow.

## **What Yggdrasil Does**

Yggdrasil transforms Discord servers into fully automated Dominions 6 hosting platforms by:

- **Automated Game Hosting**: Creates and manages Dominions 6 server instances with configurable settings (maps, mods, eras, game rules)
- **Intelligent Turn Management**: Monitors turn progression, manages chess clocks, and automatically processes turns when timers expire
- **Comprehensive Backup System**: Automatically backs up game states before and after turn processing to prevent data loss  
- **Smart Notifications**: Sends Discord alerts for turn starts, missing turns, timer warnings, and game status changes
- **Player Management**: Tracks nation claims, player extensions, role assignments, and permission management
- **File Management**: Handles pretender uploads (.2h files), mod installations, map management, and file security
- **Game State Monitoring**: Real-time monitoring of game progress, player activity, and server health
- **Automated Recovery**: Handles server crashes, connection issues, and provides rollback capabilities

## **How It Works**

Yggdrasil operates through several interconnected components working together:

### **Core Architecture**
- **Discord Bot (Ratatorskr)**: Provides slash commands and user interaction interface
- **Game Server Manager (Nidhogg)**: Launches and controls Dominions 6 server processes using screen sessions
- **File System Manager (Bifrost)**: Handles all file operations, uploads, backups, and security
- **Database Manager (Vedrfolnir)**: SQLite-based storage for games, players, timers, and state tracking
- **Timer System (Norns)**: Continuous monitoring and countdown management with automatic actions
- **API Server (Gjallarhorn)**: FastAPI endpoints for game automation hooks and external integrations

### **Automated Game Lifecycle**
1. **Game Creation**: Players use Discord commands to create games with customizable settings
2. **Lobby Management**: Automatic Discord channel and role creation for each game
3. **Pretender Collection**: Players upload nation files directly through Discord
4. **Server Launch**: Dominions 6 server automatically starts with proper configuration
5. **Turn Processing**: System monitors for turn completion and processes automatically
6. **Backup & Recovery**: Game states are backed up before each turn with rollback capability
7. **Notifications**: Discord alerts keep players informed of game progress and deadlines

This was born from both a technical challenge ("can I automate this complex workflow?") and a practical need to solve the pain points of hosting Dominions 6 games on Discord servers. Built from the ground up to be community-deployable, allowing anyone to spin up their own automated hosting service.

**Note**: While functional and actively used, this system is still evolving. Deploy at your own discretion and feel free to reach out for help with setup or troubleshooting. 

---

## **Features**
- **Discord Integration**: Manages games, player roles, and channels through Discord commands.
- **Timer Management**: Automates game timers, allowing pausing, extending, and resetting.
- **Game Management**:
  - Create, edit, start, and stop games.
  - Assign winners and delete lobbies when games are completed.
- **FastAPI Integration**: Supports pre-execution backups and post-execution notifications for game turns.
- **Backup System**: Ensures game files are periodically backed up safely.
- **Extensibility**: Modular structure allows for easy addition of new commands and features.
- **Friendly Nation Names**: All nation selection interfaces now display human-readable nation names alongside technical identifiers:
- **Claim dropdowns** show "Tsmuwich (modnat_402)" instead of just "modnat_402"
- **Pretenders command** displays "Ulm (mid_ulm): Player Name" for better readability
- **Real-time parsing** of statusdump.txt ensures names are always current and accurate

- **Advanced Game Configuration**: The `/extra-game-settings` command provides access to 19+ advanced Dominions 6 parameters:
  - Research rate (Slow, Normal, Fast, Very Fast)
  - Diplomacy settings (Disabled, Weak, Binding)
  - Score graphs, event rarity, magic site frequency, and more
  - Autocomplete suggestions for all parameters with user-friendly names

- **Improved Navigation**: Browse commands use paginated dropdowns without confirmation requirements:
  - `/view-maps` and `/view-mods` let you explore available content
  - Enhanced file organization with emoji and description support

---

## **Getting Started**

### **System Requirements**
- **Python**: 3.11.2
- **Operating System**: Linux (Tested on Debian & WSL)
- **Dominions 6**: Installed on the same server

### **Modules**
- **yggdrasil.py**: Main script
- **vedrfolnir.py**: SQLite Module
- **norns.py**: Timer Module
- **nidhogg.py**: Dom binary Module
- **gjallarhorn.py**: API Module
- **bifrost.py**: Filesystem I/O Module
---

### **Dependencies**
Install the following dependencies to ensure the application works as intended.

#### **Python Libraries**
Set up a virtual environment and install the required libraries:
```bash
python3 -m venv ygg-venv
source ygg-venv/bin/activate
pip install -r requirements.txt
```

#### **System Packages**
Install the required system packages using `apt`:
```bash
sudo apt install screen
sudo apt install curl
sudo apt install lsb-release
sudo apt install libgl1
sudo apt install libglu1-mesa
sudo apt install libsdl2-2.0-0
```
These are mostly just to run the dom binary.

---

### **Installation**
1. Clone the repository:
   ```bash
   git clone https://github.com/JTorKag/yggdrasil.git
   cd yggdrasil
   ```

2. Set up your virtual environment:
   ```bash
   python3 -m venv ygg-venv
   source ygg-venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure the application:
   - Create a configuration file (e.g., `config.json`). "Use template provided"
   - Use absolute folder paths.
   - Add required details such as:
     - Discord Bot Token
     - Guild ID
     - Dominions folder path

4. Start the bot:
   ```bash
   python yggdrasil.py
   ```

### **Running as a System Service (Optional)**

For production deployments, you can run Yggdrasil as a systemd service to ensure it starts automatically and restarts on failure.

1. **Configure the service template**:
   ```bash
   cp yggdrasil.service.template yggdrasil.service
   ```
   
2. **Edit the service file** and replace the placeholders:
   - `YOUR_USERNAME` → your actual username
   - `/path/to/yggdrasil` → your actual Yggdrasil installation path
   
3. **Install and enable the service**:
   ```bash
   sudo cp yggdrasil.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable yggdrasil.service
   sudo systemctl start yggdrasil.service
   ```

4. **Check service status**:
   ```bash
   sudo systemctl status yggdrasil.service
   ```

**Service Management Commands**:
- Start: `sudo systemctl start yggdrasil.service`
- Stop: `sudo systemctl stop yggdrasil.service`  
- Restart: `sudo systemctl restart yggdrasil.service`
- View logs: `journalctl -u yggdrasil.service -f`

---

### **Discord Slash Commands**

Commands are organized by function and include permission restrictions to ensure proper game management.

**Permission Levels:**
- **Main Bot Channel**: Commands restricted to designated primary bot channels
- **Game Channels**: Commands that work only in individual game lobby channels  
- **Host/Admin**: Requires Game Host or Game Admin Discord role
- **Owner/Admin**: Requires being the game creator or having Game Admin role
- **Admin Only**: Requires Game Admin Discord role

#### **Game Creation & Setup**
- `/new-game` - Create a new game with detailed settings *[Main Bot Channel, Host/Admin]*
- `/edit-game` - Edit game properties (map, mods, settings) *[Game Channel, Owner/Admin]*
- `/extra-game-settings` - Configure advanced game parameters (research rate, diplo, hall of fame, etc.) *[Game Channel, Owner/Admin]*
- `/select-map` - Choose from available maps *[Game Channel, Owner/Admin]*
- `/select-mods` - Choose from available mods *[Game Channel, Owner/Admin]*
- `/view-maps` - Browse available maps without selection *[Main Bot Channel]*
- `/view-mods` - Browse available mods without selection *[Main Bot Channel]*
- `/upload-map` - Upload custom map files *[Main Bot Channel, Host/Admin]*
- `/upload-mod` - Upload custom mod files *[Main Bot Channel, Host/Admin]*

#### **Game Control & Hosting**
- `/launch` - Launch the game server process *[Game Channel, Owner/Admin]*
- `/start-game` - Begin the game after all pretenders claimed *[Game Channel, Owner/Admin]*
- `/force-host` - Force game to process turn immediately *[Game Channel, Owner/Admin]*
- `/restart-game-to-lobby` - Reset game back to lobby state *[Game Channel, Owner/Admin]*
- `/kill` - Stop game server process *[Game Channel, Owner/Admin]*
- `/end-game` - Mark game as finished *[Game Channel, Owner/Admin]*

#### **Player & Nation Management**
- `/claim` - Claim/unclaim nations via dropdown menu *[Game Channel]*
- `/unclaim` - Admin removal of nation claims *[Game Channel, Owner/Admin]*
- `/leave-game` - Set your claim to an inactive state, not the same as unclaiming *[Game Channel]*
- `/clear-claims` - Remove all nation claims in game *[Game Channel, Owner/Admin]*
- `/pretenders` - View all submitted pretender files *[Game Channel]*
- `/remove` - Remove pretender files from lobby *[Game Channel, Owner/Admin]*
- `/get-turn-save` - Get your .2h and .trn files for the current turn via DM *[Game Channel]*
- `/get-turn-all-saves` - Get all your .2h and .trn files from all turns via DM *[Game Channel]*

#### **Timer & Turn Management**
- `/timer` - Check remaining time on current turn *[Game Channel]*
- `/pause` - Pause/unpause game timer *[Game Channel, Owner/Admin]*
- `/extend-timer` - Add/remove time from current turn *[Game Channel, Conditionally Owner/Admin]*
- `/set-default-timer` - Change default turn timer *[Game Channel, Owner/Admin]*
- `/roll-back` - Restore game to previous turn backup *[Game Channel, Owner/Admin]*
- `/extensions-stats` - View player extension usage *[Game Channel]*
- `/chess-clock-setup` - Configure individual player time banks *[Game Channel, Owner/Admin]*
- `/player-extension-rules` - Set per-player extension limits *[Game Channel, Owner/Admin]*

#### **Game Information & Status**
- `/game-info` - Display detailed game settings and status *[Game Channel]*
- `/undone` - Show which players haven't taken their turn *[Game Channel]*
- `/list-active-games` - View all running games *[Main Bot Channel]*
- `/get-version` - Show Dominions server version *[Main Bot Channel]*

#### **Administrative Commands**
- `/delete-lobby` - Permanently delete game lobby and role *[Game Channel, Owner/Admin]*
- `/reset-game-started` - Reset game started flag *[Game Channel, Admin Only]*

---

### **API Endpoints**
#### `/preexec_backup`
Triggered before the turn progresses. This backs up game files to a secure location.

#### `/postexec_notify`
Triggered after the turn progresses. Notifies the Discord channel with:
- The current turn number
- Remaining time until the next turn
- Players who missed submitting their turns

---

### **Database Management**
The application uses **SQLite** for storing game and timer data. Key tables include:
- **`games`**: Stores game metadata such as map, era, and active status.
- **`players`**: Tracks player claims and their nations.
- **`gameTimers`**: Manages turn timers and defaults.

---

### **Troubleshooting**
1. **Timer Not Updating**
   - Ensure the TimerManager is initialized and running during startup.
   - Check the `gameTimers` table to ensure `timer_running` is set to `true`.

2. **API Errors**
   - Verify the `dom_data_folder` and `backup_data_folder` paths in the configuration file.
   - Ensure the API server is running on `127.0.0.1:8000`.

3. **Missing Permissions**
   - Ensure the bot has the following Discord permissions:
     - Manage Roles
     - Manage Channels
     - Send Messages
     - Read Message History
     - Manage Messages

---

### **Contributing**
Feel free to open issues or submit pull requests to improve the application. Contributions are welcome! 

---

### **License**
This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.  
You are free to use, modify, and distribute the code, provided that all modifications remain under the same license. For more details, see the [LICENSE](LICENSE) file.

---

### **Acknowledgments**
- **Mr.Clockwork**: Special thanks to the contributors of [MrClockwork-v4](https://github.com/Drithyl/MrClockwork-v4) for inspiration and guidance.
- **Dominions 6 Community**: For their support and feedback during development.
- **socalgg**: For being the reason I put myself through this mess.
