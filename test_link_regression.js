const fs = require('fs');
const assert = require('assert');

// Read actual production ivan-widget.js
const code = fs.readFileSync('./assets/js/ivan-widget.js', 'utf8');

// Create sandbox to test functions from ivan-widget.js
const sandbox = {
  window: {},
  document: {
    createElement: () => ({ innerHTML: '', style: {}, addEventListener: () => {} })
  },
  HTMLElement: class {},
  customElements: {
    get: () => null,
    define: () => {}
  }
};

const fn = new Function('window', 'document', 'HTMLElement', 'customElements', code);
fn(sandbox.window, sandbox.document, sandbox.HTMLElement, sandbox.customElements);

// Extract renderMarkdown and sanitizeUrl from the widget or re-execute inside sandbox
// Let's create an instance or evaluate functions
console.log('Testing ivan-widget.js loaded successfully into sandbox.');

// Let's test the complete Markdown pipeline extracted directly from ivan-widget.js source
const renderMarkdownMatch = code.match(/function renderMarkdown\([\s\S]*?\n  \}/);
const sanitizeUrlMatch = code.match(/function sanitizeUrl\([\s\S]*?\n  \}/);
const escapeHtmlMatch = code.match(/function escapeHtml\([\s\S]*?\n  \}/);

assert(renderMarkdownMatch, 'renderMarkdown found in ivan-widget.js');
assert(sanitizeUrlMatch, 'sanitizeUrl found in ivan-widget.js');
assert(escapeHtmlMatch, 'escapeHtml found in ivan-widget.js');

const evalCode = `
${escapeHtmlMatch[0]}
${sanitizeUrlMatch[0]}
${renderMarkdownMatch[0]}
return { escapeHtml, sanitizeUrl, renderMarkdown };
`;

const { escapeHtml, sanitizeUrl, renderMarkdown } = (new Function(evalCode))();

console.log('==================================================');
console.log('RUNNING REGRESSION TEST SUITE FOR LINKS');
console.log('==================================================');

// Case 1: Markdown link: [Assessment](https://nav.ac/dma7t)
console.log('[RUN] Case 1: Markdown link [Assessment](https://nav.ac/dma7t)');
const res1 = renderMarkdown('Access the [Assessment](https://nav.ac/dma7t) now.');
assert(res1.includes('<a href="https://nav.ac/dma7t" target="_blank" rel="noopener noreferrer">Assessment</a>'), 'Case 1 failed: ' + res1);
console.log('[PASS] Case 1 passed.');

// Case 2: Markdown link with URL as text: [https://nav.ac/dma7t](https://nav.ac/dma7t)
console.log('[RUN] Case 2: Markdown link with URL as text [https://nav.ac/dma7t](https://nav.ac/dma7t)');
const res2 = renderMarkdown('Visit [https://nav.ac/dma7t](https://nav.ac/dma7t).');
assert(res2.includes('<a href="https://nav.ac/dma7t" target="_blank" rel="noopener noreferrer">https://nav.ac/dma7t</a>'), 'Case 2 failed: ' + res2);
console.log('[PASS] Case 2 passed.');

// Case 3: Plain URL: https://nav.ac/dma7t
console.log('[RUN] Case 3: Plain URL https://nav.ac/dma7t');
const res3 = renderMarkdown('You can access the Strategic Maturity Assessment tool directly at https://nav.ac/dma7t.');
assert(res3.includes('<a href="https://nav.ac/dma7t" target="_blank" rel="noopener noreferrer">https://nav.ac/dma7t</a>.'), 'Case 3 failed: ' + res3);
console.log('[PASS] Case 3 passed.');

// Case 4: Link in a streamed SSE response
console.log('[RUN] Case 4: Link in a streamed SSE response (token accumulation and done event)');
let streamAccum = '';
const tokens = ['You can access ', 'the Assessment directly at ', 'https://nav.ac', '/dma7t', '.'];
for (const t of tokens) {
  streamAccum += t;
}
const res4 = renderMarkdown(streamAccum);
assert(res4.includes('<a href="https://nav.ac/dma7t" target="_blank" rel="noopener noreferrer">https://nav.ac/dma7t</a>'), 'Case 4 failed: ' + res4);
console.log('[PASS] Case 4 passed.');

// Case 5: Link in a normal JSON response
console.log('[RUN] Case 5: Link in a normal JSON response');
const jsonAnswer = "The Strategic Maturity Assessment is a diagnostic tool.\n\nYou can access it at [https://nav.ac/dma7t](https://nav.ac/dma7t).";
const res5 = renderMarkdown(jsonAnswer);
assert(res5.includes('<a href="https://nav.ac/dma7t" target="_blank" rel="noopener noreferrer">https://nav.ac/dma7t</a>'), 'Case 5 failed: ' + res5);
console.log('[PASS] Case 5 passed.');

// Case 6: Unsafe URL: javascript:alert(1) must not become clickable
console.log('[RUN] Case 6: Unsafe URLs must not become clickable');
const res6a = renderMarkdown('[Test](javascript:alert(1))');
assert(!res6a.includes('<a href="javascript'), 'Case 6a failed: unsafe link created: ' + res6a);
const res6b = renderMarkdown('Raw javascript:alert(1) call');
assert(!res6b.includes('<a href="javascript'), 'Case 6b failed: unsafe link created: ' + res6b);
const res6c = renderMarkdown('[Data](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)');
assert(!res6c.includes('<a href="data:'), 'Case 6c failed: data link created: ' + res6c);
console.log('[PASS] Case 6 passed: javascript: and data: URLs rejected.');

// Case 7: Normal text and existing Markdown formatting must continue working
console.log('[RUN] Case 7: Normal text and existing Markdown formatting');
const res7 = renderMarkdown('**Bold** and *Italic* and `inline code with https://nav.ac/dma7t` and:\n- Item 1\n- Item 2 with https://nav.ac/dma7t');
assert(res7.includes('<strong>Bold</strong>'), 'Bold failed');
assert(res7.includes('<em>Italic</em>'), 'Italic failed');
assert(res7.includes('<code>inline code with https://nav.ac/dma7t</code>'), 'Inline code failed (URL inside code must NOT be converted to <a>)');
assert(!res7.includes('<code>inline code with <a href'), 'URL inside inline code became <a>');
assert(res7.includes('<li>Item 2 with <a href="https://nav.ac/dma7t" target="_blank" rel="noopener noreferrer">https://nav.ac/dma7t</a></li>'), 'List item link failed');
console.log('[PASS] Case 7 passed: Bold, italic, code blocks, lists preserved.');

console.log('==================================================');
console.log('ALL 7 JAVASCRIPT REGRESSION TESTS PASSED!');
console.log('==================================================');

