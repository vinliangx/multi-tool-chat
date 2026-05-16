import MarkdownPreview from "react-markdown";
import remarkGfm from "remark-gfm";

export type BubbleUserArgs = { text: string; label: string };

export default function BubbleUser({ label, text }: BubbleUserArgs) {
  return (
    <div className="flex flex-col py-1.5">
      <div className="self-end text-[80%] text-blue-200">{label}</div>
      <div className="chat-user">
        <div className="chat-markdown-safe">
          <MarkdownPreview remarkPlugins={[remarkGfm]}>{text}</MarkdownPreview>
        </div>
      </div>
    </div>
  );
}
