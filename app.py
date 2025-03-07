import os
import sys
import traceback
import logging
from flask import Flask, request, render_template, jsonify, send_file, url_for, Response, redirect
import tempfile
import json
import threading
import time
import uuid
import secrets
from werkzeug.utils import secure_filename
import html2text
import re
import mimetypes
from pathlib import Path
import shutil
import hashlib
from email import message_from_string, policy
from email.parser import Parser
from datetime import datetime
import subprocess
from openai import OpenAI
import tiktoken

# Note: For proxy settings with OpenAI, set environment variables:
# os.environ['HTTP_PROXY'] = 'http://your-proxy-server:port'
# os.environ['HTTPS_PROXY'] = 'http://your-proxy-server:port'

# Model context windows - maximum tokens each model can handle
MODEL_CONTEXT_WINDOWS = {
    "gpt-4o": 120000,      # Further reduced to prevent context length errors
    "gpt-4o-mini": 120000  # Further reduced to prevent context length errors
}

# Maximum output tokens for each model
MODEL_MAX_OUTPUT_TOKENS = {
    "gpt-4o": 15000,      # Reduced to provide error margin
    "gpt-4o-mini": 15000  # Reduced to provide error margin
}

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='templates/static')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['RESULTS_FOLDER'] = 'results'
app.config['MAX_CONTENT_LENGTH'] = 8000 * 1024 * 1024  # 8GB max upload size

# Global variables to track processing state for multiple users
# Now using a dictionary with session IDs as keys for multiple concurrent users
processing_statuses = {}

# Function to get or create processing status for a session
def get_processing_status(session_id):
    if session_id not in processing_statuses:
        processing_statuses[session_id] = {
            'current_job': None,
            'status': 'idle',  # idle, processing, completed, error, cancelled
            'progress': 0,
            'message': '',
            'error': None,
            'result_file': None,
            'summaries': [],
            'last_activity': time.time()
        }
    return processing_statuses[session_id]

# Function to clean up old processing statuses
def cleanup_old_sessions():
    current_time = time.time()
    to_remove = []
    for session_id, status in processing_statuses.items():
        # Remove sessions older than 1 hour with no activity
        if current_time - status['last_activity'] > 3600:
            # Don't remove active processing jobs
            if status['status'] != 'processing':
                to_remove.append(session_id)
    
    for session_id in to_remove:
        del processing_statuses[session_id]

# Community Monthly Limited Key configuration
# Always use environment variables for API keys - never hard-code in source
# This should be provided at docker build/run time and not stored in the repository
TRIAL_API_KEY = os.environ.get('PRELOADED_API_KEY', '')

