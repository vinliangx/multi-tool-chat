import MarkdownPreview from "react-markdown";
import remarkGfm from "remark-gfm";

export type BubbleAssistantArgs = { text: string; source: string };
export default function BubbleAssistant({ text, source }: BubbleAssistantArgs) {
  return (
    <div className="flex max-w-full min-w-full flex-col py-2">
      <div className="self-start text-[80%] text-gray-300">Assistant</div>
      <div className="chat-assistant">
        <div className="chat-markdown-safe">
          <MarkdownPreview remarkPlugins={[remarkGfm]}>{text}</MarkdownPreview>
        </div>
        <div className="pt mt-4 flex items-end pb-4 text-[75%]">
          <div className="flex-1 self-end text-right">Source:</div>
          <div className="ml-2 flex rounded-2xl bg-gray-200 px-2 font-bold text-black">
            {source}
          </div>
        </div>
      </div>
    </div>
  );
}
