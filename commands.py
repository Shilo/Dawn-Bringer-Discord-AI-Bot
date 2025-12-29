"""
Command system for Dawn Bringer Discord Bot.

This module handles all commands and provides a framework
for adding new commands easily.
"""

import discord
from typing import Callable
from functools import wraps
import os
import sys

# Admin user IDs (Discord user IDs as integers)
# Add your admin user IDs here
ADMIN_USER_IDS = {
    149792180439875584, # ShiloBuff
    437873507041280020  # ShiloBuff.
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
    async def wrapper(*args, **kwargs):
        # Handle both methods (self, message, ...) and functions (message, ...)
        if len(args) >= 2:
            # It's a method call: (self, message, ...)
            message = args[1]
        elif len(args) >= 1:
            # It's a function call: (message, ...)
            message = args[0]
        else:
            # No message argument, can't check
            return None
        
        if not is_admin(message.author):
            # Extract command name from message for generic error
            content = message.content.strip()
            # Return silently if not a command (!) or if it's the !! debug shortcut
            if not content.startswith("!") or content.startswith("!!"):
                return None  # Return silently if not a command or is !! shortcut
            parts = content[1:].split(None, 1)
            command_name = parts[0].lower() if parts else "unknown"
            await message.reply(f"❌ Command `{command_name}` not found or not available to you.")
            return None
        return await func(*args, **kwargs)
    return wrapper


class CommandHandler:
    """Handler for commands."""
    
    def __init__(self, get_ai_response_func=None, get_token_info_func=None, 
                 send_response_message_func=None, get_prompt_func=None, model=None,
                 get_knowledge_string_func=None, client=None, shutdown_event=None,
                 question_channel_name=None, set_restarting_flag_func=None,
                 set_shutting_down_flag_func=None):
        """Initialize the command handler.
        
        Args:
            get_ai_response_func: Function to get AI response
            get_token_info_func: Function to get token info
            send_response_message_func: Function to send response messages (required)
            get_prompt_func: Function to extract prompt from message (for bot name handling)
            model: Model name string
            get_knowledge_string_func: Function to get knowledge base stats string
            client: Discord client instance (for shutdown/restart commands)
            shutdown_event: asyncio.Event for signaling shutdown
            question_channel_name: Name of the question channel for logout messages
            set_restarting_flag_func: Function to set the restarting flag (to skip logout message)
            set_shutting_down_flag_func: Function to set the shutting down flag (to skip duplicate logout message)
        """
        self.commands = {}
        self.get_ai_response = get_ai_response_func
        self.get_token_info = get_token_info_func
        if send_response_message_func is None:
            raise ValueError("send_response_message_func is required")
        self.send_response_message = send_response_message_func
        self.get_prompt = get_prompt_func
        self.model = model
        self.get_knowledge_string = get_knowledge_string_func
        self.client = client
        self.shutdown_event = shutdown_event
        self.question_channel_name = question_channel_name
        self.set_restarting_flag = set_restarting_flag_func
        self.set_shutting_down_flag = set_shutting_down_flag_func
        self._register_default_commands()
    
    def _register_default_commands(self):
        """Register default commands."""
        self.register_command("debug", self.handle_debug)
        self.register_command("help", self.handle_help)
        self.register_command("stats", self.handle_stats)
        self.register_command("shutdown", self.handle_shutdown)
        self.register_command("restart", self.handle_restart)
    
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
        
        # Check for !! shortcut for debug command (admin only)
        if content.startswith("!!") and len(content) > 2:
            # Treat !! as shortcut for !debug
            if "debug" in self.commands:
                # Extract everything after !!
                debug_args = content[2:].strip()
                await self.commands["debug"](message, debug_args)
                return True
        
        # Check for ! commands
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
        
        Admin users see full request and response, including retrieved chunks.
        Uses the same prompt extraction logic as normal messages (handles bot names).
        
        Args:
            message: The Discord message
            args: The arguments after !debug (the prompt/question)
        """
        if not all([self.get_ai_response, self.get_token_info, self.send_response_message, self.model]):
            await message.reply("Error: Command handler not properly initialized.")
            return
        
        # Strip !debug or !! and use get_prompt to handle bot names like normal messages
        if self.get_prompt:
            # Remove !debug or !! from the message content temporarily
            original_content = message.content
            content_lower = original_content.lower()
            # Remove !debug (case-insensitive) or !! from the start
            if content_lower.startswith("!debug"):
                modified_content = original_content[6:].strip()  # Remove "!debug" (6 chars)
            elif original_content.startswith("!!"):
                modified_content = original_content[2:].strip()  # Remove "!!" (2 chars)
            else:
                modified_content = original_content.replace("!debug", "", 1).strip()
            
            # Temporarily modify message.content to use get_prompt logic
            message.content = modified_content
            try:
                prompt = self.get_prompt(message)
            finally:
                # Restore original content
                message.content = original_content
        else:
            # Fallback: just use args directly
            prompt = args.strip() if args else None
        
        if not prompt:
            await message.reply("Usage: `!debug <your question>` or `!!<your question>`")
            return
        
        async with message.channel.typing():
            try:
                # For debug command, we need scores, so pass include_scores=True
                # This adds overhead (extra vector search) but only for debug commands
                response_text, token_usage, full_prompt, metadata = self.get_ai_response(prompt, include_scores=True)
                
                # Build debug output with retrieved chunks
                debug_parts = []
                
                # Add retrieved chunks section
                retrieved_chunks = metadata.get("retrieved_chunks", [])
                if retrieved_chunks:
                    debug_parts.append("# Retrieved Chunks")
                    
                    # Check if we have scores
                    scores_available = any(chunk.get("distance_score") is not None for chunk in retrieved_chunks)
                    if scores_available:
                        # ChromaDB returns DISTANCE scores (lower = more relevant)
                        debug_parts.append("*Distance Score: Lower = more relevant (typically 0.0-2.0, values > 1.2 are often less relevant)*")
                    
                    for i, chunk in enumerate(retrieved_chunks, 1):
                        source = chunk.get("source", "Unknown")
                        doc_type = chunk.get("doc_type", "general")
                        content = chunk.get("content", "")
                        distance_score = chunk.get("distance_score")
                        
                        # Truncate very long chunks for readability
                        content_preview = content[:500] + "..." if len(content) > 500 else content
                        
                        # Escape markdown that could break code blocks
                        # Only escape if triple backticks are present
                        if "```" in content_preview:
                            content_preview = content_preview.replace("```", "\\`\\`\\`")
                        
                        # Format score if available
                        score_text = ""
                        if distance_score is not None:
                            # Highlight if score is high (less relevant)
                            if distance_score > 1.2:
                                score_text = f" (Distance: {distance_score:.4f} ⚠️ less relevant)"
                            else:
                                score_text = f" (Distance: {distance_score:.4f})"
                        
                        debug_parts.append(f"## Chunk {i}: {source} ({doc_type}){score_text}\n```\n{content_preview}\n```")
                else:
                    debug_parts.append("# Retrieved Chunks\n*No chunks retrieved*")
                
                # Add full prompt section
                # Only escape if triple backticks are present to avoid unnecessary escaping
                if "```" in full_prompt:
                    # Escape triple backticks with backslashes
                    full_prompt = full_prompt.replace("```", "\\`\\`\\`")
                debug_parts.append(f"# Full Prompt\n```\n{full_prompt}\n```")
                
                # Add response section
                # Escape any markdown in response that could break formatting
                if "```" in response_text:
                    response_text = response_text.replace("```", "\\`\\`\\`")
                # Put response in code block to prevent markdown interpretation
                debug_parts.append(f"# Response\n```\n{response_text}\n```")
                
                formatted_response = "\n\n".join(debug_parts)
                
                # Print to console for debugging
                print("\n" + "="*80)
                print("DEBUG OUTPUT:")
                print("="*80)
                print(formatted_response)
                print("="*80 + "\n")
                
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
        knowledge_info = ""
        if self.get_knowledge_string:
            knowledge_info = f"\n\n`{self.get_knowledge_string()}`"
        
        if user_is_admin:
            help_text = f"""**📋 Available Commands (Admin)**

**Public Commands:**
`!help` - Show this help message
`!help <command>` - Get detailed help for a specific command
`!stats` - Show knowledge base statistics

**Admin-Only Commands:**
`!debug <question>` or `!!<question>` - Ask a question (shows full request/response for admins)
`!shutdown` - Gracefully quit the bot
`!restart` - Reboot the bot

**Usage:**
- Mention the bot or use its name to ask questions normally
- Ask a relevant game question{knowledge_info}"""
        else:
            help_text = f"""**📋 Available Commands**

`!help` - Show this help message
`!help <command>` - Get detailed help for a specific command
`!stats` - Show knowledge base statistics

**Usage:**
- You can also mention the bot or use its name to ask questions normally
- Questions in the question channel are automatically answered{knowledge_info}"""
        
        await message.reply(help_text)
    
    async def handle_stats(self, message: discord.Message, args: str):
        """Handle the !stats command.
        
        Shows the bot's knowledge base statistics.
        
        Args:
            message: The Discord message
            args: Unused (command takes no arguments)
        """
        if self.get_knowledge_string:
            await message.reply(f"`{self.get_knowledge_string()}`")
        else:
            await message.reply("❌ Stats information not available.")
    
    @admin_only
    async def handle_shutdown(self, message: discord.Message, args: str):
        """Handle the !shutdown command.
        
        Gracefully shuts down the bot (Admin only).
        
        Args:
            message: The Discord message
            args: Unused (command takes no arguments)
        """
        # Reply to the command message (unless we're in the question channel)
        if not self.question_channel_name or message.channel.name != self.question_channel_name:
            try:
                await message.reply("🛑 Shutting down...")
            except:
                pass
        
        # Signal shutdown - the main handler will send the logout message
        if self.shutdown_event:
            self.shutdown_event.set()
        else:
            # Fallback: close client directly
            if self.client:
                await self.client.close()
    
    @admin_only
    async def handle_restart(self, message: discord.Message, args: str):
        """Handle the !restart command.
        
        Restarts the bot by restarting the Python process (Admin only).
        
        Args:
            message: The Discord message
            args: Unused (command takes no arguments)
        """
        # Set restarting flag to skip logout message
        if self.set_restarting_flag:
            self.set_restarting_flag(True)
        
        # Send restart message to question channel
        if self.client and self.question_channel_name:
            try:
                for guild in self.client.guilds:
                    channel = discord.utils.get(guild.text_channels, name=self.question_channel_name)
                    if channel:
                        try:
                            await channel.send("🔄 Restarting... I'll be back in a moment.")
                        except Exception as e:
                            print(f"Error sending restart message: {e}")
                        break
            except Exception as e:
                print(f"Error sending restart message: {e}")
        
        # Also reply to the command message (unless we're in the question channel)
        if not self.question_channel_name or message.channel.name != self.question_channel_name:
            try:
                await message.reply("🔄 Restarting...")
            except:
                pass
        
        # Close the client first
        if self.client:
            await self.client.close()
        
        # Restart the process
        try:
            # Get the script path and arguments
            script_path = sys.argv[0]
            script_args = sys.argv[1:]
            
            # Use os.execv to replace the current process
            # This will restart the bot with the same arguments
            os.execv(sys.executable, [sys.executable, script_path] + script_args)
        except Exception as e:
            print(f"Error restarting bot: {e}")
            # Reset flag on error
            if self.set_restarting_flag:
                self.set_restarting_flag(False)
            try:
                await message.channel.send(f"❌ Error restarting: {e}")
            except:
                pass
    
    def _get_command_help(self, command_name: str, user_is_admin: bool) -> str | None:
        """Get detailed help for a specific command.
        
        Args:
            command_name: Name of the command
            user_is_admin: Whether the user is an admin
            
        Returns:
            Help text for the command, or None if not found/not available
        """
        # Admin-only commands
        admin_only_commands = {"debug", "shutdown", "restart"}
        
        # If command is admin-only and user is not admin, return None
        if command_name in admin_only_commands and not user_is_admin:
            return None
        
        command_help = {
            "debug": {
                "description": "Ask a question and get an AI response (Admin only)",
                "usage": "`!debug <your question>` or `!!<your question>`",
                "admin_details": "Admins see the full prompt sent to the AI and the response, along with token usage.",
                "example": "`!debug What is the best class for beginners?`"
            },
            "help": {
                "description": "Show available commands and get help",
                "usage": "`!help` or `!help <command>`",
                "admin_details": "Admins see all available commands including admin-only ones.",
                "user_details": "Users see only public commands.",
                "example": "`!help` or `!help debug`"
            },
            "stats": {
                "description": "Show knowledge base statistics (files and words)",
                "usage": "`!stats`",
                "example": "`!stats`"
            },
            "shutdown": {
                "description": "Gracefully shut down the bot (Admin only)",
                "usage": "`!shutdown`",
                "admin_details": "Sends a logout message and closes the bot connection.",
                "example": "`!shutdown`"
            },
            "restart": {
                "description": "Restart the bot (Admin only)",
                "usage": "`!restart`",
                "admin_details": "Sends a logout message and restarts the bot process.",
                "example": "`!restart`"
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
        
        if "example" in help_info:
            help_text += f"**Example:** {help_info['example']}"
        
        return help_text


# Global command handler instance (will be initialized in bot.py)
command_handler = None

