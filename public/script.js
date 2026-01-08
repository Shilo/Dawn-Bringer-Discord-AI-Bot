// =============================================================================
// CONSTANTS AND GLOBAL VARIABLES
// =============================================================================

// Use window.chatContainer if available (for share page), otherwise get from DOM
let chatContainer = window.chatContainer;
if (!chatContainer) {
    chatContainer = document.getElementById('chatContainer');
    if (chatContainer) {
        window.chatContainer = chatContainer; // Make it available globally
    }
}

// Main page elements
const questionInput = document.getElementById('questionInput');
const questionInputBottom = document.getElementById('questionInputBottom');
const stats = document.getElementById('stats');
const bottomInputWrapper = document.getElementById('bottomInputWrapper');
const welcomeContainer = document.getElementById('welcomeContainer');

// Share page elements
const sharedHeader = document.getElementById('sharedHeader');
const sharedInfo = document.getElementById('sharedInfo');
const originalMessages = document.getElementById('originalMessages');

// Global state
let toastTimeout = null;
let currentRequestController = null; // For aborting ongoing requests


// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Toggle overflow menu visibility
 */
function toggleOverflowMenu() {
    const dropdown = document.getElementById('overflowDropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

/**
 * Close overflow menu when clicking outside
 */
document.addEventListener('click', function (event) {
    const overflowContainer = document.querySelector('.overflow-menu-container');
    const dropdown = document.getElementById('overflowDropdown');

    if (overflowContainer && dropdown && !overflowContainer.contains(event.target)) {
        dropdown.classList.remove('show');
    }
});

/**
 * Reset - clear messages and reset UI to initial state
 */
function resetChat() {
    // Clear loading
    removeLoading();

    // Clear all messages
    const container = window.chatContainer || chatContainer;
    if (container) {
        const messages = container.querySelectorAll('.message');
        messages.forEach(message => message.remove());
    }

    // Reset UI state
    updateInputState();

    // Hide shared header
    if (sharedHeader) {
        sharedHeader.classList.add('hidden');
    }

    // Change URL back to homepage if not already there
    if (window.location.pathname !== '/') {
        window.history.pushState(null, '', '/');
    }

    // Focus input
    if (questionInput) {
        questionInput.focus();
    }
}


/**
 * Auto-resize textarea based on content
 */
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

/**
 * Format stats text to be more readable
 */
function formatStatsText(statsText) {
    if (!statsText || statsText.includes('Initializing') || statsText.includes('not initialized')) {
        return statsText || 'Loading...';
    }

    // Handle the new format: "🧠 AI Model: GPT-5 Mini | 📚 Knowledge: ~149k words, 743 articles"
    const match = statsText.match(/🧠\s+AI Model:\s+([^|]+)\s+\|\s+📚\s+Knowledge:\s+~?(\d+[km]?)\s+words?,\s+(\d+)/i);
    if (match) {
        const model = match[1].trim();
        const wordCount = match[2];
        const docCount = match[3];
        return `${model} • ${wordCount} words • ${docCount} articles`;
    }

    // Extract numbers from legacy format "~149k words, 743 articles" for backward compatibility
    const legacyMatch = statsText.match(/(\d+[km]?)\s+words?,\s+(\d+)/i);
    if (legacyMatch) {
        return `${legacyMatch[1]} words • ${legacyMatch[2]} articles`;
    }

    // Fallback to original if pattern doesn't match
    return statsText;
}

/**
 * Check if device supports touch
 */
function isTouchDevice() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

// =============================================================================
// UI STATE MANAGEMENT
// =============================================================================

// Input synchronization - only add event listeners if elements exist (share page doesn't have questionInput)

if (questionInput) {
    questionInput.addEventListener('input', function () {
        autoResize(this);
        if (questionInputBottom) {
            questionInputBottom.value = this.value;
            autoResize(questionInputBottom);
        }
    });
}

if (questionInputBottom) {
    questionInputBottom.addEventListener('input', function () {
        autoResize(this);
        if (questionInput) {
            questionInput.value = this.value;
            autoResize(questionInput);
        }
    });
}

/**
 * Update UI state based on message count
 */
function updateInputState() {
    // Use window.chatContainer if set (for share page), otherwise use the const chatContainer
    const container = window.chatContainer || chatContainer;
    if (!container) return;

    const hasMessages = container.querySelectorAll('.message').length > 0;

    if (hasMessages) {
        if (welcomeContainer) welcomeContainer.style.display = 'none';
        if (bottomInputWrapper) bottomInputWrapper.classList.add('visible');
        container.classList.add('has-messages');
        if (questionInputBottom) questionInputBottom.focus();
        // Show the new chat button when there are messages
        const headerButton = document.querySelector('.header-button');
        if (headerButton) {
            headerButton.style.display = 'flex';
        }
    } else {
        if (welcomeContainer) welcomeContainer.style.display = 'flex';
        if (bottomInputWrapper) bottomInputWrapper.classList.remove('visible');
        container.classList.remove('has-messages');
        if (questionInput) {
            autoResize(questionInput);
            questionInput.focus();
        }
        // Hide the new chat button when there are no messages
        const headerButton = document.querySelector('.header-button');
        if (headerButton) {
            headerButton.style.display = 'none';
        }
    }
}


// =============================================================================
// STATS LOADING
// =============================================================================

/**
 * Load stats on page load and refresh periodically until RAG is ready
 */
async function loadStats() {
    if (!stats) return; // Skip if stats element doesn't exist (e.g., on share page)

    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        const statsText = data.stats || 'Ready';
        const formattedText = formatStatsText(statsText);
        stats.textContent = formattedText;

        // If RAG is still initializing, check again in 2 seconds
        if (statsText.includes('Initializing') || statsText.includes('not initialized')) {
            setTimeout(loadStats, 2000);
        }
    } catch (error) {
        if (stats) stats.textContent = 'Loading...';
        // Retry after 2 seconds on error
        setTimeout(loadStats, 2000);
    }
}

// Only load stats if stats element exists
if (stats) {
    loadStats();

    // Refresh stats every 30 seconds to keep it updated (only if not initializing)
    setInterval(() => {
        if (!stats) return;
        const currentText = stats.textContent;
        if (!currentText.includes('Initializing') && !currentText.includes('not initialized')) {
            loadStats();
        }
    }, 30000);
}

// =============================================================================
// MESSAGE FORMATTING AND DISPLAY
// =============================================================================

/**
 * Format message text with full markdown support
 */
function formatMessage(text) {
    // Handle null/undefined
    if (!text) {
        return '';
    }

    // Convert to string if needed
    text = String(text);

    // Check if marked is available (markdown parser)
    if (typeof marked !== 'undefined') {
        try {
            // Configure marked options
            marked.setOptions({
                breaks: true,  // Convert line breaks to <br>
                gfm: true,     // GitHub Flavored Markdown
                headerIds: false,  // Disable header IDs for cleaner output
                mangle: false   // Don't mangle email addresses
            });

            // Create custom extension for Discord underline syntax (__text__)
            // This extension integrates with marked's tokenizer to handle __text__ properly
            const discordUnderlineExtension = {
                name: 'discordUnderline',
                level: 'inline',  // Inline-level extension
                start(src) {
                    // Find the first occurrence of __ that's not part of ___
                    const match = src.match(/__(?![_])/);
                    return match ? match.index : undefined;
                },
                tokenizer(src, tokens) {
                    // Match __text__ but not ___text___ (bold + underline)
                    // Pattern: __ not followed by _, then content, then __ not preceded by _
                    const rule = /^__(?![_])(.+?)(?<!_)__/;
                    const match = rule.exec(src);
                    if (match) {
                        return {
                            type: 'discordUnderline',
                            raw: match[0],
                            text: match[1]
                        };
                    }
                },
                renderer(token) {
                    return `<u>${token.text}</u>`;
                }
            };

            // Use marked with the custom extension
            // marked.use() returns a new instance with the extension applied
            const markedWithExtension = marked.use({ extensions: [discordUnderlineExtension] });

            // Parse markdown to HTML
            return markedWithExtension.parse(text);
        } catch (error) {
            console.warn('Markdown parsing error:', error);
            // Fall back to basic formatting if marked fails
        }
    }

    // Fallback: Basic markdown-like formatting if marked is not available
    // Escape HTML first
    let formatted = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // Code blocks (must be processed before other formatting)
    const codeBlockPlaceholder = '___CODE_BLOCK_PLACEHOLDER___';
    const codeBlocks = [];
    let codeBlockIndex = 0;

    formatted = formatted.replace(/```([\s\S]*?)```/g, (match, content) => {
        const placeholder = `${codeBlockPlaceholder}${codeBlockIndex}___`;
        codeBlocks.push({ placeholder, content: `<pre><code>${content}</code></pre>` });
        codeBlockIndex++;
        return placeholder;
    });

    // Inline code (must be processed before underline)
    const inlineCodePlaceholder = '___INLINE_CODE_PLACEHOLDER___';
    const inlineCodes = [];
    let inlineCodeIndex = 0;

    formatted = formatted.replace(/`([^`]+)`/g, (match, content) => {
        const placeholder = `${inlineCodePlaceholder}${inlineCodeIndex}___`;
        inlineCodes.push({ placeholder, content: `<code>${content}</code>` });
        inlineCodeIndex++;
        return placeholder;
    });

    // Discord underline syntax (__text__) - must be after code protection
    formatted = formatted.replace(/__(?![_])(.+?)(?<!_)__/g, '<u>$1</u>');

    // Restore inline code
    inlineCodes.forEach(({ placeholder, content }) => {
        formatted = formatted.replace(placeholder, content);
    });

    // Restore code blocks
    codeBlocks.forEach(({ placeholder, content }) => {
        formatted = formatted.replace(placeholder, content);
    });

    // Links
    formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" style="color: #00aff4;">$1</a>');

    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

/**
 * Format sources for HTML display (similar to Discord format)
 */
function formatSources(sources) {
    if (!sources || sources.length === 0) return '';

    let html = '<div class="message-sources">';
    sources.forEach(source => {
        const name = source.name || source.source;
        const url = source.url;
        const externalLink = source.external_link; // [ref_name, external_url] or null
        const startLine = source.start_line;
        const endLine = source.end_line;

        // If both GitHub link and external link exist, merge them into a single badge
        if (url && externalLink && Array.isArray(externalLink) && externalLink.length === 2) {
            const [refName, externalUrl] = externalLink;
            html += `<div class="source-link-group">`;
            html += `<a href="${url}" target="_blank" class="source-link source-link-left">${name}</a>`;
            html += `<div class="source-link-separator"></div>`;
            html += `<a href="${externalUrl}" target="_blank" class="source-link source-link-right">${refName}</a>`;
            html += `</div>`;
        } else {
            // Main source button (GitHub link or just name)
            // Note: Line numbers are included in the URL, not shown in button text
            if (url) {
                html += `<a href="${url}" target="_blank" class="source-link">${name}</a>`;
            } else {
                html += `<span class="source-link" style="background: #4f545c;">${name}</span>`;
            }

            // External link button (Discord/website) if available (only if no GitHub link)
            if (externalLink && Array.isArray(externalLink) && externalLink.length === 2) {
                const [refName, externalUrl] = externalLink;
                html += `<a href="${externalUrl}" target="_blank" class="source-link">${refName}</a>`;
            }
        }
    });
    html += '</div>';
    return html;
}

// =============================================================================
// CORE CHAT FUNCTIONALITY
// =============================================================================

/**
 * Add message to chat
 */
function addMessage(author, text, isUser = false, sources = null, stats = null, prompt = null) {
    // Hide welcome message and centered input when first message is added
    updateInputState();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;

    // Store prompt in data attribute for regenerate/extend buttons
    if (prompt) {
        messageDiv.setAttribute('data-prompt', prompt);
    }

    // Store original markdown text for copy functionality
    if (text) {
        messageDiv.setAttribute('data-markdown', String(text));
    }

    // Store sources data for copy functionality (Discord format)
    if (sources && sources.length > 0) {
        messageDiv.setAttribute('data-sources', JSON.stringify(sources));
    }

    let statsHtml = '';
    if (stats) {
        statsHtml = `<div class="message-stats">💵 $${stats.cost.toFixed(6)} | 🪙 ${stats.tokens} (${stats.prompt_tokens} prompt + ${stats.completion_tokens} completion)</div>`;
    }

    // Action buttons (regenerate/extend after 10 seconds if prompt exists, copy always at end)
    let buttonsHtml = '';
    if (!isUser) {
        let actionButtons = '';

        if (prompt) {
            // Add regenerate/extend buttons after 10 seconds delay (like Discord bot)
            actionButtons += '<button class="regenerate-btn" onclick="handleRegenerate(this)" title="Regenerate message" style="display: none;">↻</button>' +
                '<button class="extend-btn" onclick="handleExtend(this)" title="Extend message" style="display: none;">+</button>';

            // Share button (always visible if prompt exists)
            actionButtons += '<button class="share-btn" onclick="handleShare(this)" title="Share conversation">🔗</button>';
        }

        // Copy button always at the end
        actionButtons += '<button class="copy-btn" onclick="handleCopy(this)" title="Copy message">⧉</button>';

        buttonsHtml = `<div class="message-buttons">${actionButtons}</div>`;
    }

    messageDiv.innerHTML = `
        <div class="message-content-wrapper">
            <div class="message-text">${formatMessage(text)}</div>
        </div>
        ${statsHtml}
        ${sources ? formatSources(sources) : ''}
        ${buttonsHtml}
    `;

    // Use window.chatContainer if set (for share page), otherwise use the const chatContainer
    const container = window.chatContainer || chatContainer;
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
    updateInputState();

    // Add touch/click handler for mobile-friendly button visibility
    if (!isUser) {
        setupMessageTouchHandler(messageDiv);
    }

    // Show regenerate/extend buttons after 10 seconds for bot messages with prompts
    if (!isUser && prompt) {
        const regenerateBtn = messageDiv.querySelector('.regenerate-btn');
        const extendBtn = messageDiv.querySelector('.extend-btn');
        if (regenerateBtn && extendBtn) {
            setTimeout(() => {
                regenerateBtn.style.display = 'inline-block';
                extendBtn.style.display = 'inline-block';
            }, 10000);
        }
    }
}

// Pure function to update button disabled state based on active class
function updateMessageButtonsDisabled(messageDiv) {
    if (!isTouchDevice()) return;

    const isActive = messageDiv.classList.contains('active');
    const buttons = messageDiv.querySelectorAll('.message-buttons button');
    buttons.forEach(button => {
        button.disabled = !isActive;
    });
}

// =============================================================================
// TOUCH/MOBILE HANDLERS
// =============================================================================

/**
 * Hide message buttons
 */
function hideMessageButtons(messageDiv) {
    messageDiv.classList.remove('active');
    updateMessageButtonsDisabled(messageDiv);
}


/**
 * Setup touch/click handler for message buttons on mobile
 */
function setupMessageTouchHandler(messageDiv) {
    if (!isTouchDevice()) return;

    updateMessageButtonsDisabled(messageDiv);

    let longPressTimer = null;
    let longPressOccurred = false;
    let touchStartX = 0;
    let touchStartY = 0;
    const LONG_PRESS_DURATION = 500; // milliseconds

    // Handle long press start
    messageDiv.addEventListener('touchstart', function (e) {
        // Don't trigger if tapping on a button or link
        if (e.target.closest('.message-buttons') || e.target.closest('a')) {
            return;
        }

        longPressOccurred = false;
        const touch = e.touches[0];
        touchStartX = touch.clientX;
        touchStartY = touch.clientY;

        // Start long press timer
        longPressTimer = setTimeout(() => {
            longPressOccurred = true;

            // Remove active from all other messages and disable their buttons
            document.querySelectorAll('.bot-message').forEach(msg => {
                if (msg !== messageDiv) {
                    hideMessageButtons(msg);
                }
            });

            // Toggle active state on this message
            messageDiv.classList.toggle('active');
            console.log(messageDiv.classList);

            // Enable/disable buttons based on active state
            updateMessageButtonsDisabled(messageDiv);
        }, LONG_PRESS_DURATION);
    }, { passive: true });

    // Cancel long press if touch moves (scrolling/dragging)
    messageDiv.addEventListener('touchmove', function (e) {
        if (!longPressTimer) return;

        const touch = e.touches[0];
        const deltaX = Math.abs(touch.clientX - touchStartX);
        const deltaY = Math.abs(touch.clientY - touchStartY);

        // If moved more than 10px, cancel long press
        if (deltaX > 10 || deltaY > 10) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
            longPressOccurred = false;
        }
    }, { passive: true });

    // Cancel long press if touch ends before duration, or prevent propagation if long press occurred
    messageDiv.addEventListener('touchend', function (e) {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        // If long press occurred, prevent all propagation
        if (longPressOccurred) {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            longPressOccurred = false;
        }
    }, { passive: false });

    // Cancel long press if touch is cancelled
    messageDiv.addEventListener('touchcancel', function (e) {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
        longPressOccurred = false;
    }, { passive: true });

    // Close buttons when clicking outside on hybrid devices
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.bot-message')) {
            document.querySelectorAll('.bot-message').forEach(msg => {
                hideMessageButtons(msg);
            });
        }
    });
}

// Show loading indicator
function showLoading() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message';
    loadingDiv.id = 'loadingMessage';
    loadingDiv.innerHTML = `
        <div class="loading">
            <span>Thinking</span>
            <div class="loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    // Use window.chatContainer if set (for share page), otherwise use the const chatContainer
    const container = window.chatContainer || chatContainer;
    if (container) {
        container.appendChild(loadingDiv);
        container.scrollTop = container.scrollHeight;
    }
}

