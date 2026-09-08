"""Test del servidor MCP de Twitter — simula la llamada completa via stdio."""
import subprocess
import json
import sys
import time

server_path = r"c:\Users\marce\OneDrive\Documentos\Proyectos_AI\meme-radar-ai\src\x-mcp\server.py"

# Iniciar servidor
p = subprocess.Popen(
    [sys.executable, server_path],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=r"c:\Users\marce\OneDrive\Documentos\Proyectos_AI\meme-radar-ai\src\x-mcp"
)

def send_request(msg):
    data = json.dumps(msg)
    p.stdin.write(data + "\n")
    p.stdin.flush()

def read_response():
    line = p.stdout.readline()
    if line:
        return json.loads(line)
    return None

# 1. Initialize
send_request({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"}
    }
})

resp = read_response()
if resp:
    print("Init OK:", resp.get("result", {}).get("serverInfo", {}).get("name", "unknown"))
else:
    print("Init FAILED")
    p.kill()
    sys.exit(1)

# 2. Initialized notification
send_request({"jsonrpc": "2.0", "method": "notifications/initialized"})

# 3. Call twitter_search
send_request({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "twitter_search",
        "arguments": {"query": "$PONS", "max_results": 2}
    }
})

# Esperar la respuesta (puede tardar por Playwright)
print("Esperando respuesta de busqueda de tweets...")
start = time.time()
while True:
    line = p.stdout.readline()
    if line:
        result = json.loads(line)
        if result.get("id") == 2:
            content = result.get("result", {}).get("content", [])
            if content:
                print(f"\nResultado en {time.time()-start:.1f}s:")
                print(content[0].get("text", "sin texto")[:500])
            else:
                error = result.get("error", {})
                print(f"Error: {error}")
            break
    if time.time() - start > 45:
        print("Timeout esperando respuesta")
        break

p.kill()
