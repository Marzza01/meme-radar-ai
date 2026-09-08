import subprocess
import json
import sys
import time
import os

def send_mcp_request(process, method, params, id):
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params if params is not None else {},
        "id": id
    }
    process.stdin.write(json.dumps(request) + '\n')
    process.stdin.flush()
    response = process.stdout.readline()
    return response

# Iniciar el servidor de X con la sesión guardada
cmd = [sys.executable, "server.py"]
process = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd="C:\\Users\\marce\\OneDrive\\Documentos\\Proyectos_AI\\meme-radar-ai\\src\\x-mcp",
    env={**os.environ, "PLAYWRIGHT_HEADLESS": "0"}  # Forzar navegador visible
)

try:
    # 1. Inicializar
    init_response = send_mcp_request(process, "initialize", {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0.0"}
    }, 1)
    print("✅ Inicialización:", init_response)
    
    time.sleep(0.5)
    
    # 2. Listar herramientas
    tools_response = send_mcp_request(process, "tools/list", {}, 2)
    print("🔧 Herramientas:", tools_response)
    
    time.sleep(0.5)
    
    # 3. Buscar tweets de $PONS
    search_response = send_mcp_request(process, "tools/call", {
        "name": "twitter_search",
        "arguments": {"query": "$PONS", "max_results": 5}
    }, 3)
    print("🐦 Búsqueda de $PONS:", search_response)

finally:
    process.stdin.close()
    process.terminate()