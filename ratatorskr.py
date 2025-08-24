"""
Ratatorskr Discord Bot - Main Module

This module serves as the main entry point for the Ratatorskr Discord bot,
importing the refactored components from the ratatorskr package.
"""

from ratatorskr.client import discordClient
from ratatorskr.utils import serverStatusJsonToDiscordFormatted

# Export the main classes and functions that external modules expect
__all__ = ['discordClient', 'serverStatusJsonToDiscordFormatted']