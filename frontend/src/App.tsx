import { useCallback, useEffect, useRef, useState } from "react";
import BubbleAssistant from "./components/BubbleAssistant";
import BubbleReasoning from "./components/BubbleReasoning";
import BubbleTool from "./components/BubbleTool";
import BubbleUser from "./components/BubbleUser";
import { ChatBox } from "./components/ChatBox";
import ChatLoadingIndicator from "./components/ChatLoadingIndicator";
import ConfirmDialog from "./components/ConfirmDialog";
import { FileUploadItem } from "./components/FileUpload";
import Header from "./components/Header";
import NavBar from "./components/NavBar";

type ToolCall = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
};

type Item =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; source: string }
  | { kind: "tool"; call: ToolCall }
  | { kind: "streaming"; text: string }
  | { kind: "reasoning_token"; text: string };

type Session = {
  user_id: string;
  session_id: string;
  created_at: Date;
  title: string;
};

const API = ""; // proxied by vite to localhost:8000

export function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [messages, setMessages] = useState<string[]>([]);
  const [files, setFiles] = useState<FileUploadItem[]>([]);
  const [keepReasoningExpanded, setKeepReasoningExpanded] = useState(false);
  const [confirm, setConfirm] = useState<{
    message: string;
    onConfirm: () => void;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const withConfirm = (message: string, action: () => void) => {
    if (!busy) {
      action();
      return;
    }
    setConfirm({
      message,
      onConfirm: () => {
        setConfirm(null);
        action();
      },
    });
  };

  const loadSessions = () => {
    fetch(`/sessions`, { method: "GET" })
      .then((response) => response.json())
      .then((data) => setSessions(data));
  };

  useEffect(loadSessions, [activeSessionId]);

  const send = useCallback(async () => {
    const textMessages: string[] = [input.trim()];
    if (!textMessages || busy) return;
    if (files && files.length > 0) {
      textMessages.push(
        "\n\nAttached Files: " + files.map((f) => `**${f.name}**`).join(","),
      );
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setMessages((m) => [...m, textMessages.join("\n")]);
    setItems((xs) => [
      ...xs,
      { kind: "user", text: textMessages.join("\n"), files: files },
    ]);
    setInput("");
    setFiles([]);
    setBusy(true);

    try {
      const resp = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeSessionId,
          message: textMessages.join("\n\n"),
          files: files,
        }),
        signal: controller.signal,
      });
      if (!resp.body) {
        setBusy(false);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      const handleEvent = (evt: string, data: Record<string, any>) => {
        if (evt === "session") {
          setActiveSessionId(data.session_id);
        } else if (evt === "reasoning_token") {
          setItems((xs) => {
            const last = xs[xs.length - 1];
            if (last && last.kind === "reasoning_token") {
              return [
                ...xs.slice(0, -1),
                { kind: "reasoning_token", text: last.text + data.content },
              ];
            }
            return [...xs, { kind: "reasoning_token", text: data.content }];
          });
        } else if (evt === "token") {
          setItems((xs) => {
            const last = xs[xs.length - 1];
            if (last && last.kind === "streaming") {
              return [
                ...xs.slice(0, -1),
                { kind: "streaming", text: last.text + data.content },
              ];
            }
            return [...xs, { kind: "streaming", text: data.content }];
          });
        } else if (evt === "tool_call") {
          const call: ToolCall = {
            id: data.id,
            name: data.name,
            args: data.args,
          };
          setItems((xs) => [...xs, { kind: "tool", call }]);
        } else if (evt === "tool_result") {
          const handle = JSON.stringify(data.content);
          setItems((xs) =>
            xs.map((it) =>
              it.kind === "tool" && it.call.id === data.tool_call_id
                ? { kind: "tool", call: { ...it.call, result: handle } }
                : it,
            ),
          );
        } else if (evt === "message") {
          setItems((xs) => {
            const withoutStreaming =
              xs.length > 0 && xs[xs.length - 1].kind === "streaming"
                ? xs.slice(0, -1)
                : xs;
            return [
              ...withoutStreaming,
              {
                kind: "assistant",
                text: String(data.content),
                source: data.source,
              },
            ];
          });
        } else if (evt === "done") {
          setBusy(false);
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split(/[\n\r]/);
        buf = blocks.pop() ?? "";
        let evt = "message";
        let dataStr = "";
        for (const block of blocks) {
          const lines = block.split("\n");
          for (const line of lines) {
            if (line.trim() == "") continue;
            if (line.startsWith("event:")) evt = line.slice(6).trim();
            else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
          }
          if (dataStr && evt) {
            handleEvent(evt, JSON.parse(dataStr));
            break;
          }
        }
      }
      if (!controller.signal.aborted) setBusy(false);
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return;
      if (!controller.signal.aborted) setBusy(false);
    }
  }, [input, busy]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 250);
  };

  useEffect(() => {
    scrollToBottom();
  }, [items]);

  const reuseSession = (session_id: string) => {
    withConfirm(
      "Switch sessions? Your current operation will be cancelled.",
      () => doReuseSession(session_id),
    );
  };

  const doReuseSession = async (session_id: string) => {
    abortRef.current?.abort();
    setBusy(false);
    setActiveSessionId(session_id);
    setItems([]);
    setMessages([]);
    setLoadingHistory(true);
    try {
      const resp = await fetch(`/sessions/${session_id}/messages`);
      const data: Item[] = await resp.json();
      setItems(data);
      setMessages(data.filter((x) => x.kind == "user").map((x) => x.text));
    } catch {
      setItems([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  const newSession = () => {
    withConfirm(
      "Start a new session? Your current operation will be cancelled.",
      () => {
        abortRef.current?.abort();
        setBusy(false);
        setActiveSessionId(null);
        setItems([]);
        setMessages([]);
        inputRef.current?.focus();
      },
    );
  };

  const deleteSession = (session_id: string) => {
    fetch(`/sessions?session_id=${session_id}`, { method: "DELETE" });
    if (activeSessionId == session_id) {
      abortRef.current?.abort();
      setBusy(false);
      setActiveSessionId(null);
      setItems([]);
      setMessages([]);
    }
    loadSessions();
  };

  const inputRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    inputRef?.current?.focus();
  }, [busy]);

  return (
    <div className="app-container flex h-screen">
      {confirm && (
        <ConfirmDialog
          message={confirm.message}
          onConfirm={confirm.onConfirm}
          onCancel={() => setConfirm(null)}
        />
      )}
      <aside>
        <Header newSession={newSession} />

        <NavBar
          activeSessionId={activeSessionId}
          sessions={sessions}
          deleteSession={(session_id) =>
            setConfirm({
              message: "Do you want to delete this session?",
              onConfirm: () => {
                deleteSession(session_id);
                setConfirm(null);
              },
            })
          }
          reuseSession={reuseSession}
        />
      </aside>

      <main className="flex flex-1 flex-col gap-3">
        <div className={`chat-contents md:rounded-tl-3xl md:rounded-bl-3xl${items.length === 0 ? " justify-center" : ""}`}>
          {items.length > 0 && (
            <div className="chat-messages">
              {items.map((it, i) => {
                if (it.kind === "reasoning_token")
                  return (
                    <BubbleReasoning
                      text={it.text}
                      reasoningExpanded={keepReasoningExpanded}
                    />
                  );
                if (it.kind === "user")
                  return <BubbleUser key={i} text={it.text} label="Me" />;
                if (it.kind === "assistant")
                  return (
                    <BubbleAssistant key={i} text={it.text} source={it.source} />
                  );
                if (it.kind === "streaming")
                  return <BubbleAssistant key={i} text={it.text} source="LLM" />;
                return (
                  <BubbleTool
                    key={i}
                    result={it.call.result}
                    args={it.call.args}
                    name={it.call.name}
                  />
                );
              })}

              <ChatLoadingIndicator loading={loadingHistory || busy} />

              <div ref={bottomRef} />
            </div>
          )}
          <ChatBox
            sessionId={activeSessionId}
            inputRef={inputRef}
            input={input}
            files={files}
            setFiles={setFiles}
            busy={busy}
            messages={messages}
            setInput={setInput}
            send={send}
            isNew={items.length == 0}
            reasoningExpanded={keepReasoningExpanded}
            setReasoningExpanded={setKeepReasoningExpanded}
          />
        </div>
      </main>
    </div>
  );
}
