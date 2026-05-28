/**
 * Chat Interface JavaScript
 * Handles sending messages, uploading PDFs, and displaying responses
 */

// Get backend URL from meta tag (set by FastAPI)
const BACKEND_URL = document.querySelector('meta[name="backend-url"]')?.content || 'http://localhost:8001';

// DOM elements
const chatHistory = document.getElementById('chatHistory');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const pdfUpload = document.getElementById('pdfUpload');
const fileName = document.getElementById('fileName');
const loading = document.getElementById('loading');

// Store uploaded PDF content
let uploadedPDFText = null;

// Send message when Enter key is pressed
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Send message when Send button is clicked
sendBtn.addEventListener('click', sendMessage);

// Handle PDF file upload
pdfUpload.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    // Display file name
    fileName.textContent = `📄 ${file.name}`;
    
    try {
        // Convert PDF to text
        const text = await extractPDFText(file);
        uploadedPDFText = text;
        
        // Show success message
        const truncated = text.substring(0, 100);
        addMessageToChat(`📎 Uploaded: ${file.name}\nExtracted content preview:\n${truncated}...`, 'bot-message');
    } catch (error) {
        console.error('PDF extraction error:', error);
        addMessageToChat('❌ Failed to extract text from PDF. Please try again.', 'bot-message');
        uploadedPDFText = null;
        fileName.textContent = '';
    }
});

/**
 * Extract text from PDF file
 */
async function extractPDFText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        
        reader.onload = async function(e) {
            try {
                const typedarray = new Uint8Array(e.target.result);
                
                // Load PDF document
                const pdf = await pdfjsLib.getDocument({ data: typedarray }).promise;
                let fullText = '';
                
                // Extract text from each page
                for (let i = 1; i <= pdf.numPages; i++) {
                    const page = await pdf.getPage(i);
                    const textContent = await page.getTextContent();
                    const pageText = textContent.items.map(item => item.str).join(' ');
                    fullText += `\n--- Page ${i} ---\n${pageText}`;
                }
                
                resolve(fullText);
            } catch (error) {
                reject(error);
            }
        };
        
        reader.onerror = reject;
        reader.readAsArrayBuffer(file);
    });
}

/**
 * Send message to backend
 */
async function sendMessage() {
    const message = userInput.value.trim();
    
    // Don't send empty messages
    if (!message && !uploadedPDFText) return;
    
    // Add user message to chat
    addMessageToChat(message || '📎 Uploaded PDF for analysis', 'user-message');
    
    // Clear input
    userInput.value = '';
    
    // Show loading indicator
    loading.style.display = 'block';
    scrollToBottom();
    
    try {
        // Prepare request body
        const requestBody = {
            message: message || 'Please analyze this PDF content',
            pdf_content: uploadedPDFText || null,
            timestamp: new Date().toISOString()
        };
        
        // Send to backend
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Add bot response to chat
        addMessageToChat(data.response || data.message || 'I received your message!', 'bot-message');
        
        // Clear uploaded PDF after sending (optional)
        if (uploadedPDFText) {
            uploadedPDFText = null;
            fileName.textContent = '';
            pdfUpload.value = '';
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        addMessageToChat('❌ Sorry, I encountered an error. Please check if the backend server is running.', 'bot-message');
    } finally {
        loading.style.display = 'none';
        scrollToBottom();
    }
}

/**
 * Add a message to the chat history
 */
function addMessageToChat(text, senderClass) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${senderClass}`;
    
    const time = new Date().toLocaleTimeString();
    
    // Handle line breaks in text
    const formattedText = text.replace(/\n/g, '<br>');
    
    messageDiv.innerHTML = `
        <div class="message-content">
            ${formattedText}
            <div class="message-time">${time}</div>
        </div>
    `;
    
    chatHistory.appendChild(messageDiv);
    scrollToBottom();
}

/**
 * Scroll chat history to bottom
 */
function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
}