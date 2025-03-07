#!/usr/bin/env python3
"""
Wrapper script for readpst command to address path issues.
This script will be used by the main application to execute readpst
with the correct path.
"""

import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("readpst_wrapper")

def find_readpst():
    """Find the readpst command path"""
    # Possible paths for readpst
    readpst_paths = [
        'readpst',                      # Default PATH
        '/opt/homebrew/bin/readpst',    # Homebrew on Apple Silicon
        '/usr/local/bin/readpst',       # Homebrew on Intel Mac
        '/usr/bin/readpst',             # Linux standard location
        '/opt/homebrew/Cellar/libpst/0.6.76/bin/readpst'  # Direct Homebrew Cellar path
    ]
    
    # Check each path
    for cmd in readpst_paths:
        try:
            logger.info(f"Checking for readpst at: {cmd}")
            
            # For Docker environment, we need special handling
            if cmd == '/usr/bin/readpst' and os.path.exists(cmd):
                logger.info(f"Found readpst at {cmd} (Direct path check)")
                return cmd
                
            # Try running the command
            output = subprocess.check_output([cmd, '--version'], stderr=subprocess.STDOUT)
            logger.info(f"Found readpst at {cmd}: {output.decode('utf-8', errors='ignore').strip()}")
            return cmd
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Failed to find readpst at {cmd}: {str(e)}")
            continue
    
    # If no command found
    logger.error("Could not find readpst in any of the expected locations")
    return None

def run_readpst(args):
    """Run readpst with the given arguments"""
    readpst_cmd = find_readpst()
    
    if not readpst_cmd:
        logger.error("readpst command not found")
        return 1
    
    # Construct the command
    cmd = [readpst_cmd] + args
    logger.info(f"Running: {' '.join(cmd)}")
    
    try:
        # Run the command
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        # Log output
        if stdout:
            logger.info(f"stdout: {stdout.decode('utf-8', errors='ignore')}")
        if stderr:
            logger.warning(f"stderr: {stderr.decode('utf-8', errors='ignore')}")
        
        # Return the exit code
        return process.returncode
    except Exception as e:
        logger.error(f"Error running readpst: {str(e)}")
        return 1

if __name__ == "__main__":
    # Remove the script name from arguments
    args = sys.argv[1:]
    
    logger.info(f"readpst_wrapper.py called with args: {args}")
    
    # Run readpst and exit with its return code
    exit_code = run_readpst(args)
    sys.exit(exit_code)