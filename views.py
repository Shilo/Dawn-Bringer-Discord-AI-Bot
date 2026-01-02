"""
Discord UI views for the Dawn Bringer Discord Bot.

This module contains custom Discord UI components like buttons and views.
"""

import discord
from discord.ui import View, Button
from typing import Callable
import asyncio


class RegenerateView(View):
    """View containing a regenerate button for AI responses."""
    
    def __init__(
        self,
        original_message: discord.Message,
        prompt: str,
        get_ai_response_func: Callable,
        strip_unimportant_response_func: Callable,
        is_direct_question_func: Callable,
        get_token_info_func: Callable,
        split_message_func: Callable,
        model: str,
        system_prompt: str = None,
        is_regenerated: bool = False,
        timeout: float = 300.0
    ):
        """Initialize the regenerate view.
        
        Args:
            original_message: The original user message that triggered the response
            prompt: The prompt/question that was used to generate the response
            get_ai_response_func: Function to get AI response
            strip_unimportant_response_func: Function to strip unimportant response prefix
            is_direct_question_func: Function to check if message is a direct question
            get_token_info_func: Function to get token info string
            split_message_func: Function to split message into chunks
            model: Model name string
            system_prompt: Base system prompt (for extended regeneration)
            is_regenerated: If True, this is a regenerated message and buttons should not be shown
            timeout: How long the view should stay active (default 5 minutes)
        """
        super().__init__(timeout=timeout)
        self.original_message = original_message
        self.prompt = prompt
        self.get_ai_response = get_ai_response_func
        self.strip_unimportant_response = strip_unimportant_response_func
        self.is_direct_question = is_direct_question_func
        self.get_token_info = get_token_info_func
        self.split_message = split_message_func
        self.model = model
        self.system_prompt = system_prompt
        self.is_regenerated = is_regenerated
        
        self.regenerate_button = Button(
            label="↻ Regenerate",
            style=discord.ButtonStyle.secondary
        )
        self.regenerate_button.callback = self.on_regenerate_click
        
        self.extend_button = Button(
            label="+ More",
            style=discord.ButtonStyle.secondary
        )
        self.extend_button.callback = self.on_extend_click
        # Don't add the buttons initially - they will be added after 10 seconds
        
        # Only start task to add buttons if this is not a regenerated message
        if not self.is_regenerated:
            self._enable_task = asyncio.create_task(self._add_button_after_delay())
        else:
            self._enable_task = None
    
    async def _add_button_after_delay(self, delay: float = 10.0):
        """Add the regenerate buttons to the view after a delay to prevent spam.
        
        Args:
            delay: Delay in seconds before adding the buttons (default 10 seconds)
        """
        try:
            await asyncio.sleep(delay)
            # Only add buttons if this is not a regenerated message
            if not self.is_regenerated:
                if self.regenerate_button not in self.children:
                    self.add_item(self.regenerate_button)
                if self.extend_button not in self.children:
                    self.add_item(self.extend_button)
                # Try to update the message if it exists
                if hasattr(self, 'message') and self.message:
                    try:
                        await self.message.edit(view=self)
                    except:
                        pass  # Message might have been deleted or we don't have permission
        except asyncio.CancelledError:
            pass  # Task was cancelled, which is fine
    
    def stop(self):
        """Stop the view and cancel any pending tasks."""
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()
        super().stop()
    
    def _get_extended_system_prompt(self, base_system_prompt: str) -> str:
        """Get extended system prompt with 1000 tokens and detailed responses.
        
        Args:
            base_system_prompt: The base system prompt
            
        Returns:
            System prompt with token limit updated to 1000 and instruction for detailed responses
        """
        # Replace "Keep responses concise and direct (max 500 tokens)" with detailed instruction
        extended_prompt = base_system_prompt.replace(
            "Keep responses concise and direct (max 500 tokens)",
            "Provide detailed, comprehensive responses (max 1000 tokens)"
        )
        # Also handle case where it might just say "max 500 tokens" separately
        extended_prompt = extended_prompt.replace("max 500 tokens", "max 1000 tokens")
        return extended_prompt
    
    async def on_regenerate_click(self, interaction: discord.Interaction):
        """Handle the regenerate button click."""
        # Cancel the enable task if it's still running
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()
        
        # Remove the buttons from the view to hide them
        if self.regenerate_button in self.children:
            self.remove_item(self.regenerate_button)
        if self.extend_button in self.children:
            self.remove_item(self.extend_button)
        
        # Try to edit the message immediately to hide the button, if that fails defer
        try:
            await interaction.response.edit_message(view=self)
        except:
            # If edit fails, defer instead
            await interaction.response.defer()
        
        # Show typing indicator
        async with interaction.channel.typing():
            try:
                # Get a new AI response with the same prompt
                response_text, token_usage, _, metadata = self.get_ai_response(self.prompt)
                
                # Check if the bot cannot answer
                response_text, is_unimportant = self.strip_unimportant_response(response_text)
                is_direct = self.is_direct_question(self.original_message)
                
                # If the response is unimportant and not a direct question, don't send a response
                if is_unimportant and not is_direct:
                    if interaction.response.is_done():
                        await interaction.followup.send("⚠️ Unable to regenerate response.", ephemeral=True)
                    else:
                        await interaction.response.send_message("⚠️ Unable to regenerate response.", ephemeral=True)
                    return
                
                # Get token info
                token_info = self.get_token_info(token_usage, self.model)
                
                # Generate GitHub source links if available (but not if response is unimportant)
                source_links = []
                if not is_unimportant:
                    from rag.utils import format_source_links
                    source_links = format_source_links(metadata, max_sources=5)
                
                # Combine response, source links, and token info
                full_message = response_text
                if source_links:
                    full_message += "\n\n" + "".join(source_links)
                full_message += "\n\n" + token_info
                
                # Split into chunks if too long
                message_chunks = self.split_message(full_message)
                
                # Don't create a view for regenerated messages (buttons should only appear on original messages)
                # Send regenerated response without buttons
                last_message = None
                for i, chunk in enumerate(message_chunks):
                    if i == 0:
                        # First chunk
                        if interaction.response.is_done():
                            sent_message = await interaction.followup.send(chunk)
                        else:
                            sent_message = await interaction.response.send_message(chunk)
                        last_message = sent_message
                    else:
                        # Subsequent chunks
                        last_message = await interaction.channel.send(chunk)
                
                # Add thumbs up and thumbs down reactions to the last message
                if last_message:
                    try:
                        await last_message.add_reaction("👍")
                        await last_message.add_reaction("👎")
                    except:
                        pass  # Ignore errors (e.g., missing permissions, deleted message)
                    
            except Exception as e:
                if interaction.response.is_done():
                    await interaction.followup.send(f"❌ Error regenerating response: {e}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Error regenerating response: {e}", ephemeral=True)
    
    async def on_extend_click(self, interaction: discord.Interaction):
        """Handle the extend (+) button click - regenerate with 1000 tokens and 10 sources."""
        # Cancel the enable task if it's still running
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()
        
        # Remove the buttons from the view to hide them
        if self.regenerate_button in self.children:
            self.remove_item(self.regenerate_button)
        if self.extend_button in self.children:
            self.remove_item(self.extend_button)
        
        # Try to edit the message immediately to hide the buttons, if that fails defer
        try:
            await interaction.response.edit_message(view=self)
        except:
            # If edit fails, defer instead
            await interaction.response.defer()
        
        # Show typing indicator
        async with interaction.channel.typing():
            try:
                # Get the base system prompt
                if self.system_prompt is None:
                    # Fallback: try to get it from bot module if available
                    try:
                        import bot
                        base_system_prompt = bot.SYSTEM_PROMPT
                    except:
                        # If we can't get it, use a default (shouldn't happen in normal operation)
                        base_system_prompt = "Role: Dawn Bringer (DB), female commander of the Dawn Valkyries from \"Run! Goddess\", leading the Valhalla Special Ops Unit in a post-apocalyptic world fighting the Infected monsters and rescuing survivors.\n\nPersonality: Supportive, knowledgeable, determined. Keep responses concise and direct (max 500 tokens)."
                else:
                    base_system_prompt = self.system_prompt
                extended_system_prompt = self._get_extended_system_prompt(base_system_prompt)
                
                # Get a new AI response with extended parameters:
                # - max_tokens_override=1000 (instead of 500)
                # - top_k_override=10 (instead of 5)
                # - system_prompt_override with "max 1000 tokens"
                response_text, token_usage, _, metadata = self.get_ai_response(
                    self.prompt,
                    max_tokens_override=1000,
                    top_k_override=10,
                    system_prompt_override=extended_system_prompt
                )
                
                # Check if the bot cannot answer
                response_text, is_unimportant = self.strip_unimportant_response(response_text)
                is_direct = self.is_direct_question(self.original_message)
                
                # If the response is unimportant and not a direct question, don't send a response
                if is_unimportant and not is_direct:
                    if interaction.response.is_done():
                        await interaction.followup.send("⚠️ Unable to regenerate response.", ephemeral=True)
                    else:
                        await interaction.response.send_message("⚠️ Unable to regenerate response.", ephemeral=True)
                    return
                
                # Get token info
                token_info = self.get_token_info(token_usage, self.model)
                
                # Generate GitHub source links if available (but not if response is unimportant)
                # Use max_sources=10 for extended regeneration
                source_links = []
                if not is_unimportant:
                    from rag.utils import format_source_links
                    source_links = format_source_links(metadata, max_sources=10)
                
                # Combine response, source links, and token info
                full_message = response_text
                if source_links:
                    full_message += "\n\n" + "".join(source_links)
                full_message += "\n\n" + token_info
                
                # Split into chunks if too long
                message_chunks = self.split_message(full_message)
                
                # Don't create a view for regenerated messages (buttons should only appear on original messages)
                # Send regenerated response without buttons
                last_message = None
                for i, chunk in enumerate(message_chunks):
                    if i == 0:
                        # First chunk
                        if interaction.response.is_done():
                            sent_message = await interaction.followup.send(chunk)
                        else:
                            sent_message = await interaction.response.send_message(chunk)
                        last_message = sent_message
                    else:
                        # Subsequent chunks
                        last_message = await interaction.channel.send(chunk)
                
                # Add thumbs up and thumbs down reactions to the last message
                if last_message:
                    try:
                        await last_message.add_reaction("👍")
                        await last_message.add_reaction("👎")
                    except:
                        pass  # Ignore errors (e.g., missing permissions, deleted message)
                    
            except Exception as e:
                if interaction.response.is_done():
                    await interaction.followup.send(f"❌ Error regenerating response: {e}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Error regenerating response: {e}", ephemeral=True)
    
    async def on_timeout(self):
        """Remove the buttons when the view times out."""
        # Cancel the enable task if it's still running
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()
        
        # Remove the buttons from the view to hide them
        if self.regenerate_button in self.children:
            self.remove_item(self.regenerate_button)
        if self.extend_button in self.children:
            self.remove_item(self.extend_button)
        try:
            # Try to update the message if it still exists
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            pass

