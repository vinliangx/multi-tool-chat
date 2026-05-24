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
    <div className="file-item group">
      <span className="text">{file.name}</span>
      {onRemove && (
        <FontAwesomeIcon
          icon={faClose}
          className="icon"
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
      <div className="tooltip">{file.name}</div>
    </div>
  );
}
