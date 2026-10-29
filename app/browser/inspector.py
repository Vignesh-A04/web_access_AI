"""Runtime page inspector for DOM accessibility tree extraction and state hashing."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.async_api import Page

from app.logging.setup import get_logger

logger = get_logger("inspector")


@dataclass
class PageObservation:
    """Concise, structured representation of the page state for LLM reasoning."""
    url: str
    title: str
    headings: List[str] = field(default_factory=list)
    interactive_elements: List[Dict[str, Any]] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    text_content_summary: str = ""
    state_hash: str = ""

    def to_summary_text(self) -> str:
        """Produce a clean, concise markdown observation suitable for Gemini."""
        lines = [
            f"### Current Page State",
            f"- **URL**: {self.url}",
            f"- **Title**: {self.title}",
        ]

        if self.headings:
            lines.append(f"- **Key Headings**: {' | '.join(self.headings[:6])}")

        if self.forms:
            lines.append("\n#### Forms Found:")
            for f in self.forms:
                lines.append(f"  - Form [ID: {f.get('id', 'none')}, Action: {f.get('action', '')}, Method: {f.get('method', 'GET')}]")

        if self.interactive_elements:
            lines.append("\n#### Interactive Elements:")
            for el in self.interactive_elements:
                el_id = el.get("element_id")
                tag = el.get("tag")
                el_type = el.get("type", "")
                text = el.get("text") or el.get("aria_label") or el.get("placeholder") or el.get("name") or ""
                extra = []
                if el.get("value"):
                    extra.append(f"value='{el['value']}'")
                if el.get("checked") is not None:
                    extra.append(f"checked={el['checked']}")
                if el.get("options"):
                    opt_preview = ", ".join([f"{o.get('label')}({o.get('value')})" for o in el["options"][:5]])
                    extra.append(f"options=[{opt_preview}]")
                if el.get("disabled"):
                    extra.append("disabled")

                extra_str = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"  - `[{el_id}]` <{tag} type='{el_type}'> \"{text.strip()}\"{extra_str}")
        else:
            lines.append("\n*No interactive form elements or buttons detected on page.*")

        if self.text_content_summary:
            lines.append(f"\n#### Page Body Excerpt:\n{self.text_content_summary[:800]}")

        return "\n".join(lines)


# JavaScript snippet executed inside page context to tag and extract elements
INSPECTION_JS = """
() => {
    // Clean previously assigned data-agent-id attributes if any
    document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute('data-agent-id'));

    let counter = 1;
    const elements = [];
    const forms = [];

    // Helper to check element visibility
    function isVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    }

    // Helper to find associated label text
    function getLabel(el) {
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        if (el.id) {
            const labelEl = document.querySelector(`label[for="${el.id}"]`);
            if (labelEl) return labelEl.innerText.trim();
        }
        const parentLabel = el.closest('label');
        if (parentLabel) return parentLabel.innerText.trim();
        return '';
    }

    // Inspect forms
    document.querySelectorAll('form').forEach(f => {
        forms.push({
            id: f.id || '',
            action: f.action || '',
            method: (f.method || 'GET').toUpperCase()
        });
    });

    // Query interactive candidates: buttons, inputs, selects, textareas, links
    const candidates = document.querySelectorAll(
        'button, input, select, textarea, a[href], [role="button"], [role="link"], [role="checkbox"], [role="menuitem"]'
    );

    candidates.forEach(el => {
        if (!isVisible(el)) return;
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute('type') || '').toLowerCase();

        // Skip hidden inputs
        if (tag === 'input' && type === 'hidden') return;

        const agentId = 'el-' + counter++;
        el.setAttribute('data-agent-id', agentId);

        const item = {
            element_id: agentId,
            tag: tag,
            type: type,
            name: el.getAttribute('name') || '',
            id: el.id || '',
            text: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
            aria_label: getLabel(el) || el.getAttribute('aria-label') || '',
            placeholder: el.getAttribute('placeholder') || '',
            role: el.getAttribute('role') || '',
            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
            value: (el.value !== undefined && tag !== 'button') ? String(el.value).slice(0, 100) : '',
            checked: (tag === 'input' && (type === 'checkbox' || type === 'radio')) ? el.checked : null,
        };

        if (tag === 'select') {
            item.options = Array.from(el.options || []).map(opt => ({
                value: opt.value,
                label: (opt.text || opt.innerText || '').trim()
            }));
        }

        elements.push(item);
    });

    // Extract key headings
    const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
        .filter(isVisible)
        .map(h => (h.innerText || '').trim())
        .filter(t => t.length > 0)
        .slice(0, 8);

    // Visible text summary (clean body text, truncated)
    const bodyClone = document.body ? document.body.cloneNode(true) : null;
    let textSummary = '';
    if (bodyClone) {
        bodyClone.querySelectorAll('script, style, noscript, svg').forEach(n => n.remove());
        textSummary = (bodyClone.innerText || '')
            .replace(/\\s+/g, ' ')
            .trim()
            .slice(0, 1000);
    }

    return {
        headings: headings,
        elements: elements,
        forms: forms,
        text_summary: textSummary
    };
}
"""


async def inspect_page(page: Page) -> PageObservation:
    """Inspect the current live page and produce a structured PageObservation."""
    url = page.url
    title = await page.title()

    try:
        data = await page.evaluate(INSPECTION_JS)
    except Exception as e:
        logger.error(f"Error inspecting page DOM: {e}")
        data = {"headings": [], "elements": [], "forms": [], "text_summary": ""}

    elements = data.get("elements", [])
    forms = data.get("forms", [])
    headings = data.get("headings", [])
    text_summary = data.get("text_summary", "")

    # Compute a deterministic hash of interactive elements + URL for state drift validation
    hash_payload = {
        "url": url,
        "elements": [
            {
                "id": el.get("element_id"),
                "tag": el.get("tag"),
                "name": el.get("name"),
                "value": el.get("value"),
                "checked": el.get("checked"),
                "text": el.get("text"),
            }
            for el in elements
        ],
    }
    state_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode("utf-8")).hexdigest()

    return PageObservation(
        url=url,
        title=title,
        headings=headings,
        interactive_elements=elements,
        forms=forms,
        text_content_summary=text_summary,
        state_hash=state_hash,
    )
