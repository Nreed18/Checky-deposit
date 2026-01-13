let currentCheckId = null;

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.editable-field').forEach(field => {
        field.addEventListener('change', handleFieldChange);
        field.addEventListener('blur', handleFieldChange);
    });

    document.querySelectorAll('.search-contact-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            currentCheckId = this.dataset.checkId;
            openContactModal();
        });
    });

    document.getElementById('submitBtn').addEventListener('click', submitBatch);
    
    updateTotalAmount();
});

async function handleFieldChange(e) {
    const field = e.target;
    const checkCard = field.closest('.check-card');
    const checkId = checkCard.dataset.checkId;
    const fieldName = field.dataset.field;
    const value = field.value;

    field.classList.add('modified');

    try {
        const response = await fetch(`/api/check/${checkId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                [fieldName]: value
            })
        });

        if (response.ok) {
            setTimeout(() => {
                field.classList.remove('modified');
            }, 1000);

            if (fieldName === 'amount') {
                updateTotalAmount();
            }
        }
    } catch (error) {
        console.error('Failed to save:', error);
    }
}

function updateTotalAmount() {
    let total = 0;
    document.querySelectorAll('[data-field="amount"]').forEach(field => {
        const val = parseFloat(field.value) || 0;
        total += val;
    });
    
    const totalElement = document.getElementById('totalAmount');
    totalElement.textContent = '$' + total.toFixed(2);
    
    const warningElement = document.getElementById('totalWarning');
    if (expectedAmount > 0) {
        const diff = Math.abs(total - expectedAmount);
        if (diff > 0.01) {
            warningElement.style.display = 'block';
            totalElement.classList.add('total-mismatch');
            totalElement.classList.remove('total-match');
        } else {
            warningElement.style.display = 'none';
            totalElement.classList.add('total-match');
            totalElement.classList.remove('total-mismatch');
        }
    }
}

function openLightbox(img) {
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightboxImage');
    lightboxImg.src = img.src;
    lightbox.style.display = 'flex';
}

function closeLightbox() {
    document.getElementById('lightbox').style.display = 'none';
}

function openContactModal() {
    const checkCard = document.querySelector(`[data-check-id="${currentCheckId}"]`);
    const name = checkCard.querySelector('[data-field="name"]').value;
    const zip = checkCard.querySelector('[data-field="zip_code"]').value;

    document.getElementById('contactSearchName').value = name;
    document.getElementById('contactSearchZip').value = zip;
    document.getElementById('contactSearchModal').style.display = 'flex';
    document.getElementById('contactResults').innerHTML = '';
}

function closeContactModal() {
    document.getElementById('contactSearchModal').style.display = 'none';
    currentCheckId = null;
}

async function searchContacts() {
    const name = document.getElementById('contactSearchName').value;
    const zip = document.getElementById('contactSearchZip').value;
    const resultsDiv = document.getElementById('contactResults');

    resultsDiv.innerHTML = '<p>Searching...</p>';

    try {
        const response = await fetch(`/api/search_contacts?name=${encodeURIComponent(name)}&zip=${encodeURIComponent(zip)}`);
        const data = await response.json();

        if (data.error) {
            resultsDiv.innerHTML = `<p class="error">${data.error}</p>`;
            return;
        }

        if (data.contacts.length === 0) {
            resultsDiv.innerHTML = '<p>No contacts found</p>';
            return;
        }

        resultsDiv.innerHTML = data.contacts.map(contact => {
            const confidenceClass = contact.confidence >= 0.8 ? 'confidence-high' : 
                                   contact.confidence >= 0.5 ? 'confidence-medium' : 'confidence-low';
            return `
                <div class="contact-result" onclick="selectContact('${contact.id}', '${contact.name.replace(/'/g, "\\'")}')">
                    <div class="contact-info">
                        <strong>${contact.name}</strong>
                        <small>${contact.email || ''} ${contact.address ? '| ' + contact.address : ''} ${contact.city ? contact.city + ', ' : ''}${contact.state || ''} ${contact.zip || ''}</small>
                    </div>
                    <span class="confidence-score ${confidenceClass}">${Math.round(contact.confidence * 100)}%</span>
                </div>
            `;
        }).join('');
    } catch (error) {
        resultsDiv.innerHTML = '<p class="error">Search failed. Please try again.</p>';
    }
}

async function selectContact(contactId, contactName) {
    try {
        await fetch(`/api/check/${currentCheckId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                hubspot_contact_id: contactId,
                needs_review: false
            })
        });

        const checkCard = document.querySelector(`[data-check-id="${currentCheckId}"]`);
        checkCard.querySelector('.contact-name').textContent = contactName;
        
        checkCard.classList.remove('check-needs-review');
        checkCard.classList.add('check-matched');
        
        const badge = checkCard.querySelector('.badge');
        if (badge) {
            badge.className = 'badge badge-success';
            badge.textContent = 'Matched (Manual)';
        }

        closeContactModal();
    } catch (error) {
        console.error('Failed to select contact:', error);
    }
}

async function submitBatch(forceSubmit = false) {
    if (expectedAmount > 0 && !forceSubmit) {
        let total = 0;
        document.querySelectorAll('[data-field="amount"]').forEach(field => {
            total += parseFloat(field.value) || 0;
        });
        
        const diff = Math.abs(total - expectedAmount);
        if (diff > 0.01) {
            const confirmMsg = `Warning: The reviewed total ($${total.toFixed(2)}) does not match the expected amount ($${expectedAmount.toFixed(2)}).\n\nDifference: $${diff.toFixed(2)}\n\nAre you sure you want to submit?`;
            if (!confirm(confirmMsg)) {
                return;
            }
            return submitBatch(true);
        }
    }
    
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';

    try {
        const response = await fetch(`/api/submit/${batchId}`, {
            method: 'POST',
            headers: forceSubmit ? { 'Content-Type': 'application/json' } : {},
            body: forceSubmit ? JSON.stringify({ force_submit: true }) : undefined
        });

        const data = await response.json();

        if (data.success) {
            alert(`Successfully created ${data.deals_created} deals in HubSpot!`);
            if (data.errors && data.errors.length > 0) {
                alert('Some errors occurred:\n' + data.errors.join('\n'));
            }
            window.location.href = '/';
        } else {
            alert('Submission failed: ' + (data.error || 'Unknown error'));
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit to HubSpot';
        }
    } catch (error) {
        alert('Network error. Please try again.');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit to HubSpot';
    }
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeLightbox();
        closeContactModal();
    }
});