// Remove loading indicator
function removeLoading() {
    const loadingMsg = document.getElementById('loadingMessage');
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

/**
 * Send message to the API and handle response
 */
async function sendMessage() {
    // Check if there's already a pending message (loading indicator)
    const loadingMsg = document.getElementById('loadingMessage');
    if (loadingMsg) {
        return; // Don't allow new submissions while waiting for response
    }

    // Get question from active input (check if elements exist)
    const activeInput = (bottomInputWrapper && bottomInputWrapper.classList.contains('visible') && questionInputBottom)
        ? questionInputBottom
        : (questionInput || questionInputBottom);

    if (!activeInput) {
        console.error('No input element found');
        return;
    }

    const question = activeInput.value.trim();
    if (!question) return;

    // Add user message
    addMessage('You', question, true);

    // Clear both inputs (only if they exist)
    if (questionInput) {
        questionInput.value = '';
        questionInput.style.height = 'auto';
    }
    if (questionInputBottom) {
        questionInputBottom.value = '';
        questionInputBottom.style.height = 'auto';
    }

    // Show loading
    showLoading();

    // Create AbortController for this request
    currentRequestController = new AbortController();
    const signal = currentRequestController.signal;

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question: question }),
            signal: signal, // Add abort signal
        });

        // Parse JSON first (works for both success and error responses)
        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error(`Failed to parse server response: ${response.statusText}`);
        }

        // Check if response is ok
        if (!response.ok) {
            // FastAPI HTTPException returns {detail: "message"}
            let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            if (data) {
                errorMessage = data.detail || data.error || errorMessage;
            }
            throw new Error(errorMessage);
        }

        // Check if response field exists
        if (!data.response) {
            throw new Error('No response received from server');
        }

        // Remove loading
        removeLoading();

        // Clear the request controller
        currentRequestController = null;

        // Add bot response with prompt stored for regenerate/extend
        addMessage(
            'Dawn Bringer',
            data.response || 'No response received',
            false,
            data.sources || null,
            data.stats || null,
            question  // Store the prompt for regenerate/extend buttons
        );

    } catch (error) {
        currentRequestController = null;
        removeLoading();

        if (error.name === 'AbortError') return;

        const errorMessage = error.message || 'An unknown error occurred';
        addMessage('Dawn Bringer', `❌ Error: ${errorMessage}`, false);
    } finally {
        // Focus appropriate input (check if elements exist)
        if (bottomInputWrapper && questionInputBottom && questionInput) {
            const activeInput = bottomInputWrapper.classList.contains('visible')
                ? questionInputBottom
                : questionInput;
            if (activeInput) activeInput.focus();
        } else if (questionInputBottom) {
            questionInputBottom.focus();
        }
    }
}

