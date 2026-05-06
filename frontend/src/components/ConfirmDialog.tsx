type ConfirmDialogArgs = {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: ConfirmDialogArgs) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-sm rounded-2xl bg-slate-900 p-6 shadow-2xl shadow-slate-900">
        <p className="mb-6 text-[95%] text-gray-200">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-xl bg-slate-800 px-4 py-2 text-sm text-slate-300 hover:bg-slate-700 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-xl bg-linear-120 from-blue-800 to-blue-600 px-4 py-2 text-sm text-blue-100 shadow-lg shadow-blue-900 hover:from-blue-700 hover:to-blue-500"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
