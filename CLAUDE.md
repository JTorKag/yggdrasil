# Yggdrasil Development Guidelines

## Critical Architectural Rules

### Database Access Pattern
**NEVER** allow Ratatorskr (Discord bot) commands to directly access the database.

- ❌ **Wrong**: `bot.db_instance.connection.execute("DELETE FROM gameTimers...")`
- ✅ **Correct**: `bot.db_instance.delete_game_timers(game_id)`

**All database operations must go through Vedrfolnir's methods.**

#### Why?
1. **Separation of Concerns**: Vedrfolnir is the database abstraction layer
2. **Safety**: Centralized error handling and retry logic
3. **Maintainability**: Database schema changes only require updates in Vedrfolnir
4. **Consistency**: All database operations follow the same patterns

#### Architecture:
```
Discord User → Ratatorskr (Bot) → Vedrfolnir (DB API) → SQLite Database
                     ↓                      ↓
              (Discord Commands)    (Database Methods)
```

### Module Responsibilities

- **Ratatorskr**: Discord interaction, command handling, user interface
- **Vedrfolnir**: Database operations, schema management, data validation
- **Nidhogg**: Dominions binary interaction, game process management
- **Bifrost**: File system operations, backups, file validation
- **Norns**: Timer management, turn processing
- **Gjallarhorn**: API endpoints for external integrations

## Testing Commands

When changes are made, test with:
- Lint: `npm run lint` (if available)
- Type check: `npm run typecheck` (if available)
- Python lint: `ruff` (if available)

## Game State Logic

### game_active vs game_ended vs game_started
- `game_active = 1`: Lobby exists (has Discord channel)
- `game_active = 0`: Lobby deleted (no Discord channel)
- `game_started = 1`: Game has begun play
- `game_started = 0`: Game in lobby state
- `game_ended = 1`: Game formally ended with winner
- `game_ended = 0`: Game not yet ended

### Lifecycle:
1. Create lobby: `game_active=1, game_started=0, game_ended=0`
2. Launch server: `game_active=1, game_started=0, game_ended=0`
3. Start game: `game_active=1, game_started=1, game_ended=0`
4. End game: `game_active=1, game_started=1, game_ended=1`
5. Delete lobby: `game_active=0, game_started=1, game_ended=1`