# Check if there are model restrictions for the community key
# ALLOWED_MODELS_WITH_PRELOADED_KEY can be "gpt-4o", "gpt-4o-mini", or comma-separated list
# If empty or not set, all models are allowed with the community key
ALLOWED_MODELS_WITH_PRELOADED_KEY = os.environ.get('ALLOWED_MODELS_WITH_PRELOADED_KEY', '')

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# Templates for analysis prompts
ANALYSIS_TEMPLATES = {
    'legal_discovery': {
        'name': 'Legal Discovery Search',
        'description': 'Search for specific terms or evidence within emails for legal proceedings, eDiscovery, or compliance purposes.',
        'prompt': """# LEGAL DISCOVERY AND COMPLIANCE ANALYSIS

## Context
This analysis is being performed as part of a legal discovery or compliance review process. The objective is to systematically search through email communications to identify relevant content that may serve as evidence or documentation for legal, regulatory, or internal compliance purposes.

## Analysis Objectives
Conduct a thorough examination of these email communications to identify:

### 1. KEY TERM IDENTIFICATION
- **Legal Terminology**: Identify legal terms, phrases, or jargon that may indicate relevant discussions
- **Compliance Language**: Look for mentions of regulatory requirements, policies, or standards
- **Warning Signs**: Identify language that might suggest misconduct, violations, or concerning behavior
- **Disclaimers and Caveats**: Note any legal disclaimers or qualifications in communications
- **Admissions or Acknowledgments**: Identify any statements that might constitute admissions regarding actions taken

### 2. EVIDENCE GATHERING
- **Factual Statements**: Catalog factual assertions made by participants that could be verified
- **Date and Time References**: Track chronology of events mentioned in communications
- **Individual Roles and Responsibilities**: Document who was involved in which activities
- **Referenced Documents**: Note mentions of other documents, reports, or materials
- **Decision Points**: Identify when and how key decisions were made

### 3. COMMUNICATION PATTERNS
- **Chain of Command**: Track how information moved through organizational hierarchy
- **Response Times**: Note delays or urgency in responses to critical communications
- **Information Sharing**: Document how widely information was distributed
- **Meeting Scheduling**: Note when face-to-face or call discussions were suggested instead of email
- **Forwarding Patterns**: Track how messages were forwarded to additional recipients

### 4. SENTIMENT AND TONE
- **Emotional Language**: Identify heightened emotional content in communications
- **Urgency Indicators**: Note language suggesting time pressure or emergency
- **Hesitation or Uncertainty**: Document expressions of doubt or uncertainty
- **Pressure or Coercion**: Identify language that might indicate inappropriate influence
- **Changes in Tone**: Note significant shifts in tone over time or in different contexts

## Emails to Analyze

{emails}

## Output Requirements

### 1. Executive Summary
- Provide a concise overview of key findings with direct relevance to legal/compliance concerns
- Highlight the most significant evidence discovered
- Outline any potential risk areas or issues requiring immediate attention

### 2. Chronological Documentation
- Present a timeline of relevant communications
- Include dates, participants, and key content for each relevant message
- Note any gaps in the communication record

### 3. Subject Matter Analysis
- Organize findings by topic areas relevant to the investigation
- Provide direct quotes with proper context for each significant finding
- Link related communications to show the complete picture

### 4. Individual Involvement Assessment
- Document each individual's participation in relevant communications
- Note their specific statements, actions, and responsibilities
- Track changes in their positions or statements over time

### 5. Evidence Catalog
- Provide a numbered inventory of all potentially relevant evidence found
- Include message metadata (date, time, participants) with each item
- Classify evidence by type and relevance

Your analysis must be objective, factual, and thoroughly documented with specific citations from the emails. Maintain neutrality and avoid speculation or conclusions that go beyond what is directly supported by the email content."""
    },
    'software_implementation': {
        'name': 'Software Implementation Review',
        'description': 'Analyze emails related to software implementation projects to identify communication patterns, issues, and success factors.',
        'prompt': """# SOFTWARE IMPLEMENTATION REVIEW ANALYSIS

## Context
This analysis examines communications from a software implementation project. Multiple stakeholders have reported varying experiences with the implementation process. We need to establish an objective understanding of what actually happened with concrete evidence.

## Analysis Objectives
Conduct a detailed, objective analysis of these email communications to determine:

### 1. COMMUNICATION PATTERNS
- **Frequency & Timing**: Track communication volume over time, noting any patterns, peaks, or gaps
- **Sender/Receiver Analysis**: Identify who initiated communications vs. who responded
- **Response Rates**: Calculate response rates for different stakeholders (e.g., "Vendor sent 12 emails, Client departments responded to 5")
- **Quality Assessment**: Evaluate clarity, completeness, and professionalism of communications
- **Follow-up Patterns**: Note how often and how quickly unanswered communications were followed up
- **Communication Mediums**: Note if different communication channels were used or suggested

### 2. PROJECT EXECUTION
- **Timeline Adherence**: Document scheduled vs. actual dates for key milestones
- **Preparation Work**: Identify requirements gathering, planning, and documentation efforts
- **Technical Implementation**: Note specific technical steps taken or issues encountered
- **Training Efforts**: Document training sessions offered, attendance, and effectiveness
- **User Adoption**: Track user feedback, resistance points, and adoption strategies
- **Issue Resolution**: Document how technical or process issues were addressed

### 3. SPECIFIC EVIDENCE
- **Missed Communications**: Identify explicit examples of messages that went unanswered
- **Deadline Misses**: Document specific instances of missed deadlines with dates and impact
- **Issue Documentation**: Catalog all problems reported, by whom, and with what severity
- **Resolution Attempts**: Document efforts to solve issues (include timestamps and personnel)
- **Change Requests**: Track formal and informal requests for changes to project scope
- **Financial Discussions**: Note any mentions of costs, budget issues, or financial impact
- **Satisfaction Indicators**: Identify expressions of satisfaction or dissatisfaction

### 4. RESPONSIBILITY PATTERNS
- **Project Management**: Evaluate VendorCompany's PM methodology and execution
- **Engagement Levels**: Quantify participation levels of different stakeholders over time
- **Accountability Patterns**: Document how issues were assigned and tracked
- **Escalation Patterns**: Note how and when issues were escalated to higher management
- **Decision-Making**: Identify who made key decisions and based on what information
- **Proactive vs. Reactive Actions**: Categorize actions as proactive planning vs. reactive problem-solving

## Emails to Analyze

{emails}

## Output Requirements

### 1. Evidence Summary
- Present multiple direct quotes from emails to support key findings
- Include message dates, senders, and recipients for all quoted evidence
- Organize evidence chronologically within each finding category

### 2. Detailed Timeline
- Create a comprehensive project timeline from the earliest to latest communication
- Highlight key events, decisions, issues, and resolution points
- Note periods of high activity vs. communication gaps

### 3. Communication Analysis
- Provide quantitative metrics where possible (response rates, time to respond, etc.)
- Include qualitative assessment of communication effectiveness
- Identify patterns in how information was shared or withheld

### 4. Issue Analysis
- Catalog all technical and process issues mentioned
- Track the lifecycle of each issue (reported → acknowledged → addressed → resolved/unresolved)
- Assess severity and impact of each issue

### 5. Responsibility Assessment
- Evaluate the contributions and accountability of each key stakeholder
- Identify specific instances of proactive vs. reactive behavior
- Note any shifts in responsibility or accountability during the project

### 6. Impact Analysis
- Document evidence of financial, operational, or reputational impacts
- Note any mentions of project success metrics and whether they were met
- Identify any indicators of satisfaction or dissatisfaction with the project outcome

Your analysis must be objective, evidence-based, and thoroughly referenced with specific examples from the emails. Focus on establishing verifiable facts rather than making judgments."""
    },
    'project_status': {
        'name': 'General Project Status Analysis',
        'description': 'Analyze emails to determine project status, risks, and timeline adherence.',
        'prompt': """# PROJECT STATUS ANALYSIS

## Context
These emails contain updates and discussions about an ongoing project. This analysis will provide a comprehensive assessment of the project's current state, risks, timeline adherence, and stakeholder engagement.

## Analysis Objectives
Conduct a detailed examination of these email communications to produce:

### 1. PROJECT STATUS ASSESSMENT
- **Phase Identification**: Determine the current phase in the project lifecycle
- **Milestone Tracking**: Document completed milestones with dates and deliverables
- **Deliverable Status**: Identify all completed, in-progress, and pending deliverables
- **Progress Metrics**: Extract any quantitative measures of progress mentioned (% complete, etc.)
- **Resource Utilization**: Analyze how resources are being allocated and utilized
- **Budget Status**: Document current budget status, expenditures, and projections
- **Quality Indicators**: Identify any mentions of quality assurance activities or issues
- **Overall Health**: Assess the overall project health based on concrete indicators

### 2. RISK AND ISSUE ANALYSIS
- **Active Issues**: Catalog all active issues with severity, impact, and ownership
- **Emerging Risks**: Identify potential risks that have been flagged but not yet materialized
- **Technical Challenges**: Document specific technical problems and their current status
- **Resource Constraints**: Note any resource shortages or allocation problems
- **Scope Management**: Track scope changes, rejections, and impact assessments
- **Dependencies**: Map critical dependencies and their current status
- **Bottlenecks**: Identify process or resource bottlenecks impacting progress
- **External Factors**: Note any external influences affecting the project (market conditions, etc.)
- **Risk Response**: Document existing risk mitigation or contingency plans

### 3. TIMELINE ANALYSIS
- **Original vs. Current**: Compare the original timeline to current projections
- **Milestone Shifts**: Track changes to key milestone dates
- **Delay Patterns**: Identify patterns in the types or causes of delays
- **Delay Causes**: Categorize and analyze the root causes of delays
- **Recovery Plans**: Document plans to recover from schedule slippage
- **Critical Path Impact**: Assess how delays are affecting the critical path
- **Forecast Accuracy**: Analyze the accuracy of previous timeline projections
- **Deadline Confidence**: Assess confidence levels in meeting upcoming deadlines

### 4. STAKEHOLDER COMMUNICATION
- **Update Frequency**: Measure the frequency and regularity of stakeholder updates
- **Information Quality**: Assess the completeness and clarity of information shared
- **Decision Patterns**: Track how decisions are made, by whom, and based on what information
- **Escalation Processes**: Document how issues are escalated and to whom
- **Client Engagement**: Measure client/sponsor participation and responsiveness
- **Team Awareness**: Assess how well the team is informed about project status
- **Feedback Loops**: Identify how feedback is solicited and incorporated
- **Communication Challenges**: Note any communication breakdowns or misunderstandings

## Emails to Analyze

{emails}

## Output Requirements

### 1. Executive Summary
- Provide a concise (1-2 paragraph) summary of the project's current status
- Highlight the 3-5 most critical findings that require immediate attention
- Include a color-coded status indicator (Green/Yellow/Red) with justification

### 2. Detailed Status Report
- Document the current phase and overall progress with specific evidence
- List all completed and pending milestones with dates
- Provide quantitative metrics where available (% complete, budget spent, etc.)
- Include a comprehensive deliverable status tracker

### 3. Critical Issues & Risks Register
- Prioritize issues based on impact and urgency
- Provide context and history for each major issue
- Document ownership and current status of resolution efforts
- Identify emerging risks with probability and impact assessments
- Include recommended actions for each major risk and issue

### 4. Timeline Analysis
- Present a revised timeline based on latest information
- Analyze variance between original and current timeline
- Document specific causes of delays with supporting evidence
- Assess the feasibility of current deadlines
- Recommend schedule adjustments where necessary

### 5. Stakeholder Analysis
- Assess engagement levels of key stakeholders
- Identify communication gaps or information silos
- Document decision bottlenecks and recommend improvements
- Evaluate the effectiveness of the current governance structure

### 6. Action Recommendations
- Provide specific, actionable recommendations prioritized by impact
- Include timeline, ownership, and success criteria for each recommendation
- Focus on both immediate interventions and long-term improvements

Your analysis must be evidence-based, objective, and thoroughly referenced with specific examples from the emails. Present information in a structured, actionable format that enables informed decision-making."""
    },
    'customer_feedback': {
        'name': 'Customer Feedback Analysis',
        'description': 'Analyze customer communications for feedback, satisfaction levels, and improvement opportunities.',
        'prompt': """# CUSTOMER FEEDBACK ANALYSIS

## Context
These emails contain customer interactions that provide insights into their experience with our products/services. This analysis will extract actionable feedback, determine satisfaction levels, and identify prioritized improvement opportunities.

## Analysis Objectives
Conduct a detailed examination of these email communications to produce:

### 1. SATISFACTION ASSESSMENT
- **Explicit Statements**: Identify direct expressions of satisfaction or dissatisfaction
- **Sentiment Analysis**: Measure tone and emotional content throughout communications
- **Loyalty Indicators**: Track signals of customer retention or churn risk
  - Repeat purchase intentions
  - Renewal discussions
  - Cancellation threats or considerations
  - Usage expansion or reduction plans
- **Advocacy Metrics**: Document referral activity and willingness
  - Positive referrals or testimonials offered
  - Negative warnings to others
  - Requests for referral incentives
  - Declined referral opportunities
- **Satisfaction Trends**: Note any changes in satisfaction over time
- **Expectation Alignment**: Identify gaps between customer expectations and reality
- **Brand Perception**: Extract comments about overall brand impression

### 2. PRODUCT/SERVICE FEEDBACK
- **Feature Requests**: Catalog specific functionality additions requested
- **Enhancement Suggestions**: Document improvements to existing features
- **Bug Reports**: Identify reported errors, malfunctions, or unexpected behaviors
  - Frequency and patterns
  - Severity and impact
  - Reproduction steps when mentioned
- **Usability Feedback**: Note comments about ease of use or complexity
- **Performance Issues**: Track mentions of speed, reliability, or technical problems
- **Comparative Analysis**: Identify comparisons to competitor products/services
- **Usage Patterns**: Extract information about how customers are using the product
- **Feature Prioritization**: Note which features customers consider most/least valuable
- **Documentation Feedback**: Capture comments about help resources and guides

### 3. SUPPORT EXPERIENCE
- **Response Time**: Measure satisfaction with speed of initial and follow-up responses
- **Resolution Effectiveness**: Assess whether issues were resolved to customer satisfaction
- **Resolution Timeline**: Document time-to-resolution for different issue types
- **Staff Interactions**: Evaluate feedback about support personnel
  - Knowledge and expertise
  - Professionalism and courtesy
  - Communication clarity
  - Follow-through and reliability
- **Support Channel Preferences**: Note preferences for different support channels
- **Self-Service Experience**: Gather feedback on knowledge bases, FAQs, and tutorials
- **Escalation Experiences**: Track comments about issue escalation processes
- **Support Accessibility**: Note any difficulties accessing support resources

### 4. VALUE PERCEPTION
- **Price-to-Value Assessment**: Evaluate customer perception of value received relative to cost
- **ROI Mentions**: Document statements about return on investment
- **Cost Concerns**: Identify price-related issues or objections
- **Competitive Pricing**: Note comparisons to competitor pricing models
- **Billing Clarity**: Track mentions of billing confusion or transparency issues
- **Discount Discussions**: Document conversations about discounts, promotions, or special pricing
- **Feature-to-Price Alignment**: Identify perceptions about which features justify the price
- **Long-term Value**: Note comments about sustained value over time

### 5. RELATIONSHIP DYNAMICS
- **Communication Quality**: Assess the effectiveness of company-customer communications
- **Trust Indicators**: Identify statements suggesting trust or distrust
- **Partnership Approach**: Note whether customers view the relationship as transactional or strategic
- **Power Dynamics**: Observe negotiation tactics and leverage discussions
- **Contact Frequency**: Evaluate satisfaction with communication frequency
- **Decision Maker Engagement**: Track involvement of different stakeholders
- **Relationship History**: Note references to past experiences and their impact on current perception

## Emails to Analyze

{emails}

## Output Requirements

### 1. Executive Summary
- Provide an overall satisfaction assessment with supporting evidence
- Highlight the 3-5 most significant findings
- Include a quantitative satisfaction score (1-10) if possible, with justification

### 2. Detailed Feedback Analysis
- Categorize feedback by product/service area with frequency counts
- Provide verbatim customer quotes to illustrate key points
- Identify patterns and trends across multiple communications
- Distinguish between isolated incidents and systemic issues

### 3. Customer Sentiment Map
- Present a visual or descriptive sentiment analysis across different product/service areas
- Identify emotional triggers (both positive and negative)
- Track sentiment changes over time or throughout conversation threads
- Document specific language patterns indicating strong sentiment

### 4. Competitive Intelligence
- Compile all competitor mentions and comparisons
- Analyze perceived strengths and weaknesses relative to competitors
- Identify competitive threats and opportunities
- Document specific competitor features that customers value

### 5. Support Experience Assessment
- Evaluate the customer support journey and experience
- Identify bottlenecks or friction points in the support process
- Document response times and resolution effectiveness
- Recommend specific improvements to support processes

### 6. Value Proposition Analysis
- Assess alignment between pricing and perceived value
- Identify which features or services drive value perception
- Document price sensitivity indicators
- Recommend potential adjustments to pricing or packaging

### 7. Prioritized Action Plan
- Recommend 5-10 specific actions prioritized by:
  - Potential impact on customer satisfaction
  - Implementation difficulty
  - Urgency based on customer sentiment
  - Strategic alignment
- For each recommendation, include:
  - Specific customer feedback supporting the recommendation
  - Expected outcome if implemented
  - Potential metrics to measure success

Your analysis must be evidence-based, objective, and thorough. Focus on identifying actionable insights that can drive meaningful improvements in customer satisfaction and business performance."""
    },
    'custom': {
        'name': 'Custom Analysis',
        'description': 'Create your own custom analysis prompt.',
        'prompt': """# CUSTOM EMAIL ANALYSIS

## Context
[Replace this with your specific context. Explain what these emails represent and why they are being analyzed.]

## Analysis Objectives
Conduct a detailed examination of these email communications to analyze:

### 1. [FIRST ANALYSIS CATEGORY]
- **[Subcategory 1]**: [Description of what to look for]
- **[Subcategory 2]**: [Description of what to look for]
- **[Subcategory 3]**: [Description of what to look for]
- **[Subcategory 4]**: [Description of what to look for]
- **[Subcategory 5]**: [Description of what to look for]

### 2. [SECOND ANALYSIS CATEGORY]
- **[Subcategory 1]**: [Description of what to look for]
- **[Subcategory 2]**: [Description of what to look for]
- **[Subcategory 3]**: [Description of what to look for]
- **[Subcategory 4]**: [Description of what to look for]
- **[Subcategory 5]**: [Description of what to look for]

### 3. [THIRD ANALYSIS CATEGORY]
- **[Subcategory 1]**: [Description of what to look for]
- **[Subcategory 2]**: [Description of what to look for]
- **[Subcategory 3]**: [Description of what to look for]
- **[Subcategory 4]**: [Description of what to look for]
- **[Subcategory 5]**: [Description of what to look for]

### 4. [FOURTH ANALYSIS CATEGORY]
- **[Subcategory 1]**: [Description of what to look for]
- **[Subcategory 2]**: [Description of what to look for]
- **[Subcategory 3]**: [Description of what to look for]
- **[Subcategory 4]**: [Description of what to look for]
- **[Subcategory 5]**: [Description of what to look for]

### 5. [FIFTH ANALYSIS CATEGORY]
- **[Subcategory 1]**: [Description of what to look for]
- **[Subcategory 2]**: [Description of what to look for]
- **[Subcategory 3]**: [Description of what to look for]
- **[Subcategory 4]**: [Description of what to look for]
- **[Subcategory 5]**: [Description of what to look for]

## Emails to Analyze

{emails}

## Output Requirements

### 1. Executive Summary
- [Describe what should be included in the executive summary]
- [Specify any quantitative assessments or metrics to be calculated]
- [Indicate how findings should be prioritized or categorized]

### 2. [FIRST OUTPUT SECTION]
- [Describe what should be included in this section]
- [Specify the format and level of detail required]
- [Indicate how evidence should be presented]
- [Specify any visualizations or structured data required]

### 3. [SECOND OUTPUT SECTION]
- [Describe what should be included in this section]
- [Specify the format and level of detail required]
- [Indicate how evidence should be presented]
- [Specify any visualizations or structured data required]

### 4. [THIRD OUTPUT SECTION]
- [Describe what should be included in this section]
- [Specify the format and level of detail required]
- [Indicate how evidence should be presented]
- [Specify any visualizations or structured data required]

### 5. [FOURTH OUTPUT SECTION]
- [Describe what should be included in this section]
- [Specify the format and level of detail required]
- [Indicate how evidence should be presented]
- [Specify any visualizations or structured data required]

### 6. [FIFTH OUTPUT SECTION]
- [Describe what should be included in this section]
- [Specify the format and level of detail required]
- [Indicate how evidence should be presented]
- [Specify any visualizations or structured data required]

### 7. Recommendations and Next Steps
- [Describe what should be included in the recommendations]
- [Specify how recommendations should be prioritized]
- [Indicate what information should accompany each recommendation]
- [Specify the format and structure of the recommendations]

Your analysis must be [describe preferred analytical approach: e.g., "evidence-based with specific quotes", "quantitative with statistical analysis", "focused on identifying patterns across communications", etc.]. Focus on [describe the primary goal of the analysis: e.g., "actionable insights", "historical reconstruction", "identifying causal relationships", etc.]."""
    }
}

