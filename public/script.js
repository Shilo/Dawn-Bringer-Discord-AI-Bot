const chatContainer = document.getElementById('chatContainer');
const questionInput = document.getElementById('questionInput');
const questionInputBottom = document.getElementById('questionInputBottom');
const stats = document.getElementById('stats');
const centeredInputWrapper = document.getElementById('centeredInputWrapper');
const bottomInputWrapper = document.getElementById('bottomInputWrapper');
const welcomeMessage = document.getElementById('welcomeMessage');

// Auto-resize textarea
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

questionInput.addEventListener('input', function () {
    autoResize(this);
    questionInputBottom.value = this.value;
    autoResize(questionInputBottom);
});

questionInputBottom.addEventListener('input', function () {
    autoResize(this);
    questionInput.value = this.value;
    autoResize(questionInput);
});

// Update UI state based on message count
function updateInputState() {
    const hasMessages = chatContainer.querySelectorAll('.message').length > 0;

    if (hasMessages) {
        centeredInputWrapper.classList.add('hidden');
        welcomeMessage.style.display = 'none';
        bottomInputWrapper.classList.add('visible');
        chatContainer.classList.add('has-messages');
        questionInputBottom.focus();
    } else {
        centeredInputWrapper.classList.remove('hidden');
        welcomeMessage.style.display = 'flex';
        bottomInputWrapper.classList.remove('visible');
        chatContainer.classList.remove('has-messages');
        questionInput.focus();
    }
}

// Format stats text to be more compact
function formatStatsText(statsText) {
    if (!statsText || statsText.includes('Initializing') || statsText.includes('not initialized')) {
        return statsText || 'Loading...';
    }

    // Extract numbers from "~149k words from 743 articles"
    const match = statsText.match(/(\d+[km]?)\s+words?\s+from\s+(\d+)/i);
    if (match) {
        return `${match[1]} words • ${match[2]} docs`;
    }

    // Fallback to original if pattern doesn't match
    return statsText;
}

// Load stats on page load and refresh periodically until RAG is ready
async function loadStats() {
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
        stats.textContent = 'Loading...';
        // Retry after 2 seconds on error
        setTimeout(loadStats, 2000);
    }
}

loadStats();

// Refresh stats every 30 seconds to keep it updated (only if not initializing)
setInterval(() => {
    const currentText = stats.textContent;
    if (!currentText.includes('Initializing') && !currentText.includes('not initialized')) {
        loadStats();
    }
}, 30000);

// Format message text with full markdown support
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

// Format sources (similar to Discord format)
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

