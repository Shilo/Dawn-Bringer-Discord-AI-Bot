// Share page specific JavaScript
// This file only loads and displays the original shared conversation
// All message handling, sending, etc. uses the core logic from script.js

const sharedHeader = document.getElementById('sharedHeader');
const sharedInfo = document.getElementById('sharedInfo');
const originalMessages = document.getElementById('originalMessages');

// Get short ID from URL
const pathParts = window.location.pathname.split('/');
const shortId = pathParts[pathParts.length - 1];

// Load the shared conversation and display it using addMessage from script.js
async function loadSharedConversation() {
    try {
        const response = await fetch(`/api/share/${shortId}`);
        if (!response.ok) {
            if (response.status === 404) {
                originalMessages.innerHTML = '<div style="text-align: center; padding: 2rem;"><h2>Share Not Found</h2><p>This shared conversation could not be found.</p><a href="/" style="color: #4a9eff;">Return to home</a></div>';
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const share = await response.json();

        // Show shared header
        sharedHeader.classList.remove('hidden');
        const createdAt = new Date(share.created_at);
        sharedInfo.textContent = `Shared ${createdAt.toLocaleDateString()} • ${share.view_count || 0} views`;

        // Parse sources and stats from metadata
        let sources = share.metadata?.sources || null;
        let stats = share.metadata?.stats || null;

        // Add original messages to originalMessages div (they'll be inside chatContainer)
        // Temporarily set chatContainer to originalMessages so addMessage uses it
        const originalChatContainer = window.chatContainer;
        window.chatContainer = originalMessages;

        // Add original messages using the shared addMessage function from script.js
        addMessage('User', share.prompt, true);
        addMessage('Dawn Bringer', share.response, false, sources, stats, share.prompt);

        // Restore chatContainer for new messages (continue conversation goes to main container)
        window.chatContainer = originalChatContainer || window.chatContainer;

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
        originalMessages.innerHTML = '<div style="text-align: center; padding: 2rem;"><h2>Error Loading Conversation</h2><p>Could not load the shared conversation.</p><a href="/" style="color: #4a9eff;">Return to home</a></div>';
    }
}

// Hide shared header when continuing the conversation
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

// Load shared conversation on page load
loadSharedConversation();

