import { faBrain } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useState } from "react";
import MarkdownPreview from "react-markdown";
import remarkGfm from "remark-gfm";

export type BubbleReasoning = { text: string; reasoningExpanded: boolean };

export default function BubbleReasoning({
  text,
  reasoningExpanded,
}: BubbleReasoning) {
  const [showDetails, setShowDetails] = useState(reasoningExpanded);
  useEffect(() => setShowDetails(reasoningExpanded), [reasoningExpanded]);
  return (
    <div className="flex flex-col py-2">
      <div className="chat-reasoning">
        {text !== undefined && (
          <div className="mt-1">
            <div
              className="cursor-pointer flex-row justify-center self-center text-gray-200"
              onClick={() => setShowDetails(!showDetails)}
            >
              <FontAwesomeIcon icon={faBrain} className="mx-2" />
              Reasoning
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