// Event listeners (only add if elements exist)
if (questionInput) {
    questionInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

if (questionInputBottom) {
    questionInputBottom.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// =============================================================================
// BUTTON HANDLERS
// =============================================================================

/**
 * Handle regenerate button click
 */
async function handleRegenerate(button) {
    // Check if there's already a pending message (loading indicator)
    const loadingMsg = document.getElementById('loadingMessage');
    if (loadingMsg) {
        return; // Don't allow new submissions while waiting for response
    }

    const messageDiv = button.closest('.message');
    const prompt = messageDiv.getAttribute('data-prompt');
    if (!prompt) return;

    // Hide buttons when regenerate is triggered
    hideMessageButtons(messageDiv);
    showToast('🔄 Regenerating message...');

    // Hide regenerate/extend buttons
    const regenerateBtn = messageDiv.querySelector('.regenerate-btn');
    const extendBtn = messageDiv.querySelector('.extend-btn');
    if (regenerateBtn) regenerateBtn.style.display = 'none';
    if (extendBtn) extendBtn.style.display = 'none';

    // Show loading
    showLoading();

    // Create AbortController for this request
    currentRequestController = new AbortController();
    const signal = currentRequestController.signal;

    try {
        const response = await fetch('/api/regenerate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt: prompt }),
            signal: signal, // Add abort signal
        });

        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error(`Failed to parse server response: ${response.statusText}`);
        }

        if (!response.ok) {
            // FastAPI HTTPException returns {detail: "message"}
            let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            if (data) {
                errorMessage = data.detail || data.error || errorMessage;
            }
            throw new Error(errorMessage);
        }

        if (!data.response) {
            throw new Error('No response received from server');
        }

        // Remove loading
        removeLoading();

        // Clear the request controller
        currentRequestController = null;

        // Update markdown data attribute
        messageDiv.setAttribute('data-markdown', String(data.response));

        // Replace the message content
        const messageText = messageDiv.querySelector('.message-text');
        const messageSources = messageDiv.querySelector('.message-sources');
        const messageStats = messageDiv.querySelector('.message-stats');

        if (messageText) {
            messageText.innerHTML = formatMessage(data.response);
        }

        if (messageSources && data.sources) {
            messageSources.outerHTML = formatSources(data.sources);
            // Store sources data for copy functionality
            messageDiv.setAttribute('data-sources', JSON.stringify(data.sources));
        } else if (data.sources) {
            // Insert sources if they don't exist
            const statsDiv = messageDiv.querySelector('.message-stats');
            if (statsDiv) {
                statsDiv.insertAdjacentHTML('beforebegin', formatSources(data.sources));
            }
            // Store sources data for copy functionality
            messageDiv.setAttribute('data-sources', JSON.stringify(data.sources));
        }

        if (messageStats && data.stats) {
            messageStats.textContent = `💵 $${data.stats.cost.toFixed(6)} | 🪙 ${data.stats.tokens} (${data.stats.prompt_tokens} prompt + ${data.stats.completion_tokens} completion)`;
        }

        // Don't show buttons for regenerated messages (like Discord bot)

    } catch (error) {
        currentRequestController = null;
        removeLoading();

        if (error.name === 'AbortError') return;

        const errorMessage = error.message || 'An unknown error occurred';
        addMessage('Dawn Bringer', `❌ Error: ${errorMessage}`, false);
    }
}