class PSTExtractor:
    def __init__(self, pst_path, output_dir):
        self.pst_path = pst_path
        self.output_dir = output_dir
        self.temp_dir = os.path.join(output_dir, 'temp_mbox')
        self.attachments_dir = os.path.join(output_dir, 'attachments')
        
        # Initialize HTML converter
        self.h = html2text.HTML2Text()
        self.h.ignore_links = True
        self.h.ignore_images = True
        self.h.ignore_tables = False  # Preserve table content
        self.h.ignore_emphasis = True
        self.h.body_width = 0  # Prevent text wrapping
        self.h.unicode_snob = True  # Use Unicode characters
        
        # Initialize email parser
        self.parser = Parser(policy=policy.default)

    def clean_text(self, text):
        """Clean text while preserving important formatting and table content"""
        if not text:
            return ""
        
        # Convert HTML to plain text if it looks like HTML
        if "<" in text and ">" in text:
            text = self.h.handle(text)
            
            # Cleanup table formatting while preserving content
            text = re.sub(r'\|\s+\|', '|', text)  # Remove empty table cells
            text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Remove excessive newlines
            text = re.sub(r'[-]+\|[-]+', '-' * 20, text)  # Replace table separators with simple line
        
        # Remove surrogate pairs and invalid Unicode
        text = text.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
        
        # Preserve paragraph breaks but remove excessive whitespace
        paragraphs = text.split('\n\n')
        cleaned_paragraphs = []
        for para in paragraphs:
            # Clean up whitespace within each paragraph
            lines = [line.strip() for line in para.splitlines()]
            cleaned_para = ' '.join(line for line in lines if line)
            if cleaned_para:
                cleaned_paragraphs.append(cleaned_para)
        
        text = '\n\n'.join(cleaned_paragraphs)
        
        # Replace any remaining problematic characters
        text = ''.join(char if ord(char) < 0x10000 else '?' for char in text)
        
        return text.strip()

    def get_email_body(self, msg):
        """Extract email body from message, handling both plain text and HTML content"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ['text/plain', 'text/html']:
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if payload:
                            text = payload.decode(charset, errors='replace')
                            if part.get_content_type() == 'text/html':
                                text = self.h.handle(text)
                            body = text
                            break
                    except Exception as e:
                        print(f"Error decoding part: {str(e)}")
                        continue
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors='replace')
            except Exception as e:
                print(f"Error decoding body: {str(e)}")
        
        return self.clean_text(body)

    def extract_pst(self):
        """Extract PST to mbox format using readpst"""
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Check if we're running in Docker
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER", False)
        
        try:
            if in_docker:
                # In Docker environment, use readpst directly
                result = subprocess.run(['/usr/bin/readpst', '-o', self.temp_dir, '-e', self.pst_path], 
                                      check=False, capture_output=True)
            else:
                # Use the wrapper script instead of calling readpst directly
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'readpst_wrapper.py')
                
                # Run the wrapper script
                result = subprocess.run([sys.executable, script_path, '-o', self.temp_dir, '-e', self.pst_path], 
                                       check=False, capture_output=True)
            
            # Check the result
            if result.returncode == 0:
                return True
            else:
                stderr = result.stderr.decode('utf-8', errors='ignore')
                stdout = result.stdout.decode('utf-8', errors='ignore')
                logger.error(f"PST extraction failed with return code {result.returncode}")
                logger.error(f"Standard error: {stderr}")
                logger.error(f"Standard output: {stdout}")
                return False
                
        except Exception as e:
            logger.error(f"Error during PST extraction: {str(e)}")
            logger.error(traceback.format_exc())
            return False

    def create_message_id(self, msg):
        """Create a unique message ID based on metadata"""
        # Create a string combining key metadata
        id_string = f"{msg['date']}_{msg['from']}_{msg['subject']}"
        # Create a hash of this string
        return hashlib.md5(id_string.encode()).hexdigest()[:8]

    def process_eml_file(self, eml_path):
        """Process a single .eml file"""
        try:
            with open(eml_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                msg = self.parser.parsestr(content)
                
                # Extract basic metadata
                email_data = {
                    "subject": self.clean_text(msg.get('subject', '')),
                    "from": self.clean_text(msg.get('from', '')),
                    "to": self.clean_text(msg.get('to', '')),
                    "cc": self.clean_text(msg.get('cc', '')),
                    "bcc": self.clean_text(msg.get('bcc', '')),
                    "date": msg.get('date', ''),
                    "body": self.get_email_body(msg)
                    # Attachments removed to clean up JSON file
                }

                # Create a unique message ID
                msg_id = self.create_message_id(email_data)
                email_data['message_id'] = msg_id

                # Check for attachments but don't include them in the output
                has_attachments = False
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_disposition() == 'attachment':
                            has_attachments = True
                            break

                email_data['has_attachments'] = has_attachments
                return email_data

        except Exception as e:
            print(f"Error processing file {eml_path}: {str(e)}")
            return None

    def process(self, status_callback=None):
        """Main processing method with status updates"""
        try:
            # Create output directories
            os.makedirs(self.output_dir, exist_ok=True)
            os.makedirs(self.attachments_dir, exist_ok=True)

            if status_callback:
                status_callback("Extracting PST file...", 5)

            # Extract PST to mbox
            extraction_result = self.extract_pst()
            
            if not extraction_result:
                if status_callback:
                    status_callback("Failed to extract PST file", 0, error=True)
                return None

            if status_callback:
                status_callback("Processing emails...", 10)

            all_messages = []
            eml_files = list(Path(self.temp_dir).rglob('*.eml'))
            total_files = len(eml_files)
            
            for i, eml_file in enumerate(eml_files):
                msg = self.process_eml_file(str(eml_file))
                if msg:
                    all_messages.append(msg)
                
                if status_callback and i % 10 == 0:
                    progress = 10 + int(30 * (i / total_files))
                    status_callback(f"Processed {i+1} emails...", progress)

            # Save to JSON
            output_file = os.path.join(self.output_dir, 'extracted_emails.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_messages, f, indent=2, ensure_ascii=False)
            
            if status_callback:
                status_callback(f"Extraction complete. {len(all_messages)} emails processed.", 40)

            return output_file

        finally:
            # Clean up temporary directory
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)

class EmailAnalyzer:
    def __init__(self, json_file, output_dir, api_key, model="gpt-4o", template_key='teams_migration', custom_prompt=None):
        self.json_file = json_file
        self.output_dir = output_dir
        self.model = model
        self.template_key = template_key
        # Initialize OpenAI client correctly - proxy settings should be via env vars
        self.client = OpenAI(api_key=api_key)
        
        if template_key == 'custom' and custom_prompt:
            self.prompt_template = custom_prompt
        else:
            self.prompt_template = ANALYSIS_TEMPLATES.get(template_key, ANALYSIS_TEMPLATES['software_implementation'])['prompt']
        
        # Create output directories
        os.makedirs(os.path.join(output_dir, 'chunks'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'analysis'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'synthesis'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'summaries'), exist_ok=True)
        
        # Get context window size for model
        self.context_window = MODEL_CONTEXT_WINDOWS.get(self.model, 128000)
        
        # Initialize tokenizer
        self.tokenizer = tiktoken.encoding_for_model("gpt-4o") if self.model in ["gpt-4o", "gpt-4o-mini"] else tiktoken.get_encoding("cl100k_base")
        
        # Maximum tokens to reserve for the response
        self.max_response_tokens = MODEL_MAX_OUTPUT_TOKENS.get(self.model, 16000)
        
        # Calculate maximum input tokens
        self.max_input_tokens = self.context_window - self.max_response_tokens
        
        # To store live summaries
        self.summaries = []
        
        logger.info(f"Using model {self.model} with context window of {self.context_window} tokens")
        logger.info(f"Maximum input tokens: {self.max_input_tokens}")
        logger.info(f"Maximum output tokens: {self.max_response_tokens}")

    def count_tokens(self, text):
        """Count the number of tokens in a text string"""
        return len(self.tokenizer.encode(text))

    def load_emails(self):
        """Load and prepare email data"""
        with open(self.json_file, 'r', encoding='utf-8') as f:
            emails = json.load(f)
        return emails

    def format_email_for_analysis(self, email):
        """Format a single email with relevant context"""
        formatted = f"""
