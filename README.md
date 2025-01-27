
# **Yggdrasil**

Yggdrasil is a robust Discord bot and game management system tailored for Dominions 6. It includes a suite of tools for managing multiplayer games, game timers, backups, and player interactions, all while leveraging a FastAPI-based API for automation and notifications.

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

---

## **Getting Started**

### **System Requirements**
- **Python**: 3.9 or later
- **Operating System**: Linux (Tested on Ubuntu/Debian)
- **Dominions 6**: Installed on the same server

---

### **Dependencies**
Install the following dependencies to ensure the application works as intended.

#### **Python Libraries**
Set up a virtual environment and install the required libraries:
```bash
python3 -m venv ygg-venv
source ygg-venv/bin/activate
pip install -U discord.py
pip install aiosqlite
pip install watchdog
pip install fastapi
pip install uvicorn
```

#### **System Packages**
Install the required system packages using `apt`:
```bash
sudo apt install lsb-release
sudo apt install screen
sudo apt install curl
```

---

### **Installation**
1. Clone the repository:
   ```bash
   git clone https://github.com/your-repo/yggdrasil.git
   cd yggdrasil
   ```

2. Set up your virtual environment:
   ```bash
   python3 -m venv ygg-venv
   source ygg-venv/bin/activate
   pip install -r requirements.txt
   ```

3. Configure the application:
   - Create a configuration file (e.g., `config.json`).
   - Add required details such as:
     - Discord Bot Token
     - Guild ID
     - Dominions folder path
     - API server details

4. Start the bot:
   ```bash
   python yggdrasil.py
   ```

---

### **Core Commands**
#### **Game Management**
- `/new-game`: Create a new game with detailed settings.
- `/edit-game`: Edit an existing game's properties.
- `/start-game`: Start a game after all pretenders are submitted.
- `/end-game`: Mark a game as finished but keep the lobby active.
- `/delete-lobby`: Delete a game’s lobby and associated role.
- `/end-game-and-lobby`: End the game and delete the lobby.

#### **Timer Management**
- `/pause-timer`: Pause a running game timer.
- `/extend-timer`: Extend or reduce the remaining time.
- `/set-timer-default`: Change the default timer value.

#### **Game Status**
- `/undone`: View the current turn status, including which nations have played or are still pending.

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