// Format sources in Discord markdown format
function formatSourcesForDiscord(sources) {
    if (!sources || sources.length === 0) return '';

    let sourceText = '> -# **Source**';

    sources.forEach(source => {
        const name = source.name || source.source;
        const url = source.url;
        const externalLink = source.external_link; // [ref_name, external_url] or null
        const startLine = source.start_line;
        const endLine = source.end_line;

        sourceText += '\n';

        // Check if this is a channel mention (starts with #)
        const isChannelMention = name && name.startsWith('#');

        if (url && !isChannelMention) {
            // Has GitHub link (line numbers are in the URL, not shown in label)
            const baseText = `> -# • [${name} ↗](<${url}>)`;

            // Add external link if available
            if (externalLink && Array.isArray(externalLink) && externalLink.length === 2) {
                const [refName, externalUrl] = externalLink;
                sourceText += `${baseText} | [${refName} ↗](<${externalUrl}>)`;
            } else {
                sourceText += baseText;
            }
        } else if (isChannelMention) {
            // Channel mention format - just show the mention without a link
            sourceText += `> -# • ${name}`;
        } else {
            // No link - show as code (line numbers not shown in label)
            const baseText = `> -# • \`${name}\``;

            // Add external link if available
            if (externalLink && Array.isArray(externalLink) && externalLink.length === 2) {
                const [refName, externalUrl] = externalLink;
                sourceText += `${baseText} | [${refName} ↗](<${externalUrl}>)`;
            } else {
                sourceText += baseText;
            }
        }
    });

    return sourceText;
}

