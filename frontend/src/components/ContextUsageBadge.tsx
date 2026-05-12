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
        <div className="context-usage-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="context-usage-stats">
        <span title="Tokens actually counted by the API (compacted context)">
          <strong>Real:</strong> {fmt(inputTokens)}
        </span>
        <span title="Tiktoken estimate of raw message content before API tokenization">
          <strong>Est:</strong> {fmt(estimatedTokens)}
        </span>
        <span title="Tokens generated in this response">
          <strong>Out:</strong> {fmt(outputTokens)}
        </span>
        <span className="context-usage-window">
          Context Window / {fmt(contextWindowLimit)}
        </span>
      </div>
    </div>
  );
}