Date: {email.get('date', 'No date')}
From: {email.get('from', 'No sender')}
To: {email.get('to', 'No recipient')}
CC: {email.get('cc', 'None')}
Subject: {email.get('subject', 'No subject')}

CONTENT:
{email.get('body', 'No body')}

{"Attachments were included" if email.get('has_attachments', False) else "No attachments"}
----------------------------------------
"""
        return formatted.strip()

    def create_chunks(self, emails):
        """Create analysis chunks from emails based on token counts with conservative limits"""
        chunks = []
        current_chunk_emails = []
        current_chunk_tokens = 0
        
        # Calculate tokens for the prompt template without emails
        base_prompt = self.prompt_template.format(emails="")
        base_prompt_tokens = self.count_tokens(base_prompt)
        
        # Set a more conservative token limit (50% of max) to prevent context overflows
        conservative_token_limit = int(self.max_input_tokens * 0.5)
        logger.info(f"Using conservative token limit of {conservative_token_limit} tokens per chunk")
        
        for email in emails:
            formatted_email = self.format_email_for_analysis(email)
            email_tokens = self.count_tokens(formatted_email)
            
            # If an individual email is somehow too large, truncate it
            if email_tokens > conservative_token_limit:
                logger.warning(f"Found extremely large email ({email_tokens} tokens). Truncating to fit within limits.")
                # Try to preserve metadata but truncate body
                lines = formatted_email.splitlines()
                metadata = []
                body = []
                
                # Capture metadata lines (usually the first 6-7 lines)
                in_body = False
                for line in lines:
                    if line.startswith("CONTENT:"):
                        in_body = True
                        metadata.append(line)
                        continue
                    
                    if in_body:
                        body.append(line)
                    else:
                        metadata.append(line)
                
                # Keep metadata and truncate body content to fit token limits
                truncated_email = "\n".join(metadata) + "\n"
                remaining_tokens = conservative_token_limit - self.count_tokens(truncated_email) - 100  # 100 token buffer
                
                current_tokens = 0
                truncated_body = []
                for line in body:
                    line_tokens = self.count_tokens(line)
                    if current_tokens + line_tokens <= remaining_tokens:
                        truncated_body.append(line)
                        current_tokens += line_tokens
                    else:
                        truncated_body.append("\n[Content truncated due to size limits...]")
                        break
                
                truncated_email += "\n".join(truncated_body)
                formatted_email = truncated_email
                email_tokens = self.count_tokens(formatted_email)
                logger.info(f"Truncated email to {email_tokens} tokens")
            
            # If adding this email would exceed token limit, create a new chunk
            if current_chunk_emails and (current_chunk_tokens + email_tokens + base_prompt_tokens > conservative_token_limit):
                # Finalize current chunk
                formatted_emails = [self.format_email_for_analysis(e) if isinstance(e, dict) else e 
                                   for e in current_chunk_emails]
                chunk_text = self.prompt_template.format(emails="\n\n".join(formatted_emails))
                
                # Double-check the chunk size
                chunk_tokens = self.count_tokens(chunk_text)
                if chunk_tokens > self.max_input_tokens:
                    logger.warning(f"Chunk exceeded max input tokens ({chunk_tokens} > {self.max_input_tokens}). " +
                                 f"Splitting into smaller chunks with fewer emails.")
                    
                    # Try splitting this chunk further if needed
                    mid = len(formatted_emails) // 2
                    if mid > 0:  # Ensure we can actually split
                        chunk1 = self.prompt_template.format(emails="\n\n".join(formatted_emails[:mid]))
                        chunk2 = self.prompt_template.format(emails="\n\n".join(formatted_emails[mid:]))
                        chunks.append(chunk1)
                        chunks.append(chunk2)
                    else:
                        # If we can't split further (only one email), truncate more aggressively
                        logger.warning("Cannot split chunk further - truncating content instead")
                        truncated_content = formatted_emails[0][:int(len(formatted_emails[0])*0.7)]  # Truncate to 70%
                        chunk_text = self.prompt_template.format(emails=truncated_content)
                        chunks.append(chunk_text)
                else:
                    chunks.append(chunk_text)
                
                # Start a new chunk
                current_chunk_emails = [formatted_email]  # Store the formatted email directly
                current_chunk_tokens = email_tokens
            else:
                # Add to current chunk
                current_chunk_emails.append(formatted_email)  # Store the formatted email directly
                current_chunk_tokens += email_tokens
                
            # Log every 100 emails
            if len(chunks) * 100 + len(current_chunk_emails) % 100 == 0:
                logger.info(f"Processed {len(chunks) * 100 + len(current_chunk_emails)} emails into {len(chunks)} chunks")
        
        # Add the last chunk if it has any emails
        if current_chunk_emails:
            formatted_emails = [e if isinstance(e, str) else self.format_email_for_analysis(e) 
                               for e in current_chunk_emails]
            chunk_text = self.prompt_template.format(emails="\n\n".join(formatted_emails))
            
            # Double-check the chunk size
            chunk_tokens = self.count_tokens(chunk_text)
            if chunk_tokens > self.max_input_tokens:
                logger.warning(f"Final chunk exceeded max input tokens ({chunk_tokens} > {self.max_input_tokens}). " +
                             f"Splitting into smaller chunks.")
                
                # Try splitting this chunk further if needed
                mid = len(formatted_emails) // 2
                if mid > 0:  # Ensure we can actually split
                    chunk1 = self.prompt_template.format(emails="\n\n".join(formatted_emails[:mid]))
                    chunk2 = self.prompt_template.format(emails="\n\n".join(formatted_emails[mid:]))
                    chunks.append(chunk1)
                    chunks.append(chunk2)
                else:
                    # If we can't split further, truncate more aggressively
                    logger.warning("Cannot split final chunk further - truncating content instead")
                    truncated_content = formatted_emails[0][:int(len(formatted_emails[0])*0.7)]  # Truncate to 70%
                    chunk_text = self.prompt_template.format(emails=truncated_content)
                    chunks.append(chunk_text)
            else:
                chunks.append(chunk_text)
            
        # Calculate and log average emails per chunk
        avg_emails_per_chunk = len(emails) / max(len(chunks), 1)
        logger.info(f"Created {len(chunks)} chunks with average of {avg_emails_per_chunk:.1f} emails per chunk")
        
        # Verify all chunk sizes
        for i, chunk in enumerate(chunks):
            chunk_tokens = self.count_tokens(chunk)
            logger.info(f"Chunk {i+1}: {chunk_tokens} tokens")
            if chunk_tokens > self.max_input_tokens:
                logger.warning(f"Chunk {i+1} is still too large: {chunk_tokens} tokens. Further processing may be needed.")
        
        return chunks

    def analyze_chunk(self, chunk, chunk_index, retries=3):
        """Analyze a single chunk using OpenAI API with a summary at the beginning"""
        chunk_tokens = self.count_tokens(chunk)
        logger.info(f"Analyzing chunk {chunk_index} with {chunk_tokens} tokens")
        
        # If the chunk is still too large, truncate it further
        if chunk_tokens > self.max_input_tokens * 0.9:  # Over 90% of max input tokens
            logger.warning(f"Chunk {chunk_index} is too large ({chunk_tokens} tokens). Truncating to fit context window.")
            
            # Find the emails section to truncate
            parts = chunk.split("Emails to Analyze:")
            if len(parts) == 2:
                pre_emails = parts[0] + "Emails to Analyze:\n\n"
                emails_content = parts[1]
                
                # Calculate how many tokens we can keep
                max_allowed = int(self.max_input_tokens * 0.8) - self.count_tokens(pre_emails) - 100  # 100 token buffer
                
                # Truncate emails content
                truncated_content = ""
                current_tokens = 0
                for line in emails_content.splitlines():
                    line_tokens = self.count_tokens(line + "\n")
                    if current_tokens + line_tokens <= max_allowed:
                        truncated_content += line + "\n"
                        current_tokens += line_tokens
                    else:
                        truncated_content += "\n[Content truncated due to size limits...]\n"
                        break
                
                # Reconstruct the chunk
                chunk = pre_emails + truncated_content
                chunk_tokens = self.count_tokens(chunk)
                logger.info(f"Truncated chunk {chunk_index} to {chunk_tokens} tokens")
        
        # Add instruction to include a summary at the beginning
        system_prompt = """You are conducting an analysis of email communications.

IMPORTANT: Begin your analysis with a very brief 1-3 sentence "QUICK SUMMARY" section that captures the most important insights from these emails. Keep this summary extremely concise for live updates - just the key points.

After the summary, provide your detailed analysis as requested in the prompt.
"""
        
        for attempt in range(retries):
            try:
                # Make final token check before API call
                total_tokens = self.count_tokens(system_prompt) + chunk_tokens
                if total_tokens > self.context_window - self.max_response_tokens:
                    logger.warning(f"Total tokens for chunk {chunk_index} too large: {total_tokens}. Performing aggressive truncation.")
                    
                    # Get approximate percentage to keep
                    keep_ratio = (self.context_window - self.max_response_tokens - self.count_tokens(system_prompt)) / chunk_tokens
                    keep_ratio = max(0.3, min(0.9, keep_ratio * 0.9))  # Min 30%, max 90%, with 10% safety margin
                    
                    # Truncate chunk content
                    max_chunk_chars = int(len(chunk) * keep_ratio)
                    chunk = chunk[:max_chunk_chars] + "\n\n[Content truncated due to length limits...]"
                    chunk_tokens = self.count_tokens(chunk)
                    logger.info(f"Aggressively truncated chunk {chunk_index} to {chunk_tokens} tokens (keep ratio: {keep_ratio:.2f})")
                
                # Make the API call
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": chunk}
                    ],
                    temperature=0.7,
                    max_tokens=self.max_response_tokens
                )
                analysis = response.choices[0].message.content
                
                # Extract the summary from the analysis
                summary = ""
                if "QUICK SUMMARY" in analysis:
                    summary_parts = analysis.split("QUICK SUMMARY")
                    if len(summary_parts) > 1:
                        summary_text = summary_parts[1].strip()
                        # Extract until the next section
                        if "\n\n" in summary_text:
                            summary = summary_text.split("\n\n")[0].strip()
                        else:
                            summary = summary_text.strip()
                
                # If no summary found or format wasn't followed, create a default one
                if not summary:
                    summary = f"Analyzed batch #{chunk_index} emails."
                
                # Limit summary length to 250 characters with ellipsis if needed
                if len(summary) > 250:
                    summary = summary[:247] + "..."
                
                # Save the summary
                summary_file = os.path.join(self.output_dir, 'summaries', f'summary_{chunk_index:03d}.txt')
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write(summary)
                
                # Add to the list of summaries
                self.summaries.append({
                    "index": chunk_index,
                    "summary": summary
                })
                
                return analysis
                
            except Exception as e:
                error_message = str(e).lower()
                
                # Handle context length exceeded specially
                if "context length exceeded" in error_message:
                    if attempt == retries - 1:
                        logger.error(f"Failed to analyze chunk {chunk_index} after {retries} attempts due to context length: {str(e)}")
                        
                        # Create a placeholder analysis to avoid breaking the process
                        placeholder = f"""QUICK SUMMARY
