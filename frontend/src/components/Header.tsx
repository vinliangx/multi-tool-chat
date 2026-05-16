import { faCode, faPenToSquare } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";

export type HeaderArgs = { newSession: () => void };

export default function Header({ newSession }: HeaderArgs) {
  return (
    <div className="m-4 flex items-center">
      <div className="flex-1">
        <div className="mb-2 text-xl font-bold">Multi-Tool Chat</div>
        <div className="text-[80%] text-slate-300">
          <FontAwesomeIcon icon={faCode} className="mr-2" />
          Coding Challenge
        </div>
      </div>
      <div>
        <button className="chat-new-button" onClick={newSession}>
          <FontAwesomeIcon icon={faPenToSquare} />
          <span>New</span>
        </button>
      </div>
    </div>
  );
}
