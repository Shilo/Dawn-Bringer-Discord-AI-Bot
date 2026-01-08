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
from io import BytesIO

# Admin user IDs (Discord user IDs as integers)
# Add your admin user IDs here
ADMIN_USER_IDS = {
    149792180439875584, # ShiloBuff
    437873507041280020  # ShiloBuff.
}

# Command prefix
COMMAND_PREFIX = "!"

# Debug command shortcut
DEBUG_SHORTCUT = COMMAND_PREFIX * 2  # !!


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
            if not content.startswith(COMMAND_PREFIX) or content.startswith(DEBUG_SHORTCUT):
                return None  # Return silently if not a command or is !! shortcut
            parts = content[len(COMMAND_PREFIX):].split(None, 1)
            command_name = parts[0].lower() if parts else "unknown"
            await message.reply(f"❌ Command `{command_name}` not found or not available to you.")
            return None
        return await func(*args, **kwargs)
    return wrapper


class CommandHandler:
    """Handler for commands."""
    
    @staticmethod
    def _create_markdown_file(filename: str, title: str, question: str, content: str) -> discord.File:
        """Create a Discord file attachment from markdown content.
        
        Args:
            filename: Name of the file (e.g., "Documentation.md")
            title: Title for the markdown (e.g., "# Documentation")
            question: The user's question
            content: The main content to include
            
        Returns:
            discord.File object ready to attach
        """
        markdown = f"{title}\n\n**Question:** {question}\n\n```\n{content}\n```"
        return discord.File(
            filename=filename,
            fp=BytesIO(markdown.encode('utf-8'))
        )
    
    @staticmethod
    def _get_threshold_from_config(query: str = None):
        """Get the effective relevance threshold from config, adjusted for query language.
        
        Args:
            query: Optional query string to get language-adjusted threshold
            
        Returns:
            Effective threshold value or None if not set
        """
        from configs import Config
        base_threshold = Config.SCORE_THRESHOLD
        
        if query is not None:
            from rag.utils import get_effective_threshold
            return get_effective_threshold(query, base_threshold)
        
        return base_threshold
    
    @staticmethod
    def _format_distance_score(distance_score: float, threshold: float = None) -> str:
        """Format distance score with relevance warning if needed.
        
        Args:
            distance_score: The distance score to format
            threshold: Optional threshold value for warning
            
        Returns:
            Formatted distance score string
        """
        formatted = f"**Distance:** `{distance_score:.4f}`"
        if threshold is not None and distance_score > threshold:
            formatted += " ⚠️ less relevant"
        return formatted
    
    def _build_chunks_markdown(self, prompt: str, retrieved_chunks: list) -> str:
        """Build markdown content for retrieved chunks documentation.
        
        Uses chunk content directly (same as prompt.md uses doc.page_content),
        ensuring documentation.md, prompt.md, and source links all reference the same content.
        
        Args:
            prompt: The user's question
            retrieved_chunks: List of chunk dictionaries with metadata
            
        Returns:
            Markdown string for the Documentation.md file
        """
        threshold = self._get_threshold_from_config(prompt)
        
        chunks_md = []
        chunks_md.append("# Documentation\n")
        chunks_md.append(f"**Question:** {prompt}\n")
        
        # Dynamic threshold description
        if threshold is not None:
            chunks_md.append(f"*Distance Score: Lower = more relevant (typically 0.0-2.0, values > {threshold} are often less relevant)*\n")
            chunks_md.append(f"*Chunks with distance > {threshold} are filtered out (ignored) by the relevance threshold.*\n")
        else:
            chunks_md.append("*Distance Score: Lower = more relevant (typically 0.0-2.0)*\n")
        
        for i, chunk in enumerate(retrieved_chunks, 1):
            source = chunk.get("source", "Unknown")
            doc_type = chunk.get("doc_type", "general")
            distance_score = chunk.get("distance_score")
            chunk_metadata = chunk.get("metadata", {})
            
            # Use chunk content directly (same as prompt.md uses doc.page_content)
            # This ensures documentation.md, prompt.md, and source links all reference the same content
            content = chunk.get("content", "")
            
            # Get line numbers from metadata for reference (used in source links)
            start_line = None
            end_line = None
            if isinstance(chunk_metadata, dict):
                try:
                    start_line = int(chunk_metadata.get("start_line")) if chunk_metadata.get("start_line") else None
                    end_line = int(chunk_metadata.get("end_line")) if chunk_metadata.get("end_line") else None
                except (ValueError, TypeError):
                    pass
            
            chunks_md.append(f"\n## Chunk {i}: {source} ({doc_type})")
            if distance_score is not None:
                chunks_md.append(self._format_distance_score(distance_score, threshold))
            chunks_md.append(f"\n```\n{content}\n```\n")
        
        return "\n".join(chunks_md)
    
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
        if content.startswith(DEBUG_SHORTCUT) and len(content) > len(DEBUG_SHORTCUT):
            # Treat !! as shortcut for !debug
            if "debug" in self.commands:
                # Extract everything after !!
                debug_args = content[len(DEBUG_SHORTCUT):].strip()
                await self.commands["debug"](message, debug_args)
                return True
        
        # Check for ! commands
        if not content.startswith(COMMAND_PREFIX):
            return False
        
        # Extract command and args
        parts = content[len(COMMAND_PREFIX):].split(None, 1)
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
        
        # Check if this is the !! shortcut
        original_content = message.content
        is_shortcut = original_content.startswith(DEBUG_SHORTCUT)
        
        # Strip !debug or !! and use get_prompt to handle bot names like normal messages
        if self.get_prompt:
            # Remove !debug or !! from the message content temporarily
            content_lower = original_content.lower()
            # Remove !debug (case-insensitive) or !! from the start
            if content_lower.startswith("!debug"):
                modified_content = original_content[6:].strip()  # Remove "!debug" (6 chars)
            elif original_content.startswith(DEBUG_SHORTCUT):
                modified_content = original_content[len(DEBUG_SHORTCUT):].strip()  # Remove DEBUG_SHORTCUT
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
            # Return silently only for !! shortcut, show usage for !debug
            if is_shortcut:
                return
            await message.reply(f"Usage: `{COMMAND_PREFIX}debug <your question>` or `{DEBUG_SHORTCUT}<your question>`")
            return
        
        async with message.channel.typing():
            try:
                # For debug command, we need scores, so pass include_scores=True
                # This adds overhead (extra vector search) but only for debug commands
                response_text, token_usage, full_prompt, metadata = await self.get_ai_response(prompt, include_scores=True)
                
                # Get raw response from metadata if available (before JSON parsing), otherwise use current response
                raw_response_text = metadata.get("raw_response", response_text)
                
                # Strip unimportant response prefix (same as normal response) for Discord message
                from bot import strip_unimportant_response, split_message, is_direct_question, SYSTEM_PROMPT
                from views import RegenerateView
                response_text, _ = strip_unimportant_response(response_text)
                
                # Build debug output - message body is just the raw response
                retrieved_chunks = metadata.get("retrieved_chunks", [])
                files_to_attach = []
                
                # Documentation file (always attach if chunks exist)
                if retrieved_chunks:
                    chunks_md_content = self._build_chunks_markdown(prompt, retrieved_chunks)
                    chunks_file = discord.File(
                        filename="Documentation.md",
                        fp=BytesIO(chunks_md_content.encode('utf-8'))
                    )
                    files_to_attach.append(chunks_file)
                
                # Prompt file (always attach)
                prompt_file = self._create_markdown_file("Prompt.md", "# Full Prompt", prompt, full_prompt)
                files_to_attach.append(prompt_file)
                
                # Response file (always attach) - use raw response text (before JSON parsing and before stripping [[UNIMPORTANT]])
                response_file = self._create_markdown_file("Response.md", "# AI Response", prompt, raw_response_text)
                files_to_attach.append(response_file)
                
                # Generate source links using shared utility function
                # For debug command, always show sources (even without GitHub links, even if unimportant)
                from rag.utils import format_source_links
                source_links = format_source_links(metadata, max_sources=5, show_without_links=True)
                
                # Message body is the normal response format (response + source links + token info)
                token_info = self.get_token_info(token_usage, self.model) if self.get_token_info else ""
                discord_message = response_text
                if source_links:
                    discord_message += "\n\n" + "".join(source_links)
                if token_info:
                    discord_message += "\n\n" + token_info
                
                # Split message into chunks if too long (Discord limit is 2000 characters)
                message_chunks = split_message(discord_message)
                
                # Add token_usage to metadata so it can be used for sharing
                if metadata is None:
                    metadata = {}
                metadata["token_usage"] = token_usage

                # Create regenerate view with buttons (same as regular bot messages)
                view = RegenerateView(
                    message,
                    prompt,
                    self.get_ai_response,
                    strip_unimportant_response,
                    is_direct_question,
                    self.get_token_info,
                    split_message,
                    self.model,
                    SYSTEM_PROMPT,
                    response_text=response_text,  # Pass full response text for sharing
                    metadata=metadata,  # Pass metadata for sources and token usage
                    is_debug=True  # Mark this as a debug command view
                )
                
                # Send all chunks, with view buttons on the last message
                last_message = None
                if message_chunks:
                    for i, chunk in enumerate(message_chunks):
                        is_last = (i == len(message_chunks) - 1)
                        if i == 0:
                            if view and is_last:
                                # Only one chunk, attach view to it
                                reply_msg = await message.reply(chunk, files=files_to_attach if files_to_attach else None, view=view)
                                # Store reference to the message in the view for timeout handling
                                view.message = reply_msg
                                last_message = reply_msg
                            else:
                                reply_msg = await message.reply(chunk)
                                last_message = reply_msg
                        else:
                            if view and is_last:
                                # Last chunk, attach view to it
                                last_message = await message.channel.send(chunk, files=files_to_attach if files_to_attach else None, view=view)
                                # Store reference to the message in the view for timeout handling
                                view.message = last_message
                            else:
                                last_message = await message.channel.send(chunk)
                
                # Add thumbs up and thumbs down reactions to the last message
                if last_message:
                    try:
                        await last_message.add_reaction("👍")
                        await last_message.add_reaction("👎")
                    except:
                        pass  # Ignore errors (e.g., missing permissions, deleted message)
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
`!debug <question>` or `{DEBUG_SHORTCUT}<question>` - Ask a question (shows full request/response for admins)
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
        is_question_channel = (not isinstance(message.channel, discord.DMChannel) and
                               self.question_channel_name and 
                               message.channel.name == self.question_channel_name)
        if not is_question_channel:
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
        is_question_channel = (not isinstance(message.channel, discord.DMChannel) and
                               self.question_channel_name and 
                               message.channel.name == self.question_channel_name)
        if not is_question_channel:
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
                "usage": f"`!debug <your question>` or `{DEBUG_SHORTCUT}<your question>`",
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

