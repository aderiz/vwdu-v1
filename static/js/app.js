// VW Down Under Price Updater - Frontend JavaScript

const socket = io();
let isProcessing = false;
let startTime = null;
let timerInterval = null;

// DOM Elements
const uploadForm = document.getElementById('uploadForm');
const csvFile = document.getElementById('csvFile');
const fileName = document.getElementById('fileName');
const uploadBtn = document.getElementById('uploadBtn');
const cancelBtn = document.getElementById('cancelBtn');
const progressSection = document.getElementById('progressSection');
const resultsSection = document.getElementById('resultsSection');
const downloadSection = document.getElementById('downloadSection');

// File input change handler
csvFile.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        fileName.textContent = file.name;
    } else {
        fileName.textContent = 'No file selected';
    }
});

// Form submission handler
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const file = csvFile.files[0];
    if (!file) {
        alert('Please select a CSV file');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    // Add test mode flag
    const testMode = document.getElementById('testMode').checked;
    formData.append('test_mode', testMode ? 'true' : 'false');
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            startProcessing();
            addLogEntry(`Started processing: ${result.filename}`, 'info');
        } else {
            alert(`Error: ${result.error}`);
        }
    } catch (error) {
        alert(`Upload failed: ${error.message}`);
    }
});

// Cancel button handler
cancelBtn.addEventListener('click', async () => {
    if (confirm('Are you sure you want to cancel processing?')) {
        try {
            await fetch('/cancel', { method: 'POST' });
            stopProcessing();
            addLogEntry('Processing cancelled by user', 'error');
        } catch (error) {
            console.error('Cancel failed:', error);
        }
    }
});

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const tabName = e.target.dataset.tab;
        
        // Update active button
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        
        // Show selected tab
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
        });
        document.getElementById(`${tabName}Tab`).classList.add('active');
    });
});

// Socket.IO event handlers
socket.on('connect', () => {
    console.log('Connected to server');
    addLogEntry('Connected to server', 'info');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    addLogEntry('Disconnected from server', 'error');
});

socket.on('status_update', (data) => {
    updateProgress(data);
});

socket.on('item_processing', (data) => {
    document.getElementById('currentItem').textContent = `${data.item_code}: ${data.item_name}`;
    addLogEntry(`Processing: ${data.item_code}`, 'info');
});

socket.on('item_updated', (data) => {
    addToUpdatesTable(data);
    addLogEntry(`✅ Updated: ${data.item_code} - £${data.old_price.toFixed(2)} → £${data.new_price.toFixed(2)}`, 'success');
});

socket.on('item_unchanged', (data) => {
    addToUnchangedTable(data);
});

socket.on('item_error', (data) => {
    addToErrorsTable(data);
    addLogEntry(`❌ Error: ${data.item_code} - ${data.error}`, 'error');
});

socket.on('processing_complete', (data) => {
    stopProcessing();
    showDownloadButtons(data.output_file, data.report_file);
    addLogEntry('Processing completed successfully!', 'success');
    alert('Processing complete! You can now download the results.');
});

socket.on('processing_error', (data) => {
    stopProcessing();
    addLogEntry(`Processing error: ${data.error}`, 'error');
    alert(`Processing error: ${data.error}`);
});

// Helper functions
function startProcessing() {
    isProcessing = true;
    uploadBtn.style.display = 'none';
    cancelBtn.style.display = 'inline-block';
    progressSection.style.display = 'block';
    resultsSection.style.display = 'block';
    
    // Clear previous results
    clearTables();
    
    // Start timer
    startTime = Date.now();
    updateTimer();
    timerInterval = setInterval(updateTimer, 1000);
}

function stopProcessing() {
    isProcessing = false;
    uploadBtn.style.display = 'inline-block';
    cancelBtn.style.display = 'none';
    
    // Stop timer
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

function updateProgress(data) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const statusText = document.getElementById('statusText');
    
    progressFill.style.width = `${data.progress_percent}%`;
    progressText.textContent = `${Math.round(data.progress_percent)}%`;
    statusText.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
    
    document.getElementById('processedCount').textContent = data.processed_items;
    document.getElementById('totalCount').textContent = data.total_items;
    document.getElementById('updatedCount').textContent = data.updates_count;
    document.getElementById('unchangedCount').textContent = data.unchanged_count;
    document.getElementById('errorCount').textContent = data.errors_count;
}

function addToUpdatesTable(data) {
    const tbody = document.querySelector('#updatesTable tbody');
    const row = tbody.insertRow();
    
    const changeColor = data.difference > 0 ? 'color: #e53e3e;' : 'color: #38a169;';
    const changeSymbol = data.difference > 0 ? '↑' : '↓';
    
    row.innerHTML = `
        <td>${data.item_code}</td>
        <td>${data.item_name}</td>
        <td>£${data.old_price.toFixed(2)}</td>
        <td>£${data.new_price.toFixed(2)}</td>
        <td style="${changeColor}">
            ${changeSymbol} £${Math.abs(data.difference).toFixed(2)} 
            (${data.difference_percent.toFixed(1)}%)
        </td>
        <td>${data.source}</td>
    `;
}

function addToErrorsTable(data) {
    const tbody = document.querySelector('#errorsTable tbody');
    const row = tbody.insertRow();
    
    row.innerHTML = `
        <td>${data.item_code}</td>
        <td>${data.item_name}</td>
        <td>£${data.current_price.toFixed(2)}</td>
        <td style="color: #e53e3e;">${data.error}</td>
    `;
}

function addToUnchangedTable(data) {
    const tbody = document.querySelector('#unchangedTable tbody');
    const row = tbody.insertRow();
    
    row.innerHTML = `
        <td>${data.item_code}</td>
        <td>${data.item_name}</td>
        <td>£${data.old_price.toFixed(2)}</td>
        <td>${data.source}</td>
    `;
}

function clearTables() {
    document.querySelector('#updatesTable tbody').innerHTML = '';
    document.querySelector('#errorsTable tbody').innerHTML = '';
    document.querySelector('#unchangedTable tbody').innerHTML = '';
}

function showDownloadButtons(csvFile, reportFile) {
    downloadSection.style.display = 'block';
    document.getElementById('downloadCsv').href = `/download/${csvFile}`;
    document.getElementById('downloadReport').href = `/download/${reportFile}`;
}

function updateTimer() {
    if (!startTime) return;
    
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const hours = Math.floor(elapsed / 3600);
    const minutes = Math.floor((elapsed % 3600) / 60);
    const seconds = elapsed % 60;
    
    const timeString = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    document.getElementById('elapsedTime').textContent = timeString;
}

function addLogEntry(message, type = 'info') {
    const logContent = document.getElementById('logContent');
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    
    const timestamp = new Date().toLocaleTimeString();
    entry.textContent = `[${timestamp}] ${message}`;
    
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
    
    // Keep only last 100 entries
    while (logContent.children.length > 100) {
        logContent.removeChild(logContent.firstChild);
    }
}