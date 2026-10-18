/**
 * 完整 GFM markdown 渲染器:
 *   - react-markdown 解析 AST
 *   - remark-gfm 扩展: 表格 / 任务列表 / 删除线 / 自动链接
 *   - 自定义 code 渲染: ```mermaid 块走 mermaid.render 输出 SVG,
 *     其他 fenced code 走等宽样式
 *   - 零依赖行内样式: 与项目 token (--text, --text-secondary, --brand,
 *     --bg-elevated, --border) 保持一致, 不破坏既有页面
 */
import { useEffect, useId, useState, type ComponentProps, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownViewProps {
  source: string;
}

interface MermaidBlockProps {
  source: string;
}

function MermaidBlock({ source }: MermaidBlockProps) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '_');
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'neutral',
          securityLevel: 'loose',
          fontFamily: 'inherit',
        });
        const { svg: rendered } = await mermaid.render(`mmd-${id}`, source);
        if (!cancelled) {
          setSvg(rendered);
          setError('');
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [source, id]);

  if (error) {
    return (
      <div className="my-3 rounded-xl border border-rose-300 bg-rose-50 p-3 text-[11px] text-rose-700">
        <p className="font-semibold">Mermaid 渲染失败</p>
        <pre className="mt-1 whitespace-pre-wrap font-mono">{error}</pre>
      </div>
    );
  }
  return (
    <div
      className="my-3 flex justify-center overflow-auto rounded-xl border border-[var(--border)] bg-[var(--surface-1)] p-3 [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg || '<span class="text-xs text-[var(--text-muted)]">渲染中…</span>' }}
    />
  );
}

function isMermaidCode(lang?: string) {
  return (lang ?? '').trim().toLowerCase() === 'mermaid';
}

export function MarkdownView({ source }: MarkdownViewProps) {
  return (
    <div className="markdown-body space-y-2 text-xs leading-6 text-[var(--text-secondary)]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => (
            <h1 className="mt-4 mb-2 text-base font-semibold tracking-tight text-[var(--text)]" {...props} />
          ),
          h2: (props) => <h2 className="mt-4 mb-2 text-sm font-semibold text-[var(--text)]" {...props} />,
          h3: (props) => (
            <h3 className="mt-3 mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]" {...props} />
          ),
          h4: (props) => <h4 className="mt-3 mb-1 text-xs font-semibold text-[var(--text)]" {...props} />,
          p: (props) => <p className="my-2 text-xs leading-6 text-[var(--text-secondary)]" {...props} />,
          strong: (props) => <strong className="font-semibold text-[var(--text)]" {...props} />,
          em: (props) => <em className="italic" {...props} />,
          del: (props) => <del className="text-[var(--text-muted)] line-through" {...props} />,
          a: (props) => (
            <a
              className="text-[var(--brand)] underline decoration-dotted underline-offset-2 hover:opacity-80"
              target="_blank"
              rel="noreferrer"
              {...props}
            />
          ),
          ul: (props) => (
            <ul className="my-2 space-y-1.5 pl-4 text-xs leading-6 text-[var(--text-secondary)] marker:text-[var(--brand)]" {...props} />
          ),
          ol: (props) => (
            <ol className="my-2 list-decimal space-y-1.5 pl-4 text-xs leading-6 text-[var(--text-secondary)]" {...props} />
          ),
          li: (props) => <li className="pl-1" {...props} />,
          blockquote: (props) => (
            <blockquote
              className="my-2 border-l-2 border-[var(--brand)] bg-[var(--brand-light)]/40 px-3 py-1.5 text-xs text-[var(--text-secondary)]"
              {...props}
            />
          ),
          hr: () => <hr className="my-4 border-[var(--border)]" />,
          code: ({ className, children, ...rest }: ComponentProps<'code'> & { children?: ReactNode }) => {
            // react-markdown 在 fenced code 块上把 language 作为 className (含 `language-xxx`)
            const langMatch = /language-(\w+)/.exec(className ?? '');
            const lang = langMatch?.[1];
            const text = String(children ?? '').replace(/\n$/, '');
            if (isMermaidCode(lang)) return <MermaidBlock source={text} />;
            // 行内 code (没 className) 与 fenced code (有 language-xxx className) 走不同样式
            if (className?.includes('language-')) {
              return (
                <pre className="my-3 overflow-auto rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-3 font-mono text-[11px] leading-5 text-[var(--text)]">
                  <code className={className} {...rest}>{text}</code>
                </pre>
              );
            }
            return (
              <code className="rounded bg-[var(--bg-elevated)] px-1 py-0.5 font-mono text-[0.92em] text-[var(--brand)]" {...rest}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>, // 让 fenced code 直接走 code 渲染, 避免外层 pre 嵌套
          table: (props) => (
            <div className="my-3 overflow-auto rounded-xl border border-[var(--border)] bg-[var(--surface-1)]">
              <table className="w-full border-collapse text-xs text-[var(--text-secondary)]" {...props} />
            </div>
          ),
          thead: (props) => (
            <thead
              className="sticky top-0 z-10 bg-[var(--bg-elevated)] text-[var(--text)] shadow-[0_1px_0_0_var(--border)]"
              {...props}
            />
          ),
          th: (props) => (
            <th
              className="border-b border-[var(--border)] px-3 py-2 text-left align-bottom font-semibold"
              {...props}
            />
          ),
          td: (props) => <td className="border-b border-[var(--border)] px-3 py-2 align-top last:border-b-0" {...props} />,
          tr: (props) => <tr className="even:bg-[var(--bg-elevated)]/40 hover:bg-[var(--brand-light)]/30" {...props} />,
          tbody: (props) => <tbody {...props} />,
          input: (props) => {
            // GFM 任务列表: 渲染为 disabled checkbox
            if (props.type === 'checkbox') {
              return (
                <input
                  type="checkbox"
                  checked={props.checked}
                  readOnly
                  disabled
                  className="mr-1.5 h-3.5 w-3.5 accent-[var(--brand)]"
                />
              );
            }
            return <input {...props} />;
          },
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
