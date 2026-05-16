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
    <div className="flex flex-col">
      <div className="chat-reasoning-wrapper">
        {text !== undefined && (
          <div className="mt-1 text-[95%]">
            <div
              className="additional-process-preview-action"
              onClick={() => setShowDetails(!showDetails)}
            >
              <FontAwesomeIcon icon={faBrain} className="mr-2" />
              Reasoning
            </div>
            {showDetails && (
              <div className="chat-reasoning">
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
