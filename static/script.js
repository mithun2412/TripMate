// ============================================================
// STATE MANAGEMENT
// ============================================================
let currentThreadId = localStorage.getItem("travel_thread_id") || null;
let latestAnswerMarkdown = "";
let isWaitingForInfo = false;
let messageHistory = [];

// ============================================================
// DOM REFS
// ============================================================
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const btnText = document.getElementById('btnText');
const btnLoader = document.getElementById('btnLoader');
const sendIcon = document.getElementById('sendIcon');
const errorBox = document.getElementById('errorBox');
const errorText = document.getElementById('errorText');

// ============================================================
// MARKDOWN RENDERER CONFIGURATION
// ============================================================

function configureMarked() {
    if (typeof marked === 'undefined') {
        console.warn('Marked library not loaded');
        return;
    }
    
    marked.setOptions({
        gfm: true,
        tables: true,
        breaks: true,
        pedantic: false,
        sanitize: false,
        smartLists: true,
        smartypants: false,
        xhtml: false
    });

    // Custom renderer for better table styling
    const renderer = new marked.Renderer();
    
    renderer.table = function(header, body) {
        return `<div class="table-wrapper"><table class="markdown-table">${header}${body}</table></div>`;
    };
    
    marked.use({ renderer });
}

// ============================================================
// BUDGET TABLE PARSER - EXTRACT DATA FROM TEXT
// ============================================================

function extractBudgetData(content) {
    const budgetData = {
        category: [],
        costs: [],
        budget: null,
        remaining: null,
        subtotal: null
    };
    
    // Try to find budget table in various formats
    const patterns = [
        // Pattern: "Category | Cost"
        /\|\s*Category\s*\|\s*Cost\s*\([₹$£]\)\s*\|/i,
        // Pattern: "Flights: ₹X, Hotels: ₹Y"
        /(?:Flights|Flight)[:\s]*[₹$£]?\s*([\d,]+)/i,
        /(?:Hotels|Hotel)[:\s]*[₹$£]?\s*([\d,]+)/i,
        /(?:Food|Transport|Meals)[:\s]*[₹$£]?\s*([\d,]+)/i,
        /(?:Budget|Total Budget)[:\s]*[₹$£]?\s*([\d,]+)/i,
        /(?:Remaining|Left)[:\s]*[₹$£]?\s*([\d,]+)/i,
    ];
    
    // Extract numbers
    const numbers = [];
    const matches = content.match(/\b[\d,]+(?:\s*-\s*[\d,]+)?\b/g);
    if (matches) {
        for (let match of matches) {
            // Clean and convert to number
            const clean = match.replace(/,/g, '');
            if (!isNaN(clean) && clean.length > 0) {
                const num = parseInt(clean);
                if (num > 0 && num < 1000000) {
                    numbers.push(num);
                }
            }
        }
    }
    
    // Categorize the numbers
    if (numbers.length >= 3) {
        // Assume: flights, hotels, food, subtotal, budget, remaining
        const categories = ['Flights', 'Hotels', 'Food & Transport'];
        
        for (let i = 0; i < Math.min(categories.length, numbers.length); i++) {
            budgetData.category.push(categories[i]);
            budgetData.costs.push(numbers[i]);
        }
        
        // Calculate subtotal
        budgetData.subtotal = budgetData.costs.reduce((a, b) => a + b, 0);
        
        // Look for budget and remaining
        if (numbers.length > categories.length) {
            // Try to find budget (typically a larger number)
            for (let num of numbers) {
                if (num > budgetData.subtotal && num < 1000000) {
                    budgetData.budget = num;
                    break;
                }
            }
            
            // If no budget found, use the next number
            if (!budgetData.budget && numbers.length > categories.length) {
                budgetData.budget = numbers[categories.length];
            }
            
            // Calculate remaining
            if (budgetData.budget && budgetData.subtotal) {
                budgetData.remaining = budgetData.budget - budgetData.subtotal;
            }
        }
    }
    
    // If we have at least some data, return it
    if (budgetData.category.length > 0) {
        return budgetData;
    }
    
    return null;
}

