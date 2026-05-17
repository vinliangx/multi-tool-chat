import {
  faCode,
  faPenToSquare,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

export type HeaderArgs = { newSession: () => void; clearCache: () => void };

export default function Header({ newSession, clearCache }: HeaderArgs) {
  return (
    <div>
      <div className="m-4 flex items-center">
        <div className="flex-1">
          <div className="mb-2 text-xl font-bold">Multi-Tool Chat</div>
          <div className="text-[80%] text-slate-300">
            <FontAwesomeIcon icon={faCode} className="mr-2" />
            Coding Challenge
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <button className="chat-new-button" onClick={newSession}>
            <FontAwesomeIcon icon={faPenToSquare} />
            <span>New</span>
          </button>
        </div>
      </div>
      <button
        className="chat-clear-cache-button fixed bottom-2 left-4"
        onClick={clearCache}
      >
        <FontAwesomeIcon icon={faTrash} />
        <span>Clear Cache</span>
      </button>
    </div>
  );
}