// Handle copy button click
async function handleCopy(button) {
    const messageDiv = button.closest('.message');

    // Hide buttons when copy is triggered
    hideMessageButtons(messageDiv);

    let markdownText = messageDiv.getAttribute('data-markdown');

    if (!markdownText) {
        // Fallback: try to get text from message-text element
        const messageText = messageDiv.querySelector('.message-text');
        if (messageText) {
            // Extract plain text as fallback
            const textToCopy = messageText.innerText || messageText.textContent;
            try {
                await navigator.clipboard.writeText(textToCopy);
                showToast('✅ Copied message to clipboard!');
                return;
            } catch (err) {
                console.error('Failed to copy:', err);
                return;
            }
        }
        return;
    }

    // Get sources and format them in Discord markdown format
    const sourcesData = messageDiv.getAttribute('data-sources');
    if (sourcesData) {
        try {
            const sources = JSON.parse(sourcesData);
            const sourcesText = formatSourcesForDiscord(sources);
            if (sourcesText) {
                markdownText += '\n\n' + sourcesText;
            }
        } catch (err) {
            console.error('Failed to parse sources:', err);
        }
    }

    try {
        await navigator.clipboard.writeText(markdownText);
        showToast('✅ Copied message to clipboard!');
    } catch (err) {
        console.error('Failed to copy:', err);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = markdownText;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showToast('✅ Copied message to clipboard!');
        } catch (fallbackErr) {
            console.error('Fallback copy failed:', fallbackErr);
        }
        document.body.removeChild(textArea);
    }
}