// ============================================================
// GENERATE TABLE HTML - FRONTEND CREATES THE TABLE
// ============================================================

function generateBudgetTableHTML(budgetData) {
    if (!budgetData || budgetData.category.length === 0) {
        return '';
    }
    
    let html = `
        <div class="budget-table-wrapper">
            <h4 class="budget-table-title">💰 Estimated Budget Breakdown</h4>
            <table class="budget-table">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Cost (₹)</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    // Add each row
    for (let i = 0; i < budgetData.category.length; i++) {
        const category = budgetData.category[i];
        const cost = budgetData.costs[i] ? budgetData.costs[i].toLocaleString() : '0';
        html += `
            <tr>
                <td>${category}</td>
                <td>₹${cost}</td>
            </tr>
        `;
    }
    
    // Add subtotal if available
    if (budgetData.subtotal) {
        html += `
            <tr class="subtotal-row">
                <td><strong>Subtotal</strong></td>
                <td><strong>₹${budgetData.subtotal.toLocaleString()}</strong></td>
            </tr>
        `;
    }
    
    // Add budget if available
    if (budgetData.budget) {
        html += `
            <tr class="budget-row">
                <td><strong>Budget</strong></td>
                <td><strong>₹${budgetData.budget.toLocaleString()}</strong></td>
            </tr>
        `;
    }
    
    // Add remaining if available
    if (budgetData.remaining !== null && budgetData.remaining >= 0) {
        const remainingClass = budgetData.remaining > 0 ? 'positive' : 'negative';
        html += `
            <tr class="remaining-row ${remainingClass}">
                <td><strong>Remaining</strong></td>
                <td><strong>₹${budgetData.remaining.toLocaleString()}</strong></td>
            </tr>
        `;
    }
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    return html;
}

// ============================================================
// CLEAN AND FIX MARKDOWN CONTENT
// ============================================================

function cleanMarkdownContent(content) {
    // Remove broken table rows (lines with too many pipes)
    const lines = content.split('\n');
    const cleanedLines = [];
    let inBrokenTable = false;
    
    for (let line of lines) {
        // Check if line has more than 4 pipes (broken table)
        const pipeCount = (line.match(/\|/g) || []).length;
        if (pipeCount > 6) {
            inBrokenTable = true;
            continue;
        }
        
        // If we were in a broken table and hit an empty line or heading, exit
        if (inBrokenTable && (line.trim() === '' || line.startsWith('#'))) {
            inBrokenTable = false;
        }
        
        // Skip if still in broken table
        if (inBrokenTable) continue;
        
        // Skip lines that are just pipes
        if (line.trim() === '|' || line.trim() === '| |') continue;
        
        cleanedLines.push(line);
    }
    
    return cleanedLines.join('\n');
}

// ============================================================
// MESSAGE FUNCTIONS
// ============================================================

function renderMessage(content, isUser = false) {
    if (isUser) {
        return content;
    }
    
    // Clean the content first
    let cleanContent = cleanMarkdownContent(content);
    
    // Extract budget data
    const budgetData = extractBudgetData(cleanContent);
    
    // Remove the budget section from content (we'll render it separately)
    let textContent = cleanContent;
    
    // Remove budget table sections
    textContent = textContent.replace(/\|\s*Category\s*\|\s*Cost\s*\([₹$£]\)\s*\|[\s\S]*?(?=\n\n|\n#|$)/gi, '');
    textContent = textContent.replace(/##\s*Estimated Budget Breakdown[\s\S]*?(?=\n\n|\n#|$)/gi, '');
    textContent = textContent.replace(/##\s*Budget Breakdown[\s\S]*?(?=\n\n|\n#|$)/gi, '');
    textContent = textContent.replace(/\|\s*---\s*\|[\s\S]*?(?=\n\n|\n#|$)/gi, '');
    
    // Remove leftover table rows
    textContent = textContent.replace(/^\|.*\|$/gm, '');
    
    // Clean up extra newlines
    textContent = textContent.replace(/\n{3,}/g, '\n\n');
    textContent = textContent.trim();
    
    // Render markdown
    let html = '';
    if (typeof marked !== 'undefined') {
        try {
            if (!marked._defaults) {
                configureMarked();
            }
            html = marked.parse(textContent);
        } catch (error) {
            console.error('Markdown parsing error:', error);
            html = textContent;
        }
    } else {
        html = textContent;
    }
    
    // If we have budget data, add the table
    if (budgetData && budgetData.category.length > 0) {
        html += generateBudgetTableHTML(budgetData);
    }
    
    return html;
}

function addMessage(content, isUser = false, isComplete = true, missingInfo = []) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (!isUser) {
        contentDiv.innerHTML = renderMessage(content, false);
    } else {
        contentDiv.textContent = content;
    }
    
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    // Handle missing info status
    if (!isUser && !isComplete && missingInfo && missingInfo.length > 0) {
        const statusDiv = document.createElement('div');
        statusDiv.className = 'info-status warning';
        statusDiv.innerHTML = `
            <i class="fas fa-info-circle"></i>
            <span>Please provide: <strong>${missingInfo.join(', ')}</strong></span>
        `;
        chatMessages.appendChild(statusDiv);
        isWaitingForInfo = true;
        updateButtonState('continue');
    } else {
        isWaitingForInfo = false;
        updateButtonState('send');
        
        if (!isUser && isComplete) {
            const statusDiv = document.createElement('div');
            statusDiv.className = 'info-status success';
            statusDiv.innerHTML = `
                <i class="fas fa-check-circle"></i>
                <span>✅ Trip plan generated successfully!</span>
            `;
            chatMessages.appendChild(statusDiv);
            
            setTimeout(() => {
                messageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        }
    }
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    messageHistory.push({
        content: content,
        isUser: isUser,
        isComplete: isComplete,
        missingInfo: missingInfo
    });
}

function addLoadingMessage() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message message-loading';
    loadingDiv.id = 'loadingMessage';
    loadingDiv.innerHTML = `
        <div class="message-content">
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeLoadingMessage() {
    const loading = document.getElementById('loadingMessage');
    if (loading) {
        loading.remove();
    }
}

// ============================================================
// BUTTON STATE MANAGEMENT
// ============================================================

function updateButtonState(state) {
    if (state === 'continue') {
        btnText.textContent = 'Continue';
        sendIcon.className = 'fas fa-arrow-right';
        sendIcon.style.display = 'inline';
        sendBtn.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
        sendBtn.className = 'continue-mode';
    } else if (state === 'send') {
        btnText.textContent = 'Send';
        sendIcon.className = 'fas fa-paper-plane';
        sendIcon.style.display = 'inline';
        sendBtn.style.background = 'linear-gradient(135deg, #4f46e5, #7c3aed)';
        sendBtn.className = '';
    } else if (state === 'loading') {
        btnText.textContent = 'Sending...';
        sendIcon.style.display = 'none';
        sendBtn.style.background = 'linear-gradient(135deg, #4f46e5, #7c3aed)';
        sendBtn.className = '';
    }
}

// ============================================================
// SEND MESSAGE - MAIN FUNCTION
// ============================================================

window.sendMessage = async function() {
    if (sendBtn.disabled) return;
    
    hideError();
    const message = userInput.value.trim();

    if (!message) {
        showError('Please enter your message.');
        userInput.focus();
        return;
    }

    addMessage(message, true);
    userInput.value = '';
    userInput.style.height = 'auto';
    
    addLoadingMessage();
    setLoading(true);
    updateButtonState('loading');

    try {
        const response = await fetch("/api/travel", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                thread_id: currentThreadId
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Something went wrong.");
        }

        currentThreadId = data.thread_id;
        localStorage.setItem("travel_thread_id", currentThreadId);

        removeLoadingMessage();

        const isComplete = data.is_complete !== false;
        const missingInfo = data.missing_info || [];
        addMessage(data.answer, false, isComplete, missingInfo);

        if (!isComplete) {
            updateButtonState('continue');
            setTimeout(() => userInput.focus(), 300);
        } else {
            updateButtonState('send');
        }

    } catch (error) {
        removeLoadingMessage();
        showError(error.message || 'An unexpected error occurred.');
        updateButtonState('send');
    } finally {
        setLoading(false);
    }
};

// ============================================================
// QUICK PROMPT
// ============================================================

window.sendQuickPrompt = function(text) {
    const welcomeMsg = chatMessages.querySelector('.bot-message:first-child');
    chatMessages.innerHTML = '';
    if (welcomeMsg) {
        chatMessages.appendChild(welcomeMsg);
    }
    
    currentThreadId = null;
    localStorage.removeItem("travel_thread_id");
    isWaitingForInfo = false;
    messageHistory = [];
    updateButtonState('send');
    
    userInput.value = text;
    setTimeout(() => sendMessage(), 100);
};

// ============================================================
// CLEAR CHAT
// ============================================================

window.clearChat = function() {
    if (messageHistory.length === 0) return;
    
    if (confirm('Clear the conversation?')) {
        const welcomeMsg = chatMessages.querySelector('.bot-message:first-child');
        chatMessages.innerHTML = '';
        if (welcomeMsg) {
            chatMessages.appendChild(welcomeMsg);
        }
        
        currentThreadId = null;
        localStorage.removeItem("travel_thread_id");
        isWaitingForInfo = false;
        messageHistory = [];
        updateButtonState('send');
        userInput.value = '';
        userInput.style.height = 'auto';
        hideError();
        userInput.focus();
    }
};

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function setLoading(isLoading) {
    sendBtn.disabled = isLoading;
    if (isLoading) {
        btnLoader.classList.remove('hidden');
    } else {
        btnLoader.classList.add('hidden');
    }
}

function showError(message) {
    errorBox.classList.remove('hidden');
    errorText.textContent = message;
    
    if (window.errorTimeout) {
        clearTimeout(window.errorTimeout);
    }
    window.errorTimeout = setTimeout(() => {
        errorBox.classList.add('hidden');
    }, 5000);
}

function hideError() {
    errorBox.classList.add('hidden');
    errorText.textContent = '';
    if (window.errorTimeout) {
        clearTimeout(window.errorTimeout);
        window.errorTimeout = null;
    }
}

// ============================================================
// KEYBOARD SHORTCUTS
// ============================================================

document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
        return;
    }
    
    if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        sendMessage();
    }
    
    if (e.key === 'Escape') {
        hideError();
        userInput.blur();
    }
});

// ============================================================
// AUTO-RESIZE TEXTAREA
// ============================================================

function autoResize() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 100) + 'px';
}

userInput.addEventListener('input', autoResize);

// ============================================================
// PASTE HANDLING
// ============================================================

userInput.addEventListener('paste', (e) => {
    setTimeout(autoResize, 50);
});

// ============================================================
// INITIALIZATION
// ============================================================

configureMarked();
updateButtonState('send');
setTimeout(autoResize, 100);
setTimeout(() => userInput.focus(), 200);

console.log('🚀 TripMate AI Chatbot initialized');
console.log('📌 Thread ID:', currentThreadId || 'New conversation');
console.log('💡 Press Enter to send, Shift+Enter for new line');
console.log('💡 Budget tables are rendered by frontend');

window.__tripMate = {
    state: {
        currentThreadId,
        isWaitingForInfo,
        messageHistory
    },
    clearChat: window.clearChat,
    sendMessage: window.sendMessage,
    extractBudgetData: extractBudgetData
};