This chunk was too large to analyze. Size: {chunk_tokens} tokens.

# Analysis Skipped - Content Too Large
This email batch could not be analyzed because it was too large for the model's context window. 
Consider breaking your PST file into smaller parts before analysis."""
                        
                        return placeholder
                    
                    # Truncate chunk size by 30% for next retry
                    max_chunk_chars = int(len(chunk) * 0.7)
                    chunk = chunk[:max_chunk_chars] + "\n\n[Content truncated due to length limits...]"
                    chunk_tokens = self.count_tokens(chunk)
                    logger.warning(f"Truncating chunk {chunk_index} to {chunk_tokens} tokens for retry {attempt+2}/{retries}")
                    time.sleep(5)  # Brief wait before retry
                    
                elif attempt == retries - 1:
                    logger.error(f"Failed to analyze chunk {chunk_index} after {retries} attempts: {str(e)}")
                    raise e
                else:
                    logger.warning(f"Retrying analysis of chunk {chunk_index} after error: {str(e)}")
                    time.sleep(20)  # Wait before retry

    def synthesize_findings(self, analyses):
        """
        Create a final synthesis of all analyses.
        For very large datasets, uses a hierarchical summarization approach to handle any number of analyses.
        """
        # For extremely large analyses sets, we should use the batch summaries instead of raw analyses
        # This gives better results for very large PST files with 100+ chunks
        if len(analyses) > 100:
            logger.info(f"Using hierarchical synthesis approach for {len(analyses)} analyses")
            return self.hierarchical_synthesis(analyses)
        
        synthesis_prompt = f"""Review these email analyses and provide a comprehensive synthesis.

Analyses to review:

{chr(10).join(analyses)}

Provide a detailed synthesis including:
1. Key findings and patterns
2. Timeline of important events
3. Major issues identified
4. Root causes and implications
5. Recommended actions
6. Supporting evidence (specific references)

Your synthesis should be well-structured with clear sections and should focus on the most significant insights across all analyses."""

        # Count tokens to ensure we don't exceed context window
        prompt_tokens = self.count_tokens(synthesis_prompt)
        logger.info(f"Synthesis prompt has {prompt_tokens} tokens")
        
        # If the prompt is too large, we need to summarize the analyses first
        if prompt_tokens > self.max_input_tokens:
            logger.warning(f"Synthesis prompt exceeds max input tokens ({prompt_tokens} > {self.max_input_tokens})")
            logger.info("Creating intermediate summaries of analyses to fit within context window")
            
            # Create batches of analyses for intermediate summarization
            batches = []
            current_batch = []
            current_batch_tokens = 0
            
            for analysis in analyses:
                analysis_tokens = self.count_tokens(analysis)
                
                if current_batch and (current_batch_tokens + analysis_tokens > self.max_input_tokens / 2):
                    batches.append(current_batch)
                    current_batch = [analysis]
                    current_batch_tokens = analysis_tokens
                else:
                    current_batch.append(analysis)
                    current_batch_tokens += analysis_tokens
            
            if current_batch:
                batches.append(current_batch)
            
            logger.info(f"Created {len(batches)} intermediate batches for summarization")
            
            # Create intermediate summaries
            intermediate_summaries = []
            for i, batch in enumerate(batches):
                intermediate_prompt = f"""Summarize these email analyses concisely while preserving key information:

{chr(10).join(batch)}

Focus on capturing the most important findings, evidence, and patterns."""
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are summarizing email analyses."},
                            {"role": "user", "content": intermediate_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=self.max_response_tokens
                    )
                    intermediate_summaries.append(response.choices[0].message.content)
                    logger.info(f"Created intermediate summary {i+1}/{len(batches)}")
                except Exception as e:
                    logger.error(f"Error creating intermediate summary: {str(e)}")
                    raise e
            
            # Check if even the intermediate summaries might be too large
            intermediate_summaries_tokens = sum(self.count_tokens(s) for s in intermediate_summaries)
            if intermediate_summaries_tokens > self.max_input_tokens * 0.8:  # 80% of max
                logger.warning(f"Intermediate summaries still too large ({intermediate_summaries_tokens} tokens). Creating second-level summaries.")
                return self.hierarchical_synthesis(analyses)  # Fall back to hierarchical approach
            
            # Create final synthesis from intermediate summaries
            final_synthesis_prompt = f"""Create a comprehensive synthesis based on these summarized analyses:

{chr(10).join(intermediate_summaries)}

Provide a detailed synthesis including:
1. Key findings and patterns
2. Timeline of important events
3. Major issues identified
4. Root causes and implications
5. Recommended actions
6. Supporting evidence (specific references)

Your synthesis should be well-structured with clear sections and should focus on the most significant insights."""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are synthesizing findings from email analyses."},
                    {"role": "user", "content": final_synthesis_prompt}
                ],
                temperature=0.7,
                max_tokens=self.max_response_tokens
            )
        else:
            # If the prompt fits within the context window, proceed normally
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are synthesizing findings from email analyses."},
                    {"role": "user", "content": synthesis_prompt}
                ],
                temperature=0.7,
                max_tokens=self.max_response_tokens
            )
        
        return response.choices[0].message.content
        
    def hierarchical_synthesis(self, analyses):
        """
        Process very large sets of analyses using a hierarchical approach.
        This can handle any number of analyses by creating summaries at multiple levels.
        """
        logger.info(f"Starting hierarchical synthesis for {len(analyses)} analyses")
        
        # Step 1: Divide analyses into manageable batches (similar to batch_analyses)
        batch_size = 15  # Reduced to 15 analyses per batch to avoid context length exceeded errors
        batches = [analyses[i:i+batch_size] for i in range(0, len(analyses), batch_size)]
        logger.info(f"Created {len(batches)} first-level batches of up to {batch_size} analyses each")
        
        # Step 2: Create first-level summaries
        first_level_summaries = []
        for i, batch in enumerate(batches):
            summary_prompt = f"""Summarize these email analyses into one concise but comprehensive summary.
Focus on capturing key findings, patterns, timeline, critical issues, and evidence.

ANALYSES TO SUMMARIZE:

{chr(10).join(batch)}

Create a detailed summary that preserves the most important insights from all these analyses."""
            
            try:
                response = self.client.chat.completions.create(
                    model=self.model, 
                    messages=[
                        {"role": "system", "content": "You are creating detailed summaries of email analyses."},
                        {"role": "user", "content": summary_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=self.max_response_tokens
                )
                first_level_summaries.append(response.choices[0].message.content)
                logger.info(f"Created first-level summary {i+1}/{len(batches)}")
            except Exception as e:
                logger.error(f"Error creating first-level summary: {str(e)}")
                raise e
        
        # Step 3: If first-level summaries are still too numerous, create second-level summaries
        if len(first_level_summaries) > 15:  # If we have more than 15 first-level summaries
            logger.info(f"Creating second-level summaries from {len(first_level_summaries)} first-level summaries")
            second_level_batch_size = 10
            second_level_batches = [first_level_summaries[i:i+second_level_batch_size] 
                                   for i in range(0, len(first_level_summaries), second_level_batch_size)]
            
            second_level_summaries = []
            for i, batch in enumerate(second_level_batches):
                summary_prompt = f"""Create a comprehensive synthesis of these email analysis summaries:

{chr(10).join(batch)}

Extract and consolidate the most important findings, trends, issues, and evidence across these summaries."""
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are synthesizing email analysis summaries into higher-level insights."},
                            {"role": "user", "content": summary_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=self.max_response_tokens
                    )
                    second_level_summaries.append(response.choices[0].message.content)
                    logger.info(f"Created second-level summary {i+1}/{len(second_level_batches)}")
                except Exception as e:
                    logger.error(f"Error creating second-level summary: {str(e)}")
                    raise e
            
            # Use the second-level summaries for the final synthesis
            summaries_for_final = second_level_summaries
        else:
            # If first-level summaries are manageable, use them directly
            summaries_for_final = first_level_summaries
        
        # Step 4: Create final synthesis from highest-level summaries
        final_synthesis_prompt = f"""Create a comprehensive final synthesis based on these email analysis summaries:

{chr(10).join(summaries_for_final)}

Provide a detailed synthesis including:
1. Key findings and patterns
2. Timeline of important events
3. Major issues identified
4. Root causes and implications
5. Recommended actions
6. Supporting evidence (specific references)