/**
 * Show toast notification
 */
function showToast(message) {
    // Cancel existing timeout if any
    if (toastTimeout) {
        clearTimeout(toastTimeout);
        toastTimeout = null;
    }

    // Remove existing toast if any
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Remove toast after animation
    toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
        toastTimeout = null;
    }, 2000);
}

// Handle extend (more) button click
async function handleExtend(button) {
    // Check if there's already a pending message (loading indicator)
    const loadingMsg = document.getElementById('loadingMessage');
    if (loadingMsg) {
        return; // Don't allow new submissions while waiting for response
    }

    const messageDiv = button.closest('.message');
    const prompt = messageDiv.getAttribute('data-prompt');
    if (!prompt) return;

    // Hide buttons when extend is triggered
    hideMessageButtons(messageDiv);
    showToast('📝 Extending message...');

    // Hide regenerate/extend buttons
    const regenerateBtn = messageDiv.querySelector('.regenerate-btn');
    const extendBtn = messageDiv.querySelector('.extend-btn');
    if (regenerateBtn) regenerateBtn.style.display = 'none';
    if (extendBtn) extendBtn.style.display = 'none';

    // Show loading
    showLoading();

    // Create AbortController for this request
    currentRequestController = new AbortController();
    const signal = currentRequestController.signal;

    try {
        const response = await fetch('/api/extend', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt: prompt }),
            signal: signal, // Add abort signal
        });

        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error(`Failed to parse server response: ${response.statusText}`);
        }

        if (!response.ok) {
            // FastAPI HTTPException returns {detail: "message"}
            let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            if (data) {
                errorMessage = data.detail || data.error || errorMessage;
            }
            throw new Error(errorMessage);
        }

        if (!data.response) {
            throw new Error('No response received from server');
        }

        // Remove loading
        removeLoading();

        // Clear the request controller
        currentRequestController = null;

        // Update markdown data attribute
        messageDiv.setAttribute('data-markdown', String(data.response));

        // Replace the message content
        const messageText = messageDiv.querySelector('.message-text');
        const messageSources = messageDiv.querySelector('.message-sources');
        const messageStats = messageDiv.querySelector('.message-stats');

        if (messageText) {
            messageText.innerHTML = formatMessage(data.response);
        }

        if (messageSources && data.sources) {
            messageSources.outerHTML = formatSources(data.sources);
            // Store sources data for copy functionality
            messageDiv.setAttribute('data-sources', JSON.stringify(data.sources));
        } else if (data.sources) {
            // Insert sources if they don't exist
            const statsDiv = messageDiv.querySelector('.message-stats');
            if (statsDiv) {
                statsDiv.insertAdjacentHTML('beforebegin', formatSources(data.sources));
            }
            // Store sources data for copy functionality
            messageDiv.setAttribute('data-sources', JSON.stringify(data.sources));
        }

        if (messageStats && data.stats) {
            messageStats.textContent = `💵 $${data.stats.cost.toFixed(6)} | 🪙 ${data.stats.tokens} (${data.stats.prompt_tokens} prompt + ${data.stats.completion_tokens} completion)`;
        }

        // Don't show buttons for extended messages (like Discord bot)

    } catch (error) {
        currentRequestController = null;
        removeLoading();

        if (error.name === 'AbortError') return;

        const errorMessage = error.message || 'An unknown error occurred';
        addMessage('Dawn Bringer', `❌ Error: ${errorMessage}`, false);
    }
}

