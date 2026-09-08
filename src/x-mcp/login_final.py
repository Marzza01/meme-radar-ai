import asyncio
from playwright.async_api import async_playwright
from browser_session import save_session

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        await save_session(context)
        await browser.close()
        print("✅ Sesión guardada correctamente.")

if __name__ == "__main__":
    asyncio.run(main())