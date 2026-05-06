import MarkdownPreview from "react-markdown";
import remarkGfm from "remark-gfm";

export type BubbleUserArgs = { text: string; label: string };

export default function BubbleUser({ label, text }: BubbleUserArgs) {
  return (
    <div className="flex flex-col py-2">
      <div className="text-blue-200 text-[80%] self-end">{label}</div>
      <div className="chat-user ">
        <div className="chat-markdown-safe">
          <MarkdownPreview remarkPlugins={[remarkGfm]}>{text}</MarkdownPreview>
        </div>
      </div>
    </div>
  );
}
