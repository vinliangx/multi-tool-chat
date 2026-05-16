import { faComments, faPaperPlane } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { KeyboardEvent, Ref, useEffect, useRef } from "react";
import FileItem from "./FileItem";
import FileUpload, { FileUploadItem } from "./FileUpload";

export type UpdateFilesState = (
  prevFiles: FileUploadItem[],
) => FileUploadItem[];

export type ChatBoxArgs = {
  inputRef: Ref<HTMLTextAreaElement>;
  input: string | undefined;
  setInput: (val: string) => void;
  busy: boolean;
  send: () => void;
  messages: string[];
  isNew: boolean;
  files: FileUploadItem[];
  setFiles: (files: FileUploadItem[] | UpdateFilesState) => void;
  sessionId?: string | null;
  reasoningExpanded: boolean;
  setReasoningExpanded: (expanded: boolean) => void;
};

export function ChatBox({
  inputRef,
  input,
  setInput,
  files,
  setFiles,
  busy,
  send,
  messages,
  isNew,
  sessionId,
  reasoningExpanded,
  setReasoningExpanded,
}: ChatBoxArgs) {
  let messageIndex = useRef(messages.length);

  const inputChatKeyPress = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      send();
    }
    if (e.key === "ArrowUp" && !e.shiftKey) {
      if (messageIndex.current > 0) {
        setInput(messages[--messageIndex.current]);
        e.preventDefault();
      }
    }
    if (e.key === "ArrowDown" && !e.shiftKey) {
      if (messageIndex.current < messages.length - 1) {
        setInput(messages[++messageIndex.current]);
        e.preventDefault();
      } else {
        setInput("");
      }
    }
  };
  function filesUploaded(newFiles: FileUploadItem[]) {
    setFiles(files.concat(newFiles));
  }
  useEffect(() => {
    if (input == "") messageIndex.current = messages.length;
  }, [input, messages]);
  return (
    <div className={isNew ? "chat-box-wrapper new" : "chat-box-wrapper"}>
      {isNew && (
        <div className="mb-10 text-center text-slate-200">
          <div className="text-3xl font-bold">
            <FontAwesomeIcon icon={faComments} className="mr-2" />
            Start here!
          </div>
          <div>Write me a question.</div>
        </div>
      )}

      <div className="mt-2 mb-2 flex items-center justify-center">
        <div className="flex text-[70%]">
          <div className="text-blue-200 max-sm:hidden">SessionID:</div>
          <div className="ml-2 flex rounded-2xl bg-slate-800 px-2 text-white max-sm:hidden">
            {sessionId ?? "(New!)"}
          </div>
          <label className="relative ml-10 inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              onClick={() => setReasoningExpanded(!reasoningExpanded)}
              className="peer sr-only"
            />

            <div className="peer h-4 w-7 rounded-full bg-gray-500 peer-checked:bg-blue-600 peer-focus:ring-4 peer-focus:ring-blue-300 peer-focus:outline-none after:absolute after:inset-s-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white rtl:peer-checked:after:-translate-x-full"></div>

            <span className="ms-3 text-xs font-medium text-gray-400 italic">
              Keep reasoning expanded
            </span>
          </label>
        </div>
      </div>
      <div className="chat-box">
        <div className="flex h-20 w-full gap-4">
          <FileUpload filesUploaded={filesUploaded} />
          <div className="chat-input-values">
            {files.length > 0 && (
              <div className="files-selected">
                {files.map((f, index) => {
                  return (
                    <FileItem
                      key={index}
                      file={f}
                      onRemove={() => {
                        setFiles((prevFiles: FileUploadItem[]) =>
                          prevFiles.filter((item) => item.url !== f.url),
                        );
                      }}
                    />
                  );
                })}
              </div>
            )}
            <textarea
              id="chatBox"
              name="chatBox"
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={inputChatKeyPress}
              placeholder={
                busy
                  ? "Thinking"
                  : "Ask anything, use ↑ and ↓ arrow keys to move between previous messages."
              }
              disabled={busy}
              className="chat-input"
            />
          </div>
          <button
            onClick={send}
            disabled={busy || !input?.trim()}
            className="rounded-xl bg-linear-120 from-blue-800 to-blue-600 px-4 py-2 text-sm text-blue-100 shadow-lg shadow-blue-900 hover:from-blue-700 hover:to-blue-500 disabled:opacity-50"
          >
            <FontAwesomeIcon icon={faPaperPlane} className="pr-2" />
            SEND
          </button>
        </div>
      </div>
    </div>
  );
}
