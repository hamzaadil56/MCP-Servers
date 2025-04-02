import asyncio
from .server import bot, stdio_server, app, DISCORD_TOKEN


async def main():
    asyncio.create_task(bot.start(DISCORD_TOKEN))

    # Open a connection using the stdio server transport and run the MCP server.
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

# -----------------------------------------------------------------------------
# Application Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
