type Props = {
  inputTokens: number;
  outputTokens: number;
  estimatedTokens: number;
  contextWindowLimit: number;
};

function fmt(n: number) {
  return n + ".";
}

export default function ContextUsageBadge({
  inputTokens,
  outputTokens,
  estimatedTokens,
  contextWindowLimit,
}: Props) {
  const pct = Math.min((inputTokens / contextWindowLimit) * 100, 100);
  return (
    <div className="context-usage-badge">
      <div className="context-usage-bar-track">
        <div
          className="context-usage-bar-fill real"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="context-usage-stats">
        <span
          title="Tokens actually counted by the API (compacted context)"
          className="cursor-pointer"
        >
          <strong>Real:</strong> {fmt(inputTokens)}
        </span>
        <span
          title="Tiktoken estimate of raw message content before API tokenization"
          className="cursor-pointer"
        >
          <strong>Est:</strong> {fmt(estimatedTokens)}
        </span>
        <span
          title="Tokens generated in this response"
          className="cursor-pointer"
        >
          <strong>Out:</strong> {fmt(outputTokens)}
        </span>
        {inputTokens > contextWindowLimit && (
          <div className="font-mono font-bold">| Message history trimmed</div>
        )}
        <span className="context-usage-window">
          Context Window / {fmt(contextWindowLimit)}
        </span>
      </div>
    </div>
  );
}