Your synthesis should be well-structured with clear sections and should focus on the most significant insights across all these email analyses."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are creating the final synthesis of email analyses, bringing together all key insights into one comprehensive report."},
                    {"role": "user", "content": final_synthesis_prompt}
                ],
                temperature=0.7,
                max_tokens=self.max_response_tokens
            )
            logger.info("Created final hierarchical synthesis")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error creating final synthesis: {str(e)}")
            raise e

    def create_batch_summary(self, analyses_batch, batch_number):
        """Create a summary of multiple analyses using gpt-4o-mini"""
        logger.info(f"Creating batch summary for batch {batch_number} with {len(analyses_batch)} analyses")
        
        # Join the analyses with separators
        combined_text = "\n\n===== NEXT ANALYSIS =====\n\n".join(analyses_batch)
        
        # Count tokens
        combined_tokens = self.count_tokens(combined_text)
        logger.info(f"Batch {batch_number} combined tokens: {combined_tokens}")
        
        # Check if the combined text exceeds the maximum input tokens
        if combined_tokens > self.max_input_tokens * 0.8:  # 80% of max to leave room for prompt
            logger.warning(f"Batch {batch_number} has too many tokens ({combined_tokens}). Splitting into smaller batches.")
            
            # Split analyses into smaller sub-batches
            sub_batch_size = max(1, len(analyses_batch) // 2)  # Divide by 2 or use 1 if only one analysis
            sub_batches = [analyses_batch[i:i+sub_batch_size] for i in range(0, len(analyses_batch), sub_batch_size)]
            
            # Process each sub-batch
            sub_summaries = []
            for i, sub_batch in enumerate(sub_batches):
                sub_summary = self._process_batch_summary(sub_batch, f"{batch_number}.{i+1}")
                sub_summaries.append(sub_summary)
            
            # Combine sub-summaries
            return self._process_batch_summary(sub_summaries, f"{batch_number}")
        else:
            # Process as a single batch
            return self._process_batch_summary(analyses_batch, batch_number)
    
    def _process_batch_summary(self, analyses_batch, batch_id):
        """Process a batch of analyses and create a summary"""
        # Join the analyses with separators (could be raw analyses or already-summarized sub-batches)
        combined_text = "\n\n===== NEXT ANALYSIS =====\n\n".join(analyses_batch)
        
        # Create the prompt with specific instructions to avoid repetitive openings
        summary_prompt = f"""Summarize these email analyses into ONE concise, insightful summary.
Focus on the most important findings, patterns, and key information.

IMPORTANT INSTRUCTIONS:
1. Begin with an attention-grabbing headline that captures the main insight (use format "KEY FINDING: [your headline]")
2. DO NOT begin with phrases like "The email analyses reveal/show/highlight" as this becomes repetitive
3. Instead, jump directly into the most significant insights and findings
4. Use varied language and sentence structures to maintain reader interest
5. Be specific rather than general whenever possible

ANALYSES TO SUMMARIZE:

{combined_text}

Create a single cohesive summary that captures the essential insights from all these analyses.
"""
        
        try:
            # Always use gpt-4o-mini for batch summaries to save costs and time
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You create concise, insightful summaries of email analyses."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.7,
                max_tokens=1500  # Limit the size of batch summaries
            )
            batch_summary = response.choices[0].message.content
            
            # Save the batch summary (only for main batches, not sub-batches)
            if not str(batch_id).count('.'):  # Only for main batches (not sub-batches with dot in ID)
                batch_dir = os.path.join(self.output_dir, 'batch_summaries')
                os.makedirs(batch_dir, exist_ok=True)
                
                # Format as integer for proper sorting in filenames
                if isinstance(batch_id, str) and batch_id.isdigit():
                    batch_num = int(batch_id)
                else:
                    batch_num = batch_id
                
                batch_file = os.path.join(batch_dir, f'batch_summary_{batch_num:03d}.txt')
                with open(batch_file, 'w', encoding='utf-8') as f:
                    f.write(batch_summary)
                    
            return batch_summary
            
        except Exception as e:
            # If context length is exceeded, split the batch and retry
            error_message = str(e).lower()
            if "context length exceeded" in error_message:
                logger.warning(f"Context length exceeded for batch {batch_id}. Splitting and retrying.")
                
                # If we only have one item, we can't split further - something is wrong
                if len(analyses_batch) <= 1:
                    logger.error(f"Cannot split batch further - single analysis too large: {str(e)}")
                    return f"Error: Analysis too large to process for batch {batch_id}"
                
                # Split the batch in half and process each half
                mid = len(analyses_batch) // 2
                first_half = analyses_batch[:mid]
                second_half = analyses_batch[mid:]
                
                # Process each half separately
                first_summary = self._process_batch_summary(first_half, f"{batch_id}.1")
                second_summary = self._process_batch_summary(second_half, f"{batch_id}.2")
                
                # Combine the summaries
                combined_summaries = [first_summary, second_summary]
                return self._process_batch_summary(combined_summaries, f"{batch_id}.combined")
            else:
                logger.error(f"Error creating batch summary {batch_id}: {str(e)}")
                return f"Error creating summary for batch {batch_id}: {str(e)}"
    
    def process(self, status_callback=None, check_cancellation_func=None):
        """Run the complete analysis process with status updates"""
        if status_callback:
            status_callback("Loading emails...", 40)
        
        emails = self.load_emails()
        
        if status_callback:
            status_callback(f"Creating chunks from {len(emails)} emails...", 45)
        
        chunks = self.create_chunks(emails)
        
        if status_callback:
            status_callback(f"Analyzing {len(chunks)} chunks...", 50)
        
        # Create a summaries file to track live progress
        summaries_json = os.path.join(self.output_dir, 'summaries.json')
        with open(summaries_json, 'w', encoding='utf-8') as f:
            json.dump({
                "template": self.template_key,
                "total_chunks": len(chunks),
                "summaries": [],
                "batch_summaries": []
            }, f)
        
        # Process chunks in parallel for faster analysis
        max_concurrent = 25  # Adjusted to 25 chunks at a time for faster processing without context issues
        analyses = [None] * len(chunks)  # Pre-allocate list to maintain order
        active_threads = []
        next_chunk_index = 0
        completed_chunks = 0
        batch_size = 15  # Reduced to 15 analyses per batch to prevent context length exceeded errors
        batch_analyses = []
        batch_number = 1
        batch_summaries = []
        
        def analyze_chunk_thread(chunk, chunk_idx, result_idx):
            try:
                # Check for cancellation before starting work
                if check_cancellation_func and check_cancellation_func():
                    logger.info(f"Cancelling chunk analysis for chunk {chunk_idx+1} before processing")
                    return False
                    
                # Save chunk for reference
                chunk_file = os.path.join(self.output_dir, 'chunks', f'chunk_{chunk_idx+1:03d}.txt')
                with open(chunk_file, 'w', encoding='utf-8') as f:
                    f.write(chunk)
                
                # Check for cancellation again before making API call
                if check_cancellation_func and check_cancellation_func():
                    logger.info(f"Cancelling chunk analysis for chunk {chunk_idx+1} before API call")
                    return False
                    
                # Analyze chunk
                analysis = self.analyze_chunk(chunk, chunk_idx+1)
                
                # Check for cancellation after API call before saving results
                if check_cancellation_func and check_cancellation_func():
                    logger.info(f"Cancelling chunk analysis for chunk {chunk_idx+1} after API call")
                    return False
                
                # Save analysis
                analysis_file = os.path.join(self.output_dir, 'analysis', f'analysis_{chunk_idx+1:03d}.txt')
                with open(analysis_file, 'w', encoding='utf-8') as f:
                    f.write(analysis)
                
                # Store the analysis in the correct position
                analyses[result_idx] = analysis
                
                # Update global progress (avoid updating UI from threads - will be done in main thread)
                return True
                
            except Exception as e:
                logger.error(f"Error analyzing chunk {chunk_idx+1}: {str(e)}")
                if status_callback:
                    progress = 50 + int(30 * ((chunk_idx+1) / len(chunks)))
                    status_callback(f"Error analyzing chunk {chunk_idx+1}: {str(e)}", progress, error=True)
                raise e
        
        # Start processing chunks
        while next_chunk_index < len(chunks) or active_threads or batch_analyses:
            # Check for cancellation
            if check_cancellation_func and check_cancellation_func():
                logger.info("Analysis cancellation detected in main processing loop, stopping all processing")
                if status_callback:
                    status_callback("Analysis cancelled by user", 0, error="Analysis cancelled by user")
                
                # Stop starting new threads and clear all queues
                next_chunk_index = len(chunks)  # No more new chunks
                batch_analyses = []  # Clear batch analysis queue
                
                return None
                
            # Start new threads up to max_concurrent
            while next_chunk_index < len(chunks) and len(active_threads) < max_concurrent:
                chunk_idx = next_chunk_index
                thread = threading.Thread(
                    target=analyze_chunk_thread,
                    args=(chunks[chunk_idx], chunk_idx, chunk_idx)
                )
                thread.daemon = True
                thread.start()
                active_threads.append((thread, chunk_idx))
                next_chunk_index += 1
                time.sleep(0.5)  # Small delay between starting threads
            
            # Check for completed threads
            still_active = []
            newly_completed = []
            
            for thread, chunk_idx in active_threads:
                if not thread.is_alive():
                    logger.info(f"Completed analysis of chunk {chunk_idx+1}")
                    completed_chunks += 1
                    newly_completed.append(chunk_idx)
                    
                    # Check if the analysis was successful
                    if analyses[chunk_idx] is not None:
                        batch_analyses.append(analyses[chunk_idx])
                else:
                    still_active.append((thread, chunk_idx))
            
            active_threads = still_active
            
            # Update status with completion information
            if status_callback and newly_completed:
                progress = 50 + int(30 * (completed_chunks / len(chunks)))
                status_callback(
                    f"Analyzing chunks... ({completed_chunks} complete)", 
                    progress
                )
            
            # Process batch summaries if we have enough completed analyses
            if len(batch_analyses) >= batch_size or (not active_threads and batch_analyses and next_chunk_index >= len(chunks)):
                # Create a batch summary
                current_batch = batch_analyses[:batch_size]
                batch_analyses = batch_analyses[batch_size:]
                
                batch_summary = self.create_batch_summary(current_batch, batch_number)
                batch_summaries.append({
                    "batch": batch_number,
                    "summary": batch_summary
                })
                
                # Update summaries json
                with open(summaries_json, 'r', encoding='utf-8') as f:
                    summaries_data = json.load(f)
                
                summaries_data["batch_summaries"] = batch_summaries
                
                with open(summaries_json, 'w', encoding='utf-8') as f:
                    json.dump(summaries_data, f, indent=2)
                
                # Update UI with batch summary
                if status_callback:
                    status_callback(
                        f"Analyzing chunks... ({completed_chunks} complete)", 
                        progress, 
                        summary=batch_summary
                    )
                
                batch_number += 1
            
            # Small delay before checking threads again
            time.sleep(1)
        
        # Check if any analysis failed
        if None in analyses:
            if status_callback:
                status_callback("One or more chunks failed to analyze", 80, error=True)
            return None
            
        # Filter out any None values just in case
        analyses = [a for a in analyses if a is not None]
        
        # Create a separate file with all batch summaries
        all_batch_summaries_file = os.path.join(self.output_dir, 'batch_summaries', 'all_batch_summaries.txt')
        with open(all_batch_summaries_file, 'w', encoding='utf-8') as f:
            f.write("# EMAIL ANALYSIS - KEY INSIGHTS\n\n")
            for i, summary in enumerate(batch_summaries):
                f.write(f"## Batch {i+1}\n\n")
                f.write(f"{summary['summary']}\n\n")
                f.write("---\n\n")
        
        if status_callback:
            status_callback("Creating final synthesis...", 90)
        
        try:
            synthesis = self.synthesize_findings(analyses)
            synthesis_file = os.path.join(self.output_dir, 'synthesis', 'final_synthesis.txt')
            with open(synthesis_file, 'w', encoding='utf-8') as f:
                f.write(synthesis)
            
            # We now have two separate result files
            insights_file = all_batch_summaries_file
            final_synthesis_file = synthesis_file
            
            if status_callback:
                status_callback("Analysis complete!", 100, 
                               result_file=final_synthesis_file,
                               insights_file=insights_file)
            
            return final_synthesis_file
            
        except Exception as e:
            if status_callback:
                status_callback(f"Error creating synthesis: {str(e)}", 90, error=True)
            return None

