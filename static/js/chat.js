document.addEventListener('DOMContentLoaded', () => {
    const chatHistory = document.getElementById('chat-history');
    const chatInput = document.getElementById('chat-input');
    const sendButton = document.getElementById('send-button');
    const tabs = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');
    const inboxMessages = document.getElementById('inbox-messages');
    const sendToDoctorBtn = document.getElementById('send-to-doctor');
    const messageToDoctorInput = document.getElementById('message-to-doctor');

    // Tab switching logic
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const target = document.getElementById(tab.dataset.tab);
            tabContents.forEach(tc => tc.classList.remove('active'));
            target.classList.add('active');

            if (tab.dataset.tab === 'inbox') {
                loadDoctorMessages();
            }
        });
    });

    // Load previous chat on page load
    loadPreviousChat();

    // Chat functionality
    sendButton.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    async function sendMessage() {
        const message = chatInput.value.trim();
        if (!message) return;

        appendMessage('user', message);
        chatInput.value = '';
        toggleTypingIndicator(true);

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message }),
            });
            const data = await response.json();
            toggleTypingIndicator(false);
            appendMessage('ai', data.response || 'Sorry, I encountered an error.');
        } catch (error) {
            toggleTypingIndicator(false);
            console.error('Error:', error);
            appendMessage('ai', 'Sorry, I could not connect to the server.');
        }
    }

    async function loadPreviousChat() {
        try {
            const res = await fetch('/chat/history', { headers: { 'Accept': 'application/json' } });
            if (!res.ok) {
                console.warn('Chat history request failed with status', res.status);
                return;
            }
            const contentType = res.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                console.warn('Chat history response was not JSON');
                return;
            }
            const history = await res.json();
            if (Array.isArray(history)) {
                // Remove any existing non-typing chat messages
                [...chatHistory.querySelectorAll('.chat-message')]
                    .filter(el => !el.classList.contains('typing-indicator'))
                    .forEach(el => el.remove());
                history.forEach(item => {
                    if (item.user) appendMessage('user', item.user);
                    if (item.ai) appendMessage('ai', item.ai);
                });
            }
        } catch (e) {
            console.error('Failed to load chat history', e);
        }
    }

    function appendMessage(sender, text) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-message', sender);
        const bubble = document.createElement('div');
        bubble.classList.add('bubble');
        bubble.textContent = text;
        messageElement.appendChild(bubble);
        chatHistory.insertBefore(messageElement, document.querySelector('.typing-indicator'));
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function toggleTypingIndicator(show) {
        const indicator = document.querySelector('.typing-indicator');
        if (indicator) {
            indicator.style.display = show ? 'flex' : 'none';
        }
    }

    // Inbox functionality
    async function loadDoctorMessages() {
        inboxMessages.innerHTML = '<p>Loading messages...</p>';
        try {
            const response = await fetch('/get-direct-messages');
            const messages = await response.json();

            if (messages.error) {
                inboxMessages.innerHTML = `<p>Error: ${messages.error}</p>`;
                return;
            }

            if (messages.length === 0) {
                inboxMessages.innerHTML = '<p>You have no messages from your doctor.</p>';
                return;
            }

            inboxMessages.innerHTML = '';
            messages.forEach(msg => {
                const msgElement = document.createElement('div');
                msgElement.classList.add('inbox-message');
                const date = new Date(msg.timestamp).toLocaleString();
                msgElement.innerHTML = `
                    <div class="message-header">
                        <strong>From: Your Doctor</strong>
                        <span class="timestamp">${date}</span>
                    </div>
                    <p>${msg.message}</p>
                `;
                inboxMessages.appendChild(msgElement);
            });
        } catch (error) {
            console.error('Error loading doctor messages:', error);
            inboxMessages.innerHTML = '<p>Could not load messages. Please try again.</p>';
        }
    }
    
    // Send message to doctor from inbox tab
    if (sendToDoctorBtn && messageToDoctorInput) {
        sendToDoctorBtn.addEventListener('click', async () => {
            const text = messageToDoctorInput.value.trim();
            if (!text) return;
            try {
                const res = await fetch('/send-message-to-doctor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });
                const data = await res.json();
                if (data && data.success) {
                    messageToDoctorInput.value = '';
                    loadDoctorMessages();
                } else if (data && data.error) {
                    alert(data.error);
                }
            } catch (e) {
                alert('Could not send message.');
            }
        });
    }

    // Initially hide typing indicator
    toggleTypingIndicator(false);
});