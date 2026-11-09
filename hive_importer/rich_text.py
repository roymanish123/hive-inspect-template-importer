"""Keep original HTML verbatim; derive a safe, inspectable rendering separately."""
import re
from html.parser import HTMLParser

import bleach
from bleach.css_sanitizer import CSSSanitizer

TAGS = {"p", "br", "div", "span", "strong", "b", "em", "i", "u", "s", "del", "sub", "sup",
        "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code",
        "a", "img", "table", "thead", "tbody", "tr", "td", "th", "hr"}
ATTRS = {"*": ["style"], "a": ["href", "title"], "img": ["src", "alt", "title", "width", "height"],
         "td": ["colspan", "rowspan"], "th": ["colspan", "rowspan"]}
CSS = CSSSanitizer(allowed_css_properties=["color", "background-color", "font-weight", "font-style",
    "text-decoration", "text-align", "font-size", "font-family", "vertical-align", "list-style-type"])


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.issues = set()
        self.text = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag not in TAGS:
            self.issues.add(f"Unsupported <{tag}> element is retained in source, omitted from preview.")
        if tag in {"script", "style"}:
            self.blocked += 1
        if tag == "img":
            self.issues.add("External image URL retained; images are not downloaded or loaded automatically.")
        for key, value in attrs:
            if key not in ATTRS.get(tag, []) + ATTRS["*"]:
                self.issues.add(f"Attribute '{key}' on <{tag}> is retained in source, omitted from preview.")
            if key in {"href", "src"} and value:
                # Browser URL parsing strips control/space characters before protocol handling.
                cleaned = re.sub(r"[\s\x00-\x20\x7f-\x9f]", "", value).lower()
                if not cleaned.startswith(("https://", "http://", "mailto:" if key == "href" else "https://", "#")):
                    self.issues.add("Unsafe or relative URL retained in source, disabled in preview.")
            if key == "style" and value:
                safe = CSS.sanitize_css(value)
                props = {x.split(":", 1)[0].strip().lower() for x in value.split(";") if ":" in x}
                if props - set(CSS.allowed_css_properties) or "url(" in value.lower() or "expression(" in value.lower():
                    self.issues.add("Unsupported CSS retained in source, omitted from preview.")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.blocked:
            self.blocked -= 1
        if tag in {"p", "div", "li", "br", "tr"}:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.blocked:
            self.text.append(data)


def render_html(original):
    inspector = Inspector()
    inspector.feed(original)
    # Remove executable element bodies in the derivative only, never from original.
    derivative = re.sub(r"<(script|style)\b[^>]*>[\s\S]*?(?:</\1\s*>|$)", "", original, flags=re.I)
    def allow_attr(tag, name, value):
        if name not in ATTRS.get(tag, []) + ATTRS["*"]:
            return False
        if name in {"src", "href"}:
            compact = re.sub(r"[\s\x00-\x20\x7f-\x9f]", "", value).lower()
            return compact.startswith(("https://", "http://", "#")) or (name == "href" and compact.startswith("mailto:"))
        return True
    safe = bleach.clean(derivative, tags=TAGS, attributes=allow_attr, protocols=["http", "https", "mailto"],
                        strip=True, css_sanitizer=CSS)
    # New tabs cannot control the app. External images are inert until explicitly enabled in UI.
    safe = re.sub(r'<a\b', '<a target="_blank" rel="noopener noreferrer"', safe)
    safe = re.sub(r'(<img\b[^>]*?)\ssrc=', r'\1 data-source-src=', safe)
    return {"safe_html": safe, "plain_text": "".join(inspector.text), "issues": sorted(inspector.issues)}
