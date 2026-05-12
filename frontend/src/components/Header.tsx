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
        <button
          className="flex h-18 w-20 cursor-pointer flex-col items-center rounded-full bg-linear-120 from-blue-800 to-blue-600 px-4 py-2 text-2xl text-blue-100 shadow-lg shadow-blue-900 hover:from-blue-700 hover:to-blue-500"
          onClick={newSession}
        >
          <FontAwesomeIcon icon={faPenToSquare} className="pt-2" />
          <span className="pt-2 text-xs">New</span>
        </button>
      </div>
    </div>
  );
}
