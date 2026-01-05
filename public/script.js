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

            // Pre-process Discord underline syntax (__text__)
            // Strategy: Convert to HTML <u> tags before parsing - marked should preserve HTML

            // Step 1: Protect code blocks and inline code first
            // Use placeholders that won't match the underline pattern (no double underscores)
            const codeBlocks = [];
            let processed = text.replace(/```[\s\S]*?```/g, (match) => {
                const placeholder = `\u0000CODEBLOCK${codeBlocks.length}\u0000`;
                codeBlocks.push({ placeholder, content: match });
                return placeholder;
            });

            const inlineCodes = [];
            processed = processed.replace(/`[^`]+`/g, (match) => {
                const placeholder = `\u0000INLINECODE${inlineCodes.length}\u0000`;
                inlineCodes.push({ placeholder, content: match });
                return placeholder;
            });

            // Step 2: Convert __text__ to <u>text</u> (Discord underline syntax)
            // This HTML will be preserved by marked
            processed = processed.replace(/__(?![_])(.+?)(?<!_)__/g, '<u>$1</u>');

            // Step 3: Restore code blocks and inline code
            inlineCodes.forEach(({ placeholder, content }) => {
                processed = processed.replace(placeholder, content);
            });

            codeBlocks.forEach(({ placeholder, content }) => {
                processed = processed.replace(placeholder, content);
            });

            // Step 4: Parse with marked (it should preserve the <u> tags)
            return marked.parse(processed);
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

    let statsHtml = '';
    if (stats) {
        statsHtml = `<div class="message-stats">💵 $${stats.cost.toFixed(6)} | 🪙 ${stats.tokens} tokens</div>`;
    }

    let buttonsHtml = '';
    if (!isUser && prompt) {
        // Add buttons after 10 seconds delay (like Discord bot)
        buttonsHtml = '<div class="message-buttons" style="display: none;">' +
            '<button class="regenerate-btn" onclick="handleRegenerate(this)">↻ Regenerate</button>' +
            '<button class="extend-btn" onclick="handleExtend(this)">+ More</button>' +
            '</div>';
    }

    messageDiv.innerHTML = `
        <div class="message-text">${formatMessage(text)}</div>
        ${sources ? formatSources(sources) : ''}
        ${statsHtml}
        ${buttonsHtml}
    `;

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    updateInputState();

    // Show buttons after 10 seconds for bot messages
    if (!isUser && prompt) {
        const buttonsDiv = messageDiv.querySelector('.message-buttons');
        if (buttonsDiv) {
            setTimeout(() => {
                buttonsDiv.style.display = 'flex';
            }, 10000);
        }
    }
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

    // Disable buttons
    const buttonsDiv = messageDiv.querySelector('.message-buttons');
    if (buttonsDiv) {
        buttonsDiv.style.display = 'none';
    }

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

    // Disable buttons
    const buttonsDiv = messageDiv.querySelector('.message-buttons');
    if (buttonsDiv) {
        buttonsDiv.style.display = 'none';
    }

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
