import { faSpinner, faWrench } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";

export type BubbleToolArgs = {
  name: string;
  args: any;
  result?: string;
  summarizeProgress?: { current: number; total: number } | null;
  onCancel?: () => void;
};

export default function BubbleTool({
  name,
  result,
  args,
  summarizeProgress,
  onCancel,
}: BubbleToolArgs) {
  const data = result ? JSON.parse(result) : undefined;
  const [showResults, setShowResults] = useState(false);
  return (
    <div className="chat-tool-wrapper">
      <div className="">
        <div
          className="additional-process-preview-action"
          onClick={() => setShowResults(!showResults)}
        >
          <div className="flex-none items-start gap-1">
            <FontAwesomeIcon icon={faWrench} className="mr-2" />
            Using tool [<span className="highlight">{name}</span>]
          </div>
          {summarizeProgress && !result && (
            <div className="ml-auto align-middle font-bold text-gray-200">
              Chunks {summarizeProgress?.current ?? 0}/
              {summarizeProgress?.total ?? 0}
              <FontAwesomeIcon icon={faSpinner} spin className="ml-2" />
              <button
                className="ml-4 cursor-pointer text-blue-300"
                onClick={onCancel}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
        {showResults && (
          <div className="chat-tool mt-1">
            <p className="py-0 text-white">Args:</p>
            <pre className="">{JSON.stringify(args)}</pre>
            {result !== undefined && (
              <p className="py-0 text-white">Response:</p>
            )}
            {result !== undefined && (
              <pre className="mt-1.5 mb-2 wrap-break-word whitespace-pre-wrap text-amber-200">
                {data}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
