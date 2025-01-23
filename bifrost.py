# filesystem I/O stuff

import os
import json
from typing import List, Optional

class bifrost:
    """A utility class for managing file I/O operations."""


    @staticmethod
    def load_config():
        """Loads the 'config.json' file as a JSON object.

        Returns:
            dict or None: Parsed JSON object from the config file, or None if an error occurs.
        """
        # Get the directory of the current script        
        # Combine it with the relative path to 'config.json'
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"Error loading config file {config_path}: {e}")
            return None
        
    @staticmethod
    def get_mods(config):
        """Fetches mods from the dom_data_folder and returns an array of JSONs for a dropdown.

        Args:
            config (dict): Configuration JSON object containing the dom_data_folder path.

        Returns:
            list[dict]: Array of JSON objects for dropdown options.
        """
        mods = []

        # Get the dom_data_folder path from the config
        dom_data_folder = config.get("dom_data_folder", "")
        if not dom_data_folder:
            print("Error: 'dom_data_folder' not found in the config.")
            return mods

        # Path to the mods folder
        mods_folder = os.path.join(dom_data_folder, "mods")

        try:
            # List all directories in the mods folder
            for item in os.listdir(mods_folder):
                item_path = os.path.join(mods_folder, item)

                # Ensure it is a directory
                if os.path.isdir(item_path):
                    # Create the JSON object for the mod
                    mod_json = {
                        "name": item,
                        "location": f"{item}/{item}.dm",
                        "yggemoji": ":placeholder_emoji:",  # Placeholder
                        "yggdescr": "Placeholder description",  # Placeholder
                    }
                    mods.append(mod_json)

        except Exception as e:
            print(f"Error reading mods folder: {e}")

        return mods
    
    @staticmethod
    def get_maps(config):
        """Fetches maps from the dom_data_folder and returns an array of JSONs for a dropdown.

        Args:
            config (dict): Configuration JSON object containing the dom_data_folder path.

        Returns:
            list[dict]: Array of JSON objects for dropdown options.
        """
        maps = []

        # Get the dom_data_folder path from the config
        dom_data_folder = config.get("dom_data_folder", "")
        if not dom_data_folder:
            print("Error: 'dom_data_folder' not found in the config.")
            return maps

        # Path to the mods folder
        maps_folder = os.path.join(dom_data_folder, "maps")

        try:
            # List all directories in the mods folder
            for item in os.listdir(maps_folder):
                item_path = os.path.join(maps_folder, item)

                # Ensure it is a directory
                if os.path.isdir(item_path):
                    # Create the JSON object for the mod
                    mod_json = {
                        "name": item,
                        "location": f"{item}/{item}.map",
                        "yggemoji": ":placeholder_emoji:",  # Placeholder
                        "yggdescr": "Placeholder description",  # Placeholder
                    }
                    maps.append(mod_json)

        except Exception as e:
            print(f"Error reading mods folder: {e}")

        return maps

    @staticmethod
    def read_file(filepath: str) -> Optional[str]:
        """Reads the contents of a file.

        Args:
            filepath (str): Path to the file to read.

        Returns:
            Optional[str]: The contents of the file, or None if an error occurs.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    @staticmethod
    def write_file(filepath: str, content: str) -> bool:
        """Writes content to a file.

        Args:
            filepath (str): Path to the file to write.
            content (str): Content to write to the file.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(content)
            return True
        except Exception as e:
            print(f"Error writing to file {filepath}: {e}")
            return False

    @staticmethod
    def list_files(directory: str, extension: Optional[str] = None) -> List[str]:
        """Lists all files in a directory, optionally filtered by extension.

        Args:
            directory (str): Path to the directory to list files from.
            extension (Optional[str]): File extension to filter by (e.g., ".txt").

        Returns:
            List[str]: A list of file paths.
        """
        try:
            files = [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
            if extension:
                files = [f for f in files if f.endswith(extension)]
            return files
        except Exception as e:
            print(f"Error listing files in directory {directory}: {e}")
            return []

    @staticmethod
    def create_directory(directory: str) -> bool:
        """Creates a directory if it does not already exist.

        Args:
            directory (str): Path to the directory to create.

        Returns:
            bool: True if the directory was created or already exists, False otherwise.
        """
        try:
            os.makedirs(directory, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating directory {directory}: {e}")
            return False

    @staticmethod
    def delete_file(filepath: str) -> bool:
        """Deletes a file.

        Args:
            filepath (str): Path to the file to delete.

        Returns:
            bool: True if the file was deleted, False otherwise.
        """
        try:
            os.remove(filepath)
            return True
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
            return False

# Example usage (to be removed or commented out in production):
if __name__ == "__main__":
    # Test the functionality
    test_dir = "test_files"
    test_file = os.path.join(test_dir, "example.txt")

    # Create a directory
    Bifrost.create_directory(test_dir)

    # Write to a file
    Bifrost.write_file(test_file, "Hello, Bifrost!")

    # Read from a file
    content = Bifrost.read_file(test_file)
    print(f"File content: {content}")

    # List files in the directory
    files = Bifrost.list_files(test_dir)
    print(f"Files in directory: {files}")

    # Delete the file
    Bifrost.delete_file(test_file)
    print(f"File deleted: {test_file not in os.listdir(test_dir)}")
