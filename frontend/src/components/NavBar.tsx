import { faTrash } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import moment from "moment";

export type NavBarArgs = {
  activeSessionId: string | null;
  sessions: { session_id: string; title: string; created_at: Date }[];
  reuseSession: (session_id: string) => void;
  deleteSession: (session_id: string) => void;
};

export default function NavBar({
  sessions,
  activeSessionId,
  reuseSession,
  deleteSession,
}: NavBarArgs) {
  return (
    <nav className="chat-sidebar">
      {sessions.length > 0 && <div className="mx-4 mb-2">Recents:</div>}

      {sessions.map((it, i) => {
        return (
          <div
            key={i}
            className="bg m-h-20 mx-2 mb-2 flex items-center rounded-xl bg-slate-900 ring ring-slate-800 hover:bg-slate-700"
          >
            <button
              onClick={() => reuseSession(it.session_id)}
              className="text-overflow-ellipsis line-clamp-2 w-full px-4 py-1 text-left hover:cursor-pointer"
            >
              <div className="flex-col items-center justify-center">
                <div
                  className={
                    activeSessionId == it.session_id
                      ? "flex text-[80%] text-amber-400"
                      : "flex text-[80%]"
                  }
                >
                  {it.title.length > 80
                    ? it.title.substring(0, 80) + "..."
                    : it.title}
                </div>
                <div className="flex text-[80%] text-slate-400">
                  {moment(it.created_at).fromNow()}
                </div>
              </div>
            </button>
            <button
              className="mx-3 w-fit rounded-2xl hover:cursor-pointer hover:text-red-500"
              onClick={() => deleteSession(it.session_id)}
            >
              <FontAwesomeIcon icon={faTrash} size="1x" />
              <i className="fa-trash"></i>
            </button>
          </div>
        );
      })}
    </nav>
  );
}
