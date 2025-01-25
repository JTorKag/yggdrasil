#!/bin/bash

# Ensure the script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root. Exiting."
    exit 1
fi

# Create the /run/screen directory if it doesn't exist
if [ ! -d "/run/screen" ]; then
    echo "Creating /run/screen directory..."
    mkdir -p /run/screen
    if [ $? -ne 0 ]; then
        echo "Failed to create /run/screen directory. Exiting."
        exit 1
    fi
    echo "/run/screen directory created successfully."
else
    echo "/run/screen directory already exists."
fi

# Set ownership of /run/screen to root:utmp
echo "Setting ownership of /run/screen to root:utmp..."
chown root:utmp /run/screen
if [ $? -ne 0 ]; then
    echo "Failed to set ownership for /run/screen. Exiting."
    exit 1
fi

# Set permissions for /run/screen
echo "Setting permissions for /run/screen to 775..."
chmod 775 /run/screen
if [ $? -ne 0 ]; then
    echo "Failed to set permissions for /run/screen. Exiting."
    exit 1
fi

echo "Screen permissions have been successfully configured."
