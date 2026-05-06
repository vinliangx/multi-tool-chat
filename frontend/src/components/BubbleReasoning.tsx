import { useState } from "react";
import MarkdownPreview from "react-markdown";
import remarkGfm from "remark-gfm";

export type BubbleReasoning = { text: string };

export default function BubbleReasoning({ text }: BubbleReasoning) {
  const [showDetails, setShowDetails] = useState(false);
  return (
    <div className="flex flex-col py-2">
      <div className="chat-reasoning">
        {text !== undefined && (
          <div className="mt-1">
            <div
              className="cursor-pointer text-[80%] text-gray-200 italic"
              onClick={() => setShowDetails(!showDetails)}
            >
              Reasoning...
            </div>
            {showDetails && (
              <div className="m-2">
                <MarkdownPreview remarkPlugins={[remarkGfm]}>
                  {text}
                </MarkdownPreview>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
