import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

/** 把文本内容转成安全 HTML，用于 assistant 内容展示。 */
export function renderMarkdown(content: string): string {
  const rendered = markdown.render(content || '')
  return DOMPurify.sanitize(rendered)
}
