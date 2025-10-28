"""
Admin-only commands - delete lobby, reset game state, etc.
"""

import discord
import asyncio
import os
from ..decorators import require_bot_channel, require_game_channel, require_game_admin, require_game_owner_or_admin, require_primary_bot_channel


def register_admin_commands(bot):
    """Register all admin-only commands to the bot's command tree."""
    

    @bot.tree.command(
        name="reset-game-started",
        description="Resets the game_started flag to allow retrying /start-game after failures (ADMIN ONLY).",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_game_channel(bot.config)
    @require_game_admin(bot.config)
    async def reset_game_started_command(interaction: discord.Interaction, confirm_game_name: str):
        await interaction.response.defer()
        
        game_id = await bot.db_instance.get_game_id_by_channel(interaction.channel_id)
        if not game_id:
            await interaction.followup.send("No game lobby is associated with this channel.")
            return
            
        game_info = await bot.db_instance.get_game_info(game_id)
        if not game_info:
            await interaction.followup.send("Game information not found.")
            return
            
        if confirm_game_name != game_info["game_name"]:
            await interaction.followup.send(
                f"The confirmation name '{confirm_game_name}' does not match the actual game name '{game_info['game_name']}'."
            )
            return
            
        if not game_info["game_started"]:
            await interaction.followup.send(f"Game '{game_info['game_name']}' is not marked as started - no reset needed.")
            return
            
        try:
            await bot.db_instance.set_game_started_value(game_id, False)
            await interaction.followup.send(
                f"✅ Game '{game_info['game_name']}' has been reset. The game_started flag is now False.\n"
                f"You can now retry `/start-game` to attempt starting the game again."
            )
            if bot.config and bot.config.get("debug", False):
                print(f"[ADMIN] Game ID {game_id} ({game_info['game_name']}) game_started flag reset by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"Failed to reset game_started flag: {e}")

    # SQLite Web Server Management Commands
    @bot.tree.command(
        name="sqlite-web-start",
        description="Start the SQLite web server with password protection (ADMIN ONLY - 30min timeout)",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    @require_game_admin(bot.config)
    async def sqlite_web_start_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Check if already running
        if hasattr(bot, 'sqlite_web_process') and bot.sqlite_web_process and bot.sqlite_web_process.returncode is None:
            await interaction.followup.send("SQLite web server is already running.", ephemeral=True)
            return
        
        password = bot.config.get("sqlite_web_password", "")
        if not password:
            await interaction.followup.send("Error: sqlite_web_password not configured in config.json", ephemeral=True)
            return
        
        install_location = bot.config.get("install_location", "/home/yggadmin/yggdrasil/")
        sqlite_web_path = os.path.join(install_location, "venv", "bin", "sqlite_web")
        db_path = os.path.join(install_location, "ygg.db")
        
        try:
            if bot.config and bot.config.get("debug", False):
                print(f"[SQLITE-WEB] Starting SQLite web server...")
                print(f"[SQLITE-WEB] Install location: {install_location}")
                print(f"[SQLITE-WEB] SQLite path: {sqlite_web_path}")
                print(f"[SQLITE-WEB] Database path: {db_path}")
                print(f"[SQLITE-WEB] Password configured: {'Yes' if password else 'No'}")
            
            # Create a temporary script to handle password input
            script_content = f'''#!/bin/bash
printf "{password}\\n{password}\\n"
'''
            script_path = os.path.join(install_location, "temp_sqlite_start.sh")
            
            if bot.config and bot.config.get("debug", False):
                print(f"[SQLITE-WEB] Creating temp script at: {script_path}")
            
            with open(script_path, 'w') as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
            
            cmd = f'bash -c "printf \\"{password}\\\\n{password}\\\\n\\" | {sqlite_web_path} -H 0.0.0.0 -p 8080 -P {db_path}"'
            
            if bot.config and bot.config.get("debug", False):
                print(f"[SQLITE-WEB] Executing command: {cmd}")
            
            bot.sqlite_web_process = await asyncio.create_subprocess_shell(
                cmd,
                cwd=install_location,
                stdout=None,  # Inherit from parent - shows in ygg terminal
                stderr=None,  # Inherit from parent - shows in ygg terminal
                preexec_fn=os.setsid  # Start in new process group for easier cleanup
            )
            
            if bot.config and bot.config.get("debug", False):
                print(f"[SQLITE-WEB] Process started with PID: {bot.sqlite_web_process.pid}")
            # Give it a moment to start
            await asyncio.sleep(0.5)
            if bot.sqlite_web_process.returncode is None:
                server_host = bot.config.get('server_host', 'localhost')
                
                # Start timeout task
                async def sqlite_timeout():
                    await asyncio.sleep(1800)  # 30 minutes
                    if hasattr(bot, 'sqlite_web_process') and bot.sqlite_web_process and bot.sqlite_web_process.returncode is None:
                        # Kill the entire process group to ensure all child processes are terminated
                        import signal as sig
                        try:
                            os.killpg(os.getpgid(bot.sqlite_web_process.pid), sig.SIGTERM)
                            await asyncio.wait_for(bot.sqlite_web_process.wait(), timeout=5.0)
                        except (ProcessLookupError, OSError):
                            # Process already dead or process group doesn't exist
                            pass
                        except asyncio.TimeoutError:
                            # Force kill if still running
                            try:
                                os.killpg(os.getpgid(bot.sqlite_web_process.pid), sig.SIGKILL)
                                await bot.sqlite_web_process.wait()
                            except (ProcessLookupError, OSError):
                                pass
                        
                        # Cancel timeout task
                        if hasattr(bot, 'sqlite_timeout_task') and bot.sqlite_timeout_task:
                            bot.sqlite_timeout_task.cancel()
                            bot.sqlite_timeout_task = None
                        
                        bot.sqlite_web_process = None
                        
                        # Notify in primary channel
                        primary_channels = bot.config.get("primary_bot_channel", [])
                        if primary_channels:
                            try:
                                channel = bot.get_channel(int(primary_channels[0]))
                                if channel:
                                    await channel.send("⏰ **SQLite web server auto-timeout** (30 minutes) - server shut down.")
                            except:
                                pass
                
                bot.sqlite_timeout_task = asyncio.create_task(sqlite_timeout())
                
                embed = discord.Embed(
                    title="🟢 SQLite Web Server Started",
                    description=f"**Access URL:** http://{server_host}:8080\n⏰ **Auto-timeout:** 30 minutes",
                    color=discord.Color.green()
                )
                embed.add_field(name="Process ID", value=str(bot.sqlite_web_process.pid), inline=True)
                embed.add_field(name="Started by", value=interaction.user.mention, inline=True)
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Clean up the temporary script after a delay
                async def cleanup_script():
                    await asyncio.sleep(10)
                    try:
                        os.remove(script_path)
                    except:
                        pass
                asyncio.create_task(cleanup_script())
            else:
                await interaction.followup.send(f"Error: SQLite web server failed to start (exit code: {bot.sqlite_web_process.returncode})", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error starting SQLite web server: {e}", ephemeral=True)

    @bot.tree.command(
        name="sqlite-web-stop",
        description="Stop the SQLite web server (ADMIN ONLY)",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    @require_game_admin(bot.config)
    async def sqlite_web_stop_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not hasattr(bot, 'sqlite_web_process') or not bot.sqlite_web_process or bot.sqlite_web_process.returncode is not None:
            await interaction.followup.send("SQLite web server is not running.", ephemeral=True)
            return
        
        try:
            # Kill the entire process group to ensure all child processes are terminated
            import signal as sig
            try:
                os.killpg(os.getpgid(bot.sqlite_web_process.pid), sig.SIGTERM)
                await asyncio.wait_for(bot.sqlite_web_process.wait(), timeout=5.0)
            except (ProcessLookupError, OSError):
                # Process already dead or process group doesn't exist
                pass
            except asyncio.TimeoutError:
                # Force kill if still running
                try:
                    os.killpg(os.getpgid(bot.sqlite_web_process.pid), sig.SIGKILL)
                    await bot.sqlite_web_process.wait()
                except (ProcessLookupError, OSError):
                    pass
            
            # Cancel timeout task
            if hasattr(bot, 'sqlite_timeout_task') and bot.sqlite_timeout_task:
                bot.sqlite_timeout_task.cancel()
                bot.sqlite_timeout_task = None
            
            bot.sqlite_web_process = None
            
            embed = discord.Embed(
                title="🔴 SQLite Web Server Stopped",
                description="Server has been shut down successfully.",
                color=discord.Color.red()
            )
            embed.add_field(name="Stopped by", value=interaction.user.mention, inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error stopping SQLite web server: {e}", ephemeral=True)

    @bot.tree.command(
        name="sqlite-web-status",
        description="Check the status of the SQLite web server (ADMIN ONLY)",
        guild=discord.Object(id=bot.guild_id)
    )
    @require_primary_bot_channel(bot.config)
    @require_game_admin(bot.config)
    async def sqlite_web_status_command(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if hasattr(bot, 'sqlite_web_process') and bot.sqlite_web_process and bot.sqlite_web_process.returncode is None:
            server_host = bot.config.get('server_host', 'localhost')
            embed = discord.Embed(
                title="🟢 SQLite Web Server Status",
                description="Server is currently running",
                color=discord.Color.green()
            )
            embed.add_field(name="Process ID", value=str(bot.sqlite_web_process.pid), inline=True)
            embed.add_field(name="Access URL", value=f"http://{server_host}:8080", inline=True)
            embed.add_field(name="Auto-timeout", value="30 minutes", inline=True)
        else:
            embed = discord.Embed(
                title="🔴 SQLite Web Server Status",
                description="Server is not running",
                color=discord.Color.red()
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    return [
        reset_game_started_command,
        sqlite_web_start_command,
        sqlite_web_stop_command,
        sqlite_web_status_command
    ]