import html
import math
import posixpath
import re

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
MERMAID_RE = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)
ATTR_RE = re.compile(r'(?P<attr>\b(?:src|href))=(?P<q>["\'])(?P<url>[^"\']*)(?P=q)')
ABSOLUTE_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|/)", re.I)
H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico")


def parse_frontmatter(text):
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    return meta, text[match.end():]


_FORMATTER = HtmlFormatter(nowrap=True)


def _highlight(code, lang, _attrs):
    lang = (lang or "").strip().lower()
    if lang == "mermaid":
        return f'<pre class="mermaid">{html.escape(code.strip())}</pre>'
    try:
        lexer = get_lexer_by_name(lang) if lang else None
    except ClassNotFound:
        lexer = None
    body = pygments_highlight(code, lexer, _FORMATTER) if lexer else html.escape(code)
    return f'<pre class="highlight"><code class="language-{html.escape(lang)}">{body}</code></pre>'


def _markdown_parser():
    md = MarkdownIt("commonmark", {"html": True, "highlight": _highlight})
    md.enable(["table", "strikethrough"])
    md.use(anchors_plugin, min_level=2, max_level=3, permalink=True, permalinkSymbol="#")
    md.use(footnote_plugin).use(tasklists_plugin)
    return md


def _toc(tokens):
    toc = []
    for i, tok in enumerate(tokens):
        if tok.type != "heading_open" or tok.tag not in ("h2", "h3") or not tok.attrGet("id"):
            continue
        name = html.escape("".join(ch.content for ch in tokens[i + 1].children or [] if ch.type in ("text", "code_inline")))
        item = {"id": tok.attrGet("id"), "name": name, "children": []}
        if tok.tag == "h3" and toc:
            toc[-1]["children"].append(item)
        else:
            toc.append(item)
    return toc


def render_markdown(text):
    md = _markdown_parser()
    tokens = md.parse(text or "")
    return md.renderer.render(tokens, md.options, {}), _toc(tokens)


def rewrite_relative_urls(html_text, owner, repo, branch, base_dir=""):
    """Aponta links/imagens relativos do README para o GitHub."""

    def repl(m):
        url = m.group("url").strip()
        if not url or ABSOLUTE_RE.match(url):
            return m.group(0)
        path, _, frag = url.partition("#")
        full = posixpath.normpath(posixpath.join(base_dir, path)).lstrip("./")
        is_image = m.group("attr") == "src" or path.lower().endswith(IMAGE_EXTS)
        if is_image:
            new = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{full}"
        else:
            new = f"https://github.com/{owner}/{repo}/blob/{branch}/{full}"
        if frag:
            new += f"#{frag}"
        return f'{m.group("attr")}={m.group("q")}{new}{m.group("q")}'

    return ATTR_RE.sub(repl, html_text)


def strip_markdown(text):
    text = MERMAID_RE.sub("", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_>#|~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_title(readme):
    if not readme:
        return None
    m = H1_RE.search(readme)
    return m.group(1).strip() if m else None


def remove_first_h1(readme):
    return H1_RE.sub("", readme, count=1)


def extract_summary(readme, limit=200):
    if not readme:
        return ""
    for block in re.split(r"\n\s*\n", remove_first_h1(readme)):
        block = block.strip()
        if not block or block.startswith(("#", "```", "|", "![", "<", "---")):
            continue
        plain = strip_markdown(block)
        if len(plain) >= 30:
            return plain if len(plain) <= limit else plain[: limit - 1].rsplit(" ", 1)[0] + "…"
    return ""


def reading_time(text):
    words = len(strip_markdown(text or "").split())
    return max(1, math.ceil(words / 200))


ACRONYMS = {"cka", "ckad", "cks", "oci", "aws", "gcp", "k8s", "iac", "sre", "api", "ci", "cd", "eks", "aks", "gke", "iam", "vpc", "vcn"}


def prettify_name(name):
    words = re.split(r"[-_\s]+", name)
    return " ".join(
        w.upper() if w.lower() in ACRONYMS else w if w.isupper() else w.capitalize() for w in words if w
    )


def detect_categories(haystack, rules):
    haystack = haystack.lower()
    found = []
    for category, keywords in rules.items():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}(?![a-z0-9])", haystack) for k in keywords):
            found.append(category)
    return found


def slugify(value):
    value = re.sub(r"[^\w\s-]", "", value.lower(), flags=re.U)
    return re.sub(r"[-\s_]+", "-", value).strip("-")
