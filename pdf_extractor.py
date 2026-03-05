"""Extract CE data from PDFs using pdfplumber and Claude AI."""
import io
import json
import os

import pdfplumber

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

CE_CATEGORIES = [
    'Financial Planning Process',
    'Insurance & Risk Management',
    'Investments',
    'Income Tax Planning',
    'Retirement Planning & Employee Benefits',
    'Estate Planning',
    'Ethics',
    'Accounting, Cash Flow Management, & Budgeting',
    'Economic & Political Environment',
    'Communications',
    'Marketing and Practice Management',
    'Strategic Thinking',
    'Technology',
    'Diversity, Equity & Inclusion (DEI)',
]

EXTRACTION_PROMPT = """You are extracting Continuing Education (CE) course information from a certificate or completion document.

Analyze the following text and extract the CE course details. The text may come from a PDF certificate, an email confirmation, or both.

Extract the following fields:
- title: The course or program name
- provider: The organization that provided the CE (e.g., CFP Board, AICPA, Kitces, etc.)
- hours: The number of CE/CPE credit hours (as a decimal number, e.g., 2.0)
- date_completed: The completion date in YYYY-MM-DD format
- category: The best matching category from this list:
  {categories}
- description: A brief description of the course content (1-2 sentences)
- confidence: Your confidence in the extraction accuracy — "high" if all fields are clearly present, "medium" if some fields required inference, "low" if significant guessing was needed

Return your response as a JSON object with exactly these fields. If a field cannot be determined, use null for that field.

{context}

Document text:
{text}"""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from all pages of a PDF.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        Concatenated text from all pages, or empty string on failure.
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages.append(page_text)
            return '\n\n'.join(pages)
    except Exception as e:
        print(f"[PDF] Failed to extract text: {e}")
        return ''


def extract_ce_data_from_text(text: str, email_subject: str = '', email_body: str = '') -> dict:
    """Use Claude to extract structured CE data from text.

    Args:
        text: Extracted PDF text or raw document text.
        email_subject: Optional email subject for additional context.
        email_body: Optional email body for additional context.

    Returns:
        Dict with extracted fields + confidence, or error dict on failure.
    """
    if not ANTHROPIC_API_KEY:
        return {
            'title': None,
            'provider': None,
            'hours': None,
            'date_completed': None,
            'category': None,
            'description': None,
            'confidence': None,
            'error_message': 'AI extraction not configured',
        }

    # Build context from email metadata if available
    context_parts = []
    if email_subject:
        context_parts.append(f"Email subject: {email_subject}")
    if email_body:
        context_parts.append(f"Email body:\n{email_body}")
    context = '\n'.join(context_parts) if context_parts else ''

    categories_str = '\n  '.join(f'- {c}' for c in CE_CATEGORIES)

    prompt = EXTRACTION_PROMPT.format(
        categories=categories_str,
        context=context,
        text=text or '(no text extracted from document)',
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': prompt}],
        )

        response_text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        data = json.loads(response_text)

        return {
            'title': data.get('title'),
            'provider': data.get('provider'),
            'hours': data.get('hours'),
            'date_completed': data.get('date_completed'),
            'category': data.get('category'),
            'description': data.get('description'),
            'confidence': data.get('confidence', 'low'),
            'error_message': None,
        }

    except json.JSONDecodeError as e:
        print(f"[PDF] Failed to parse Claude response as JSON: {e}")
        return {
            'title': None, 'provider': None, 'hours': None,
            'date_completed': None, 'category': None, 'description': None,
            'confidence': None,
            'error_message': f'Failed to parse AI response: {e}',
        }
    except Exception as e:
        print(f"[PDF] Claude API error: {e}")
        return {
            'title': None, 'provider': None, 'hours': None,
            'date_completed': None, 'category': None, 'description': None,
            'confidence': None,
            'error_message': f'AI extraction failed: {e}',
        }
