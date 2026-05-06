import { faClose } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import ConfirmDialog from "./ConfirmDialog";
import { FileUploadItem } from "./FileUpload";

export type FileItemArgs = {
  file: FileUploadItem;
  onRemove?: () => void;
};

export default function FileItem({ file, onRemove }: FileItemArgs) {
  const [confirm, setConfirm] = useState<{
    message: string;
  } | null>(null);
  return (
    <div className="rounded-2xl bg-amber-300 px-2 text-[80%] font-bold text-black shadow-2xl">
      {file.name}
      {onRemove && (
        <FontAwesomeIcon
          icon={faClose}
          className="ml-1 cursor-pointer"
          onClick={() =>
            setConfirm({ message: "Do you want to remove this file?" })
          }
        />
      )}
      {confirm && (
        <ConfirmDialog
          message={confirm.message}
          onConfirm={() => {
            if (onRemove) onRemove();
            setConfirm(null);
          }}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
