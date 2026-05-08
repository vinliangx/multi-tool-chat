import { useState } from "react";

export type BubbleToolArgs = {
  name: string;
  args: any;
  result?: string;
};

export default function BubbleTool({ name, result, args }: BubbleToolArgs) {
  const data = result ? JSON.parse(result) : undefined;
  const [showResults, setShowResults] = useState(false);
  return (
    <div className="flex flex-col py-2">
      <div className="chat-tool">
        <div
          className="cursor-pointer text-[80%] text-gray-100"
          onClick={() => setShowResults(!showResults)}
        >
          Using tool [
          <span className="font-semibold text-blue-400">{name}</span>]
        </div>
        {showResults && (
          <div className="mt-1">
            <p className="py-2 text-white">Args:</p>
            <pre className="mt-1.5 mb-0 wrap-break-word whitespace-pre-wrap text-amber-200">
              {JSON.stringify(args)}
            </pre>
            {result !== undefined && (
              <p className="py-2 text-white">Response:</p>
            )}
            {result !== undefined && (
              <pre className="mt-1.5 mb-0 wrap-break-word whitespace-pre-wrap text-amber-200">
                {data}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
