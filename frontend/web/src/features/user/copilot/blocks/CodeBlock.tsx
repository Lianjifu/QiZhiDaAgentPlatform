/**
 * CodeBlock — 语法高亮代码块 (基于 highlight.js).
 * - 按 language 注册常见语言 (bash / json / python / typescript / xml / sql / css)
 * - 输出 hljs 标准化 HTML, 套 github-dark 风格
 * - 自带"复制"按钮 (clipboard API)
 */
import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import css from 'highlight.js/lib/languages/css';
import go from 'highlight.js/lib/languages/go';
import java from 'highlight.js/lib/languages/java';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import python from 'highlight.js/lib/languages/python';
import ruby from 'highlight.js/lib/languages/ruby';
import rust from 'highlight.js/lib/languages/rust';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';

let _registered = false;
function ensureRegistered() {
  if (_registered) return;
  hljs.registerLanguage('bash', bash);
  hljs.registerLanguage('css', css);
  hljs.registerLanguage('go', go);
  hljs.registerLanguage('java', java);
  hljs.registerLanguage('javascript', javascript);
  hljs.registerLanguage('json', json);
  hljs.registerLanguage('python', python);
  hljs.registerLanguage('ruby', ruby);
  hljs.registerLanguage('rust', rust);
  hljs.registerLanguage('sql', sql);
  hljs.registerLanguage('typescript', typescript);
  hljs.registerLanguage('xml', xml);
  hljs.registerLanguage('yaml', yaml);
  _registered = true;
}

function highlight(code: string, language: string): string {
  ensureRegistered();
  try {
    if (language && language !== 'plaintext' && language !== 'plain') {
      return hljs.highlight(code, { language, ignoreIllegals: true }).value;
    }
    return hljs.highlightAuto(code).value;
  } catch {
    return escapeHtml(code);
  }
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function CodeBlock({
  language,
  code,
  showCopy = true,
}: {
  language: string;
  code: string;
  showCopy?: boolean;
}) {
  const html = highlight(code, language);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };
  return (
    <div className="relative overflow-hidden rounded-md border border-slate-700 bg-[#0d1117]">
      <div className="flex items-center justify-between border-b border-slate-700 bg-[#161b22] px-2.5 py-1 font-mono text-[10px] text-slate-400">
        <span>{language || 'plain'}</span>
        {showCopy ? (
          <button
            type="button"
            onClick={() => void copy()}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            title="复制"
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {copied ? '已复制' : '复制'}
          </button>
        ) : null}
      </div>
      <pre className="overflow-auto p-2.5 font-mono text-[11px] leading-5 text-slate-100">
        <code
          className={language ? `hljs language-${language}` : 'hljs'}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </pre>
    </div>
  );
}
