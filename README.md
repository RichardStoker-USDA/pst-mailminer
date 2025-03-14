# PST MailMiner

A Docker & AI powered email analysis tool that transforms PST archives into actionable insights for legal discovery, project tracking, and customer feedback analysis using large language models (LLM). Create custom analyses via a simple wizard interface or by importing your own templates.

## Features

- Advanced PST file analysis with AI-powered insights
- Upload PST files up to 8GB in size
- Extract and process email content with metadata
- Premium analysis using OpenAI's GPT-4o and GPT-4o-mini models
- Multiple analysis templates for different use cases
- Custom template creation wizard with import/export capabilities
- Real-time processing status with live insights
- Secure, private results with unique result URLs
- Elegant, modern UI with responsive design

## Deployment Options

### Using Docker (Recommended)

**Prerequisites:**
- Docker and Docker Compose installed on your system
- [Get Docker](https://docs.docker.com/get-docker/) if not already installed

**Quick Start:**

1. **Use Pre-built Image (Easiest Method):**
   ```bash
   # Create a docker-compose.yml file with the following content:
   
   version: '3.8'
   services:
     pst-mailminer:
       image: ghcr.io/richardstoker-usda/pst-mailminer:latest
       container_name: pst-mailminer
       ports:
         - "5050:5050"
       volumes:
         - pst_uploads:/app/uploads
         - pst_results:/app/results
       # Optional environment variables for API key functionality
       environment:
         # Add your own OpenAI API key here to provide a preloaded key option
         - PRELOADED_API_KEY=your_openai_api_key_here
         # Restrict the preloaded key to specific models (optional)
         - ALLOWED_MODELS_WITH_PRELOADED_KEY=gpt-4o,gpt-4o-mini
       restart: unless-stopped
   
   volumes:
     pst_uploads:
     pst_results:
   ```
   
   Then run:
   ```bash
   docker-compose up -d
   ```
   
   > **Note**: You can optionally configure a preloaded API key by setting the PRELOADED_API_KEY environment variable. This adds a convenience button to the interface allowing users to use this key instead of entering their own. You can customize the button text and notification message with COMMUNITY_BUTTON_TEXT, COMMUNITY_MESSAGE_TITLE, and COMMUNITY_MESSAGE_DETAILS environment variables. This feature is ideal for team deployments or when you want to provide a preconfigured API key for convenience. By default, the preloaded key can use both GPT-4o and GPT-4o-mini models.

2. **Alternative: Build from Source:**
   ```bash
   git clone https://github.com/RichardStoker-USDA/pst-mailminer.git
   cd pst-mailminer
   docker-compose up -d
   ```
   
   When building from source, you will need to configure your own OpenAI API key.

3. Access the application at http://localhost:5050

### Docker Deployment Details

The application is designed to run in Docker with minimal configuration. The recommended configuration using the prebuilt image:

```yaml
version: '3.8'
services:
  pst-mailminer:
    image: ghcr.io/richardstoker-usda/pst-mailminer:latest
    container_name: pst-mailminer
    ports:
      - "5050:5050"
    volumes:
      - pst_uploads:/app/uploads
      - pst_results:/app/results
    environment:
      # Optional: Pre-loaded API key for convenience (add your own OpenAI API key)
      - PRELOADED_API_KEY=your_openai_api_key_here
      # Optional: Restrict preloaded key to specific models (comma-separated list)
      - ALLOWED_MODELS_WITH_PRELOADED_KEY=gpt-4o,gpt-4o-mini
      # Optional: Customize the preloaded key button text
      - COMMUNITY_BUTTON_TEXT=Use Preloaded Key
      # Optional: Customize the notification message (displayed when using preloaded key)
      - COMMUNITY_MESSAGE_TITLE=Using Preloaded API Key
      - COMMUNITY_MESSAGE_DETAILS=Using organization's preloaded API key
    restart: unless-stopped

volumes:
  pst_uploads:  # Temporary storage for uploaded PST files
  pst_results:  # Storage for analysis results
```

#### Persistent Storage

By default, the application uses Docker volumes for storage. If you want to persist data across container restarts and have easier access to the results, you can modify the volumes configuration:

```yaml
volumes:
  - ./data/uploads:/app/uploads
  - ./data/results:/app/results
```

This will store all uploads and results in the `./data` directory on your host system.

## Using the Application

1. **Access the Web Interface**:
   - Open http://localhost:5050 in your browser
   
2. **API Key Options**:
   - **Preloaded API Key**: Optionally configure your own OpenAI API key as a preloaded key
   - **Custom API Key**: Users can provide their own OpenAI API key with access to GPT-4o or GPT-4o-mini models
   - **Customizable Button**: You can change the preloaded key button text and notification message
   - API keys are never stored on the server, only used for API calls
   - Typical analysis costs vary depending on model and file size

3. **Select a Model**:
   - GPT-4o: Premium model for highest quality analysis
   - GPT-4o-mini: Cost-effective option for larger PST files

4. **Choose or Create a Template**:
   - Select from pre-built templates:
     - Teams Voice Migration Audit
     - General Project Status Analysis
     - Legal Discovery Search
     - Customer Feedback Analysis
   - Or create a custom template using the wizard

5. **Upload Your PST File**:
   - Drag and drop or select your PST file (up to 8GB)
   - Click "Start Analysis" to begin processing

6. **Monitor Analysis Progress**:
   - View real-time progress updates
   - See live insights as batches are processed
   - Average processing time depends on file size and model selected

7. **Review and Download Results**:
   - View the complete analysis in your browser
   - Download the full synthesis or key insights as text files
   - Results are accessible through unique URLs for privacy

## Analysis Templates

### Built-in Templates

1. **Software Implementation Review**:
   - Analyze communication patterns during migration projects
   - Track issue resolution and document decision making
   - Identify responsibilities and project execution patterns

2. **Legal Discovery Search**:
   - Search for specific terms or evidence for legal proceedings
   - Documentation for eDiscovery or compliance purposes
   - Identify key communications relevant to legal matters

3. **General Project Status Analysis**:
   - Determine project status and risk assessment
   - Track timeline adherence and milestone completion
   - Identify blockers and communication patterns

4. **Customer Feedback Analysis**:
   - Extract customer sentiment and key concerns
   - Identify common issues and improvement opportunities
   - Track product/service feedback patterns

### Custom Templates

Create specialized templates for your specific needs with the template creation wizard or import previously saved templates.

## System Requirements

- Docker-capable system with at least 4GB RAM
- Internet connection for OpenAI API calls
- Sufficient disk space for PST file processing
- Modern web browser with JavaScript enabled

## Important Notes

- This application processes emails locally within the Docker container
- No data is sent to external servers except to OpenAI's API for analysis
- OpenAI API costs apply based on model usage and data volume
- PST files and analyses are not persistent unless you configure volume mapping
- Please read the [DISCLAIMER.md](DISCLAIMER.md) for important usage terms and conditions

## Credits

Developed by Richard Stoker on EnRichedLab - a testing lab for AI empowered apps and solutions.

## License

This software is licensed under a modified BSD-3-Clause license with ethical use provisions.
Copyright © 2025 Richard Stoker. All rights reserved.

See the [LICENSE](LICENSE) file for the full license text.

### Third-Party Licenses

This project uses several open-source libraries:

- Flask and Werkzeug: BSD-3-Clause
- html2text, OpenAI, tiktoken: MIT
- Python Standard Library: Python Software Foundation License

See [LICENSES.md](LICENSES.md) for complete third-party license information.
