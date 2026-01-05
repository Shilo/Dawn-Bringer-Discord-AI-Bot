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
        return `📚 ${match[1]} words • ${match[2]} docs`;
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

            // Parse markdown to HTML
            return marked.parse(text);
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

    // Code blocks
    formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

    // Inline code
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Links
    formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" style="color: #00aff4;">$1</a>');

    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

// Format sources
function formatSources(sources) {
    if (!sources || sources.length === 0) return '';

    let html = '<div class="message-sources">';
    sources.forEach(source => {
        if (source.url) {
            html += `<a href="${source.url}" target="_blank" class="source-link">${source.name || source.source}</a>`;
        } else {
            html += `<span class="source-link" style="background: #4f545c;">${source.name || source.source}</span>`;
        }
    });
    html += '</div>';
    return html;
}

// Add message to chat
function addMessage(author, text, isUser = false, sources = null, stats = null) {
    // Hide welcome message and centered input when first message is added
    updateInputState();

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;

    let statsHtml = '';
    if (stats) {
        statsHtml = `<div class="message-stats">💵 $${stats.cost.toFixed(6)} | 🪙 ${stats.tokens} tokens</div>`;
    }

    messageDiv.innerHTML = `
        <div class="message-text">${formatMessage(text)}</div>
        ${sources ? formatSources(sources) : ''}
        ${statsHtml}
    `;

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    updateInputState();
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
            const errorMessage = data.detail || data.error || `HTTP ${response.status}: ${response.statusText}`;
            throw new Error(errorMessage);
        }

        // Check if response field exists
        if (!data.response) {
            throw new Error('No response received from server');
        }

        // Remove loading
        removeLoading();

        // Add bot response
        addMessage(
            'Dawn Bringer',
            data.response || 'No response received',
            false,
            data.sources || null,
            data.stats || null
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

// Initialize UI state
updateInputState();