def process_pst_file(pst_path, output_dir, api_key, model="gpt-4o", template_key="teams_migration", custom_prompt=None, session_id=None):
    """Process a PST file and analyze its contents"""
    # Get the processing status for this session
    processing_status = get_processing_status(session_id)
    
    # Set up a cancellation flag that can be checked across threads
    cancel_event = threading.Event()
    
    # Check for cancellation
    def check_cancellation():
        # First check our local event flag
        if cancel_event.is_set():
            return True
            
        # Then refresh the status to catch changes
        current_status = get_processing_status(session_id)
        if current_status.get('status') == 'cancelled':
            # Set our local flag to ensure all threads know we're cancelled
            cancel_event.set()
            return True
            
        return False
    
    def update_status(message, progress, error=None, result_file=None, insights_file=None, summary=None):
        # Get the current status to ensure we're working with the latest
        current_status = get_processing_status(session_id)
        
        # Update the status
        current_status['message'] = message
        current_status['progress'] = progress
        current_status['error'] = error
        current_status['last_activity'] = time.time()
        
        # Store the latest summary if provided
        if summary:
            if 'summaries' not in current_status:
                current_status['summaries'] = []
            current_status['summaries'].append(summary)
            # Keep only the latest 10 summaries to avoid context getting too large
            if len(current_status['summaries']) > 10:
                current_status['summaries'] = current_status['summaries'][-10:]
        
        if error:
            current_status['status'] = 'error'
        elif result_file:
            current_status['status'] = 'completed'
            current_status['result_file'] = result_file
            if insights_file:
                current_status['insights_file'] = insights_file
        else:
            # Only update to processing if not cancelled
            if current_status['status'] != 'cancelled':
                current_status['status'] = 'processing'
    
    try:
        # Check if the file still exists
        if not os.path.exists(pst_path):
            error_msg = f"PST file not found: {pst_path}"
            update_status("Failed to find PST file", 0, error=error_msg)
            return
            
        # Check if we're running in Docker
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER", False)
        
        if in_docker:
            # In Docker we should have readpst directly available
            if not os.path.exists("/usr/bin/readpst"):
                error_msg = "readpst command not found in Docker environment."
                update_status(error_msg, 0, error=error_msg)
                return
        else:
            # Not in Docker, use the wrapper script
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'readpst_wrapper.py')
            if not os.path.exists(script_path):
                error_msg = "readpst_wrapper.py script not found."
                update_status(error_msg, 0, error=error_msg)
                return
                
            # Make the script executable
            if not os.access(script_path, os.X_OK):
                os.chmod(script_path, 0o755)
                
            # Test the wrapper script
            try:
                result = subprocess.run([sys.executable, script_path, '--version'], 
                                       check=False, capture_output=True)
                
                if result.returncode != 0:
                    stderr = result.stderr.decode('utf-8', errors='ignore')
                    stdout = result.stdout.decode('utf-8', errors='ignore')
                    error_msg = "readpst command not found. Please install libpst."
                    update_status(error_msg, 0, error=error_msg)
                    return
            except Exception as e:
                error_msg = f"Error testing readpst wrapper: {str(e)}"
                update_status(error_msg, 0, error=error_msg)
                return
        
        # Extract emails from PST
        extractor = PSTExtractor(pst_path, output_dir)
        json_file = extractor.process(update_status)
        
        if not json_file:
            error_msg = "PST extraction failed. No emails were extracted."
            update_status("Failed to extract emails from PST file", 0, error=error_msg)
            return
        
        # Verify the JSON file exists and has content
        if not os.path.exists(json_file) or os.path.getsize(json_file) == 0:
            error_msg = f"JSON file is empty or does not exist: {json_file}"
            update_status("Extraction produced an empty result", 0, error=error_msg)
            return
            
        # Check if extracted emails are valid
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                emails = json.load(f)
                
            if not emails or not isinstance(emails, list) or len(emails) == 0:
                error_msg = "No emails found in the PST file"
                update_status(error_msg, 0, error=error_msg)
                return
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format in extracted emails: {str(e)}"
            update_status("Failed to parse extracted emails", 0, error=error_msg)
            return
            
        # Analyze emails
        analyzer = EmailAnalyzer(json_file, output_dir, api_key, model, template_key, custom_prompt)
        synthesis_file = analyzer.process(update_status, check_cancellation)
        
        if not synthesis_file:
            error_msg = "Email analysis failed. No synthesis was generated."
            update_status("Failed to analyze emails", 0, error=error_msg)
            return
        
    except Exception as e:
        error_msg = f"An error occurred during processing: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        update_status(error_msg, 0, error=str(e))

@app.route('/')
def index():
    """Render the homepage with the file upload form"""
    # Pass along whether a trial key is available to the template
    has_trial_key = bool(TRIAL_API_KEY)
    return render_template('index.html', templates=ANALYSIS_TEMPLATES, has_trial_key=has_trial_key)

@app.route('/download-template')
def download_template():
    """Provide a downloadable template example"""
    template_content = """# CUSTOM EMAIL ANALYSIS TEMPLATE - PST MINER

## Context
These emails contain communications related to [PROJECT/SUBJECT]. This analysis will examine patterns, trends, and key information to provide actionable insights.

## Analysis Objectives
Conduct a detailed examination of these email communications to analyze:

### 1. COMMUNICATION PATTERNS
- **Response Times**: Average time between messages and patterns in response delays
- **Key Participants**: Primary senders and recipients, identifying central figures
- **Information Flow**: How information moves through the organization
- **Meeting Scheduling**: Frequency and patterns in meeting arrangements

### 2. PROJECT EXECUTION
- **Timeline Adherence**: Scheduled vs. actual milestone completion dates
- **Issue Tracking**: Problems raised and their resolution status
- **Decision Making**: How and by whom decisions are made
- **Resource Allocation**: How resources are assigned and managed

### 3. CONTENT ANALYSIS
- **Key Topics**: Main subjects discussed across communications
- **Sentiment Trends**: Changes in tone or attitude over time
- **Action Items**: Tasks assigned and their completion status
- **Success Indicators**: Evidence of project progress and achievements

## Emails to Analyze

{emails}

## Output Requirements

### 1. Executive Summary
- Provide a concise overview of the most significant findings
- Highlight 3-5 key insights that require attention
- Include recommendations for immediate action

### 2. Detailed Analysis
- Organize findings by category with specific evidence from emails
- Include relevant quotes or references to specific messages
- Present data visualizations where appropriate

### 3. Timeline Reconstruction
- Create a chronological view of key events
- Identify critical decision points and their outcomes
- Note any significant delays or acceleration periods

### 4. Recommendations
- Provide actionable, prioritized next steps
- Include rationale for each recommendation
- Suggest implementation approaches where relevant

Your analysis should be objective, evidence-based, and focused on providing valuable insights that can inform future decisions and actions.
"""
    return Response(
        template_content,
        mimetype="text/plain",
        headers={"Content-disposition": "attachment; filename=custom_template_example.txt"}
    )

@app.route('/status')
def status():
    # Get session_id from query parameters or use default
    session_id = request.args.get('session_id')
    
    # If no session ID provided, return an error
    if not session_id:
        # For backwards compatibility, if there's only one session, return that
        if len(processing_statuses) == 1:
            session_id = list(processing_statuses.keys())[0]
        else:
            return jsonify({
                'status': 'error',
                'error': 'Session ID is required',
                'message': 'No session ID provided'
            }), 400
    
    # Get processing status for this session
    processing_status = get_processing_status(session_id)
    
    # Update last activity time
    processing_status['last_activity'] = time.time()
    
    # Make a copy to avoid modifying the original
    status_data = processing_status.copy()
    # Remove internal tracking fields
    if 'last_activity' in status_data:
        del status_data['last_activity']
    
    # Return the status
    return jsonify(status_data)
    
@app.route('/cancel-analysis', methods=['POST'])
def cancel_analysis():
    """Cancel the current analysis process"""
    # Get session_id from request
    session_id = request.json.get('session_id') if request.is_json else request.form.get('session_id')
    
    # If no session ID provided, return an error
    if not session_id:
        # For backwards compatibility, if there's only one session, use that
        if len(processing_statuses) == 1:
            session_id = list(processing_statuses.keys())[0]
        else:
            return jsonify({
                'status': 'error', 
                'error': 'Session ID is required',
                'message': 'No session ID provided'
            }), 400
    
    # Get processing status for this session
    processing_status = get_processing_status(session_id)
    
    if processing_status['status'] == 'processing':
        # Set status to cancelled
        processing_status['status'] = 'cancelled'
        processing_status['message'] = 'Analysis cancelled by user'
        processing_status['error'] = 'Analysis cancelled by user'
        processing_status['last_activity'] = time.time()
        logger.info(f"Analysis cancelled by user - session {session_id}")
        
        # The actual stopping of the process will be handled by the polling mechanism
        # After 5 seconds, reset the status to idle to allow new analysis
        def reset_status_after_delay():
            time.sleep(5)
            # Get the current status again to ensure we're working with the latest
            current_status = get_processing_status(session_id)
            if current_status['status'] == 'cancelled':
                current_status.update({
                    'status': 'idle',
                    'progress': 0,
                    'message': 'Ready for new analysis',
                    'error': None,
                    'result_file': None,
                    'summaries': [],
                    'last_activity': time.time()
                })
                logger.info(f"Status reset to idle after cancellation - session {session_id}")
        
        # Start a thread to reset the status after a delay
        reset_thread = threading.Thread(target=reset_status_after_delay)
        reset_thread.daemon = True
        reset_thread.start()
        
        return jsonify({'status': 'cancelled', 'message': 'Analysis cancelled successfully'})
    
    return jsonify({'status': processing_status['status'], 'message': 'No active analysis to cancel'})

# Dictionary to track results by unique ID
result_pages = {}

@app.route('/results/<result_id>')
def results_with_id(result_id):
    """Render the results page for a specific ID"""
    if result_id not in result_pages:
        return redirect(url_for('index'))
    
    job_data = result_pages[result_id]
    
    # Read the synthesis file
    synthesis_content = ""
    if job_data['result_file'] and os.path.exists(job_data['result_file']):
        with open(job_data['result_file'], 'r', encoding='utf-8') as f:
            synthesis_content = f.read()
    
    # Read the insights file
    insights_content = ""
    if 'insights_file' in job_data and job_data['insights_file'] and os.path.exists(job_data['insights_file']):
        with open(job_data['insights_file'], 'r', encoding='utf-8') as f:
            insights_content = f.read()
    
    return render_template('results.html', 
                          synthesis=synthesis_content,
                          insights=insights_content,
                          result_id=result_id)

@app.route('/results')
def results():
    """Redirect to the results page with the current job ID"""
    # Get session_id from query parameters
    session_id = request.args.get('session_id')
    
    # If no session ID provided, try to find a completed session
    if not session_id:
        # For backwards compatibility, check if there's only one session
        if len(processing_statuses) == 1:
            session_id = list(processing_statuses.keys())[0]
        else:
            # Look for any completed session
            completed_sessions = [sid for sid, status in processing_statuses.items() 
                                if status.get('status') == 'completed' and 'current_job' in status]
            if completed_sessions:
                session_id = completed_sessions[0]
            else:
                # If no completed session found, redirect to index
                return redirect(url_for('index'))
    
    # Get processing status for this session
    processing_status = get_processing_status(session_id)
    
    if processing_status['status'] != 'completed' or 'current_job' not in processing_status:
        return redirect(url_for('index'))
    
    job_id = processing_status['current_job']
    result_id = processing_status.get('result_id', None)
    
    if not result_id:
        return redirect(url_for('index'))
    
    # Save the results data in our dictionary for later access
    if result_id not in result_pages:
        result_pages[result_id] = {
            'result_file': processing_status['result_file'],
            'insights_file': processing_status.get('insights_file', None),
            'session_id': session_id
        }
    
    return redirect(url_for('results_with_id', result_id=result_id))

