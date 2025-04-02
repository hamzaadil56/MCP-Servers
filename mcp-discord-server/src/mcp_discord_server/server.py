import os
import asyncio
import logging
from datetime import datetime
from typing import Any, List
from functools import wraps

import discord
from discord.ext import commands
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord-mcp-server")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is required")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------------------------------------------------------
# MCP Server Initialization
# -----------------------------------------------------------------------------
# Create an MCP server instance. The MCP (Model Context Protocol) server will
# allow external calls to registered tools (commands) in this application.
app = Server("discord-server")

# Global variable to store the Discord client instance once the bot is ready.
discord_client = None


def format_reactions(reactions: List[dict]) -> str:
    """
    Format a list of reaction dictionaries into a human-readable string.
    Each reaction is shown as: emoji(count).
    If no reactions are present, returns "No reactions".
    """
    if not reactions:
        return "No reactions"
    return ", ".join(f"{r['emoji']}({r['count']})" for r in reactions)


def require_discord_client(func):
    """
    Decorator to ensure the Discord client is ready before executing a tool.
    Raises a RuntimeError if the client is not yet available.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not discord_client:
            raise RuntimeError("Discord client not ready")
        return await func(*args, **kwargs)
    return wrapper


@bot.event
async def on_ready():
    """
    Event handler called when the Discord bot successfully logs in.
    Sets the global discord_client variable and logs the bot's username.
    """
    global discord_client
    discord_client = bot
    logger.info(f"Logged in as {bot.user.name}")


@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="add_reaction",
            description="Add a reaction to a message",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "ID of the channel containing the message",
                    },
                    "message_id": {
                        "type": "string",
                        "description": "ID of the message to react to",
                    },
                    "emoji": {
                        "type": "string",
                        "description": "Emoji to react with (Unicode or custom emoji ID)",
                    },
                },
                "required": ["channel_id", "message_id", "emoji"],
            },
        ),
        Tool(
            name="send_message",
            description="Send a message to a specific channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID where the message will be sent",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the message to send",
                    },
                },
                "required": ["channel_id", "content"],
            },
        ),
        Tool(
            name="read_messages",
            description="Read recent messages from a channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID from which to fetch messages",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of messages to fetch (max 100)",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["channel_id"],
            },
        ),
    ]


@app.call_tool()
@require_discord_client
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    if name == "send_message":
        # Retrieve the channel and send the message with the provided content.
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.send(arguments["content"])
        return [
            TextContent(
                type="text",
                text=f"Message sent successfully. Message ID: {message.id}"
            )
        ]

    elif name == "read_messages":
        # Retrieve the channel and fetch a limited number of recent messages.
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        limit = min(int(arguments.get("limit", 10)), 100)
        messages = []
        async for message in channel.history(limit=limit):
            reaction_data = []
            # Iterate through reactions and collect emoji data.
            for reaction in message.reactions:
                emoji_str = (
                    str(reaction.emoji.name)
                    if hasattr(reaction.emoji, "name") and reaction.emoji.name
                    else (
                        str(reaction.emoji.id)
                        if hasattr(reaction.emoji, "id")
                        else str(reaction.emoji)
                    )
                )
                reaction_info = {"emoji": emoji_str, "count": reaction.count}
                logger.debug(f"Found reaction: {emoji_str}")
                reaction_data.append(reaction_info)
            messages.append(
                {
                    "id": str(message.id),
                    "author": str(message.author),
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                    "reactions": reaction_data,
                }
            )
        # Format the messages for output.
        formatted_messages = "\n".join(
            f"{m['author']} ({m['timestamp']}): {m['content']}\nReactions: {format_reactions(m['reactions'])}"
            for m in messages
        )
        return [
            TextContent(
                type="text",
                text=f"Retrieved {len(messages)} messages:\n\n{formatted_messages}"
            )
        ]

    elif name == "add_reaction":
        # Retrieve the channel and message, then add the specified reaction.
        channel = await discord_client.fetch_channel(int(arguments["channel_id"]))
        message = await channel.fetch_message(int(arguments["message_id"]))
        await message.add_reaction(arguments["emoji"])
        return [
            TextContent(
                type="text",
                text=f"Added reaction '{arguments['emoji']}' to message {message.id}"
            )
        ]

    # If the tool name is not recognized, raise an error.
    raise ValueError(f"Unknown tool: {name}")


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
