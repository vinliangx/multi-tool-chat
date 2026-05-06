import { Slab } from "react-loading-indicators";

export type ChatLoadingIndicatorArgs = {
  loading: boolean;
  label?: string;
};

export default function ChatLoadingIndicator({
  loading,
  label,
}: ChatLoadingIndicatorArgs) {
  if (loading)
    return (
      <div className="text-center py-4">
        <Slab
          color={["#32cd32", "#327fcd", "#cd32cd", "#cd8032"]}
          text={label ?? "Thinking..."}
          textColor="white"
        />
      </div>
    );
  return "";
}