// Add message to chat
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

    let statsHtml = '';
    if (stats) {
        statsHtml = `<div class="message-stats">💵 $${stats.cost.toFixed(6)} | 🪙 ${stats.tokens} tokens</div>`;
    }

    // Action buttons (regenerate/extend after 10 seconds if prompt exists, copy always at end)
    let buttonsHtml = '';
    if (!isUser) {
        let actionButtons = '';

        if (prompt) {
            // Add regenerate/extend buttons after 10 seconds delay (like Discord bot)
            actionButtons += '<button class="regenerate-btn" onclick="handleRegenerate(this)" title="Regenerate message" style="display: none;">↻</button>' +
                '<button class="extend-btn" onclick="handleExtend(this)" title="Extend message" style="display: none;">+</button>';
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

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
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
    console.log(isActive, buttons);
    buttons.forEach(button => {
        button.disabled = !isActive;
    });
}

// Hide message buttons
function hideMessageButtons(messageDiv) {
    messageDiv.classList.remove('active');
    updateMessageButtonsDisabled(messageDiv);
}

// Check if device supports touch
function isTouchDevice() {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

// Setup touch/click handler for message buttons on mobile
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
    chatContainer.appendChild(loadingDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Remove loading indicator
function removeLoading() {
    const loadingMsg = document.getElementById('loadingMessage');
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

// Send message
async function sendMessage() {
    // Check if there's already a pending message (loading indicator)
    const loadingMsg = document.getElementById('loadingMessage');
    if (loadingMsg) {
        return; // Don't allow new submissions while waiting for response
    }

    // Get question from active input
    const activeInput = bottomInputWrapper.classList.contains('visible')
        ? questionInputBottom
        : questionInput;

    const question = activeInput.value.trim();
    if (!question) return;

    // Add user message
    addMessage('You', question, true);

    // Clear both inputs
    questionInput.value = '';
    questionInputBottom.value = '';
    questionInput.style.height = 'auto';
    questionInputBottom.style.height = 'auto';

    // Show loading
    showLoading();

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question: question }),
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
        removeLoading();
        const errorMessage = error.message || 'An unknown error occurred';
        addMessage('Dawn Bringer', `❌ Error: ${errorMessage}`, false);
    } finally {
        // Focus appropriate input
        const activeInput = bottomInputWrapper.classList.contains('visible')
            ? questionInputBottom
            : questionInput;
        activeInput.focus();
    }
}

// Event listeners
questionInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

questionInputBottom.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Handle regenerate button click
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
    showToast('Regenerating message...');

    // Hide regenerate/extend buttons
    const regenerateBtn = messageDiv.querySelector('.regenerate-btn');
    const extendBtn = messageDiv.querySelector('.extend-btn');
    if (regenerateBtn) regenerateBtn.style.display = 'none';
    if (extendBtn) extendBtn.style.display = 'none';

    // Show loading
    showLoading();

    try {
        const response = await fetch('/api/regenerate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt: prompt }),
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
        } else if (data.sources) {
            // Insert sources if they don't exist
            const statsDiv = messageDiv.querySelector('.message-stats');
            if (statsDiv) {
                statsDiv.insertAdjacentHTML('beforebegin', formatSources(data.sources));
            }
        }

        if (messageStats && data.stats) {
            messageStats.textContent = `💵 $${data.stats.cost.toFixed(6)} | 🪙 ${data.stats.tokens} tokens`;
        }

        // Don't show buttons for regenerated messages (like Discord bot)

    } catch (error) {
        removeLoading();
        const errorMessage = error.message || 'An unknown error occurred';
        addMessage('Dawn Bringer', `❌ Error: ${errorMessage}`, false);
    }
}

// Handle copy button click
async function handleCopy(button) {
    const messageDiv = button.closest('.message');

    // Hide buttons when copy is triggered
    hideMessageButtons(messageDiv);

    const markdownText = messageDiv.getAttribute('data-markdown');

    if (!markdownText) {
        // Fallback: try to get text from message-text element
        const messageText = messageDiv.querySelector('.message-text');
        if (messageText) {
            // Extract plain text as fallback
            const textToCopy = messageText.innerText || messageText.textContent;
            try {
                await navigator.clipboard.writeText(textToCopy);
                showToast('Copied message');
                return;
            } catch (err) {
                console.error('Failed to copy:', err);
                return;
            }
        }
        return;
    }

    try {
        await navigator.clipboard.writeText(markdownText);
        showToast('Copied message');
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
            showToast('Copied message');
        } catch (fallbackErr) {
            console.error('Fallback copy failed:', fallbackErr);
        }
        document.body.removeChild(textArea);
    }
}

// Show toast notification
let toastTimeout = null;
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
    showToast('Extending message...');

    // Hide regenerate/extend buttons
    const regenerateBtn = messageDiv.querySelector('.regenerate-btn');
    const extendBtn = messageDiv.querySelector('.extend-btn');
    if (regenerateBtn) regenerateBtn.style.display = 'none';
    if (extendBtn) extendBtn.style.display = 'none';

    // Show loading
    showLoading();

    try {
        const response = await fetch('/api/extend', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt: prompt }),
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
        } else if (data.sources) {
            // Insert sources if they don't exist
            const statsDiv = messageDiv.querySelector('.message-stats');
            if (statsDiv) {
                statsDiv.insertAdjacentHTML('beforebegin', formatSources(data.sources));
            }
        }

        if (messageStats && data.stats) {
            messageStats.textContent = `💵 $${data.stats.cost.toFixed(6)} | 🪙 ${data.stats.tokens} tokens`;
        }

        // Don't show buttons for extended messages (like Discord bot)

    } catch (error) {
        removeLoading();
        const errorMessage = error.message || 'An unknown error occurred';
        addMessage('Dawn Bringer', `❌ Error: ${errorMessage}`, false);
    }
}

// Initialize UI state
updateInputState();

// Initialize centered input to 3 lines height
autoResize(questionInput);
