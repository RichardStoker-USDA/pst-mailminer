/**
 * Handles file upload via AJAX with progress tracking
 */
document.addEventListener('DOMContentLoaded', function() {
    // Check if organization key is available and show/hide button accordingly
    fetch('/check-trial-key')
        .then(response => response.json())
        .then(data => {
            if (!data.show_button) {
                // Hide the organization key button if no key is configured
                document.getElementById('useTrialApiKeyBtn').style.display = 'none';
            }
        })
        .catch(err => {
            console.error('Error checking organization key:', err);
        });
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Main elements
    const uploadForm = document.getElementById('uploadForm');
    const uploadCard = document.getElementById('uploadCard');
    const statusCard = document.getElementById('statusCard');
    const progressBar = document.getElementById('progressBar');
    const statusMessage = document.getElementById('statusMessage');
    const resultContainer = document.getElementById('resultContainer');
    const errorContainer = document.getElementById('errorContainer');
    const errorMessage = document.getElementById('errorMessage');
    const downloadBtn = document.getElementById('downloadBtn');
    const startNewBtn = document.getElementById('startNewBtn');
    const tryAgainBtn = document.getElementById('tryAgainBtn');
    const uploadBtn = document.getElementById('uploadBtn');
    const fileInput = document.getElementById('pst_file');
    const apiKeyInput = document.getElementById('api_key');
    const fileNameDisplay = document.getElementById('fileName');
    const fileSizeDisplay = document.getElementById('fileSize');
    const fileContainer = document.getElementById('fileContainer');
    const cancelAnalysisBtn = document.getElementById('cancelAnalysisBtn');
    const useTrialApiKeyBtn = document.getElementById('useTrialApiKeyBtn');
    const trialKeyNotice = document.getElementById('trialKeyNotice');
    const trialKeyMessage = document.getElementById('trialKeyMessage');
    const apiKeyFeedback = document.getElementById('apiKeyFeedback');
    
    // Community Monthly Limited Key - this is a placeholder that will be replaced with a real API key 
    // in the backend for security
    const TRIAL_KEY_PLACEHOLDER = '<<PRELOADED_KEY>>';
    let usingTrialKey = false;
    
    // Custom template wizard elements
    const wizardSteps = document.querySelectorAll('.wizard-step');
    const wizardPanels = document.querySelectorAll('.wizard-panel');
    const nextStepBtns = document.querySelectorAll('.next-step');
    const prevStepBtns = document.querySelectorAll('.prev-step');
    const addCategoryBtn = document.querySelector('.add-category-btn');
    const useTemplateBtn = document.getElementById('useTemplateBtn');
    const downloadTemplateBtn = document.getElementById('downloadTemplateBtn');
    const customTitleInput = document.getElementById('custom_title');
    const customContextInput = document.getElementById('custom_context');
    const customObjectiveInput = document.getElementById('custom_objective_primary');
    const customPromptTextarea = document.getElementById('custom_prompt');
    
    // File upload elements
    const dropArea = document.getElementById('dropArea');
    const browseBtn = document.getElementById('browseBtn');
    const removeFileBtn = document.getElementById('removeFileBtn');
    
    // Template file import
    const templateFileInput = document.getElementById('template_file');
    const browseTemplateBtn = document.getElementById('browseTemplateBtn');
    
    // Template selection
    const templateCards = document.querySelectorAll('.template-card');
    const customPromptContainer = document.getElementById('customPromptContainer');
    
    templateCards.forEach(card => {
        card.addEventListener('click', function() {
            // Update radio button
            const radio = this.querySelector('input[type="radio"]');
            radio.checked = true;
            
            // Update UI
            templateCards.forEach(c => c.classList.remove('selected'));
            this.classList.add('selected');
        });
        
        // Set initial selected state
        const radio = card.querySelector('input[type="radio"]');
        if (radio.checked) {
            card.classList.add('selected');
        }
    });
    
    // Wizard navigation
    if (wizardSteps && wizardPanels) {
        // Handle next step buttons
        nextStepBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const nextStep = this.getAttribute('data-goto');
                goToWizardStep(nextStep);
                generateTemplatePreview();
            });
        });
        
        // Handle previous step buttons
        prevStepBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                const prevStep = this.getAttribute('data-goto');
                goToWizardStep(prevStep);
            });
        });
        
        // Handle step clicks
        wizardSteps.forEach(step => {
            step.addEventListener('click', function() {
                const stepNum = this.getAttribute('data-step');
                goToWizardStep(stepNum);
            });
        });
        
        // Function to navigate between wizard steps
        function goToWizardStep(stepNumber) {
            // Update steps UI
            wizardSteps.forEach(s => {
                s.classList.remove('active');
                if (s.getAttribute('data-step') === stepNumber) {
                    s.classList.add('active');
                }
            });
            
            // Update panels
            wizardPanels.forEach(p => {
                p.classList.remove('active');
                if (p.getAttribute('data-panel') === stepNumber) {
                    p.classList.add('active');
                }
            });
        }
    }
    
    // Add category button
    if (addCategoryBtn) {
        addCategoryBtn.addEventListener('click', function() {
            const categories = document.querySelector('.objective-categories');
            const newCategory = document.createElement('div');
            newCategory.className = 'objective-category';
            newCategory.innerHTML = `
                <div class="d-flex">
                    <input type="text" class="form-control" placeholder="Category: E.g., Technical Issues">
                    <button type="button" class="btn btn-sm btn-outline-danger ms-2 remove-category-btn">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            `;
            
            // Insert before the add button
            categories.insertBefore(newCategory, this.parentNode);
            
            // Setup remove button
            const removeBtn = newCategory.querySelector('.remove-category-btn');
            removeBtn.addEventListener('click', function() {
                categories.removeChild(newCategory);
                generateTemplatePreview();
            });
            
            generateTemplatePreview();
        });
    }
    
    // Generate template from wizard inputs
    function generateTemplatePreview() {
        if (!customTitleInput || !customContextInput || !customObjectiveInput || !customPromptTextarea) {
            return;
        }
        
        const title = customTitleInput.value || "CUSTOM EMAIL ANALYSIS";
        const context = customContextInput.value || "These emails contain communications that need to be analyzed for insights and patterns.";
        const objective = customObjectiveInput.value || "Identify patterns and insights from email communications";
        
        // Get categories
        const categoryInputs = document.querySelectorAll('.objective-category input');
        let categories = [];
        categoryInputs.forEach((input, index) => {
            if (input.value) {
                categories.push(input.value);
            } else {
                categories.push(`Category ${index + 1}`);
            }
        });
        
        // Get selected output sections
        const outputSections = [];
        document.querySelectorAll('.output-sections .form-check-input:checked').forEach(checkbox => {
            outputSections.push(checkbox.nextElementSibling.textContent.trim());
        });
        
        // Build template
        let template = `# ${title.toUpperCase()}\n\n`;
        template += `## Context\n${context}\n\n`;
        template += `## Analysis Objectives\nConduct a detailed examination of these email communications to analyze:\n\n`;
        
        // Add categories
        categories.forEach((category, index) => {
            template += `### ${index + 1}. ${category.toUpperCase()}\n`;
            template += `- **Key Point 1**: Description of what to look for\n`;
            template += `- **Key Point 2**: Description of what to look for\n`;
            template += `- **Key Point 3**: Description of what to look for\n\n`;
        });
        
        // Add emails placeholder
        template += `## Emails to Analyze\n\n{emails}\n\n`;
        
        // Add output requirements
        template += `## Output Requirements\n\n`;
        outputSections.forEach((section, index) => {
            template += `### ${index + 1}. ${section}\n`;
            template += `- Include detailed findings with supporting evidence\n`;
            template += `- Provide specific examples from the emails\n`;
            template += `- Organize information in a clear, structured format\n\n`;
        });
        
        template += `Your analysis should be objective, evidence-based, and focused on providing valuable insights that can inform future decisions and actions.`;
        
        // Update the textarea
        customPromptTextarea.value = template;
    }
    
    // Use template button
    if (useTemplateBtn) {
        useTemplateBtn.addEventListener('click', function() {
            // Find the custom template radio button and select it
            const customRadio = document.querySelector('input[name="template"][value="custom"]');
            if (customRadio) {
                customRadio.checked = true;
            }
            
            // Switch to the presets tab to show it's selected
            const presetsTab = document.getElementById('presets-tab');
            const customTab = document.getElementById('custom-tab');
            
            if (presetsTab && presetsTab.classList.contains('active')) {
                presetsTab.click();
            }
        });
    }
    
    // Download template button
    if (downloadTemplateBtn) {
        downloadTemplateBtn.addEventListener('click', function() {
            // If there's content in the textarea, download it
            if (customPromptTextarea && customPromptTextarea.value) {
                const template = customPromptTextarea.value;
                const blob = new Blob([template], {type: 'text/plain'});
                const url = URL.createObjectURL(blob);
                
                // Create temporary link and trigger download
                const a = document.createElement('a');
                const title = customTitleInput.value || "custom_template";
                const filename = title.toLowerCase().replace(/\s+/g, '_') + '.txt';
                
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        });
    }
    
    // File upload handling with drag and drop
    if (dropArea && fileInput) {
        // Click browse button to trigger file input
        if (browseBtn) {
            browseBtn.addEventListener('click', function() {
                fileInput.click();
            });
        }
        
        // Remove file button
        if (removeFileBtn) {
            removeFileBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                fileInput.value = '';
                fileContainer.classList.add('hidden');
                uploadBtn.disabled = true;
            });
        }
        
        // Handle drag events
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropArea.addEventListener(eventName, function(e) {
                e.preventDefault();
                e.stopPropagation();
            });
        });
        
        // Highlight when dragging over
        ['dragenter', 'dragover'].forEach(eventName => {
            dropArea.addEventListener(eventName, function() {
                dropArea.classList.add('highlight');
            });
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropArea.addEventListener(eventName, function() {
                dropArea.classList.remove('highlight');
            });
        });
        
        // Handle dropped files
        dropArea.addEventListener('drop', function(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            
            if (files.length > 0) {
                fileInput.files = files;
                
                // Trigger the change event manually
                const event = new Event('change');
                fileInput.dispatchEvent(event);
            }
        });
    }
    
    // Template file import
    if (templateFileInput && browseTemplateBtn) {
        browseTemplateBtn.addEventListener('click', function() {
            templateFileInput.click();
        });
        
        templateFileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                const file = this.files[0];
                
                // Read the file
                const reader = new FileReader();
                reader.onload = function(e) {
                    // Switch to the custom tab
                    document.getElementById('custom-tab').click();
                    
                    // Go to step 4 (review)
                    goToWizardStep('4');
                    
                    // Set the template text
                    if (customPromptTextarea) {
                        customPromptTextarea.value = e.target.result;
                    }
                    
                    // Select the custom template radio button
                    const customRadio = document.querySelector('input[name="template"][value="custom"]');
                    if (customRadio) {
                        customRadio.checked = true;
                    }
                };
                reader.readAsText(file);
            }
        });
    }
    
    // File selection handling
    fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            const file = this.files[0];
            const fileName = file.name;
            const fileSize = formatFileSize(file.size);
            
            fileNameDisplay.textContent = fileName;
            fileSizeDisplay.textContent = fileSize;
            fileContainer.classList.remove('hidden');
            
            // Enable upload button if API key is also present
            if (apiKeyInput.value.trim() !== '') {
                uploadBtn.disabled = false;
            }
        } else {
            fileContainer.classList.add('hidden');
            uploadBtn.disabled = true;
        }
    });
    
    // API key input handling
    apiKeyInput.addEventListener('input', function() {
        // If user starts typing their own key, disable trial mode
        if (usingTrialKey && this.value.trim() !== TRIAL_KEY_PLACEHOLDER) {
            disableTrialMode();
        }
        
        // Enable upload button if file is also selected
        if (fileInput.files.length > 0 && this.value.trim() !== '') {
            uploadBtn.disabled = false;
        } else {
            uploadBtn.disabled = true;
        }
    });
    
    // Trial API key button
    if (useTrialApiKeyBtn) {
        useTrialApiKeyBtn.addEventListener('click', function() {
            if (usingTrialKey) {
                // If already using trial key, toggle it off
                disableTrialMode();
            } else {
                // Otherwise check if trial key is valid and enable it
                checkTrialKeyValidity();
            }
        });
    }
    
    // Function to check if trial key is valid (not over monthly limit)
    function checkTrialKeyValidity() {
        // Show a loading state
        useTrialApiKeyBtn.disabled = true;
        useTrialApiKeyBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Checking...';
        
        // Make a test request to the server
        fetch('/check-trial-key', {
            method: 'GET'
        })
        .then(response => response.json())
        .then(data => {
            useTrialApiKeyBtn.disabled = false;
            useTrialApiKeyBtn.innerHTML = '<i class="bi bi-people"></i> Use Community Key';
            
            if (data.valid) {
                // Trial key is valid, enable trial mode
                enableTrialMode();
            } else if (data.error === 'missing_key') {
                // Trial key is not configured
                showTrialKeyMissing();
            } else {
                // Community key is over monthly limit, show error
                showTrialKeyError(data.message || 'Monthly quota exceeded for Community Limited Key. Please try again later or use your own API key.');
            }
        })
        .catch(error => {
            console.error('Error checking community key:', error);
            useTrialApiKeyBtn.disabled = false;
            useTrialApiKeyBtn.innerHTML = '<i class="bi bi-people"></i> Use Community Key';
            showTrialKeyError('Error checking Community Monthly Limited Key availability. Please try again later or use your own API key.');
        });
    }
    
    // Function to enable trial mode
    function enableTrialMode() {
        usingTrialKey = true;
        
        // Set the placeholder API key value
        apiKeyInput.value = TRIAL_KEY_PLACEHOLDER;
        apiKeyInput.disabled = true;
        
        // Add active class to the community key button and update text
        useTrialApiKeyBtn.classList.remove('btn-outline-primary');
        useTrialApiKeyBtn.classList.add('btn-primary');
        useTrialApiKeyBtn.innerHTML = '<i class="bi bi-people-fill"></i> Using Community Key';
        
        // Show the key notice
        trialKeyNotice.classList.remove('d-none');
        
        // Handle model restrictions based on allowed_models from API response
        fetch('/check-trial-key')
            .then(response => response.json())
            .then(data => {
                if (data.valid && data.allowed_models && data.allowed_models.length > 0) {
                    // We have model restrictions
                    const gpt4oMiniRadio = document.getElementById('model-gpt4o-mini');
                    const gpt4oRadio = document.getElementById('model-gpt4o');
                    const allowedModels = data.allowed_models;
                    
                    // Handle GPT-4o
                    if (gpt4oRadio) {
                        if (allowedModels.includes('gpt-4o')) {
                            gpt4oRadio.disabled = false;
                        } else {
                            gpt4oRadio.disabled = true;
                            const gpt4oLabel = document.querySelector('label[for="model-gpt4o"]');
                            if (gpt4oLabel) {
                                gpt4oLabel.style.opacity = '0.6';
                                gpt4oLabel.style.cursor = 'not-allowed';
                            }
                        }
                    }
                    
                    // Handle GPT-4o-mini
                    if (gpt4oMiniRadio) {
                        if (allowedModels.includes('gpt-4o-mini')) {
                            gpt4oMiniRadio.disabled = false;
                            // If gpt-4o is disabled, ensure gpt-4o-mini is selected
                            if (gpt4oRadio && gpt4oRadio.disabled) {
                                gpt4oMiniRadio.checked = true;
                            }
                        } else {
                            gpt4oMiniRadio.disabled = true;
                            const gpt4oMiniLabel = document.querySelector('label[for="model-gpt4o-mini"]');
                            if (gpt4oMiniLabel) {
                                gpt4oMiniLabel.style.opacity = '0.6';
                                gpt4oMiniLabel.style.cursor = 'not-allowed';
                            }
                            
                            // If both are disabled, this is an error
                            if (gpt4oRadio && gpt4oRadio.disabled) {
                                showTrialKeyError('No allowed models available with the organization API key.');
                            }
                        }
                    }
                }
            })
            .catch(err => {
                console.error('Error checking allowed models:', err);
            });
        
        // Enable upload button if file is selected
        if (fileInput.files.length > 0) {
            uploadBtn.disabled = false;
        }
    }
    
    // Function to disable trial mode
    function disableTrialMode() {
        usingTrialKey = false;
        
        // Clear the API key input if it still has the placeholder
        if (apiKeyInput.value === TRIAL_KEY_PLACEHOLDER) {
            apiKeyInput.value = '';
        }
        
        // Enable the API key input
        apiKeyInput.disabled = false;
        
        // Reset the community key button
        useTrialApiKeyBtn.classList.add('btn-outline-primary');
        useTrialApiKeyBtn.classList.remove('btn-primary');
        useTrialApiKeyBtn.innerHTML = '<i class="bi bi-people"></i> Use Community Key';
        
        // Hide the key notice
        trialKeyNotice.classList.add('d-none');
        
        // Re-enable all model options
        const gpt4oRadio = document.getElementById('model-gpt4o');
        const gpt4oMiniRadio = document.getElementById('model-gpt4o-mini');
        
        if (gpt4oRadio) {
            gpt4oRadio.disabled = false;
            const gpt4oLabel = document.querySelector('label[for="model-gpt4o"]');
            if (gpt4oLabel) {
                gpt4oLabel.style.opacity = '';
                gpt4oLabel.style.cursor = '';
            }
        }
        
        if (gpt4oMiniRadio) {
            gpt4oMiniRadio.disabled = false;
            const gpt4oMiniLabel = document.querySelector('label[for="model-gpt4o-mini"]');
            if (gpt4oMiniLabel) {
                gpt4oMiniLabel.style.opacity = '';
                gpt4oMiniLabel.style.cursor = '';
            }
        }
        
        // Disable upload button if API key is empty
        if (apiKeyInput.value.trim() === '') {
            uploadBtn.disabled = true;
        }
    }
    
    // Function to show community key error
    function showTrialKeyError(message) {
        trialKeyNotice.classList.remove('d-none');
        trialKeyNotice.classList.remove('alert-success');
        trialKeyNotice.classList.add('alert-warning');
        trialKeyMessage.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-2"></i>${message}`;
    }
    
    // Function to show community key missing message
    function showTrialKeyMissing() {
        // If the community key is missing, just hide the button completely
        useTrialApiKeyBtn.style.display = 'none';
    }
    
    // Form submission
    uploadForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Basic validation
        if (fileInput.files.length === 0) {
            showError('Please select a PST file to upload.');
            return;
        }
        
        if (apiKeyInput.value.trim() === '') {
            showError('Please enter your OpenAI API key or use the trial key.');
            return;
        }
        
        // Get selected model
        let model = 'gpt-4o'; // Default model
        document.querySelectorAll('input[name="model"]').forEach(radio => {
            if (radio.checked) {
                model = radio.value;
            }
        });
        
        // Get selected template
        let templateKey = 'teams_migration';
        document.querySelectorAll('input[name="template"]').forEach(radio => {
            if (radio.checked) {
                templateKey = radio.value;
            }
        });
        
        // Check if custom template requires a prompt
        if (templateKey === 'custom') {
            const customPrompt = document.getElementById('custom_prompt').value.trim();
            if (customPrompt === '') {
                showError('Please enter a custom analysis prompt.');
                return;
            }
        }
        
        // Show status card with validating API key message
        uploadCard.style.display = 'none';
        statusCard.style.display = 'block';
        resultContainer.classList.add('hidden');
        errorContainer.classList.add('hidden');
        progressBar.style.width = '0%';
        statusMessage.textContent = 'Validating API key...';
        
        // Initialize fun messages
        const funMessage = document.getElementById('funMessage');
        const progressPercentage = document.getElementById('progressPercentage');
        
        if (funMessage && progressPercentage) {
            progressPercentage.textContent = '0%';
            funMessage.textContent = 'Checking your API key before we begin...';
        }
        
        // Get form data
        const formData = new FormData(uploadForm);
        
        // If using trial key, add a special form field to indicate this
        if (usingTrialKey) {
            formData.set('using_trial_key', 'true');
        }
        
        // Add or retrieve session ID
        let sessionId = localStorage.getItem('pst_mailminer_session_id');
        if (!sessionId) {
            sessionId = 'session_' + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
            localStorage.setItem('pst_mailminer_session_id', sessionId);
        }
        formData.set('session_id', sessionId);
        
        // Upload file - API key validation happens on server before processing starts
        uploadFile(formData);
    });
    
    function uploadFile(formData) {
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    // Show more user-friendly message for job in progress
                    if (data.error && data.error.includes('A job is already in progress')) {
                        // Create a special error modal for this case
                        showJobInProgressMessage();
                        throw new Error('HANDLED');
                    }
                    
                    // For API key errors, show a better message
                    if (data.error && data.error.includes('Invalid API key')) {
                        throw new Error('Your API key is invalid. Please check your OpenAI API key and try again.');
                    }
                    
                    throw new Error(data.error || 'Server error occurred');
                });
            }
            return response.json();
        })
        .then(data => {
            // Update status message to show we're moving to the next step
            statusMessage.textContent = 'API key validated! Starting analysis...';
            if (funMessage) {
                funMessage.textContent = 'API key is good! Now unpacking your emails...';
            }
            
            // Start polling for status
            pollStatus();
        })
        .catch(error => {
            if (error.message !== 'HANDLED') {
                showError(error.message || 'An error occurred while uploading the file.');
                console.error('Error:', error);
            }
        });
    }
    
    let jobPollInterval = null;

    function showJobInProgressMessage() {
        // Create a modal element
        const modalDiv = document.createElement('div');
        modalDiv.className = 'modal fade';
        modalDiv.id = 'jobInProgressModal';
        modalDiv.setAttribute('tabindex', '-1');
        modalDiv.setAttribute('aria-labelledby', 'jobInProgressModalLabel');
        modalDiv.setAttribute('aria-hidden', 'true');
        
        modalDiv.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header bg-info">
                        <h5 class="modal-title" id="jobInProgressModalLabel">Analysis Already in Progress</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <div class="d-flex align-items-center mb-3">
                            <i class="bi bi-hourglass-split text-info me-3" style="font-size: 2rem;"></i>
                            <p class="mb-0">Another analysis is currently running. Your analysis will start automatically when the current job completes.</p>
                        </div>
                        <div class="current-job-status p-3 bg-light rounded mb-3">
                            <h6 class="text-muted mb-2"><i class="bi bi-info-circle me-2"></i>Current Job Status</h6>
                            <div class="d-flex align-items-center">
                                <div class="spinner-border text-primary me-2" role="status" style="width: 1rem; height: 1rem;">
                                    <span class="visually-hidden">Loading...</span>
                                </div>
                                <span id="currentJobProgress">Checking status...</span>
                            </div>
                            <div class="progress mt-2" style="height: 6px;">
                                <div id="currentJobProgressBar" class="progress-bar" role="progressbar" style="width: 0%"></div>
                            </div>
                        </div>
                        <p class="text-muted small">You can close this window and check back later. Your analysis will start automatically when the server is available.</p>
                        <div class="alert alert-success d-none" id="jobCompletedAlert">
                            <i class="bi bi-check-circle me-2"></i>
                            <span>Current job completed! You can start your analysis now.</span>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">OK</button>
                        <button type="button" class="btn btn-success d-none" id="startQueuedJobBtn">
                            <i class="bi bi-play-fill me-1"></i>Start My Analysis
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modalDiv);
        
        // Initialize and show the modal
        const modal = new bootstrap.Modal(modalDiv);
        modal.show();
        
        // Function to update current job status
        function updateCurrentJobStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const progressBar = document.getElementById('currentJobProgressBar');
                    const progressText = document.getElementById('currentJobProgress');
                    const completedAlert = document.getElementById('jobCompletedAlert');
                    const startBtn = document.getElementById('startQueuedJobBtn');
                    
                    if (data.status === 'processing') {
                        // Update progress
                        progressBar.style.width = `${data.progress}%`;
                        progressText.textContent = `${data.message} (${data.progress}% complete)`;
                    } 
                    else if (data.status === 'completed' || data.status === 'idle' || data.status === 'cancelled') {
                        // Job is done
                        clearInterval(jobPollInterval);
                        completedAlert.classList.remove('d-none');
                        startBtn.classList.remove('d-none');
                        progressText.textContent = 'Server is now available!';
                        progressBar.style.width = '100%';
                        progressBar.classList.add('bg-success');
                    }
                })
                .catch(error => {
                    console.error('Error checking job status:', error);
                });
        }
        
        // Start polling for job status
        updateCurrentJobStatus();
        jobPollInterval = setInterval(updateCurrentJobStatus, 3000);
        
        // Add event listener to the start button
        const startBtn = document.getElementById('startQueuedJobBtn');
        startBtn.addEventListener('click', function() {
            modal.hide();
            // Get the form data and submit
            const formData = new FormData(uploadForm);
            uploadFile(formData);
        });
        
        // Clean up when the modal is hidden
        modalDiv.addEventListener('hidden.bs.modal', function() {
            clearInterval(jobPollInterval);
            document.body.removeChild(modalDiv);
        });
    }
    
    // Track existing summaries to prevent duplicates
    const processedSummaries = new Set();
    // Keep track of first poll for elapsed time
    let startTime = null;
    
    function pollStatus() {
        // Get session ID
        const sessionId = localStorage.getItem('pst_mailminer_session_id');
        
        fetch('/status' + (sessionId ? `?session_id=${sessionId}` : ''))
        .then(response => response.json())
        .then(data => {
            // Update progress
            progressBar.style.width = data.progress + '%';
            progressBar.setAttribute('aria-valuenow', data.progress);
            
            // Update percentage display
            const progressPercentage = document.getElementById('progressPercentage');
            if (progressPercentage) {
                progressPercentage.textContent = `${data.progress}%`;
            }
            
            // Initialize start time if this is the first poll
            if (!startTime && data.status === 'processing') {
                startTime = new Date();
            }
            
            // Replace technical status message with fun alternative 
            // and track elapsed time
            let elapsedText = '';
            if (startTime) {
                const elapsed = Math.floor((new Date() - startTime) / 1000);
                const minutes = Math.floor(elapsed / 60);
                const seconds = elapsed % 60;
                elapsedText = ` (${minutes}m ${seconds}s elapsed)`;
            }
            
            // Create a fun status message based on the progress
            let friendlyMessage;
            if (data.message.includes("Extracting PST")) {
                friendlyMessage = "Unpacking your emails" + elapsedText;
            } else if (data.message.includes("Processed")) {
                // Extract just the number from "Processed X emails..."
                const match = data.message.match(/Processed (\d+)/);
                const count = match ? match[1] : "";
                friendlyMessage = `Discovering email treasures${count ? ` (${count} found)` : ""}${elapsedText}`;
            } else if (data.message.includes("chunks")) {
                friendlyMessage = `Email investigation in progress${elapsedText}`;
            } else {
                friendlyMessage = data.message + elapsedText;
            }
            
            statusMessage.textContent = friendlyMessage;
            
            // Update fun message based on progress
            const funMessage = document.getElementById('funMessage');
            if (funMessage) {
                // Different fun messages based on progress stage
                const funMessages = [
                    { threshold: 5, message: "Warming up the digital magnifying glass... 🔍", icon: "bi-search" },
                    { threshold: 15, message: "Emails are spilling their secrets... 🤐", icon: "bi-envelope-open" },
                    { threshold: 25, message: "Digging through the email treasure chest... 💎", icon: "bi-gem" },
                    { threshold: 35, message: "Teaching AI to read between the lines... 📝", icon: "bi-robot" },
                    { threshold: 45, message: "Brewing some insight potion... 🧪", icon: "bi-flask" },
                    { threshold: 55, message: "Connecting the digital dots... 🔗", icon: "bi-link" },
                    { threshold: 65, message: "Extracting the email wisdom... 🧠", icon: "bi-lightbulb" },
                    { threshold: 75, message: "Translating techspeak to English... 🗣️", icon: "bi-translate" },
                    { threshold: 85, message: "Adding sprinkles of AI magic... ✨", icon: "bi-stars" },
                    { threshold: 95, message: "Final polish, almost there... 💫", icon: "bi-magic" },
                    { threshold: 100, message: "Ta-da! Analysis complete! 🎉", icon: "bi-trophy" }
                ];
                
                // Find the appropriate message for current progress
                let currentMessageObj = funMessages[0];
                for (let i = 0; i < funMessages.length; i++) {
                    if (data.progress < funMessages[i].threshold) {
                        break;
                    }
                    currentMessageObj = funMessages[i];
                }
                
                // Update message and icon
                funMessage.textContent = currentMessageObj.message;
                
                // Update icon if needed
                const iconEl = document.querySelector('.fun-message-icon i');
                if (iconEl && iconEl.className !== `bi ${currentMessageObj.icon}`) {
                    iconEl.className = `bi ${currentMessageObj.icon}`;
                }
            }
            
            // Handle summaries
            if (data.summaries && data.summaries.length > 0) {
                const summariesContainer = document.getElementById('summariesContainer');
                const summariesList = document.getElementById('summariesList');
                
                // Show the summaries container
                summariesContainer.classList.remove('hidden');
                
                // Only add new summaries, don't rebuild the entire list
                // Display summaries differently now - they come from batches of 5 chunks
                data.summaries.forEach((summary, index) => {
                    // Create a unique ID for this summary
                    const summaryId = `summary-${index}`;
                    
                    // Only add if we haven't processed this summary before
                    if (!processedSummaries.has(summaryId)) {
                        processedSummaries.add(summaryId);
                        
                        const listItem = document.createElement('div');
                        listItem.className = 'list-group-item';
                        listItem.id = summaryId;
                        listItem.innerHTML = `
                            <p class="mb-1">${summary}</p>
                        `;
                        summariesList.appendChild(listItem);
                        
                        // Always scroll to the newest insight when it's added
                        summariesList.scrollTop = summariesList.scrollHeight;
                    }
                });
            }
            
            if (data.status === 'completed') {
                // Redirect to the results page for a professional display
                window.location.href = '/results';
            } else if (data.status === 'error') {
                // Show error
                showError(data.error || 'An unknown error occurred.');
            } else if (data.status === 'processing') {
                // Continue polling if not stopped
                if (!window.stopPolling) {
                    setTimeout(pollStatus, 2000);
                }
            }
        })
        .catch(error => {
            showError('An error occurred while checking status.');
            console.error('Error:', error);
        });
    }
    
    function showError(message) {
        errorMessage.textContent = message;
        errorContainer.classList.remove('hidden');
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // Download full analysis button
    downloadBtn.addEventListener('click', function() {
        window.location.href = '/download';
    });
    
    // Download insights button
    const downloadInsightsBtn = document.getElementById('downloadInsightsBtn');
    if (downloadInsightsBtn) {
        downloadInsightsBtn.addEventListener('click', function() {
            window.location.href = '/download-insights';
        });
    }
    
    // Start new button
    startNewBtn.addEventListener('click', function() {
        uploadCard.style.display = 'block';
        statusCard.style.display = 'none';
    });
    
    // Try again button
    tryAgainBtn.addEventListener('click', function() {
        uploadCard.style.display = 'block';
        statusCard.style.display = 'none';
    });
    
    // Cancel analysis button
    if (cancelAnalysisBtn) {
        cancelAnalysisBtn.addEventListener('click', function() {
            if (confirm('Are you sure you want to cancel the analysis? Any API credits used so far will not be refunded.')) {
                // Stop the polling
                window.stopPolling = true;
                
                // Get session ID
                const sessionId = localStorage.getItem('pst_mailminer_session_id');
                const formData = new FormData();
                if (sessionId) {
                    formData.append('session_id', sessionId);
                }
                
                // Call the cancel endpoint
                fetch('/cancel-analysis', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    // Go back to upload form
                    uploadCard.style.display = 'block';
                    statusCard.style.display = 'none';
                    
                })
                .catch(error => {
                    console.error('Error cancelling analysis:', error);
                    
                    // Go back to upload form anyway
                    uploadCard.style.display = 'block';
                    statusCard.style.display = 'none';
                });
            }
        });
    }
    
    // Add warning when user tries to leave the page during analysis
    window.addEventListener('beforeunload', function(e) {
        if (statusCard.style.display === 'block' && progressBar.getAttribute('aria-valuenow') < 100) {
            // Standard message (user's browser will show its own message)
            const message = 'Analysis is in progress. If you leave, you will lose progress and any API credits used.';
            e.returnValue = message;
            return message;
        }
    });
});