// Handle share button click
async function handleShare(button) {
    const messageDiv = button.closest('.message');
    const prompt = messageDiv.getAttribute('data-prompt');
    const response = messageDiv.getAttribute('data-markdown');

    if (!prompt || !response) {
        showToast('❌ Cannot share: Missing prompt or response!');
        return;
    }

    // Disable button while sharing
    button.disabled = true;
    showToast('🔗 Creating share link...');

    try {
        // Get sources and stats if available
        const sourcesElement = messageDiv.querySelector('.message-sources');
        const statsElement = messageDiv.querySelector('.message-stats');

        let metadata = null;

        // Extract sources if available
        let sources = null;
        if (sourcesElement) {
            // Try to extract source links from the DOM
            const sourceLinks = sourcesElement.querySelectorAll('a');
            if (sourceLinks.length > 0) {
                sources = [];
                sourceLinks.forEach(link => {
                    const href = link.getAttribute('href');
                    const text = link.textContent;
                    if (href && text) {
                        sources.push({
                            name: text,
                            url: href
                        });
                    }
                });
            }
        }

        // Extract stats if available
        let stats = null;
        if (statsElement) {
            const statsText = statsElement.textContent;
            // Parse stats: "💵 $0.000123 | 🪙 456 tokens"
            const costMatch = statsText.match(/\$([\d.]+)/);
            const tokensMatch = statsText.match(/(\d+)\s+tokens/);
            if (costMatch && tokensMatch) {
                stats = {
                    cost: parseFloat(costMatch[1]),
                    tokens: parseInt(tokensMatch[1])
                };
            }
        }

        // Build metadata object
        if (sources || stats) {
            metadata = {};
            if (sources) {
                metadata.sources = sources;
            }
            if (stats) {
                metadata.stats = stats;
            }
        }

        const response_api = await fetch('/api/share', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: prompt,
                response: response,
                metadata: metadata
            }),
        });

        if (!response_api.ok) {
            throw new Error(`HTTP ${response_api.status}`);
        }

        const data = await response_api.json();
        const shortUrl = data.url;

        // Copy URL to clipboard
        hideMessageButtons(messageDiv);
        try {
            await navigator.clipboard.writeText(shortUrl);
            showToast('✅ Share link copied to clipboard!');
        } catch (clipboardError) {
            // Fallback: show URL in a prompt
            prompt('Share link (copy this):', shortUrl);
            showToast('✅ Share link created!');
        }

        // Update URL to include share ID so refresh will reload the shared conversation
        const shareId = data.short_id;
        if (shareId) {
            window.history.pushState(null, '', `/${shareId}`);
        }

        // Mark button as shared and hide it
        button.classList.add('shared');
        button.style.display = 'none';

    } catch (error) {
        console.error('Error sharing:', error);
        showToast('❌ Error creating share link!');
        button.disabled = false;
    }
}

// =============================================================================
// MAIN PAGE INITIALIZATION
// =============================================================================

// Initialize UI state (only if on main page, not share page)
if (questionInput && welcomeContainer) {
    updateInputState();
}

// Initialize centered input to 3 lines height (only if element exists)
if (questionInput) {
    autoResize(questionInput);
}

// =============================================================================
// SHARE PAGE LOGIC
// =============================================================================

// Share page initialization - check if we're on a share URL
const pathParts = window.location.pathname.split('/');
const shortId = pathParts[pathParts.length - 1];

// Check if this is a valid share ID (6 alphanumeric characters) and not just "/"
const isShareUrl = shortId && shortId.length > 0 && shortId !== '/' && shortId.match(/^[a-zA-Z0-9]{6}$/);

// Initialize share page or main page based on URL
if (isShareUrl) {
    // Load the shared conversation
    loadSharedConversation();
} else {
    // Load homepage as normal - invalid share URLs just show the main page
    // Initially hide the new chat button on main page (will show when messages exist)
    const headerButton = document.querySelector('.header-button');
    if (headerButton) {
        headerButton.style.display = 'none';
    }
}

