/**
 * Cyberpunk Chat Matrix - High Performance Markdown & Code Interactive Engine with Groq AI
 */

document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const queryInput = document.getElementById('query-input');
    const chatHistory = document.getElementById('chat-history');
    const sendBtn = document.getElementById('send-btn');
    const sessionId = document.getElementById('session-id')?.value;
    const typingIndicator = document.getElementById('typing-indicator');

    if (!chatForm || !queryInput || !sessionId) return;

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // Configure marked if present
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            gfm: true,
            breaks: true,
            headerIds: false,
            mangle: false
        });
    }

    // Robust markdown rendering function
    function renderMarkdown(text) {
        if (!text) return '';
        
        if (typeof marked !== 'undefined') {
            try {
                return marked.parse(text);
            } catch (e) {
                console.error("Marked parsing error:", e);
            }
        }

        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Fenced code blocks
        html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
        });

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        html = html.replace(/^[•\-\*]\s+(.*$)/gim, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>(\n|(?=<li>)))/gim, '<ul>$1</ul>');
        html = html.replace(/\n\n/g, '</p><p>');
        return `<p>${html}</p>`;
    }

    // Render all pre-existing server-rendered message bodies on load
    document.querySelectorAll('.msg-text').forEach(el => {
        const raw = el.textContent || el.innerText;
        if (raw && !el.dataset.rendered) {
            el.innerHTML = renderMarkdown(raw);
            el.dataset.rendered = 'true';
        }
    });

    // Highlight pre-existing code blocks if hljs is loaded
    if (typeof hljs !== 'undefined') {
        document.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
    }

    scrollToBottom();

    // Suggestion chips click
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            queryInput.value = chip.textContent.trim();
            chatForm.dispatchEvent(new Event('submit'));
        });
    });

    // Toggle sources helper
    function setupSourceToggles(container) {
        container.querySelectorAll('.citation-toggle-btn').forEach(btn => {
            if (btn.dataset.bound) return;
            btn.dataset.bound = 'true';
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetId = btn.dataset.target;
                const packets = document.getElementById(targetId);
                const arrow = btn.querySelector('.arrow');
                if (packets) {
                    if (packets.style.display === 'none' || !packets.style.display) {
                        packets.style.display = 'flex';
                        if (arrow) arrow.textContent = '▼';
                    } else {
                        packets.style.display = 'none';
                        if (arrow) arrow.textContent = '▶';
                    }
                }
            });
        });
    }

    setupSourceToggles(document);

    // Append message to UI
    function appendMessage(role, text, sources = [], providerBadge = null) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-msg ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = role === 'user' ? 'USR' : 'AI';

        const body = document.createElement('div');
        body.className = 'msg-body cyber-cut';

        // Add provider badge if returned
        if (role === 'assistant' && providerBadge) {
            const badge = document.createElement('div');
            badge.className = 'model-provider-badge';
            badge.innerHTML = `⚡ ${providerBadge}`;
            body.appendChild(badge);
        }

        const msgText = document.createElement('div');
        msgText.className = 'msg-text';
        msgText.innerHTML = renderMarkdown(text);
        body.appendChild(msgText);

        // Render sources/citations if present
        if (sources && sources.length > 0) {
            const citeContainer = document.createElement('div');
            citeContainer.className = 'citation-container';

            const citeId = `packet-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

            citeContainer.innerHTML = `
                <div class="citation-header citation-toggle-btn" data-target="${citeId}">
                    <span class="arrow">▶</span>
                    <span>Sources (${sources.length})</span>
                </div>
                <div class="citation-packets" id="${citeId}" style="display:none;">
                    ${sources.map(src => `
                        <div class="data-packet-chip">
                            <div class="packet-meta">
                                <span>Excerpt #${src.chunk_index} ${src.page_number ? `(Page ${src.page_number})` : ''}</span>
                            </div>
                            <div class="packet-snippet">${src.snippet}</div>
                        </div>
                    `).join('')}
                </div>
            `;
            body.appendChild(citeContainer);
        }

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(body);

        if (typingIndicator) {
            chatHistory.insertBefore(msgDiv, typingIndicator);
        } else {
            chatHistory.appendChild(msgDiv);
        }

        // Highlight code
        if (typeof hljs !== 'undefined') {
            msgDiv.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
        }

        setupSourceToggles(msgDiv);
        scrollToBottom();
    }

    // Chat submit with real-time word-by-word typewriter streaming (ChatGPT/Claude style)
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;

        appendMessage('user', query);
        queryInput.value = '';
        queryInput.disabled = true;
        sendBtn.disabled = true;

        if (typingIndicator) {
            typingIndicator.style.display = 'flex';
            scrollToBottom();
        }

        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

        try {
            const response = await fetch(`/api/chat/${sessionId}/ask/?stream=true`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ message: query })
            });

            if (typingIndicator) typingIndicator.style.display = 'none';

            if (!response.ok) {
                let errText = 'Server error.';
                try {
                    const errData = await response.json();
                    errText = errData.error || errText;
                } catch(e) {}
                appendMessage('assistant', `⚠️ ${errText}`);
                return;
            }

            // Create streaming assistant message card
            const msgDiv = document.createElement('div');
            msgDiv.className = 'chat-msg assistant';

            const avatar = document.createElement('div');
            avatar.className = 'msg-avatar';
            avatar.textContent = 'AI';

            const body = document.createElement('div');
            body.className = 'msg-body cyber-cut';

            const badgeContainer = document.createElement('div');
            body.appendChild(badgeContainer);

            const msgText = document.createElement('div');
            msgText.className = 'msg-text';
            msgText.innerHTML = '<span class="typing-cursor">▌</span>';
            body.appendChild(msgText);

            const citeContainer = document.createElement('div');
            body.appendChild(citeContainer);

            msgDiv.appendChild(avatar);
            msgDiv.appendChild(body);
            chatHistory.appendChild(msgDiv);
            scrollToBottom();

            // Stream reader loop
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let accumulatedText = '';
            let sources = [];
            let providerBadge = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // keep remainder

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(trimmed.substring(6));

                        if (event.type === 'meta') {
                            providerBadge = event.provider;
                            sources = event.sources || [];
                            if (providerBadge) {
                                badgeContainer.innerHTML = `<div class="model-provider-badge">⚡ ${providerBadge}</div>`;
                            }
                        } else if (event.type === 'token') {
                            accumulatedText += event.token;
                            msgText.innerHTML = renderMarkdown(accumulatedText) + '<span class="typing-cursor">▌</span>';
                            scrollToBottom();
                        } else if (event.type === 'done') {
                            accumulatedText = event.answer || accumulatedText;
                        }
                    } catch (err) {
                        console.warn("SSE parse warning", err);
                    }
                }
            }

            // Finalize message rendering
            msgText.innerHTML = renderMarkdown(accumulatedText);

            if (sources && sources.length > 0) {
                const citeId = `packet-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
                citeContainer.className = 'citation-container';
                citeContainer.innerHTML = `
                    <div class="citation-header citation-toggle-btn" data-target="${citeId}">
                        <span class="arrow">▶</span>
                        <span>Sources (${sources.length})</span>
                    </div>
                    <div class="citation-packets" id="${citeId}" style="display:none;">
                        ${sources.map(src => `
                            <div class="data-packet-chip">
                                <div class="packet-meta">
                                    <span>Excerpt #${src.chunk_index} ${src.page_number ? `(Page ${src.page_number})` : ''}</span>
                                </div>
                                <div class="packet-snippet">${src.snippet}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Highlight syntax
            if (typeof hljs !== 'undefined') {
                msgDiv.querySelectorAll('pre code').forEach(block => {
                    hljs.highlightElement(block);
                });
            }

            setupSourceToggles(msgDiv);
            scrollToBottom();

        } catch (err) {
            if (typingIndicator) typingIndicator.style.display = 'none';
            appendMessage('assistant', `⚠️ Network error: ${err.message}`);
        } finally {
            queryInput.disabled = false;
            sendBtn.disabled = false;
            queryInput.focus();
            scrollToBottom();
        }
    });
});
