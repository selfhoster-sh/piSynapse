/**
 * Markdown text processing Web Worker
 * Handles CPU-intensive text processing: escaping, math parsing, markdown stripping
 * No DOM access - pure string manipulation for off-main-thread execution
 */

// HTML escaping - must match main thread's esc()
function esc(s) {
  return String(s || '')
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/"/g, '"')
    .replace(/'/g, "'");
}

// LaTeX math command to unicode mapping
const MATH_DICT = {
  '\\rightarrow': '\u2192', '\\leftarrow': '\u2190', '\\Rightarrow': '\u21D2', '\\Leftarrow': '\u21D0',
  '\\leftrightarrow': '\u2194', '\\Leftrightarrow': '\u21D4', '\\times': '\u00D7', '\\div': '\u00F7',
  '\\leq': '\u2264', '\\geq': '\u2265', '\\neq': '\u2260', '\\approx': '\u2248', '\\pm': '\u00B1',
  '\\cdot': '\u00B7', '\\infty': '\u221E', '\\Delta': '\u0394', '\\alpha': '\u03B1', '\\beta': '\u03B2',
  '\\theta': '\u03B8', '\\pi': '\u03C0', '\\sigma': '\u03C3', '\\sum': '\u2211', '\\prod': '\u220F', '\\sqrt': '\u221A'
};

function parseMath(s) {
  return s.replace(/\\[a-zA-Z]+/g, m => MATH_DICT[m] || m);
}

// Strip markdown syntax for plain text preview / search
function stripMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\*{1,3}([^*]+)\*{1,3}/g, '$1')
    .replace(/_{1,3}([^_]+)_{1,3}/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^[\-\*_]{3,}\s*$/gm, '')
    .replace(/^>\s*/gm, '')
    .replace(/^[\-\*\+]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/\|/g, ' ')
    .replace(/(?<!\w)[*_]{1,2}(?!\w)/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/ {2,}/g, ' ')
    .trim();
}

// Worker message handler
self.onmessage = (e) => {
  const { type, text } = e.data || {};
  
  try {
    let result;
    switch (type) {
      case 'parseMath':
        result = parseMath(text);
        break;
      case 'stripMarkdown':
        result = stripMarkdown(text);
        break;
      case 'esc':
        result = esc(text);
        break;
      case 'fullProcess':
        // Run all text processing in sequence
        let processed = esc(text);
        processed = parseMath(processed);
        result = processed;
        break;
      default:
        throw new Error(`Unknown worker message type: ${type}`);
    }
    self.postMessage({ ok: true, type, result });
  } catch (err) {
    self.postMessage({ ok: false, type, error: err.message });
  }
};