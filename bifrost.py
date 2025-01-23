# filesystem I/O stuff

import os
import json
from typing import List, Optional
import stat
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import zipfile
from pathlib import Path


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
    def parse_ygg_metadata(file_path):
        """
        Parse a file to extract #yggemoji and #yggdescr metadata.

        Args:
            file_path (str): The path to the file to parse.

        Returns:
            dict: A dictionary containing 'yggemoji' and 'yggdescr' values, if found.
        """
        metadata = {
            "yggemoji": "::",
            "yggdescr": ""
        }

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = line.strip()
                    if line.startswith("#yggemoji"):
                        emoji = line[len("#yggemoji"):].strip().strip('"').strip("'")
                        metadata["yggemoji"] = f":{emoji}:" if emoji else "::"
                    elif line.startswith("#yggdescr"):
                        description = line[len("#yggdescr"):].strip().strip('"').strip("'")
                        metadata["yggdescr"] = description
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error parsing file {file_path}: {e}")

        return metadata

    @staticmethod
    def get_mods(config):
        """
        Fetches mods from the dom_data_folder and returns an array of JSONs for a dropdown.

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
            # Use scandir for efficient directory listing
            with os.scandir(mods_folder) as entries:
                for entry in entries:
                    if entry.is_dir():
                        # Location of the .dm file
                        dm_file_path = os.path.join(entry.path, f"{entry.name}.dm")

                        # Check if the file exists before parsing
                        if os.path.isfile(dm_file_path):
                            metadata = bifrost.parse_ygg_metadata(dm_file_path)
                        else:
                            metadata = {"yggemoji": "::", "yggdescr": ""}

                        # Create the JSON object for the mod
                        mod_json = {
                            "name": entry.name,
                            "location": f"{entry.name}/{entry.name}.dm",
                            "yggemoji": metadata.get("yggemoji", "::"),
                            "yggdescr": metadata.get("yggdescr", ""),
                        }
                        mods.append(mod_json)

        except Exception as e:
            print(f"Error reading mods folder: {e}")

        return mods

    @staticmethod
    def get_maps(config):
        """
        Fetches maps from the dom_data_folder and returns an array of JSONs for a dropdown.

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

        # Path to the maps folder
        maps_folder = os.path.join(dom_data_folder, "maps")

        try:
            # Use scandir for efficient directory listing
            with os.scandir(maps_folder) as entries:
                for entry in entries:
                    if entry.is_dir():
                        # Location of the .map file
                        map_file_path = os.path.join(entry.path, f"{entry.name}.map")

                        # Check if the file exists before parsing
                        if os.path.isfile(map_file_path):
                            metadata = bifrost.parse_ygg_metadata(map_file_path)
                        else:
                            metadata = {"yggemoji": "::", "yggdescr": ""}

                        # Create the JSON object for the map
                        map_json = {
                            "name": entry.name,
                            "location": f"{entry.name}/{entry.name}.map",
                            "yggemoji": metadata.get("yggemoji", "::"),
                            "yggdescr": metadata.get("yggdescr", ""),
                        }
                        maps.append(map_json)

        except Exception as e:
            print(f"Error reading maps folder: {e}")

        return maps


    @staticmethod
    def load_config():
        """Loads the 'config.json' file as a JSON object."""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"Error loading config file {config_path}: {e}")
            return None

    @staticmethod
    def remove_execution_permission(path: str):
        """
        Remove execute permissions from a single file.
        """
        if not os.path.exists(path):
            print(f"File {path} does not exist. Skipping.")
            return

        try:
            if os.path.isdir(path):
                # Skip directories entirely
                return

            # Remove execute permissions for files
            st = os.stat(path)
            new_mode = st.st_mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH
            os.chmod(path, new_mode)
        except Exception as e:
            raise e



    @staticmethod
    def remove_execution_permission_recursive(folder_path: str):
        """
        Remove execute permissions from files within a folder and all its contents.
        Provide a summarized report at the end and only log failures per item.
        """
        total_files = 0
        failed_items = []

        try:
            for root, dirs, files in os.walk(folder_path, topdown=False):
                # Process files
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        bifrost.remove_execution_permission(file_path)
                        total_files += 1
                    except PermissionError:
                        failed_items.append({"type": "file", "path": file_path, "error": "Permission denied"})
                    except Exception as e:
                        failed_items.append({"type": "file", "path": file_path, "error": str(e)})

                # Ensure directories retain their permissions
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        st = os.stat(dir_path)
                        new_mode = st.st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
                        os.chmod(dir_path, new_mode)
                    except PermissionError:
                        failed_items.append({"type": "directory", "path": dir_path, "error": "Permission denied"})
                    except Exception as e:
                        failed_items.append({"type": "directory", "path": dir_path, "error": str(e)})

            # Ensure the root folder retains its permissions
            try:
                st = os.stat(folder_path)
                new_mode = st.st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
                os.chmod(folder_path, new_mode)
            except PermissionError:
                failed_items.append({"type": "directory", "path": folder_path, "error": "Permission denied"})
            except Exception as e:
                failed_items.append({"type": "directory", "path": folder_path, "error": str(e)})

            # Summarized report
            print(f"Execution permissions removed from files:")
            print(f"  Total files processed: {total_files}")

            if failed_items:
                print("\nItems that failed to process:")
                for item in failed_items:
                    print(f"  [{item['type'].capitalize()}] {item['path']}: {item['error']}")
            else:
                print("  All items processed successfully.")
        except Exception as e:
            print(f"Error processing folder {folder_path}: {e}")




    @staticmethod
    def set_folder_no_exec(folder_path: str):
        """
        Prevent the folder and new contents from having executable permissions by default.

        Args:
            folder_path (str): The path to the folder.
        """
        try:
            # Remove executable permissions for the folder itself
            bifrost.remove_execution_permission(folder_path)

            # Set umask to prevent new files and directories from being created with executable permissions
            os.umask(0o111)
            print(f"Execution permissions restricted for: {folder_path}")
        except Exception as e:
            print(f"Error setting folder permissions for {folder_path}: {e}")

    @staticmethod
    def watch_folder(folder_path: str):
        """
        Monitor a folder for changes and remove execution permissions for newly added files.

        Args:
            folder_path (str): The path to the folder to watch.
        """
        class PermissionHandler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    bifrost.remove_execution_permission(event.src_path)

            def on_modified(self, event):
                if event.is_directory:
                    return  # Skip directories

                # Ensure the file exists before handling it
                if os.path.exists(event.src_path):
                    try:
                        bifrost.remove_execution_permission(event.src_path)
                    except Exception as e:
                        print(f"Error handling modified event for {event.src_path}: {e}")
                else:
                    print(f"File {event.src_path} does not exist. Skipping event.")


        try:
            observer = Observer()
            handler = PermissionHandler()
            observer.schedule(handler, folder_path, recursive=True)
            observer.start()
            print(f"Watching for changes in: {folder_path}")
            return observer  # Return the observer to manage its lifecycle
        except Exception as e:
            print(f"Error watching folder {folder_path}: {e}")

    @staticmethod
    def initialize_dom_data_folder(config):
        """
        Initialize the dom_data_folder by removing execution permissions and setting up a watcher.

        Args:
            config (dict): The configuration dictionary containing 'dom_data_folder'.
        """
        dom_data_folder = config.get("dom_data_folder")
        if not dom_data_folder:
            print("Error: 'dom_data_folder' not found in the config.")
            return

        # Remove execution permissions recursively
        bifrost.remove_execution_permission_recursive(dom_data_folder)

        # Set the folder to restrict executable permissions for new files
        bifrost.set_folder_no_exec(dom_data_folder)

        # Watch the folder for new files
        observer = bifrost.watch_folder(dom_data_folder)

        return observer

    @staticmethod
    def handle_map_upload(file_data: bytes, filename: str, config: dict) -> dict:
        """
        Handles the upload and extraction of a map zip file from raw binary data.

        Args:
            file_data (bytes): The raw binary content of the zip file.
            filename (str): The name of the uploaded file.
            config (dict): Configuration JSON containing the dom_data_folder path.

        Returns:
            dict: A dictionary containing success status, extracted path, and error (if any).
        """
        try:
            # Derive the maps folder path from config
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                return {"success": False, "error": "Configuration error: dom_data_folder is not set."}

            maps_folder = Path(dom_data_folder) / "maps"
            maps_folder.mkdir(parents=True, exist_ok=True)  # Ensure the maps folder exists

            # Save the binary data as a zip file
            zip_file_path = maps_folder / filename
            if zip_file_path.exists():
                return {"success": False, "error": f"A file with the name '{filename}' already exists in the maps folder."}

            with open(zip_file_path, "wb") as f:
                f.write(file_data)  # Write the raw binary data to the zip file
            print(f"Saved zip file to {zip_file_path}")

            # Determine the extraction folder (same name as the zip file, without the extension)
            extract_folder = maps_folder / zip_file_path.stem
            if extract_folder.exists():
                return {"success": False, "error": f"A folder named '{zip_file_path.stem}' already exists in the maps folder."}

            # Extract the zip file into the extraction folder
            bifrost.safe_extract_zip(str(zip_file_path), str(extract_folder))

            # Return success with extracted path
            return {"success": True, "extracted_path": str(extract_folder)}

        except zipfile.BadZipFile:
            return {"success": False, "error": "The uploaded file is not a valid zip file."}
        except Exception as e:
            return {"success": False, "error": str(e)}
        

    @staticmethod
    def handle_mod_upload(file_data: bytes, filename: str, config: dict) -> dict:
        """
        Handles the upload and extraction of a mod zip file from raw binary data.

        Args:
            file_data (bytes): The raw binary content of the zip file.
            filename (str): The name of the uploaded file.
            config (dict): Configuration JSON containing the dom_data_folder path.

        Returns:
            dict: A dictionary containing success status, extracted path, and error (if any).
        """
        try:
            # Derive the mods folder path from config
            dom_data_folder = config.get("dom_data_folder")
            if not dom_data_folder:
                return {"success": False, "error": "Configuration error: dom_data_folder is not set."}

            mods_folder = Path(dom_data_folder) / "mods"
            mods_folder.mkdir(parents=True, exist_ok=True)  # Ensure the mods folder exists

            # Save the binary data as a zip file
            zip_file_path = mods_folder / filename
            if zip_file_path.exists():
                return {"success": False, "error": f"A file with the name '{filename}' already exists in the mods folder."}

            with open(zip_file_path, "wb") as f:
                f.write(file_data)  # Write the raw binary data to the zip file
            print(f"Saved zip file to {zip_file_path}")

            # Determine the extraction folder (same name as the zip file, without the extension)
            extract_folder = mods_folder / zip_file_path.stem
            if extract_folder.exists():
                return {"success": False, "error": f"A folder named '{zip_file_path.stem}' already exists in the mods folder."}

            # Extract the zip file into the extraction folder
            bifrost.safe_extract_zip(str(zip_file_path), str(extract_folder))

            # Return success with extracted path
            return {"success": True, "extracted_path": str(extract_folder)}

        except zipfile.BadZipFile:
            return {"success": False, "error": "The uploaded file is not a valid zip file."}
        except Exception as e:
            return {"success": False, "error": str(e)}



    @staticmethod
    def safe_extract_zip(zip_path: str, extract_to: str):
        """
        Extract a zip file and ensure directories and files have proper permissions.
        """
        try:
            # Ensure the extraction directory exists and is writable
            os.makedirs(extract_to, exist_ok=True)
            os.chmod(extract_to, 0o755)  # Ensure the folder is accessible

            # Extract the zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            print(f"Extracted {zip_path} to {extract_to}")

            # Ensure directories are writable and executable
            for root, dirs, files in os.walk(extract_to):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    os.chmod(dir_path, 0o755)  # Set read, write, and execute permissions for directories
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    os.chmod(file_path, 0o644)  # Set read and write permissions for files

            # Remove execute permissions from files
            bifrost.remove_execution_permission_recursive(extract_to)

            # Delete the zip file after extraction
            os.remove(zip_path)
            print(f"Deleted zip file: {zip_path}")

        except zipfile.BadZipFile:
            raise ValueError(f"{zip_path} is not a valid zip file.")
        except PermissionError as e:
            raise RuntimeError(f"Permission denied during extraction: {e}")
        except Exception as e:
            raise RuntimeError(f"Error extracting zip file {zip_path}: {e}")


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

# # Example usage (to be removed or commented out in production):
# if __name__ == "__main__":
#     # Test the functionality
#     test_dir = "test_files"
#     test_file = os.path.join(test_dir, "example.txt")

#     # Create a directory
#     bifrost.create_directory(test_dir)

#     # Write to a file
#     bifrost.write_file(test_file, "Hello, Bifrost!")

#     # Read from a file
#     content = bifrost.read_file(test_file)
#     print(f"File content: {content}")

#     # List files in the directory
#     files = bifrost.list_files(test_dir)
#     print(f"Files in directory: {files}")

#     # Delete the file
#     bifrost.delete_file(test_file)
#     print(f"File deleted: {test_file not in os.listdir(test_dir)}")
