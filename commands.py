"""
Command system for Dawn Bringer Discord Bot.

This module handles all commands and provides a framework
for adding new commands easily.
"""

import discord
from typing import Callable
from functools import wraps

# Admin user IDs (Discord user IDs as integers)
# Add your admin user IDs here
ADMIN_USER_IDS = {
    437873507041280020
}


def is_admin(user: discord.User | discord.Member) -> bool:
    """Check if a user is an admin.
    
    Args:
        user: Discord user or member object
        
    Returns:
        True if user is an admin, False otherwise
    """
    return user.id in ADMIN_USER_IDS


def admin_only(func: Callable) -> Callable:
    """Decorator to restrict a command to admins only.
    
    Args:
        func: The command function to wrap
        
    Returns:
        Wrapped function that checks admin status
    """
    @wraps(func)
    async def wrapper(message: discord.Message, *args, **kwargs):
        if not is_admin(message.author):
            await message.reply("❌ This command is restricted to admins only.")
            return None
        return await func(message, *args, **kwargs)
    return wrapper


class CommandHandler:
    """Handler for commands."""
    
    def __init__(self, get_ai_response_func=None, get_token_info_func=None, 
                 send_response_message_func=None, model=None):
        """Initialize the command handler.
        
        Args:
            get_ai_response_func: Function to get AI response
            get_token_info_func: Function to get token info
            send_response_message_func: Function to send response messages (required)
            model: Model name string
        """
        self.commands = {}
        self.get_ai_response = get_ai_response_func
        self.get_token_info = get_token_info_func
        if send_response_message_func is None:
            raise ValueError("send_response_message_func is required")
        self.send_response_message = send_response_message_func
        self.model = model
        self._register_default_commands()
    
    def _register_default_commands(self):
        """Register default commands."""
        self.register_command("debug", self.handle_debug)
        self.register_command("help", self.handle_help)
    
    def register_command(self, command_name: str, handler: Callable):
        """Register a new command.
        
        Args:
            command_name: The command name (without ! prefix)
            handler: Async function that handles the command
                     Should take (message, args) as parameters
        """
        self.commands[command_name.lower()] = handler
    
    async def handle_command(self, message: discord.Message) -> bool:
        """Handle a command if it matches.
        
        Args:
            message: The Discord message
            
        Returns:
            True if a command was handled, False otherwise
        """
        content = message.content.strip()
        if not content.startswith("!"):
            return False
        
        # Extract command and args
        parts = content[1:].split(None, 1)
        command_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Check if command exists
        if command_name in self.commands:
            handler = self.commands[command_name]
            await handler(message, args)
            return True
        
        return False
    
    @admin_only
    async def handle_debug(self, message: discord.Message, args: str):
        """Handle the !debug command.
        
        Admin users see full request and response.
        Non-admin users see only the response.
        
        Args:
            message: The Discord message
            args: The arguments after !debug (the prompt/question)
        """
        if not args:
            await message.reply("Usage: `!debug <your question>`")
            return
        
        if not all([self.get_ai_response, self.get_token_info, self.split_message, self.model]):
            await message.reply("Error: Command handler not properly initialized.")
            return
        
        async with message.channel.typing():
            try:
                response_text, token_usage, full_prompt = self.get_ai_response(args)
                
                # Admin: show full request and response
                formatted_response = f"## Prompt\n\n{full_prompt}\n\n## Response\n\n{response_text}"
                
                # Send response message (token info will be added inside)
                await self.send_response_message(message, formatted_response, token_usage)
            except Exception as e:
                await message.reply(f"Error: {e}")
    
    async def handle_help(self, message: discord.Message, args: str):
        """Handle the !help command.
        
        Shows contextual help based on user's admin status.
        
        Args:
            message: The Discord message
            args: Optional command name to get specific help
        """
        user_is_admin = is_admin(message.author)
        
        # If specific command help requested
        if args:
            command_name = args.strip().lower()
            help_text = self._get_command_help(command_name, user_is_admin)
            if help_text:
                await message.reply(help_text)
            else:
                await message.reply(f"❌ Command `{command_name}` not found or not available to you.")
            return
        
        # General help
        if user_is_admin:
            help_text = """**📋 Available Commands (Admin)**

**Public Commands:**
`!help` - Show this help message
`!help <command>` - Get detailed help for a specific command
`!debug <question>` - Ask a question (shows full request/response for admins)

**Admin-Only Commands:**
*Additional admin commands will appear here as they are added.*

**Usage:**
- You can also mention the bot or use its name to ask questions normally
- Questions in the question channel are automatically answered"""
        else:
            help_text = """**📋 Available Commands**

`!help` - Show this help message
`!help <command>` - Get detailed help for a specific command
`!debug <question>` - Ask a question (shows response only)

**Usage:**
- You can also mention the bot or use its name to ask questions normally
- Questions in the question channel are automatically answered"""
        
        await message.reply(help_text)
    
    def _get_command_help(self, command_name: str, user_is_admin: bool) -> str | None:
        """Get detailed help for a specific command.
        
        Args:
            command_name: Name of the command
            user_is_admin: Whether the user is an admin
            
        Returns:
            Help text for the command, or None if not found/not available
        """
        command_help = {
            "debug": {
                "description": "Ask a question and get an AI response",
                "usage": "`!debug <your question>`",
                "admin_details": "Admins see the full prompt sent to the AI and the response, along with token usage.",
                "user_details": "Users see only the response and token usage.",
                "example": "`!debug What is the best class for beginners?`"
            },
            "help": {
                "description": "Show available commands and get help",
                "usage": "`!help` or `!help <command>`",
                "admin_details": "Admins see all available commands including admin-only ones.",
                "user_details": "Users see only public commands.",
                "example": "`!help` or `!help debug`"
            }
        }
        
        if command_name not in command_help:
            return None
        
        help_info = command_help[command_name]
        help_text = f"**Command: `!{command_name}`**\n\n"
        help_text += f"**Description:** {help_info['description']}\n"
        help_text += f"**Usage:** {help_info['usage']}\n"
        
        if user_is_admin and "admin_details" in help_info:
            help_text += f"**Admin Info:** {help_info['admin_details']}\n"
        elif "user_details" in help_info:
            help_text += f"**Note:** {help_info['user_details']}\n"
        
        if "example" in help_info:
            help_text += f"**Example:** {help_info['example']}"
        
        return help_text


# Global command handler instance (will be initialized in bot.py)
command_handler = None

