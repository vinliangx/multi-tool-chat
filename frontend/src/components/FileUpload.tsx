import { faAdd, faPaperclip } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { ChangeEvent, useEffect, useRef, useState } from "react";
import { ThreeDot } from "react-loading-indicators";
import { apiFetch } from "../api";

export type FileUploadItem = { name: string; url: string };
export type FileUploadArgs = {
  filesUploaded: (urls: FileUploadItem[]) => void;
  setBusy: (val: boolean) => void;
};

export default function FileUpload({ filesUploaded, setBusy }: FileUploadArgs) {
  const [isOpen, setIsOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const handleClickOutside = (event: globalThis.MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files) return;
    setIsUploading(true);
    setBusy(true);
    const uploadedFiles: FileUploadItem[] = [];
    try {
      for (let index = 0; index < files.length; index++) {
        const file = files.item(index);
        if (!file) continue;
        const res = await apiFetch("/upload_url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            file_name: file.name,
            file_type: file.type,
          }),
        });

        const { key, url } = await res.json();

        await fetch(url, {
          method: "PUT",
          headers: {
            "Content-Type": file.type,
          },
          body: file,
        });
        uploadedFiles.push({
          name: file.name,
          url: `s3://file-uploads/${key}`,
        });
      }
    } finally {
      setBusy(false);
      setIsOpen(false);
      setIsUploading(false);
      filesUploaded(uploadedFiles);
    }
  }
  return (
    <div className="relative flex-col self-center" ref={menuRef}>
      {/* Popup Menu Content */}
      {isOpen && (
        <div className="float absolute mt-2 rounded-2xl bg-slate-900 text-white shadow-lg shadow-slate-800 sm:-top-30 sm:left-0 md:-top-30 md:-left-20">
          <ul className="gap-20">
            <li className="px-4 py-2 text-slate-400">Options</li>
            <li className="py-3">
              <button
                className="mx-2 flex w-60 rounded-full bg-slate-800 px-4 py-2 text-left hover:cursor-pointer hover:bg-slate-700"
                onClick={() => {
                  fileInputRef.current?.click();
                }}
              >
                <FontAwesomeIcon icon={faPaperclip} className="mr-4" />
                Upload file
                {isUploading && (
                  <div className="ml-5 flex items-center">
                    <ThreeDot
                      color={["#32cd32", "#327fcd", "#cd32cd", "#cd8032"]}
                      size="small"
                    />
                  </div>
                )}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileChange}
                multiple
                accept=".csv,image/*,application/pdf"
                style={{ display: "none" }}
              />
            </li>
          </ul>
        </div>
      )}
      <button
        className="text-xl text-white hover:cursor-pointer"
        onClick={() => setIsOpen(!isOpen)}
      >
        <FontAwesomeIcon
          icon={faAdd}
          className="h-10 w-10 rounded-full bg-slate-700 p-2 hover:bg-slate-600"
        />
      </button>
    </div>
  );
}
