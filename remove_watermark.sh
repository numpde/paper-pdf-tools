#!/bin/bash
# File: remove_watermark.sh

# Define repository path
REPO="/home/ra/repos/no-watermark"

echo "Running script from $REPO"
echo "Arguments: $@"
echo "Current directory: $(pwd)"

# Check repository directory exists
if [ ! -d "$REPO" ]; then
    echo "Error: Repository directory $REPO not found."
    exit 1
fi

# Activate the virtual environment
if [ -f "$REPO/.venv/bin/activate" ]; then
    source "$REPO/.venv/bin/activate"
else
    echo "Error: Virtual environment not found in $REPO/.venv"
    exit 1
fi

# Ensure at least one argument is provided
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 input_pdf [output_pdf]"
    exit 1
fi

which python

SCRIPT="$REPO/remove_watermark.py"

# Check that "$REPO/remove_watermark.py" exists
if [ ! -f "$SCRIPT" ]; then
    echo "Error: Python script '$SCRIPT' not found."
    exit 1
fi

# Run the Python script (adjust the script name if needed)
python "$SCRIPT" "$@"
