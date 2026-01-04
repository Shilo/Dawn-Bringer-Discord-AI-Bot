const chatContainer = document.getElementById('chatContainer');
const questionInput = document.getElementById('questionInput');
const sendButton = document.getElementById('sendButton');
const stats = document.getElementById('stats');

// Auto-resize textarea
questionInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 200) + 'px';
});

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

// Format message text (handle markdown-like formatting)
function formatMessage(text) {
    // Handle null/undefined
    if (!text) {
        return '';
    }

    // Convert to string if needed
    text = String(text);

    // Escape HTML
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
    // Remove welcome message if it exists
    const welcomeMsg = chatContainer.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;

    const avatar = isUser ? '👤' : '☀️';
    const authorName = isUser ? 'You' : 'Dawn Bringer';
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let statsHtml = '';
    if (stats) {
        statsHtml = `<div class="message-stats">💵 $${stats.cost.toFixed(6)} | 🪙 ${stats.tokens} tokens</div>`;
    }

    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">${authorName}</span>
                <span class="message-timestamp">${timestamp}</span>
            </div>
            <div class="message-text">${formatMessage(text)}</div>
            ${sources ? formatSources(sources) : ''}
            ${statsHtml}
        </div>
    `;

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Show loading indicator
function showLoading() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message';
    loadingDiv.id = 'loadingMessage';
    loadingDiv.innerHTML = `
        <div class="message-avatar">☀️</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">Dawn Bringer</span>
            </div>
            <div class="loading">
                <span>Thinking</span>
                <div class="loading-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
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
    const question = questionInput.value.trim();
    if (!question || sendButton.disabled) return;

    // Add user message
    addMessage('You', question, true);

    // Clear input
    questionInput.value = '';
    questionInput.style.height = 'auto';

    // Disable input
    sendButton.disabled = true;
    questionInput.disabled = true;

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
        // Re-enable input
        sendButton.disabled = false;
        questionInput.disabled = false;
        questionInput.focus();
    }
}

// Event listeners
sendButton.addEventListener('click', sendMessage);

questionInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Focus input on load
questionInput.focus();

