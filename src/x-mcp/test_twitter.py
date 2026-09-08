"""Script de prueba completo para el servidor MCP de Twitter/X.

Verifica:
1. Conexión e inicialización del protocolo MCP.
2. Listado de herramientas disponibles.
3. Llamada de prueba a la herramienta 'twitter_search'.
"""

import os
import sys
import asyncio
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Soporte UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


async def test_mcp_server():
    server_dir = Path(__file__).parent.resolve()
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        cwd=str(server_dir),
        env=os.environ.copy()
    )

    print("🚀 Iniciando prueba del servidor MCP de Twitter...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Inicializar
            init_result = await session.initialize()
            print("✅ 1. Inicialización completada:")
            print(f"   - Servidor: {init_result.serverInfo.name} (v{init_result.serverInfo.version})")
            print(f"   - Versión protocolo: {init_result.protocolVersion}")

            # 2. Listar herramientas
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"\n🔧 2. Herramientas registradas ({len(tool_names)}):")
            for t in tool_names:
                print(f"   - {t}")

            # 3. Llamar a twitter_search
            print("\n🐦 3. Probando búsqueda de '$PONS' con twitter_search...")
            call_result = await session.call_tool(
                "twitter_search",
                arguments={"query": "$PONS", "max_results": 3}
            )

            print("\n📝 Resultado obtenido:")
            if call_result.content:
                for c in call_result.content:
                    if hasattr(c, "text"):
                        print(c.text)
                    else:
                        print(c)
            else:
                print("Respuesta vacía.")


if __name__ == "__main__":
    asyncio.run(test_mcp_server())