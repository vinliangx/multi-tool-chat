export type BubbleToolArgs = {
  name: string;
  args: any;
  result?: string;
};

export default function BubbleTool({ name, result, args }: BubbleToolArgs) {
  const data = result ? JSON.parse(result) : undefined;
  return (
    <div className="flex flex-col py-2">
      <div className="chat-tool">
        <div className="text-gray-100">
          Using tool [
          <span className="font-semibold text-blue-400">{name}</span>]
        </div>
        {result !== undefined && (
          <details className="mt-1">
            <summary className="text-[110%] text-gray-300">View result</summary>
            <p className="py-2 text-white">Args:</p>
            <pre className="mt-1.5 mb-0 wrap-break-word whitespace-pre-wrap text-amber-200">
              {JSON.stringify(args)}
            </pre>
            <p className="py-2 text-white">Response:</p>
            <pre className="mt-1.5 mb-0 wrap-break-word whitespace-pre-wrap text-amber-200">
              {data}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