// New chat handler
function handleNewChat() {
    // Abort ongoing request
    if (currentRequestController) {
        currentRequestController.abort();
        currentRequestController = null;
    }

    // Reset UI
    resetChat();

    // Prevent navigation
    return false;
}

// Handle browser back/forward navigation
window.addEventListener('popstate', () => {
    // Re-initialize based on new URL
    const pathParts = window.location.pathname.split('/');
    const currentShortId = pathParts[pathParts.length - 1];

    // Check if this is a valid share ID (6 alphanumeric characters)
    const isShareUrl = currentShortId && currentShortId.length > 0 && currentShortId !== '/' && currentShortId.match(/^[a-zA-Z0-9]{6}$/);

    if (isShareUrl) {
        // Load the shared conversation
        loadSharedConversation(currentShortId);
    } else {
        // Reset to homepage state
        resetChat();
    }
});

/**
 * Load the shared conversation and display it using addMessage
 */
async function loadSharedConversation(shareId = shortId) {
    try {
        const response = await fetch(`/api/share/${shareId}`);
        if (!response.ok) {
            if (response.status === 404) {
                if (originalMessages) {
                    originalMessages.innerHTML = '<div style="text-align: center; padding: 2rem;"><h2>Share Not Found</h2><p>This shared conversation could not be found.</p><a href="/" style="color: #4a9eff;">Return to home</a></div>';
                }
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const share = await response.json();

        // Show shared header
        if (sharedHeader) {
            sharedHeader.classList.remove('hidden');
            const createdAt = new Date(share.created_at);
            if (sharedInfo) {
                sharedInfo.textContent = `Shared ${createdAt.toLocaleDateString()} • ${share.view_count || 0} views`;
            }
        }

        // Parse sources and stats from metadata
        let sources = share.metadata?.sources || null;
        let stats = share.metadata?.stats || null;

        // Add original messages to originalMessages div (they'll be inside chatContainer)
        // Temporarily set chatContainer to originalMessages so addMessage uses it
        const originalChatContainer = window.chatContainer;
        if (originalMessages) {
            window.chatContainer = originalMessages;

            // Add original messages using the shared addMessage function from script.js
            addMessage('User', share.prompt, true);
            addMessage('Dawn Bringer', share.response, false, sources, stats, share.prompt);

            // Restore chatContainer for new messages (continue conversation goes to main container)
            window.chatContainer = originalChatContainer || window.chatContainer;
        }

        // Ensure the parent chat container has the has-messages class for proper scrolling
        // This fixes the issue where you can't scroll to the top after adding new messages
        const parentContainer = document.getElementById('chatContainer');
        if (parentContainer) {
            // Always ensure has-messages class is on the parent container
            parentContainer.classList.add('has-messages');
            // Scroll to top to show the beginning of the conversation
            setTimeout(() => {
                parentContainer.scrollTop = 0;
            }, 100);
        }

        // Override updateInputState to always ensure parent container has has-messages class
        // This fixes scrolling issues when new messages are added
        const originalUpdateInputState = window.updateInputState || updateInputState;
        window.updateInputState = function () {
            const result = originalUpdateInputState();
            // Always ensure parent container has has-messages class if there are any messages
            if (parentContainer) {
                const hasAnyMessages = parentContainer.querySelectorAll('.message').length > 0;
                if (hasAnyMessages) {
                    parentContainer.classList.add('has-messages');
                }
            }
            return result;
        };

        // Set up listener to hide shared header when continuing conversation
        setupSharedHeaderHider();

    } catch (error) {
        console.error('Error loading shared conversation:', error);
        if (originalMessages) {
            originalMessages.innerHTML = '<div style="text-align: center; padding: 2rem;"><h2>Error Loading Conversation</h2><p>Could not load the shared conversation.</p><a href="/" style="color: #4a9eff;">Return to home</a></div>';
        }
    }
}

/**
 * Hide shared header when continuing the conversation
 */
function setupSharedHeaderHider() {
    // Watch for new messages being added to chatContainer (but not to originalMessages)
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                // Check if a new message was added directly to chatContainer (not to originalMessages)
                if (node.nodeType === 1 && node.classList && node.classList.contains('message')) {
                    const container = window.chatContainer || document.getElementById('chatContainer');
                    // If message is added directly to chatContainer (not inside originalMessages), hide header
                    if (container && node.parentElement === container && !originalMessages.contains(node)) {
                        if (sharedHeader && !sharedHeader.classList.contains('hidden')) {
                            sharedHeader.classList.add('hidden');
                            observer.disconnect(); // Stop observing once header is hidden
                        }
                    }
                }
            });
        });
    });

    // Observe the chat container for new messages
    const container = window.chatContainer || document.getElementById('chatContainer');
    if (container) {
        observer.observe(container, { childList: true });
    }
}