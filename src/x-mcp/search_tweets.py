"""Buscador de tweets a través del servidor MCP de Twitter/X.

Utiliza el cliente estándar MCP para inicializar la conexión y ejecutar la herramienta 'twitter_search'.
"""

import os
import sys
import asyncio
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configurar salida UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


async def search_twitter_mcp(query: str = "$PONS", max_results: int = 5):
    server_dir = Path(__file__).parent.resolve()
    
    # Parámetros para iniciar el servidor MCP por stdio
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        cwd=str(server_dir),
        env=os.environ.copy()
    )

    print(f"📡 Conectando con el servidor MCP de Twitter...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Handshake de inicialización MCP
            init_result = await session.initialize()
            server_name = init_result.serverInfo.name if init_result.serverInfo else "twitter-mcp"
            server_ver = init_result.serverInfo.version if init_result.serverInfo else "unknown"
            print(f"✅ Servidor MCP inicializado con éxito: {server_name} v{server_ver}")

            # 2. Llamada a la herramienta twitter_search
            print(f"🐦 Buscando tweets para '{query}' (máx: {max_results})...\n")
            response = await session.call_tool(
                "twitter_search",
                arguments={"query": query, "max_results": max_results}
            )

            # 3. Mostrar resultados
            print("=" * 60)
            print(f"RESULTADOS DE BÚSQUEDA PARA: {query}")
            print("=" * 60)
            
            if response.content:
                for item in response.content:
                    if hasattr(item, "text"):
                        print(item.text)
                    else:
                        print(item)
            else:
                print("No se recibió contenido en la respuesta del servidor.")
            print("=" * 60)


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "$PONS"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    asyncio.run(search_twitter_mcp(query, max_results))


if __name__ == "__main__":
    main()