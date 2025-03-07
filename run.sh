#!/bin/bash
# Script to set up and run the PST Email Analyzer

# Check if libpst is installed and set the path
READPST_PATH=""
if command -v readpst &> /dev/null; then
    READPST_PATH=$(dirname $(which readpst))
    echo "Found readpst at: $(which readpst)"
else
    echo "readpst command not found. Installing libpst..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        brew install libpst
        if command -v readpst &> /dev/null; then
            READPST_PATH=$(dirname $(which readpst))
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        sudo apt-get update && sudo apt-get install -y pst-utils
        if command -v readpst &> /dev/null; then
            READPST_PATH=$(dirname $(which readpst))
        fi
    else
        echo "Unsupported OS. Please install libpst manually."
        exit 1
    fi
fi

if [ -z "$READPST_PATH" ]; then
    echo "Failed to find readpst even after installation attempt."
    exit 1
fi

echo "Using readpst from: $READPST_PATH"

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Install required packages
echo "Installing required packages..."
pip install -r requirements.txt

# Create required directories
mkdir -p uploads results

# Set environment for the application
export PATH="$READPST_PATH:$PATH"
echo "PATH set to: $PATH"

# Set organization API key as environment variable 
# Note: For production deployments, this key should be set externally
# You can set the PRELOADED_API_KEY environment variable before running this script
# If not set, the user will need to provide their own API key through the UI

# Verify readpst is available in the current environment
if command -v readpst &> /dev/null; then
    echo "readpst is available at: $(which readpst)"
    readpst --version
else
    echo "ERROR: readpst is still not available in the PATH"
    echo "Attempting to create symbolic link..."
    mkdir -p venv/bin
    ln -sf "$READPST_PATH/readpst" venv/bin/readpst
    echo "Created symlink: venv/bin/readpst -> $READPST_PATH/readpst"
fi

# Run the application
echo "Starting PST Email Analyzer on port 5050..."
echo "Access the application at: http://localhost:5050"
python app.py