"""
Meme commands - fun image manipulation commands.
"""

import discord
from PIL import Image, ImageDraw, ImageFont
import io
import os


async def should_shame_player(bot, game_id: int, undone_nations: list, played_but_not_finished: list) -> tuple:
    """
    Check if exactly one player is left undone/unfinished and get their Discord name.

    Args:
        bot: The Discord bot instance
        game_id: The game ID to check
        undone_nations: List of nation names that are undone
        played_but_not_finished: List of nation names that are unfinished

    Returns:
        tuple: (should_shame: bool, player_name: str or None, nation: str or None)
    """
    import random

    # Combine undone and unfinished nations
    incomplete_nations = undone_nations + played_but_not_finished

    print(f"[DEBUG SHAME] Total incomplete nations: {len(incomplete_nations)} - {incomplete_nations}")

    # If there's not exactly 1 incomplete nation, don't shame
    if len(incomplete_nations) != 1:
        print(f"[DEBUG SHAME] Not exactly 1 incomplete nation, skipping shame")
        return (False, None, None)

    target_nation = incomplete_nations[0]
    print(f"[DEBUG SHAME] Target nation to shame: {target_nation}")

    try:
        # Get all players for this game from the database
        players = await bot.db_instance.get_currently_claimed_players(game_id)
        print(f"[DEBUG SHAME] Found {len(players)} claimed players")

        # Find ALL players who claimed this nation
        claimant_names = []
        for player in players:
            print(f"[DEBUG SHAME] Checking player: {player.get('nation_name')} vs {target_nation}")
            if player["nation_name"] == target_nation:
                player_id = player["player_id"]

                # Get the Discord user
                try:
                    print(f"[DEBUG SHAME] Found matching player! player_id={player_id}")
                    user = await bot.fetch_user(int(player_id))
                    if user:
                        # Get display name (nickname or username)
                        player_name = user.display_name
                        print(f"[DEBUG SHAME] Fetched user: {player_name}")

                        if player_name:
                            claimant_names.append(player_name)

                except Exception as e:
                    print(f"[DEBUG SHAME] Error fetching user {player_id}: {e}")

        if claimant_names:
            # Pick a random claimant to shame
            chosen_victim = random.choice(claimant_names)
            last_letter = chosen_victim[-1]
            victim_with_repeat = chosen_victim + (last_letter * 4)

            print(f"[DEBUG SHAME] Randomly chose victim: {victim_with_repeat} from {len(claimant_names)} claimants")
            return (True, victim_with_repeat, target_nation)

    except Exception as e:
        print(f"Error checking for shame: {e}")

    return (False, None, None)


def generate_skeletor_image(text: str) -> io.BytesIO:
    """
    Generate a Skeletor meme image with the given text.

    Args:
        text: The text to overlay on the bottom of the Skeletor image

    Returns:
        BytesIO buffer containing the PNG image

    Raises:
        FileNotFoundError: If the skeletor.png base image is not found
    """
    # Load the base image
    base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources", "skeletor.png")

    if not os.path.exists(base_path):
        raise FileNotFoundError("Skeletor base image not found at resources/skeletor.png")

    # Open the image
    img = Image.open(base_path)

    # Create a drawing context
    draw = ImageDraw.Draw(img)

    # Get image dimensions
    img_width, img_height = img.size

    # Try to use a nice font, fall back to default if not available
    base_font_size = 100  # Starting font size
    font_size = base_font_size

    # Find the appropriate font file
    font_path_found = None
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]
    for font_path in font_paths:
        if os.path.exists(font_path):
            font_path_found = font_path
            break

    # Function to calculate wrapped lines and check if they fit
    def get_wrapped_lines_and_check_fit(font_obj):
        max_width = img_width - 60  # 30px padding on each side
        lines = []
        words = text.split()
        current_line = []
        max_line_width = 0

        for word in words:
            # Check if this single word is too wide
            word_bbox = draw.textbbox((0, 0), word, font=font_obj)
            word_width = word_bbox[2] - word_bbox[0]

            if word_width > max_width:
                # Single word is too wide, need smaller font
                return None, 0

            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font_obj)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                current_line.append(word)
                max_line_width = max(max_line_width, text_width)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)

        if current_line:
            final_line = ' '.join(current_line)
            bbox = draw.textbbox((0, 0), final_line, font=font_obj)
            max_line_width = max(max_line_width, bbox[2] - bbox[0])
            lines.append(final_line)

        return lines, max_line_width

    # Find the right font size that fits
    font = None
    lines = []
    min_font_size = 20

    try:
        while font_size >= min_font_size:
            if font_path_found:
                font = ImageFont.truetype(font_path_found, font_size)
            else:
                font = ImageFont.load_default()
                lines = [text]  # Just use text as-is with default font
                break

            lines, max_line_width = get_wrapped_lines_and_check_fit(font)

            # If any single word is too wide, reduce font size
            if lines is None:
                font_size -= 5
                continue

            # Calculate total text height
            line_height = font_size + 15
            total_text_height = len(lines) * line_height

            # Check if text fits within image height (with padding)
            if total_text_height + 60 <= img_height:  # 30px padding top and bottom
                break

            # Reduce font size and try again
            font_size -= 5

        if font is None:
            font = ImageFont.load_default()
            lines = [text]

    except Exception as e:
        font = ImageFont.load_default()
        lines = [text]

    # Calculate final text height and position
    line_height = font_size + 15
    total_text_height = len(lines) * line_height

    # Position text at the bottom of the image, overlaying it
    y_position = img_height - total_text_height - 30

    # Draw each line of text with black border (stroke)
    border_width = 3
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x_position = (img_width - text_width) // 2
        y = y_position + (i * line_height)

        # Draw black border by drawing text multiple times around the main position
        for adj_x in range(-border_width, border_width + 1):
            for adj_y in range(-border_width, border_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x_position + adj_x, y + adj_y), line, font=font, fill='black')

        # Draw white text on top
        draw.text((x_position, y), line, font=font, fill='white')

    # Save to bytes buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return buffer


def register_meme_commands(bot):
    """
    Register all meme commands to the bot's command tree.

    Note: The !skeletor command is handled in client.py on_message() as a hidden message-based command.
    """
    # No slash commands registered here currently
    # All meme functionality is available through message commands or programmatic calls
    pass