@app.route('/download/<result_id>')
def download_with_id(result_id):
    if result_id in result_pages and result_pages[result_id]['result_file'] and os.path.exists(result_pages[result_id]['result_file']):
        return send_file(result_pages[result_id]['result_file'], as_attachment=True, 
                         download_name="complete_synthesis.txt")
    return "No result file available", 404

@app.route('/download-insights/<result_id>')
def download_insights_with_id(result_id):
    if result_id in result_pages and 'insights_file' in result_pages[result_id] and result_pages[result_id]['insights_file'] and os.path.exists(result_pages[result_id]['insights_file']):
        return send_file(result_pages[result_id]['insights_file'], as_attachment=True,
                         download_name="key_insights.txt")
    return "No insights file available", 404

@app.route('/download')
def download():
    if 'result_id' in processing_status and processing_status['result_id'] in result_pages:
        return redirect(url_for('download_with_id', result_id=processing_status['result_id']))
    
    if processing_status['result_file'] and os.path.exists(processing_status['result_file']):
        return send_file(processing_status['result_file'], as_attachment=True, 
                         download_name="complete_synthesis.txt")
    return "No result file available", 404

@app.route('/download-insights')
def download_insights():
    if 'result_id' in processing_status and processing_status['result_id'] in result_pages:
        return redirect(url_for('download_insights_with_id', result_id=processing_status['result_id']))
    
    if 'insights_file' in processing_status and processing_status['insights_file'] and os.path.exists(processing_status['insights_file']):
        return send_file(processing_status['insights_file'], as_attachment=True,
                         download_name="key_insights.txt")
    return "No insights file available", 404

@app.route('/check-trial-key')
def check_trial_key():
    """Check if the Community Monthly Limited Key is valid (not over limit)"""
    if not TRIAL_API_KEY:
        return jsonify({
            'valid': False, 
            'error': 'missing_key', 
            'message': 'No Community Monthly Limited Key configured',
            'show_button': False  # Indicate that the button should be hidden
        }), 200
    
    try:
        # Create OpenAI client with community key
        client = OpenAI(api_key=TRIAL_API_KEY)
        
        # Make a minimal API call to test if the key is working and not hitting limits
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=1
        )
        
        # Get allowed models for this key
        allowed_models = []
        if ALLOWED_MODELS_WITH_PRELOADED_KEY:
            allowed_models = [model.strip() for model in ALLOWED_MODELS_WITH_PRELOADED_KEY.split(',')]
        
        # If we get here, the key is valid
        return jsonify({
            'valid': True,
            'allowed_models': allowed_models,
            'show_button': True  # The button should be shown
        }), 200
    except Exception as e:
        error_message = str(e).lower()
        if "rate limit" in error_message or "quota" in error_message or "billing" in error_message:
            return jsonify({
                'valid': False, 
                'message': 'Monthly quota exceeded for Community Limited Key. Please use your own API key.',
                'show_button': True  # Still show the button but with error
            }), 200
        else:
            logger.error(f"Error checking Community Monthly Limited Key: {e}")
            return jsonify({
                'valid': False, 
                'message': f'Error validating Community Monthly Limited Key: {str(e)}',
                'show_button': True  # Still show the button but with error
            }), 200

@app.route('/upload', methods=['POST'])
def upload():
    try:
        logger.info("Upload request received")
        
        # Generate a unique session ID if not provided
        session_id = request.form.get('session_id')
        if not session_id:
            session_id = f"session_{secrets.token_hex(16)}"
        
        # Clean up old sessions
        cleanup_old_sessions()
            
        # Get processing status for this session
        processing_status = get_processing_status(session_id)
        
        # Check if processing is already in progress for this session
        if processing_status['status'] == 'processing':
            logger.warning(f"Rejected upload: A job is already in progress for session {session_id}")
            return jsonify({
                'error': 'A job is already in progress. Please wait for it to complete or cancel it.'
            }), 400
        
        # Reset status for this session
        processing_status.update({
            'status': 'idle',
            'progress': 0,
            'message': '',
            'error': None,
            'result_file': None,
            'summaries': [],
            'last_activity': time.time()
        })
        
        # Check if using trial key
        using_trial_key = request.form.get('using_trial_key') == 'true'
        
        # Get API key
        api_key = request.form.get('api_key')
        if using_trial_key:
            # Use the trial key instead of the one provided
            if not TRIAL_API_KEY:
                logger.warning("Rejected upload: Trial key requested but no trial key available")
                return jsonify({'error': 'Trial API key is not available'}), 400
            api_key = TRIAL_API_KEY
            logger.info("Using trial API key")
        elif not api_key:
            logger.warning("Rejected upload: No API key provided")
            return jsonify({'error': 'API key is required'}), 400
        
        # Validate API key before proceeding
        try:
            # Create OpenAI client with provided key
            client = OpenAI(api_key=api_key)
            
            # Make a minimal API call to test if the key is valid
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Test"}],
                max_tokens=1
            )
            logger.info("API key validation successful")
        except Exception as e:
            error_message = str(e)
            logger.warning(f"API key validation failed: {error_message}")
            return jsonify({'error': f'Invalid API key: {error_message}'}), 400
        
        logger.info("API key received and validated (not logged for security)")
        
        # Get model selection
        model = request.form.get('model', 'gpt-4o')
        
        # If using trial key, enforce gpt-4o-mini model
        if using_trial_key and model != 'gpt-4o-mini':
            logger.warning(f"Rejected model selection for trial key: {model}. Forcing gpt-4o-mini.")
            model = 'gpt-4o-mini'
        
        logger.info(f"Model selected: {model}")
        
        # Get template selection
        template_key = request.form.get('template', 'teams_migration')
        custom_prompt = request.form.get('custom_prompt')
        logger.info(f"Template selected: {template_key}")
        
        if template_key == 'custom' and not custom_prompt:
            logger.warning("Rejected upload: Custom template selected but no prompt provided")
            return jsonify({'error': 'Custom prompt is required when using custom template'}), 400
        
        # Get PST file
        if 'pst_file' not in request.files:
            logger.warning("Rejected upload: No file part in the request")
            return jsonify({'error': 'No file uploaded'}), 400
        
        pst_file = request.files['pst_file']
        logger.info(f"File received: {pst_file.filename}")
        
        if pst_file.filename == '':
            logger.warning("Rejected upload: Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        if not pst_file.filename.lower().endswith('.pst'):
            logger.warning(f"Rejected upload: Not a PST file - {pst_file.filename}")
            return jsonify({'error': 'The uploaded file must be a .pst file'}), 400
        
        # Save file
        filename = secure_filename(pst_file.filename)
        pst_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        logger.info(f"Saving PST file to: {pst_path}")
        pst_file.save(pst_path)
        
        # Verify file was saved correctly
        if not os.path.exists(pst_path):
            logger.error(f"File save failed: {pst_path} does not exist")
            return jsonify({'error': 'Failed to save the uploaded file'}), 500
            
        file_size = os.path.getsize(pst_path)
        logger.info(f"File saved successfully. Size: {file_size} bytes")
        
        if file_size == 0:
            logger.error("Uploaded file is empty (0 bytes)")
            return jsonify({'error': 'The uploaded file is empty'}), 400
        
        # Create output directory
        job_id = f"job_{int(time.time())}"
        output_dir = os.path.join(app.config['RESULTS_FOLDER'], job_id)
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Created output directory: {output_dir}")
        
        # Generate a unique result ID
        result_id = f"r{secrets.token_hex(16)}"
        
        # Start processing thread
        processing_status['status'] = 'processing'
        processing_status['message'] = 'Starting job...'
        processing_status['current_job'] = job_id
        processing_status['result_id'] = result_id
        processing_status['session_id'] = session_id
        processing_status['last_activity'] = time.time()
        
        thread = threading.Thread(
            target=process_pst_file, 
            args=(pst_path, output_dir, api_key, model, template_key, custom_prompt, session_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing',
            'message': 'Job started',
            'job_id': job_id
        })
        
    except Exception as e:
        error_msg = f"Error during upload: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return jsonify({'error': error_msg}), 500

if __name__ == '__main__':
    # In production use gunicorn
    # For development:
    port = int(os.environ.get("PORT", 5050))
    
    # Check if we're running in Docker
    in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER", False)
    
    if in_docker:
        logger.info("Running in Docker environment")
        # In Docker, readpst should be available at /usr/bin/readpst
        if os.path.exists("/usr/bin/readpst"):
            logger.info("Found readpst at /usr/bin/readpst")
            # Check if it works
            try:
                result = subprocess.run(["/usr/bin/readpst", "-V"], check=False, capture_output=True)
                logger.info(f"readpst test result: {result.returncode}")
                if result.stdout:
                    logger.info(f"readpst output: {result.stdout.decode('utf-8', errors='ignore')}")
                if result.stderr:
                    logger.info(f"readpst error: {result.stderr.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logger.error(f"Error testing readpst: {str(e)}")
        else:
            logger.error("readpst not found at expected Docker location: /usr/bin/readpst")
    else:
        # Check if the readpst wrapper script is available
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'readpst_wrapper.py')
        if not os.path.exists(script_path):
            logger.error("readpst_wrapper.py script not found in the application directory")
        else:
            # Make the script executable
            if not os.access(script_path, os.X_OK):
                os.chmod(script_path, 0o755)
                logger.info(f"Made {script_path} executable")
            
            # Test the wrapper script
            try:
                result = subprocess.run([sys.executable, script_path, '--version'], 
                                       check=False, capture_output=True)
                
                if result.returncode == 0:
                    logger.info("readpst wrapper script is working correctly")
                    stdout = result.stdout.decode('utf-8', errors='ignore')
                    logger.info(f"readpst version: {stdout}")
                else:
                    stderr = result.stderr.decode('utf-8', errors='ignore')
                    stdout = result.stdout.decode('utf-8', errors='ignore')
                    logger.warning(f"readpst wrapper script test failed: {stderr}")
                    logger.warning(f"Output: {stdout}")
                    logger.error("readpst may not be properly installed. Install with: brew install libpst")
            except Exception as e:
                logger.error(f"Error testing readpst wrapper: {str(e)}")
                logger.error(traceback.format_exc())
                logger.error("readpst may not be properly installed. Install with: brew install libpst")
        
    # Start the server
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)