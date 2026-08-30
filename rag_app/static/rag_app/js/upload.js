/**
 * Cyberpunk Document Upload & Matrix Fast Scanner Engine
 */

document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const scanner = document.getElementById('matrix-scanner');
    const logContainer = document.getElementById('scanner-logs');
    const progressBar = document.getElementById('progress-bar');
    const uploadStatus = document.getElementById('upload-status');

    if (!dropzone || !fileInput) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
            fileInput.files = files;
            handleFileUpload(files[0]);
        }
    });

    dropzone.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileUpload(e.target.files[0]);
        }
    });

    function logStep(text, type = 'info') {
        const time = new Date().toLocaleTimeString();
        const p = document.createElement('p');
        const color = type === 'error' ? 'var(--neon-pink)' : type === 'success' ? 'var(--neon-green)' : 'var(--neon-cyan)';
        p.style.color = color;
        p.style.marginBottom = '4px';
        p.innerHTML = `<span style="opacity:0.6">[${time}]</span> <span>⚡ ${text}</span>`;
        logContainer.appendChild(p);
        scanner.scrollTop = scanner.scrollHeight;
    }

    async function handleFileUpload(file) {
        if (!file) return;

        scanner.style.display = 'block';
        logContainer.innerHTML = '';
        progressBar.style.width = '15%';
        progressBar.style.background = 'var(--neon-cyan)';
        uploadStatus.innerText = 'UPLOADING TO MATRIX CORE...';

        logStep(`Uploading ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)...`);

        const formData = new FormData();
        formData.append('file', file);
        formData.append('title', file.name);

        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

        try {
            const response = await fetch('/api/documents/upload/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                },
                body: formData
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Upload request failed.');
            }

            const docId = data.document_id;
            const redirectUrl = data.redirect_url || `/chat/${docId}/`;

            progressBar.style.width = '35%';
            uploadStatus.innerText = 'VECTORIZING DOCUMENT IN BATCHES...';
            logStep("Document uploaded. Parsing text and computing batch vector embeddings...");

            // Poll status until indexed
            let currentPct = 35;
            const pollInterval = setInterval(async () => {
                try {
                    const statusRes = await fetch(`/api/documents/${docId}/status/`);
                    if (statusRes.ok) {
                        const statusData = await statusRes.json();
                        
                        if (statusData.status === 'indexed') {
                            clearInterval(pollInterval);
                            progressBar.style.width = '100%';
                            uploadStatus.innerText = 'INDEXING COMPLETE! REDIRECTING...';
                            logStep(`Done! Indexed ${statusData.total_chunks} semantic chunks successfully.`, 'success');
                            setTimeout(() => {
                                window.location.href = redirectUrl;
                            }, 500);
                        } else if (statusData.status === 'failed') {
                            clearInterval(pollInterval);
                            progressBar.style.width = '100%';
                            progressBar.style.background = 'var(--neon-pink)';
                            uploadStatus.innerText = 'INDEXING FAILED';
                            logStep(`Error: ${statusData.error_message || 'Indexing failed'}`, 'error');
                        } else {
                            // Still processing - increment progress bar smoothly
                            if (currentPct < 90) {
                                currentPct += 10;
                                progressBar.style.width = `${currentPct}%`;
                            }
                        }
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }, 600);

        } catch (err) {
            progressBar.style.width = '100%';
            progressBar.style.background = 'var(--neon-pink)';
            logStep(`ERROR: ${err.message}`, 'error');
            uploadStatus.innerText = 'UPLOAD ANOMALY';
            if (window.cyberAlert) {
                await window.cyberAlert(`Upload Error: ${err.message}`, 'UPLOAD ERROR', '❌');
            } else {
                alert(`Upload Error: ${err.message}`);
            }
        }
    }

    // Attach document delete handlers
    document.querySelectorAll('.btn-delete-doc').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            const docId = btn.getAttribute('data-doc-id');
            const docTitle = btn.getAttribute('data-doc-title') || 'this document';
            
            const confirmed = window.cyberConfirm 
                ? await window.cyberConfirm(`Are you sure you want to delete "${docTitle}"? All associated vectors and chat history will be permanently deleted.`, 'CONFIRM DELETION', '⚠️')
                : confirm(`Delete document "${docTitle}"?`);

            if (confirmed) {
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
                try {
                    const res = await fetch(`/api/documents/${docId}/delete/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': csrfToken,
                        }
                    });
                    if (res.ok) {
                        window.location.reload();
                    } else {
                        if (window.cyberAlert) {
                            await window.cyberAlert("Failed to delete document.", "SYSTEM ERROR", "❌");
                        } else {
                            alert("Failed to delete document.");
                        }
                    }
                } catch (e) {
                    if (window.cyberAlert) {
                        await window.cyberAlert("Network error deleting document.", "NETWORK ERROR", "❌");
                    } else {
                        alert("Network error deleting document.");
                    }
                }
            }
        });
    });
});
