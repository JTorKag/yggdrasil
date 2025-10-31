#!/usr/bin/env python3
"""
Migration script: Convert existing chess timer data to new schema.

This script migrates chess timer data from the players table to the new chess_timers table.
For each game+nation combination with active chess clock, it creates a chess_timer entry
and links all players claiming that nation to the shared timer.

Run this once after deploying the chess timer refactor.
"""

import asyncio
import aiosqlite
import sqlite3


async def migrate_chess_timers(db_path='ygg.db'):
    """Migrate existing chess timer data to the new schema."""
    print("Starting chess timer migration...")

    conn = await aiosqlite.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    try:
        async with conn.cursor() as cursor:
            # Find all games with chess clock active
            await cursor.execute("""
                SELECT game_id, game_name, chess_clock_active
                FROM games
                WHERE chess_clock_active = 1
            """)
            games = await cursor.fetchall()

            if not games:
                print("No games with active chess clocks found. Nothing to migrate.")
                return

            print(f"Found {len(games)} games with chess clocks active.")

            total_timers_created = 0
            total_players_linked = 0

            for game in games:
                game_id = game['game_id']
                game_name = game['game_name']
                print(f"\nProcessing game: {game_name} (ID: {game_id})")

                # Get all distinct nations in this game with their max chess_clock_time_remaining
                await cursor.execute("""
                    SELECT nation, MAX(chess_clock_time_remaining) as max_time
                    FROM players
                    WHERE game_id = ? AND currently_claimed = 1
                    GROUP BY nation
                """, (game_id,))
                nations = await cursor.fetchall()

                for nation_row in nations:
                    nation = nation_row['nation']
                    time_remaining = nation_row['max_time'] or 0

                    # Check if chess_timer already exists for this game+nation
                    await cursor.execute("""
                        SELECT chess_timer_id FROM chess_timers
                        WHERE game_id = ? AND nation = ?
                    """, (game_id, nation))
                    existing = await cursor.fetchone()

                    if existing:
                        chess_timer_id = existing['chess_timer_id']
                        print(f"  Nation {nation}: chess_timer already exists (ID: {chess_timer_id})")
                    else:
                        # Create new chess_timer
                        await cursor.execute("""
                            INSERT INTO chess_timers (game_id, nation, time_remaining)
                            VALUES (?, ?, ?)
                        """, (game_id, nation, time_remaining))
                        chess_timer_id = cursor.lastrowid
                        total_timers_created += 1
                        print(f"  Nation {nation}: created chess_timer (ID: {chess_timer_id}, time: {time_remaining}s)")

                    # Link all players for this nation to the chess_timer
                    await cursor.execute("""
                        UPDATE players
                        SET chess_timer_id = ?
                        WHERE game_id = ? AND nation = ? AND currently_claimed = 1
                    """, (chess_timer_id, game_id, nation))
                    players_updated = cursor.rowcount
                    total_players_linked += players_updated
                    print(f"    Linked {players_updated} player(s) to this chess_timer")

            await conn.commit()

            print(f"\n{'='*60}")
            print(f"Migration complete!")
            print(f"  Chess timers created: {total_timers_created}")
            print(f"  Players linked: {total_players_linked}")
            print(f"{'='*60}")

            # Optional: Clear old chess_clock_time_remaining values (no longer used)
            print("\nCleaning up old chess_clock_time_remaining column...")
            await cursor.execute("""
                UPDATE players SET chess_clock_time_remaining = 0
            """)
            await conn.commit()
            print("Old column values cleared (column kept for schema compatibility)")

    except Exception as e:
        print(f"Error during migration: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    print("Chess Timer Migration Script")
    print("This will migrate existing chess timer data to the new nation-based schema.")
    response = input("\nDo you want to proceed? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        asyncio.run(migrate_chess_timers())
    else:
        print("Migration cancelled.")
