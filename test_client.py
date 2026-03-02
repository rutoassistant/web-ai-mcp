import json
import subprocess
import sys
import threading

def read_output(proc):
    """Read stdout from the process line by line."""
    for line in iter(proc.stdout.readline, ''):
        try:
            msg = json.loads(line)
            print(f"Server: {json.dumps(msg, indent=2)}")
        except json.JSONDecodeError:
            print(f"Server (raw): {line.strip()}")

def main():
    print("Starting Web AI MCP Server via Docker...", flush=True)
    
    # Run the docker container
    # Use --network host to ensure internet access (avoid nested bridge issues)
    cmd = ["docker", "run", "-i", "--rm", "--network", "host", "web-ai-mcp"]
    
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered
    )

    # Start reading thread
    reader = threading.Thread(target=read_output, args=(proc,), daemon=True)
    reader.start()

    # 1. Initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }
    
    print(f"Client: Sending initialize...")
    proc.stdin.write(json.dumps(init_req) + "\n")
    proc.stdin.flush()

    # Wait a bit for response (async handling is better but this is a simple test)
    import time
    time.sleep(2) 

    # 2. Initialized Notification
    notify = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }
    proc.stdin.write(json.dumps(notify) + "\n")
    proc.stdin.flush()

    # 3. List Tools
    list_tools = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    print(f"Client: Listing tools...")
    proc.stdin.write(json.dumps(list_tools) + "\n")
    proc.stdin.flush()
    
    time.sleep(2)

    # 4. Call chat_send (Test with a simple query)
    call_tool = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "chat_send",
            "arguments": {
                "message": "Hello, what is 2+2? Answer briefly."
            }
        }
    }
    print(f"Client: Calling chat_send...", flush=True)
    proc.stdin.write(json.dumps(call_tool) + "\n")
    proc.stdin.flush()

    # Wait for response (might take 10-20s for browser launch + query)
    print("Waiting for response (up to 45s)...", flush=True)
    time.sleep(45)

    # 5. Call screenshot for debugging
    call_screenshot = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "screenshot",
            "arguments": {}
        }
    }
    print(f"Client: Calling screenshot...", flush=True)
    proc.stdin.write(json.dumps(call_screenshot) + "\n")
    proc.stdin.flush()
    
    print("Waiting for screenshot (20s)...", flush=True)
    time.sleep(20)
    
    proc.terminate()

if __name__ == "__main__":
    main()
