import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownMessageProps = {
  content: string | null;
};

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children: linkChildren }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {linkChildren}
          </a>
        ),
      }}
    >
      {content ?? ""}
    </ReactMarkdown>
  );
}
