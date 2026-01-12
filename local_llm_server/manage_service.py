#!/usr/bin/env python3
import os
import sys
import json
import time
import signal
import argparse
import subprocess
import logging

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEYS_FILE = os.path.join(BASE_DIR, "api_keys.json")
START_SCRIPT = os.path.join(BASE_DIR, "start_vllm.sh")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def load_keys():
    if not os.path.exists(API_KEYS_FILE):
        return []
    try:
        with open(API_KEYS_FILE, 'r') as f:
            data = json.load(f)
            return data.get("api_keys", [])
    except Exception as e:
        logging.error(f"Error reading keys: {e}")
        return []

def save_keys(keys):
    try:
        with open(API_KEYS_FILE, 'w') as f:
            json.dump({"api_keys": keys}, f, indent=2)
        logging.info("API keys updated successfully.")
    except Exception as e:
        logging.error(f"Error saving keys: {e}")

def add_key(key):
    keys = load_keys()
    if key in keys:
        logging.warning(f"Key '{key}' already exists.")
        return
    keys.append(key)
    save_keys(keys)
    logging.info(f"Added key: {key}")

def remove_key(key):
    keys = load_keys()
    if key not in keys:
        logging.warning(f"Key '{key}' not found.")
        return
    keys.remove(key)
    save_keys(keys)
    logging.info(f"Removed key: {key}")

def list_keys():
    keys = load_keys()
    print("Allowed API Keys:")
    for k in keys:
        print(f" - {k}")

def find_processes():
    """Find pids of vllm, server.py"""
    pids = []
    try:
        # Use pgrep to find processes
        # Check for vllm
        try:
            out = subprocess.check_output(["pgrep", "-f", "vllm serve"]).decode().strip()
            if out:
                pids.extend(out.split('\n'))
        except subprocess.CalledProcessError:
            pass
            
        # Check for server.py
        try:
            out = subprocess.check_output(["pgrep", "-f", "python server.py"]).decode().strip()
            if out:
                pids.extend(out.split('\n'))
        except subprocess.CalledProcessError:
            pass
            
    except Exception as e:
        logging.error(f"Error finding processes: {e}")
    
    return list(set(pids)) # Unique PIDs

def start_service(background=False):
    logging.info("Starting service...")
    
    if background:
        # Start in background using nohup
        log_file = os.path.join(BASE_DIR, "service.log")
        cmd = f"nohup {START_SCRIPT} > {log_file} 2>&1 &"
        os.system(cmd)
        logging.info(f"Service started in background. Logs: {log_file}")
    else:
        # Start in foreground
        try:
            subprocess.run([START_SCRIPT], check=True)
        except KeyboardInterrupt:
            logging.info("Stopping service...")
            stop_service()

def stop_service():
    logging.info("Stopping service...")
    pids = find_processes()
    if not pids:
        logging.info("No running service found.")
        return

    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
            logging.info(f"Killed process {pid}")
        except ProcessLookupError:
            pass
        except Exception as e:
            logging.error(f"Error killing {pid}: {e}")
            
    logging.info("Service stopped.")

def main():
    parser = argparse.ArgumentParser(description="Manage Local LLM Server")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start
    start_parser = subparsers.add_parser("start", help="Start the service")
    start_parser.add_argument("-d", "--detach", action="store_true", help="Run in background")

    # Stop
    subparsers.add_parser("stop", help="Stop the service")

    # Status
    subparsers.add_parser("status", help="Check service status")

    # Add Key
    add_parser = subparsers.add_parser("add-key", help="Add a new API key")
    add_parser.add_argument("key", help="The API key string")

    # Remove Key
    rm_parser = subparsers.add_parser("rm-key", help="Remove an API key")
    rm_parser.add_argument("key", help="The API key string")

    # List Keys
    subparsers.add_parser("list-keys", help="List all API keys")

    args = parser.parse_args()

    if args.command == "start":
        start_service(args.detach)
    elif args.command == "stop":
        stop_service()
    elif args.command == "status":
        pids = find_processes()
        if pids:
            print(f"Service is RUNNING. PIDs: {', '.join(pids)}")
        else:
            print("Service is STOPPED.")
    elif args.command == "add-key":
        add_key(args.key)
    elif args.command == "rm-key":
        remove_key(args.key)
    elif args.command == "list-keys":
        list_keys()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
