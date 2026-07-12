#!/usr/bin/env python3
"""Build the CCAF Study Hub: artifact HTML + standalone GitHub Pages index.html."""
import json, re, sys, base64, urllib.request
from pathlib import Path

import markdown  # pip install markdown

FONT_SRC = [
    ('OpenDyslexic', 400, 'https://cdn.jsdelivr.net/npm/@fontsource/opendyslexic@5/files/opendyslexic-latin-400-normal.woff2'),
    ('OpenDyslexic', 700, 'https://cdn.jsdelivr.net/npm/@fontsource/opendyslexic@5/files/opendyslexic-latin-700-normal.woff2'),
    ('Atkinson Hyperlegible', 400, 'https://cdn.jsdelivr.net/npm/@fontsource/atkinson-hyperlegible@5/files/atkinson-hyperlegible-latin-400-normal.woff2'),
    ('Atkinson Hyperlegible', 700, 'https://cdn.jsdelivr.net/npm/@fontsource/atkinson-hyperlegible@5/files/atkinson-hyperlegible-latin-700-normal.woff2'),
]

def font_faces():
    """Fetch dyslexia fonts (cached to disk) and return @font-face CSS with data URIs. Best-effort."""
    cache = BUILD / 'fontcache'
    cache.mkdir(exist_ok=True)
    rules = []
    for fam, wt, url in FONT_SRC:
        fn = cache / (url.rsplit('/', 1)[-1])
        try:
            if not fn.exists():
                with urllib.request.urlopen(url, timeout=20) as r:
                    fn.write_bytes(r.read())
            b64 = base64.b64encode(fn.read_bytes()).decode()
            rules.append(f"@font-face{{font-family:'{fam}';font-weight:{wt};font-style:normal;font-display:swap;"
                         f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
        except Exception as e:
            print(f'  font skip {fam} {wt}: {e}')
    return '\n'.join(rules)

BUILD = Path(__file__).resolve().parent
KIT = BUILD.parent

DOC_SPECS = [
    # (relative path, group, fallback title)
    ('playbook/00-answer-physics.md', 'Start here', 'Answer Physics'),
    ('scenarios/01-customer-support-agent.md', 'Scenario walkthroughs', 'Customer Support Resolution Agent'),
    ('scenarios/02-claude-code-codegen.md', 'Scenario walkthroughs', 'Code Generation with Claude Code'),
    ('scenarios/03-multi-agent-research.md', 'Scenario walkthroughs', 'Multi-Agent Research System'),
    ('scenarios/04-dev-productivity-agent.md', 'Scenario walkthroughs', 'Developer Productivity with Claude'),
    ('scenarios/05-claude-code-ci.md', 'Scenario walkthroughs', 'Claude Code for Continuous Integration'),
    ('scenarios/06-structured-extraction.md', 'Scenario walkthroughs', 'Structured Data Extraction'),
    ('playbook/domain-1-agentic-architecture.md', 'Domain playbooks', 'D1 · Agentic Architecture & Orchestration (27%)'),
    ('playbook/domain-2-tool-design-mcp.md', 'Domain playbooks', 'D2 · Tool Design & MCP Integration (18%)'),
    ('playbook/domain-3-claude-code-config.md', 'Domain playbooks', 'D3 · Claude Code Configuration & Workflows (20%)'),
    ('playbook/domain-4-prompt-structured-output.md', 'Domain playbooks', 'D4 · Prompt Engineering & Structured Output (20%)'),
    ('playbook/domain-5-context-reliability.md', 'Domain playbooks', 'D5 · Context Management & Reliability (15%)'),
    ('exercises/exercise-1-2-agent-and-claude-code.md', 'Build exercises', 'Exercises 1–2: Agent Loop & Claude Code Setup'),
    ('exercises/exercise-3-4-extraction-and-research.md', 'Build exercises', 'Exercises 3–4: Extraction Pipeline & Research Agents'),
]

def doc_id(rel):
    return Path(rel).stem

def title_of(md_text, fallback):
    m = re.search(r'^#\s+(.+)$', md_text, re.M)
    if not m:
        return fallback
    t = m.group(1).strip()
    # strip markdown emphasis/links from title
    t = re.sub(r'[*_`]', '', t)
    t = re.sub(r'^\d+\s*[—–-]\s*', '', t)  # "00 — Answer Physics" -> "Answer Physics"
    return t or fallback

md_engine = markdown.Markdown(extensions=['tables', 'fenced_code', 'sane_lists'])

order, items = [], {}
for rel, group, fallback in DOC_SPECS:
    p = KIT / rel
    text = p.read_text(encoding='utf-8')
    did = doc_id(rel)
    md_engine.reset()
    html = md_engine.convert(text)
    words = len(re.sub(r'```.*?```', ' ', text, flags=re.S).split())
    order.append(did)
    items[did] = {'title': title_of(text, fallback), 'group': group, 'html': html, 'words': words}

docs_payload = json.dumps({'order': order, 'items': items}, separators=(',', ':')).replace('</', '<\\/')

bank = json.load(open(KIT / 'questions' / 'bank.json'))
bank_payload = json.dumps(bank, separators=(',', ':')).replace('</', '<\\/')

smap_path = KIT / 'questions' / 'study-map.json'
smap = json.load(open(smap_path)) if smap_path.exists() else {}
smap_payload = json.dumps(smap, separators=(',', ':')).replace('</', '<\\/')

faces = font_faces()

tpl = (BUILD / 'quiz-template.html').read_text(encoding='utf-8')
assert '/*__BANK__*/' in tpl and '/*__DOCS__*/' in tpl and '/*__STUDYMAP__*/' in tpl
body = (tpl
        .replace('/*__FONTFACES__*/', faces, 1)
        .replace('/*__BANK__*/', bank_payload, 1)
        .replace('/*__DOCS__*/', docs_payload, 1)
        .replace('/*__STUDYMAP__*/', smap_payload, 1))
print('study-map keys:', len(smap), '| embedded font faces:', faces.count('@font-face'))

# artifact version (claude.ai wraps it in a document skeleton)
(BUILD / 'ccaf-practice.html').write_text(body, encoding='utf-8')

# standalone version for GitHub Pages
site = (
    '<!doctype html>\n<html lang="en">\n<head>\n'
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<meta name="color-scheme" content="light dark">\n'
    '<link rel="icon" href="data:image/svg+xml,'
    '%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E'
    '%3Ctext y=%22.9em%22 font-size=%2290%22%3E%F0%9F%8E%93%3C/text%3E%3C/svg%3E">\n'
    '</head>\n<body>\n' + body + '\n</body>\n</html>\n'
)
(KIT / 'index.html').write_text(site, encoding='utf-8')

print('artifact KB:', len(body) // 1024)
print('site KB:', len(site) // 1024)
print('docs:', len(order), 'total words:', sum(d['words'] for d in items.values()))
