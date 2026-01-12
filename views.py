"""
Discord UI views for the Dawn Bringer Discord Bot.

This module contains custom Discord UI components like buttons and views.
"""

import discord
from discord.ui import View, Button
from typing import Callable
import asyncio
from io import BytesIO


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
        timeout: float = 300.0,
        response_text: str = None,
        metadata: dict = None,
        is_debug: bool = False,
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
            is_regenerated: If True, this is a regenerated message and regenerate/extend buttons should not be shown
            timeout: How long the view should stay active (default 5 minutes)
            response_text: Store full response text for sharing
            metadata: Store metadata for sources
            is_debug: If True, this view is for a debug command (includes scores and debug files)
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
        self.response_text = response_text  # Store full response text for sharing
        self.metadata = metadata  # Store metadata for sources
        self.is_debug = is_debug  # Whether this is for a debug command

        self.regenerate_button = Button(
            label="↻ Regenerate", style=discord.ButtonStyle.secondary
        )
        self.regenerate_button.callback = self.on_regenerate_click

        self.extend_button = Button(label="+ More", style=discord.ButtonStyle.secondary)
        self.extend_button.callback = self.on_extend_click

        self.share_button = Button(
            label="🔗 Share", style=discord.ButtonStyle.secondary
        )
        self.share_button.callback = self.on_share_click

        # Add share button immediately (no delay needed)
        self.add_item(self.share_button)

        # Only start task to add regenerate/extend buttons after delay if this is not a regenerated message
        if not self.is_regenerated:
            self._enable_task = asyncio.create_task(self._add_button_after_delay())
        else:
            self._enable_task = None

    async def _add_button_after_delay(self, delay: float = 10.0):
        """Add the regenerate and extend buttons to the view after a delay to prevent spam.

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
                # Share button is already added, no need to add it again
                # Try to update the message if it exists
                if hasattr(self, "message") and self.message:
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
        """Get extended system prompt with extended token limit and detailed responses.

        Args:
            base_system_prompt: The base system prompt

        Returns:
            System prompt with token limit updated to max(Config.MAX_TOKENS, 1000) and instruction for detailed responses
        """
        # Replace concise instruction with detailed instruction
        extended_prompt = base_system_prompt.replace(
            "Concise and direct.", "Detailed and comprehensive."
        )
        # Replace token limit
        from configs import Config

        extended_prompt = extended_prompt.replace(
            "Maximum length: 500 tokens.",
            f"Maximum length: {max(Config.MAX_TOKENS, 1000)} tokens.",
        )
        return extended_prompt

    @staticmethod
    def _build_chunks_markdown(prompt: str, retrieved_chunks: list) -> str:
        """Build markdown content for retrieved chunks documentation.

        Uses chunk content directly (same as prompt.md uses doc.page_content),
        ensuring documentation.md, prompt.md, and source links all reference the same content.

        Args:
            prompt: The user's question
            retrieved_chunks: List of chunk dictionaries with metadata

        Returns:
            Markdown string for the Documentation.md file
        """
        # Get threshold from config
        from configs import Config

        base_threshold = Config.SCORE_THRESHOLD
        threshold = base_threshold  # Use base threshold directly to avoid import issues

        chunks_md = []
        chunks_md.append("# Documentation\n")
        chunks_md.append(f"**Question:** {prompt}\n")

        # Dynamic threshold description
        if threshold is not None:
            chunks_md.append(
                f"*Distance Score: Lower = more relevant (typically 0.0-2.0, values > {threshold} are often less relevant)*\n"
            )
            chunks_md.append(
                f"*Chunks with distance > {threshold} are filtered out (ignored) by the relevance threshold.*\n"
            )
        else:
            chunks_md.append(
                "*Distance Score: Lower = more relevant (typically 0.0-2.0)*\n"
            )

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
                    start_line = (
                        int(chunk_metadata.get("start_line"))
                        if chunk_metadata.get("start_line")
                        else None
                    )
                    end_line = (
                        int(chunk_metadata.get("end_line"))
                        if chunk_metadata.get("end_line")
                        else None
                    )
                except (ValueError, TypeError):
                    pass

            chunks_md.append(f"\n## Chunk {i}: {source} ({doc_type})")
            if distance_score is not None:
                formatted = f"**Distance:** `{distance_score:.4f}`"
                if threshold is not None and distance_score > threshold:
                    formatted += " ⚠️ less relevant"
                chunks_md.append(formatted)
            chunks_md.append(f"\n```\n{content}\n```\n")

        return "\n".join(chunks_md)

    @staticmethod
    def _create_markdown_file(filename: str, title: str, question: str, content: str):
        """Create a Discord file attachment from markdown content.

        Args:
            filename: Name of the file (e.g., "Documentation.md")
            title: Title for the markdown (e.g., "# Documentation")
            question: The user's question
            content: The main content to include

        Returns:
            discord.File object ready to attach
        """
        from io import BytesIO
        import discord

        markdown = f"{title}\n\n**Question:** {question}\n\n```\n{content}\n```"
        return discord.File(filename=filename, fp=BytesIO(markdown.encode("utf-8")))

    async def on_regenerate_click(self, interaction: discord.Interaction):
        """Handle the regenerate button click."""
        # Cancel the enable task if it's still running
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()

        # Remove the buttons from the view to hide them (keep share button)
        if self.regenerate_button in self.children:
            self.remove_item(self.regenerate_button)
        if self.extend_button in self.children:
            self.remove_item(self.extend_button)
        # Keep share button visible

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
                # For debug commands, include scores
                if self.is_debug:
                    response_text, token_usage, full_prompt, metadata = (
                        await self.get_ai_response(self.prompt, include_scores=True)
                    )
                else:
                    response_text, token_usage, _, metadata = (
                        await self.get_ai_response(self.prompt)
                    )

                # Check if the bot cannot answer
                response_text, is_unimportant = self.strip_unimportant_response(
                    response_text
                )
                is_direct = self.is_direct_question(self.original_message)

                # If the response is unimportant and not a direct question, don't send a response
                if is_unimportant and not is_direct:
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            "⚠️ Unable to regenerate response.", ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            "⚠️ Unable to regenerate response.", ephemeral=True
                        )
                    return

                # Handle debug command response format
                if self.is_debug:
                    # For debug commands, create the debug files and format response like debug command
                    from bot import strip_unimportant_response
                    from rag.utils import format_source_links
                    import discord
                    from io import BytesIO

                    # Get raw response from metadata if available (before JSON parsing), otherwise use current response
                    raw_response_text = metadata.get("raw_response", response_text)

                    # Strip unimportant response prefix for Discord message
                    response_text, _ = strip_unimportant_response(response_text)

                    # Build debug output - message body is just the raw response
                    retrieved_chunks = metadata.get("retrieved_chunks", [])
                    files_to_attach = []

                    # Documentation file (always attach if chunks exist)
                    if retrieved_chunks:
                        chunks_md_content = RegenerateView._build_chunks_markdown(
                            self.prompt, retrieved_chunks
                        )
                        chunks_file = discord.File(
                            filename="Documentation.md",
                            fp=BytesIO(chunks_md_content.encode("utf-8")),
                        )
                        files_to_attach.append(chunks_file)

                    # Prompt file (always attach)
                    full_prompt = metadata.get(
                        "full_prompt", f"Debug query: {self.prompt}"
                    )
                    prompt_file = RegenerateView._create_markdown_file(
                        "Prompt.md", "# Full Prompt", self.prompt, full_prompt
                    )
                    files_to_attach.append(prompt_file)

                    # Response file (always attach) - use raw response text
                    response_file = RegenerateView._create_markdown_file(
                        "Response.md", "# AI Response", self.prompt, raw_response_text
                    )
                    files_to_attach.append(response_file)

                    # Generate source links
                    source_links = format_source_links(
                        metadata, max_sources=5, show_without_links=True
                    )

                    # Message body is the normal response format
                    token_info = self.get_token_info(token_usage, self.model)
                    discord_message = response_text
                    if source_links:
                        discord_message += "\n\n" + "".join(source_links)
                    if token_info:
                        discord_message += "\n\n" + token_info

                    # Split message into chunks if too long
                    message_chunks = self.split_message(discord_message)

                    # Create a view with share button for debug regenerated messages
                    share_view = RegenerateView(
                        self.original_message,
                        self.prompt,
                        self.get_ai_response,
                        self.strip_unimportant_response,
                        self.is_direct_question,
                        self.get_token_info,
                        self.split_message,
                        self.model,
                        self.system_prompt,
                        is_regenerated=True,
                        response_text=response_text,
                        metadata=metadata,
                        is_debug=True,
                    )

                    # Send all chunks, with files attached to the last chunk
                    last_message = None
                    for i, chunk in enumerate(message_chunks):
                        is_last = i == len(message_chunks) - 1
                        if is_last:
                            # Last chunk with files and share button
                            if interaction.response.is_done():
                                sent_message = await interaction.followup.send(
                                    chunk, files=files_to_attach, view=share_view
                                )
                            else:
                                sent_message = await interaction.response.send_message(
                                    chunk, files=files_to_attach, view=share_view
                                )
                            last_message = sent_message
                        else:
                            # Other chunks without files
                            if interaction.response.is_done():
                                last_message = await interaction.followup.send(chunk)
                            else:
                                last_message = await interaction.response.send_message(
                                    chunk
                                )

                    # Add thumbs up and thumbs down reactions to the last message
                    if last_message:
                        try:
                            await last_message.add_reaction("👍")
                            await last_message.add_reaction("👎")
                        except:
                            pass  # Ignore errors (e.g., missing permissions, deleted message)

                    return
                else:
                    # Normal response handling
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

                # Create a view with share button for regenerated messages
                share_view = RegenerateView(
                    self.original_message,
                    self.prompt,
                    self.get_ai_response,
                    self.strip_unimportant_response,
                    self.is_direct_question,
                    self.get_token_info,
                    self.split_message,
                    self.model,
                    self.system_prompt,
                    is_regenerated=True,
                    response_text=response_text,
                    metadata=metadata,
                )

                # Send regenerated response with share button
                last_message = None
                for i, chunk in enumerate(message_chunks):
                    if i == 0:
                        # First chunk
                        if interaction.response.is_done():
                            sent_message = await interaction.followup.send(
                                chunk, view=share_view
                            )
                        else:
                            sent_message = await interaction.response.send_message(
                                chunk, view=share_view
                            )
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
                    await interaction.followup.send(
                        f"❌ Error regenerating response: {e}", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Error regenerating response: {e}", ephemeral=True
                    )

    async def on_extend_click(self, interaction: discord.Interaction):
        """Handle the extend (+) button click - regenerate with extended token limit and 10 sources."""
        # Cancel the enable task if it's still running
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()

        # Remove the buttons from the view to hide them (keep share button)
        if self.regenerate_button in self.children:
            self.remove_item(self.regenerate_button)
        if self.extend_button in self.children:
            self.remove_item(self.extend_button)
        # Keep share button visible

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
                        base_system_prompt = 'Role: Dawn Bringer (DB), female commander of the Dawn Valkyries from "Run! Goddess", leading the Valhalla Special Ops Unit in a post-apocalyptic world fighting the Infected monsters and rescuing survivors.\n\nPersonality: Supportive, knowledgeable, determined. Keep responses concise and direct (max 500 tokens).'
                else:
                    base_system_prompt = self.system_prompt
                extended_system_prompt = self._get_extended_system_prompt(
                    base_system_prompt
                )

                # Calculate extended threshold (25% increase from default)
                # This allows more chunks that are slightly less relevant but still useful for comprehensive answers
                from configs import Config

                base_threshold = Config.SCORE_THRESHOLD or 1.2
                extended_threshold = base_threshold * 1.25

                # Get a new AI response with extended parameters:
                # - max_tokens_override=Config.MAX_TOKENS * 2 (instead of Config.MAX_TOKENS)
                # - top_k_override=10 (instead of 5)
                # - score_threshold_override=1.5 (25% increase from default 1.2)
                # - system_prompt_override with extended token limit
                # For debug commands, include scores
                if self.is_debug:
                    response_text, token_usage, full_prompt, metadata = (
                        await self.get_ai_response(
                            self.prompt,
                            max_tokens_override=Config.MAX_TOKENS * 2,
                            top_k_override=10,
                            score_threshold_override=extended_threshold,
                            system_prompt_override=extended_system_prompt,
                            include_scores=True,
                        )
                    )
                else:
                    response_text, token_usage, _, metadata = (
                        await self.get_ai_response(
                            self.prompt,
                            max_tokens_override=Config.MAX_TOKENS * 2,
                            top_k_override=10,
                            score_threshold_override=extended_threshold,
                            system_prompt_override=extended_system_prompt,
                        )
                    )

                # Check if the bot cannot answer
                response_text, is_unimportant = self.strip_unimportant_response(
                    response_text
                )
                is_direct = self.is_direct_question(self.original_message)

                # If the response is unimportant and not a direct question, don't send a response
                if is_unimportant and not is_direct:
                    if interaction.response.is_done():
                        await interaction.followup.send(
                            "⚠️ Unable to regenerate response.", ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            "⚠️ Unable to regenerate response.", ephemeral=True
                        )
                    return

                # Handle debug command response format
                if self.is_debug:
                    # For debug commands, create the debug files and format response like debug command
                    from bot import strip_unimportant_response
                    from rag.utils import format_source_links
                    import discord
                    from io import BytesIO

                    # Get raw response from metadata if available (before JSON parsing), otherwise use current response
                    raw_response_text = metadata.get("raw_response", response_text)

                    # Strip unimportant response prefix for Discord message
                    response_text, _ = strip_unimportant_response(response_text)

                    # Build debug output - message body is just the raw response
                    retrieved_chunks = metadata.get("retrieved_chunks", [])
                    files_to_attach = []

                    # Documentation file (always attach if chunks exist)
                    if retrieved_chunks:
                        chunks_md_content = RegenerateView._build_chunks_markdown(
                            self.prompt, retrieved_chunks
                        )
                        chunks_file = discord.File(
                            filename="Documentation.md",
                            fp=BytesIO(chunks_md_content.encode("utf-8")),
                        )
                        files_to_attach.append(chunks_file)

                    # Prompt file (always attach)
                    full_prompt = metadata.get(
                        "full_prompt", f"Debug query: {self.prompt}"
                    )
                    prompt_file = RegenerateView._create_markdown_file(
                        "Prompt.md", "# Full Prompt", self.prompt, full_prompt
                    )
                    files_to_attach.append(prompt_file)

                    # Response file (always attach) - use raw response text
                    response_file = RegenerateView._create_markdown_file(
                        "Response.md", "# AI Response", self.prompt, raw_response_text
                    )
                    files_to_attach.append(response_file)

                    # Generate source links
                    source_links = format_source_links(
                        metadata, max_sources=10, show_without_links=True
                    )

                    # Message body is the normal response format
                    token_info = self.get_token_info(token_usage, self.model)
                    discord_message = response_text
                    if source_links:
                        discord_message += "\n\n" + "".join(source_links)
                    if token_info:
                        discord_message += "\n\n" + token_info

                    # Split message into chunks if too long
                    message_chunks = self.split_message(discord_message)

                    # Create a view with share button for debug extended messages
                    share_view = RegenerateView(
                        self.original_message,
                        self.prompt,
                        self.get_ai_response,
                        self.strip_unimportant_response,
                        self.is_direct_question,
                        self.get_token_info,
                        self.split_message,
                        self.model,
                        self.system_prompt,
                        is_regenerated=True,
                        response_text=response_text,
                        metadata=metadata,
                        is_debug=True,
                    )

                    # Send all chunks, with files attached to the last chunk
                    last_message = None
                    for i, chunk in enumerate(message_chunks):
                        is_last = i == len(message_chunks) - 1
                        if is_last:
                            # Last chunk with files and share button
                            if interaction.response.is_done():
                                sent_message = await interaction.followup.send(
                                    chunk, files=files_to_attach, view=share_view
                                )
                            else:
                                sent_message = await interaction.response.send_message(
                                    chunk, files=files_to_attach, view=share_view
                                )
                            last_message = sent_message
                        else:
                            # Other chunks without files
                            if interaction.response.is_done():
                                last_message = await interaction.followup.send(chunk)
                            else:
                                last_message = await interaction.response.send_message(
                                    chunk
                                )

                    # Add thumbs up and thumbs down reactions to the last message
                    if last_message:
                        try:
                            await last_message.add_reaction("👍")
                            await last_message.add_reaction("👎")
                        except:
                            pass  # Ignore errors (e.g., missing permissions, deleted message)

                    return
                else:
                    # Normal extended response handling
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

                # Create a view with share button for extended messages
                share_view = RegenerateView(
                    self.original_message,
                    self.prompt,
                    self.get_ai_response,
                    self.strip_unimportant_response,
                    self.is_direct_question,
                    self.get_token_info,
                    self.split_message,
                    self.model,
                    self.system_prompt,
                    is_regenerated=True,
                    response_text=response_text,
                    metadata=metadata,
                )

                # Send extended response with share button
                last_message = None
                for i, chunk in enumerate(message_chunks):
                    if i == 0:
                        # First chunk
                        if interaction.response.is_done():
                            sent_message = await interaction.followup.send(
                                chunk, view=share_view
                            )
                        else:
                            sent_message = await interaction.response.send_message(
                                chunk, view=share_view
                            )
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
                    await interaction.followup.send(
                        f"❌ Error regenerating response: {e}", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ Error regenerating response: {e}", ephemeral=True
                    )

    async def on_share_click(self, interaction: discord.Interaction):
        """Handle the share button click."""
        # Defer the interaction immediately
        await interaction.response.defer(ephemeral=True)

        try:
            import share_db
            import os

            # Get the message object first (needed for metadata)
            if hasattr(self, "message") and self.message:
                message = self.message
            else:
                message = interaction.message

            # Get the response text - use stored response_text if available, otherwise from message
            if self.response_text:
                response_text = self.response_text
            else:
                # Fallback: get from message content
                response_text = message.content

            # Clean up response text (remove source links and token info for cleaner share)
            # Keep the main response content
            lines = response_text.split("\n")
            cleaned_lines = []
            skip_next = False
            for line in lines:
                # Skip token info line (starts with -#)
                if line.strip().startswith("-#"):
                    continue
                # Skip source links (markdown links)
                if line.strip().startswith("[") and "](" in line:
                    continue
                cleaned_lines.append(line)
            response_text = "\n".join(cleaned_lines).strip()

            # Get metadata if available (sources, stats, etc.)
            metadata = {
                "discord_message_id": message.id,
                "discord_channel_id": (
                    message.channel.id if hasattr(message.channel, "id") else None
                ),
            }

            # Extract sources from stored metadata if available
            sources = []
            if hasattr(self, "metadata") and self.metadata:
                retrieved_chunks = self.metadata.get("retrieved_chunks", [])
                used_source_indices = self.metadata.get("used_source_indices")

                # If we have used_source_indices, only show those sources
                if used_source_indices is not None:
                    used_indices_set = set(used_source_indices)
                    chunks_to_show = [
                        chunk
                        for chunk in retrieved_chunks
                        if chunk.get("source_index") in used_indices_set
                    ]
                else:
                    chunks_to_show = retrieved_chunks[
                        :5
                    ]  # Show top 5 if no specific indices

                seen_sources = set()
                for chunk in chunks_to_show:
                    source = chunk.get("source", "Unknown")
                    if source in seen_sources:
                        continue
                    seen_sources.add(source)

                    # Get metadata and file_path
                    chunk_metadata = chunk.get("metadata", {})
                    if isinstance(chunk_metadata, dict):
                        file_path = chunk_metadata.get("file_path") or chunk.get(
                            "file_path"
                        )
                        channel_id = chunk_metadata.get("channel_id")
                    else:
                        file_path = chunk.get("file_path")
                        channel_id = None

                    # If file_path is not set, use source as file_path
                    if not file_path:
                        file_path = source

                    # Check if this is a channel ID (gift code document)
                    is_channel_id = False
                    if channel_id is not None:
                        is_channel_id = True
                        channel_id = (
                            int(channel_id)
                            if isinstance(channel_id, str) and channel_id.isdigit()
                            else channel_id
                        )
                    elif isinstance(file_path, str) and file_path.isdigit():
                        is_channel_id = True
                        channel_id = int(file_path)

                    # Try to get URL
                    url = None
                    start_line = None
                    end_line = None
                    if is_channel_id:
                        # Generate Discord channel link
                        import bot

                        server_id = bot.GIFT_CODE_SERVER_ID
                        if server_id and channel_id:
                            if isinstance(server_id, str) and server_id.isdigit():
                                server_id = int(server_id)
                            url = (
                                f"https://discord.com/channels/{server_id}/{channel_id}"
                            )
                    elif file_path:
                        if isinstance(chunk_metadata, dict):
                            start_line = chunk_metadata.get("start_line")
                            end_line = chunk_metadata.get("end_line")
                            try:
                                start_line = int(start_line) if start_line else None
                            except (ValueError, TypeError):
                                start_line = None
                            try:
                                end_line = int(end_line) if end_line else None
                            except (ValueError, TypeError):
                                end_line = None

                        from rag.utils import generate_github_link

                        normalized_path = str(file_path).replace("\\", "/")
                        from configs import Config

                        docs_dir_name = Config.DOCS_DIR.name
                        github_file_path = (
                            f"{docs_dir_name}/{normalized_path}"
                            if not normalized_path.startswith(f"{docs_dir_name}/")
                            else normalized_path
                        )
                        url = generate_github_link(
                            github_file_path, start_line, end_line
                        )

                    # Format source name
                    if is_channel_id:
                        from shared_state import get_gift_code_channel

                        channel = get_gift_code_channel()
                        if channel and channel.id == channel_id:
                            name = f"#{channel.name}"
                        else:
                            name = f"#{channel_id}"
                    elif file_path:
                        file_path_str = str(file_path).replace("\\", "/")
                        if "/" in file_path_str:
                            name = file_path_str.split("/")[-1]
                        else:
                            name = file_path_str
                        if name.endswith(".md"):
                            name = name[:-3]
                    else:
                        source_str = str(source).replace("\\", "/")
                        if "/" in source_str:
                            name = source_str.split("/")[-1]
                            if name.endswith(".md"):
                                name = name[:-3]
                        else:
                            name = str(source)

                    # Try to read external link from .meta file
                    external_link_info = None
                    if file_path and not is_channel_id:
                        from rag.utils import read_external_link_from_meta

                        external_link_info = read_external_link_from_meta(file_path)

                    sources.append(
                        {
                            "source": source,
                            "name": name,
                            "url": url,
                            "external_link": external_link_info,
                            "start_line": start_line,
                            "end_line": end_line,
                        }
                    )

            # Add sources to metadata if found
            if sources:
                metadata["sources"] = sources

            # Extract stats from metadata if available
            if hasattr(self, "metadata") and self.metadata:
                token_usage = self.metadata.get("token_usage")
                if token_usage:
                    import bot

                    cost = bot.calculate_cost(
                        token_usage.prompt_tokens,
                        token_usage.completion_tokens,
                        self.model,
                    )
                    metadata["stats"] = {
                        "cost": cost,
                        "tokens": token_usage.total_tokens,
                        "prompt_tokens": token_usage.prompt_tokens,
                        "completion_tokens": token_usage.completion_tokens,
                    }

            # Create share
            short_id = share_db.create_share(self.prompt, response_text, metadata)

            # Get the base URL
            railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
            if railway_public_domain:
                base_url = f"https://{railway_public_domain}"
            else:
                # Fallback - use a placeholder or try to construct from request
                base_url = "https://your-domain.railway.app"  # User will need to set RAILWAY_PUBLIC_DOMAIN

            short_url = f"{base_url}/{short_id}"

            # Send the share URL to the user
            await interaction.followup.send(
                f"🔗 **Share link created!**\n\n{short_url}\n\n*You can ask questions on the shared page.*",
                ephemeral=True,
            )

        except Exception as e:
            print(f"⚠️ Error sharing message: {e}")
            import traceback

            print(traceback.format_exc())
            await interaction.followup.send(
                f"❌ Error creating share link: {e}", ephemeral=True
            )

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
        if self.share_button in self.children:
            self.remove_item(self.share_button)
        try:
            # Try to update the message if it still exists
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except:
            pass


class InteractionRegenerateView(RegenerateView):
    """View containing regenerate buttons for Discord slash command interactions."""

    def __init__(
        self,
        interaction: discord.Interaction,
        prompt: str,
        get_ai_response_func: Callable,
        strip_unimportant_response_func: Callable,
        is_direct_question_func: Callable,
        get_token_info_func: Callable,
        split_message_func: Callable,
        model: str,
        system_prompt: str = None,
        is_regenerated: bool = False,
        timeout: float = 300.0,
        response_text: str = None,
        metadata: dict = None,
        is_debug: bool = False,
    ):
        """Initialize the interaction regenerate view.

        Args:
            interaction: The Discord interaction that triggered the response
            prompt: The prompt/question that was used to generate the response
            get_ai_response_func: Function to get AI response
            strip_unimportant_response_func: Function to strip unimportant response prefix
            is_direct_question_func: Function to check if message is a direct question
            get_token_info_func: Function to get token info string
            split_message_func: Function to split message into chunks
            model: Model name string
            system_prompt: Base system prompt (for extended regeneration)
            is_regenerated: If True, this is a regenerated message and regenerate/extend buttons should not be shown
            timeout: How long the view should stay active (default 5 minutes)
            response_text: Store full response text for sharing
            metadata: Store metadata for sources
            is_debug: If True, this view is for a debug command (includes scores and debug files)
        """
        # Don't call super().__init__() since we need different initialization
        View.__init__(self, timeout=timeout)
        self.interaction = interaction
        self.prompt = prompt
        self.get_ai_response = get_ai_response_func
        self.strip_unimportant_response = strip_unimportant_response_func
        self.is_direct_question = is_direct_question_func
        self.get_token_info = get_token_info_func
        self.split_message = split_message_func
        self.model = model
        self.system_prompt = system_prompt
        self.is_regenerated = is_regenerated
        self.response_text = response_text  # Store full response text for sharing
        self.metadata = metadata  # Store metadata for sources
        self.is_debug = is_debug  # Whether this is for a debug command

        # Initialize buttons same as parent class
        self.regenerate_button = Button(
            label="↻ Regenerate", style=discord.ButtonStyle.secondary
        )
        self.regenerate_button.callback = self.on_regenerate_click

        self.extend_button = Button(label="+ More", style=discord.ButtonStyle.secondary)
        self.extend_button.callback = self.on_extend_click

        self.share_button = Button(
            label="🔗 Share", style=discord.ButtonStyle.secondary
        )
        self.share_button.callback = self.on_share_click

        # Add share button immediately (no delay needed)
        self.add_item(self.share_button)

        # Only start task to add regenerate/extend buttons after delay if this is not a regenerated message
        if not self.is_regenerated:
            self._enable_task = asyncio.create_task(self._add_button_after_delay())
        else:
            self._enable_task = None

    async def _add_button_after_delay(self, delay: float = 10.0):
        """Add the regenerate and extend buttons to the view after a delay to prevent spam.

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
                # Share button is already added, no need to add it again
                # Try to update the message if it exists
                if hasattr(self, "message") and self.message:
                    try:
                        await self.message.edit(view=self)
                    except:
                        pass  # Message might have been deleted or we don't have permission
        except asyncio.CancelledError:
            pass  # Task was cancelled, which is fine

    async def on_regenerate_click(self, interaction: discord.Interaction):
        """Handle regenerate button click for interactions."""
        await interaction.response.defer()

        try:
            # Cancel the enable task if it's still running
            if self._enable_task is not None and not self._enable_task.done():
                self._enable_task.cancel()

            # Remove the buttons from the view to hide them (keep share button)
            if self.regenerate_button in self.children:
                self.remove_item(self.regenerate_button)
            if self.extend_button in self.children:
                self.remove_item(self.extend_button)
            # Keep share button visible

            # Update the interaction to hide the buttons
            await interaction.edit_original_response(view=self)

            # Generate new response
            result = await self.get_ai_response(self.prompt)
            if result is None:
                await interaction.followup.send(
                    "❌ Unable to regenerate response. Please try again.",
                    ephemeral=True,
                )
                return

            new_response_text, token_usage, _, new_metadata = result

            # Strip unimportant response prefix (removes [[UNIMPORTANT]] marker)
            new_response_text, is_unimportant = self.strip_unimportant_response(
                new_response_text
            )

            # For interactions, we treat as direct questions, so we always send the response
            # (unlike message-based regeneration which might skip unimportant responses)

            # Get token info
            token_info = self.get_token_info(token_usage, self.model)

            # Generate GitHub source links if available
            from rag.utils import format_source_links

            source_links = format_source_links(new_metadata, max_sources=5)

            # Combine response, source links, and token info
            full_message = new_response_text
            if source_links:
                full_message += "\n\n" + "".join(source_links)
            full_message += "\n\n" + token_info

            # Split into chunks if too long
            message_chunks = self.split_message(full_message)

            # Send regenerated response as followup
            last_message = None
            for i, chunk in enumerate(message_chunks):
                if i == 0:
                    last_message = await interaction.followup.send(
                        chunk,
                        view=InteractionRegenerateView(
                            interaction,
                            self.prompt,
                            self.get_ai_response,
                            self.strip_unimportant_response,
                            self.is_direct_question,
                            self.get_token_info,
                            self.split_message,
                            self.model,
                            self.system_prompt,
                            is_regenerated=True,
                            response_text=new_response_text,
                            metadata=new_metadata,
                        ),
                    )
                else:
                    last_message = await interaction.followup.send(chunk)

            # Add thumbs up and thumbs down reactions to the last message
            if last_message:
                try:
                    await last_message.add_reaction("👍")
                    await last_message.add_reaction("👎")
                except:
                    pass  # Ignore errors (e.g., missing permissions, deleted message)

        except Exception as e:
            print(f"❌ Error regenerating response: {e}")
            import traceback

            print(traceback.format_exc())
            try:
                await interaction.followup.send(
                    "❌ An error occurred while regenerating. Please try again.",
                    ephemeral=True,
                )
            except:
                pass
        finally:
            # Re-enable buttons (though this view is for the old message)
            pass

    async def on_extend_click(self, interaction: discord.Interaction):
        """Handle extend button click for interactions."""
        await interaction.response.defer()

        try:
            # Cancel the enable task if it's still running
            if self._enable_task is not None and not self._enable_task.done():
                self._enable_task.cancel()

            # Remove the buttons from the view to hide them (keep share button)
            if self.regenerate_button in self.children:
                self.remove_item(self.regenerate_button)
            if self.extend_button in self.children:
                self.remove_item(self.extend_button)
            # Keep share button visible

            # Update the interaction to hide the buttons
            await interaction.edit_original_response(view=self)

            # Get extended system prompt
            extended_system_prompt = self._get_extended_system_prompt(
                self.system_prompt
            )

            # Calculate extended threshold (25% increase from default)
            # This allows more chunks that are slightly less relevant but still useful for comprehensive answers
            from configs import Config

            base_threshold = Config.SCORE_THRESHOLD or 1.2
            extended_threshold = base_threshold * 1.25

            # Generate extended response with override parameters
            response_text, token_usage, _, metadata = await self.get_ai_response(
                self.prompt,
                max_tokens_override=Config.MAX_TOKENS * 2,
                top_k_override=10,
                score_threshold_override=extended_threshold,
                system_prompt_override=extended_system_prompt,
            )

            # Check if the bot cannot answer
            response_text, is_unimportant = self.strip_unimportant_response(
                response_text
            )
            # For interactions, we treat as direct questions
            is_direct = True

            # If the response is unimportant, don't send a response
            if is_unimportant and not is_direct:
                await interaction.followup.send(
                    "❌ Unable to extend response. Please try again.", ephemeral=True
                )
                return

            # Prepare result tuple
            result = (response_text, token_usage, metadata)

            new_response_text, token_usage, new_metadata = result

            # Get token info
            token_info = self.get_token_info(token_usage, self.model)

            # Generate GitHub source links if available
            from rag.utils import format_source_links

            source_links = format_source_links(new_metadata, max_sources=5)

            # Combine response, source links, and token info
            full_message = new_response_text
            if source_links:
                full_message += "\n\n" + "".join(source_links)
            full_message += "\n\n" + token_info

            # Split into chunks if too long
            message_chunks = self.split_message(full_message)

            # Send extended response as followup
            last_message = None
            for i, chunk in enumerate(message_chunks):
                if i == 0:
                    last_message = await interaction.followup.send(
                        chunk,
                        view=InteractionRegenerateView(
                            interaction,
                            self.prompt,
                            self.get_ai_response,
                            self.strip_unimportant_response,
                            self.is_direct_question,
                            self.get_token_info,
                            self.split_message,
                            self.model,
                            self.system_prompt,
                            is_regenerated=True,
                            response_text=new_response_text,
                            metadata=new_metadata,
                        ),
                    )
                else:
                    last_message = await interaction.followup.send(chunk)

            # Add thumbs up and thumbs down reactions to the last message
            if last_message:
                try:
                    await last_message.add_reaction("👍")
                    await last_message.add_reaction("👎")
                except:
                    pass  # Ignore errors (e.g., missing permissions, deleted message)

        except Exception as e:
            print(f"❌ Error extending response: {e}")
            import traceback

            print(traceback.format_exc())
            try:
                await interaction.followup.send(
                    "❌ An error occurred while extending. Please try again.",
                    ephemeral=True,
                )
            except:
                pass
        finally:
            # Re-enable buttons (though this view is for the old message)
            pass

    async def on_share_click(self, interaction: discord.Interaction):
        """Handle share button click for interactions."""
        # Defer the interaction immediately
        await interaction.response.defer(ephemeral=True)

        try:
            import share_db
            import os

            # Get the response text - use stored response_text if available
            if self.response_text:
                response_text = self.response_text
            else:
                # Fallback: this shouldn't happen for interactions
                response_text = "Shared response"

            # Clean up response text (remove source links and token info for cleaner share)
            # Keep the main response content
            lines = response_text.split("\n")
            cleaned_lines = []
            skip_next = False
            for line in lines:
                # Skip token info line (starts with -#)
                if line.strip().startswith("-#"):
                    continue
                # Skip source links (markdown links)
                if line.strip().startswith("[") and "](" in line:
                    continue
                cleaned_lines.append(line)
            response_text = "\n".join(cleaned_lines).strip()

            # Get metadata if available (sources, stats, etc.)
            metadata = {}

            # Extract sources from stored metadata if available
            sources = []
            if hasattr(self, "metadata") and self.metadata:
                retrieved_chunks = self.metadata.get("retrieved_chunks", [])
                used_source_indices = self.metadata.get("used_source_indices")

                # If we have used_source_indices, only show those sources
                if used_source_indices is not None:
                    used_indices_set = set(used_source_indices)
                    retrieved_chunks = [
                        chunk
                        for i, chunk in enumerate(retrieved_chunks)
                        if i in used_indices_set
                    ]

                for chunk in retrieved_chunks:
                    chunk_metadata = chunk.get("metadata", {})
                    file_path = chunk_metadata.get("source")
                    channel_id = chunk_metadata.get("channel_id")

                    # Try to get URL
                    url = None
                    start_line = None
                    end_line = None
                    if channel_id:
                        # Generate Discord channel link
                        import bot

                        server_id = bot.GIFT_CODE_SERVER_ID
                        if server_id and channel_id:
                            if isinstance(server_id, str) and server_id.isdigit():
                                server_id = int(server_id)
                            url = (
                                f"https://discord.com/channels/{server_id}/{channel_id}"
                            )
                    elif file_path:
                        if isinstance(chunk_metadata, dict):
                            start_line = chunk_metadata.get("start_line")
                            end_line = chunk_metadata.get("end_line")
                            try:
                                start_line = int(start_line) if start_line else None
                            except (ValueError, TypeError):
                                start_line = None
                            try:
                                end_line = int(end_line) if end_line else None
                            except (ValueError, TypeError):
                                end_line = None

                        from rag.utils import generate_github_link

                        normalized_path = str(file_path).replace("\\", "/")
                        from configs import Config

                        docs_dir_name = Config.DOCS_DIR.name
                        github_file_path = (
                            f"{docs_dir_name}/{normalized_path}"
                            if not normalized_path.startswith(f"{docs_dir_name}/")
                            else normalized_path
                        )
                        url = generate_github_link(
                            github_file_path, start_line, end_line
                        )

                    # Format source name
                    if channel_id:
                        from shared_state import get_gift_code_channel

                        channel = get_gift_code_channel()
                        if channel and channel.id == channel_id:
                            name = f"#{channel.name}"
                        else:
                            name = f"#{channel_id}"
                    elif file_path:
                        file_path_str = str(file_path).replace("\\", "/")
                        if "/" in file_path_str:
                            name = file_path_str.split("/")[-1]
                        else:
                            name = file_path_str
                        if name.endswith(".md"):
                            name = name[:-3]

                    external_link_info = None
                    if file_path and isinstance(chunk_metadata, dict):
                        external_link = chunk_metadata.get("external_link")
                        if external_link:
                            external_link_info = {
                                "url": external_link,
                                "title": chunk_metadata.get("external_title", ""),
                            }

                    sources.append(
                        {
                            "name": name,
                            "url": url,
                            "external_link": external_link_info,
                            "start_line": start_line,
                            "end_line": end_line,
                        }
                    )

            # Add sources to metadata if found
            if sources:
                metadata["sources"] = sources

            # Extract stats from metadata if available
            if hasattr(self, "metadata") and self.metadata:
                token_usage = self.metadata.get("token_usage")
                if token_usage:
                    import bot

                    cost = bot.calculate_cost(
                        token_usage.prompt_tokens,
                        token_usage.completion_tokens,
                        self.model,
                    )
                    metadata["stats"] = {
                        "cost": cost,
                        "tokens": token_usage.total_tokens,
                        "prompt_tokens": token_usage.prompt_tokens,
                        "completion_tokens": token_usage.completion_tokens,
                    }

            # Create the share entry
            short_id = share_db.create_share(self.prompt, response_text, metadata)

            # Get the base URL
            railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
            if railway_public_domain:
                base_url = f"https://{railway_public_domain}"
            else:
                # Fallback - use a placeholder or try to construct from request
                base_url = "https://your-domain.railway.app"  # User will need to set RAILWAY_PUBLIC_DOMAIN

            short_url = f"{base_url}/{short_id}"

            # Send the share URL to the user
            await interaction.followup.send(
                f"🔗 **Share link created!**\n\n{short_url}\n\n*You can ask questions on the shared page.*",
                ephemeral=True,
            )

        except Exception as e:
            print(f"⚠️ Error sharing message: {e}")
            import traceback

            print(traceback.format_exc())
            await interaction.followup.send(
                f"❌ Error creating share link: {e}", ephemeral=True
            )

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
        if self.share_button in self.children:
            self.remove_item(self.share_button)
        try:
            # Try to update the message if it still exists
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except:
            pass
