import React, { memo, useMemo } from "react";

interface Props {
  content: string;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMarkdown(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code class=\"md-inline-code\">$1</code>");
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    "<a href=\"$2\" target=\"_blank\" rel=\"noreferrer\" class=\"md-link\">$1</a>",
  );
  return out;
}

function renderBlock(block: string): string {
  const trimmed = block.trim();
  if (!trimmed) return "";

  const lines = trimmed.split("\n");
  const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
  if (heading && lines.length === 1) {
    const level = heading[1].length;
    const tag = level === 1 ? "h3" : level === 2 ? "h4" : "h5";
    return `<${tag} class="md-heading">${inlineMarkdown(heading[2])}</${tag}>`;
  }

  const isBulletList = lines.every((l) => /^\s*[-*]\s+/.test(l) || l.trim() === "");
  if (isBulletList) {
    const items = lines
      .filter((l) => l.trim())
      .map((l) => `<li>${inlineMarkdown(l.replace(/^\s*[-*]\s+/, ""))}</li>`)
      .join("");
    return `<ul class="md-list list-disc pl-5 space-y-1">${items}</ul>`;
  }

  const isNumbered = lines.every((l) => /^\s*\d+\.\s+/.test(l) || l.trim() === "");
  if (isNumbered) {
    const items = lines
      .filter((l) => l.trim())
      .map((l) => `<li>${inlineMarkdown(l.replace(/^\s*\d+\.\s+/, ""))}</li>`)
      .join("");
    return `<ol class="md-list list-decimal pl-5 space-y-1">${items}</ol>`;
  }

  if (trimmed.startsWith("```") && trimmed.endsWith("```")) {
    const code = trimmed.slice(3, -3).replace(/^\w+\n/, "");
    return `<pre class="md-code-block"><code>${escapeHtml(code)}</code></pre>`;
  }

  return `<p class="md-paragraph whitespace-pre-wrap">${inlineMarkdown(trimmed).replace(/\n/g, "<br />")}</p>`;
}

function AssistantMarkdown({ content }: Props) {
  const html = useMemo(() => {
    const blocks = content.split(/\n{2,}/);
    return blocks.map(renderBlock).filter(Boolean).join("");
  }, [content]);

  return (
    <div
      className="assistant-markdown space-y-2 text-sm leading-[1.65] break-words [&_.md-inline-code]:rounded [&_.md-inline-code]:bg-surface-container-high [&_.md-inline-code]:px-1 [&_.md-inline-code]:py-0.5 [&_.md-inline-code]:text-[0.85em] [&_.md-code-block]:overflow-x-auto [&_.md-code-block]:rounded-lg [&_.md-code-block]:bg-surface-container-high [&_.md-code-block]:p-2.5 [&_.md-code-block]:text-xs [&_.md-heading]:font-semibold [&_.md-heading]:text-on-surface [&_.md-link]:text-primary [&_.md-link]:underline"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default memo(AssistantMarkdown);
