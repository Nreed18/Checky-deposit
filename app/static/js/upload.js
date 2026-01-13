document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('uploadForm');
    const fileInput = document.getElementById('pdf_file');
    const fileDisplay = document.querySelector('.file-upload-display');
    const fileText = document.querySelector('.file-text');
    const fileName = document.querySelector('.file-name');
    const uploadBtn = document.getElementById('uploadBtn');
    const btnText = uploadBtn.querySelector('.btn-text');
    const btnLoading = uploadBtn.querySelector('.btn-loading');
    const errorDiv = document.getElementById('uploadError');

    fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            fileText.style.display = 'none';
            fileName.style.display = 'block';
            fileName.textContent = this.files[0].name;
            fileDisplay.style.borderColor = '#27ae60';
            fileDisplay.style.backgroundColor = '#f0fff4';
        } else {
            fileText.style.display = 'block';
            fileName.style.display = 'none';
            fileDisplay.style.borderColor = '#bdc3c7';
            fileDisplay.style.backgroundColor = 'transparent';
        }
    });

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        errorDiv.style.display = 'none';
        
        if (!fileInput.files.length) {
            showError('Please select a PDF file');
            return;
        }

        btnText.style.display = 'none';
        btnLoading.style.display = 'inline';
        uploadBtn.disabled = true;

        const formData = new FormData(form);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                window.location.href = data.redirect;
            } else {
                showError(data.error || 'Upload failed');
                resetButton();
            }
        } catch (error) {
            showError('Network error. Please try again.');
            resetButton();
        }
    });

    function showError(message) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }

    function resetButton() {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
        uploadBtn.disabled = false;
    }
});
