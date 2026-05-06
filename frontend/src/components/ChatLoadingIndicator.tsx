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
      <div className="py-4 text-center">
        <Slab
          color={["#32cd32", "#327fcd", "#cd32cd", "#cd8032"]}
          text={label ?? "Processing..."}
          textColor="white"
        />
      </div>
    );
  return "";
}
