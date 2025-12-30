"""
Discord UI views for the Dawn Bringer Discord Bot.

This module contains custom Discord UI components like buttons and views.
"""

import discord
from discord.ui import View, Button
from typing import Callable


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
        
        self.regenerate_button = Button(
            label="🔄 Regenerate",
            style=discord.ButtonStyle.secondary
        )
        self.regenerate_button.callback = self.on_regenerate_click
        self.add_item(self.regenerate_button)
    
    async def on_regenerate_click(self, interaction: discord.Interaction):
        """Handle the regenerate button click."""
        # Defer the interaction to prevent timeout
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
                    await interaction.followup.send("⚠️ Unable to regenerate response.", ephemeral=True)
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
                
                # Create a new view for the regenerated response
                new_view = RegenerateView(
                    self.original_message,
                    self.prompt,
                    self.get_ai_response,
                    self.strip_unimportant_response,
                    self.is_direct_question,
                    self.get_token_info,
                    self.split_message,
                    self.model
                )
                
                # Send regenerated response
                for i, chunk in enumerate(message_chunks):
                    if i == 0:
                        # First chunk with the regenerate button
                        await interaction.followup.send(chunk, view=new_view)
                    else:
                        # Subsequent chunks without buttons
                        await interaction.channel.send(chunk)
                
                # Disable the button on the original message
                self.regenerate_button.disabled = True
                self.regenerate_button.label = "🔄 Regenerated"
                try:
                    await interaction.message.edit(view=self)
                except:
                    pass  # Message might have been deleted or we don't have permission
                    
            except Exception as e:
                await interaction.followup.send(f"❌ Error regenerating response: {e}", ephemeral=True)
    
    async def on_timeout(self):
        """Disable the button when the view times out."""
        self.regenerate_button.disabled = True
        self.regenerate_button.label = "🔄 Regenerate (expired)"
        try:
            # Try to update the message if it still exists
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except:
            pass

