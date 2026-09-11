import { useState, useRef, useEffect, useCallback } from "react";

// ---------------------------------------------------------------------------
// Types matching api/chat.py response schema
// ---------------------------------------------------------------------------

interface ToolTraceItem {
  name: string;
  args: Record<string, unknown>;
  source: string;
}

interface ChatResponse {
  answer: string;
  tool_trace: ToolTraceItem[];
  sources: string[];
  refused: boolean;
  refusal_reason: string;
  guard_passed: boolean;
  ungrounded_numbers: string[];
  rounds: number;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  trace?: ToolTraceItem[];
  sources?: string[];
  refused?: boolean;
  guard_passed?: boolean;
  loading?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function fetchSuggestedQuestions(): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE}/api/chat/questions`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.questions ?? [];
  } catch {
    return [];
  }
}

async function sendQuestion(
  question: string,
  dataset: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, dataset }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Chat request failed");
  }
  return res.json();
}

function uid() {
  return Math.random().toString(36).slice(2);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ToolTrace({ trace, sources }: { trace: ToolTraceItem[]; sources: string[] }) {
  const [open, setOpen] = useState(false);
  if (!trace.length) return null;

  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          background: "none",
          border: "none",
          color: "var(--color-ink-faint, #9ca3af)",
          fontSize: 11,
          cursor: "pointer",
          padding: 0,
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <span style={{ fontSize: 10 }}>{open ? "▾" : "▸"}</span>
        {trace.length} tool{trace.length > 1 ? "s" : ""} used
        {sources.length > 0 && ` · ${sources.join(", ")}`}
      </button>

      {open && (
        <div
          style={{
            marginTop: 6,
            padding: "8px 10px",
            background: "rgba(0,0,0,0.15)",
            borderRadius: 8,
            fontSize: 11,
            fontFamily: "monospace",
            color: "var(--color-ink-faint, #9ca3af)",
          }}
        >
          {trace.map((t, i) => (
            <div key={i} style={{ marginBottom: i < trace.length - 1 ? 6 : 0 }}>
              <span style={{ color: "#60a5fa" }}>{t.name}</span>
              {Object.keys(t.args).length > 0 && (
                <span> ({JSON.stringify(t.args)})</span>
              )}
              {t.source && (
                <span style={{ opacity: 0.6 }}> → {t.source}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        marginBottom: 12,
      }}
    >
      <div
        style={{
          maxWidth: "88%",
          padding: "10px 14px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "4px 18px 18px 18px",
          background: isUser
            ? "linear-gradient(135deg, #2563eb, #7c3aed)"
            : "rgba(255,255,255,0.07)",
          color: "#f1f5f9",
          fontSize: 13.5,
          lineHeight: 1.55,
          boxShadow: isUser
            ? "0 2px 12px rgba(37,99,235,0.3)"
            : "0 1px 4px rgba(0,0,0,0.2)",
          border: isUser ? "none" : "1px solid rgba(255,255,255,0.08)",
          position: "relative",
        }}
      >
        {msg.loading ? (
          <span style={{ opacity: 0.6 }}>
            <TypingDots />
          </span>
        ) : (
          <>
            {msg.refused && (
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  color: "#f59e0b",
                  marginBottom: 6,
                  textTransform: "uppercase",
                }}
              >
                ⚠ Not available
              </div>
            )}
            {!msg.guard_passed && msg.guard_passed !== undefined && (
              <div
                style={{
                  fontSize: 10,
                  color: "#f97316",
                  marginBottom: 4,
                }}
              >
                ⚠ Some figures may be unverified
              </div>
            )}
            <span style={{ whiteSpace: "pre-wrap" }}>{msg.text}</span>
          </>
        )}
      </div>

      {!isUser && !msg.loading && msg.trace && (
        <div style={{ maxWidth: "88%", paddingLeft: 4 }}>
          <ToolTrace trace={msg.trace} sources={msg.sources ?? []} />
        </div>
      )}
    </div>
  );
}

function TypingDots() {
  return (
    <span style={{ display: "inline-flex", gap: 3, alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#94a3b8",
            display: "inline-block",
            animation: `chatDot 1.2s ${i * 0.2}s ease-in-out infinite`,
          }}
        />
      ))}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main ChatPanel component
// ---------------------------------------------------------------------------

interface ChatPanelProps {
  /** Pass true only when /api/health confirmed the backend is reachable. */
  backendConnected: boolean;
  /** 'historical' | 'live' — determines which dataset the agent grounds on. */
  dataset: string;
}

export function ChatPanel({ backendConnected, dataset }: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestedQs, setSuggestedQs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Fetch suggested questions once the panel is first opened.
  useEffect(() => {
    if (open && suggestedQs.length === 0) {
      fetchSuggestedQuestions().then(setSuggestedQs);
    }
  }, [open]);

  // Scroll to bottom on new message.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input when opened.
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || loading) return;
      setInput("");
      setError(null);

      const userMsg: Message = { id: uid(), role: "user", text: q };
      const loadingMsg: Message = {
        id: uid(),
        role: "assistant",
        text: "",
        loading: true,
      };

      setMessages((prev) => [...prev, userMsg, loadingMsg]);
      setLoading(true);

      try {
        const resp = await sendQuestion(q, dataset);
        setMessages((prev) =>
          prev.map((m) =>
            m.loading
              ? {
                  id: m.id,
                  role: "assistant",
                  text: resp.answer,
                  trace: resp.tool_trace,
                  sources: resp.sources,
                  refused: resp.refused,
                  guard_passed: resp.guard_passed,
                }
              : m
          )
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
        setMessages((prev) => prev.filter((m) => !m.loading));
      } finally {
        setLoading(false);
      }
    },
    [loading, dataset]
  );

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  // The offline rule (D16): hide the panel entirely when the backend is unreachable.
  if (!backendConnected) return null;

  return (
    <>
      {/* Keyframe injection */}
      <style>{`
        @keyframes chatDot {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
        @keyframes chatPanelIn {
          from { opacity: 0; transform: translateY(12px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>

      {/* Floating action button */}
      <button
        id="chat-fab"
        onClick={() => setOpen((o) => !o)}
        title="Ask HeatLens"
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 1000,
          width: 56,
          height: 56,
          borderRadius: "50%",
          border: "none",
          cursor: "pointer",
          background: "linear-gradient(135deg, #2563eb, #7c3aed)",
          boxShadow: "0 4px 20px rgba(37,99,235,0.5)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 22,
          transition: "transform 0.2s, box-shadow 0.2s",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.1)";
          (e.currentTarget as HTMLButtonElement).style.boxShadow =
            "0 6px 28px rgba(37,99,235,0.65)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)";
          (e.currentTarget as HTMLButtonElement).style.boxShadow =
            "0 4px 20px rgba(37,99,235,0.5)";
        }}
      >
        {open ? "✕" : "💬"}
      </button>

      {/* Chat panel */}
      {open && (
        <div
          id="chat-panel"
          style={{
            position: "fixed",
            bottom: 92,
            right: 24,
            zIndex: 999,
            width: 380,
            maxWidth: "calc(100vw - 48px)",
            height: 520,
            maxHeight: "calc(100vh - 120px)",
            display: "flex",
            flexDirection: "column",
            borderRadius: 16,
            overflow: "hidden",
            background:
              "linear-gradient(180deg, rgba(15,23,42,0.97) 0%, rgba(15,23,42,0.99) 100%)",
            backdropFilter: "blur(24px)",
            border: "1px solid rgba(255,255,255,0.1)",
            boxShadow:
              "0 24px 64px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.07)",
            animation: "chatPanelIn 0.2s ease-out",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "14px 16px",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.03)",
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: "linear-gradient(135deg, #2563eb, #7c3aed)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 16,
                }}
              >
                🔥
              </div>
              <div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 14,
                    color: "#f1f5f9",
                    letterSpacing: "-0.01em",
                  }}
                >
                  HeatLens Assistant
                </div>
                <div style={{ fontSize: 11, color: "#64748b" }}>
                  Grounded on {dataset} data
                </div>
              </div>
            </div>
            <div
              style={{
                fontSize: 10,
                color: "#22c55e",
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "#22c55e",
                  display: "inline-block",
                }}
              />
              Live
            </div>
          </div>

          {/* Messages area */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px 14px",
              scrollbarWidth: "thin",
              scrollbarColor: "rgba(255,255,255,0.1) transparent",
            }}
          >
            {messages.length === 0 ? (
              <div style={{ paddingBottom: 8 }}>
                <p
                  style={{
                    fontSize: 12.5,
                    color: "#64748b",
                    marginBottom: 12,
                    lineHeight: 1.5,
                  }}
                >
                  Ask me anything about the heat-stress data. Every number I give
                  traces back to a data tool — I never invent figures.
                </p>

                {suggestedQs.length > 0 && (
                  <div>
                    <p
                      style={{
                        fontSize: 11,
                        color: "#475569",
                        marginBottom: 8,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      Suggested
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {suggestedQs.slice(0, 5).map((q, i) => (
                        <button
                          key={i}
                          onClick={() => send(q)}
                          style={{
                            textAlign: "left",
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid rgba(255,255,255,0.07)",
                            borderRadius: 10,
                            padding: "8px 12px",
                            color: "#94a3b8",
                            fontSize: 12.5,
                            cursor: "pointer",
                            transition: "background 0.15s, color 0.15s",
                          }}
                          onMouseEnter={(e) => {
                            (e.currentTarget as HTMLButtonElement).style.background =
                              "rgba(37,99,235,0.15)";
                            (e.currentTarget as HTMLButtonElement).style.color = "#e2e8f0";
                          }}
                          onMouseLeave={(e) => {
                            (e.currentTarget as HTMLButtonElement).style.background =
                              "rgba(255,255,255,0.04)";
                            (e.currentTarget as HTMLButtonElement).style.color = "#94a3b8";
                          }}
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
            )}

            {error && (
              <div
                style={{
                  padding: "8px 12px",
                  background: "rgba(239,68,68,0.1)",
                  borderRadius: 8,
                  border: "1px solid rgba(239,68,68,0.2)",
                  color: "#fca5a5",
                  fontSize: 12.5,
                  marginTop: 4,
                }}
              >
                ❌ {error}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div
            style={{
              padding: "10px 12px",
              borderTop: "1px solid rgba(255,255,255,0.06)",
              background: "rgba(0,0,0,0.2)",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-end",
                background: "rgba(255,255,255,0.05)",
                borderRadius: 12,
                border: "1px solid rgba(255,255,255,0.1)",
                padding: "6px 6px 6px 12px",
                transition: "border-color 0.2s",
              }}
              onFocusCapture={(e) =>
                ((e.currentTarget as HTMLDivElement).style.borderColor =
                  "rgba(37,99,235,0.5)")
              }
              onBlurCapture={(e) =>
                ((e.currentTarget as HTMLDivElement).style.borderColor =
                  "rgba(255,255,255,0.1)")
              }
            >
              <textarea
                id="chat-input"
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="Ask about heat stress data…"
                rows={1}
                disabled={loading}
                style={{
                  flex: 1,
                  background: "none",
                  border: "none",
                  outline: "none",
                  color: "#e2e8f0",
                  fontSize: 13.5,
                  resize: "none",
                  lineHeight: 1.5,
                  maxHeight: 100,
                  overflowY: "auto",
                  fontFamily: "inherit",
                }}
              />
              <button
                id="chat-send"
                onClick={() => send(input)}
                disabled={!input.trim() || loading}
                style={{
                  flexShrink: 0,
                  width: 34,
                  height: 34,
                  borderRadius: 8,
                  border: "none",
                  cursor: input.trim() && !loading ? "pointer" : "not-allowed",
                  background:
                    input.trim() && !loading
                      ? "linear-gradient(135deg, #2563eb, #7c3aed)"
                      : "rgba(255,255,255,0.07)",
                  color: "#fff",
                  fontSize: 16,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  transition: "background 0.2s",
                }}
              >
                {loading ? "⏳" : "↑"}
              </button>
            </div>
            <p
              style={{
                fontSize: 10,
                color: "#334155",
                marginTop: 6,
                textAlign: "center",
              }}
            >
              All figures are grounded on baked data — no numbers are invented.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
