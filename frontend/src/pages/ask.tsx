import { useEffect, useState, type FormEvent } from "react";
import {
  Bot,
  Check,
  Clipboard,
  History,
  LoaderCircle,
  MessageSquare,
  Send,
  Sparkles,
  Trash2,
  UserRound,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type AskAnswer, type ChatMessageItem } from "@/lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  answer?: AskAnswer;
  error?: boolean;
  createdAt?: string | null;
};

const suggestions = [
  "What are my top 5 products?",
  "Which items sold the lowest volume?",
  "What was my highest revenue month?",
  "What were my biggest expenses?",
  "What is my net profit?",
  "How is my business performing?",
  "Compare this month with last month",
  "Are there any unusual spikes or drops?",
  "Why did profit change between periods?",
];

export function AskPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Hello! Ask me about sales, expenses, profit, top or bottom products, unusual activity, or changes between months.",
    },
  ]);
  const [savedHistory, setSavedHistory] = useState<ChatMessageItem[]>([]);
  const [question, setQuestion] = useState("");
  const [isWaiting, setIsWaiting] = useState(false);
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Load past chat history on page mount
  useEffect(() => {
    let isMounted = true;
    async function loadHistory() {
      try {
        const history = await api.chatHistory();
        if (!isMounted) return;
        setSavedHistory(history);

        if (history.length > 0) {
          // Reconstruct conversation messages in chronological order
          const restoredMessages: Message[] = [
            {
              id: "welcome",
              role: "assistant",
              text: "Hello! Here are your previous questions and answers. Feel free to ask a new question or pick from the suggested prompts below.",
            },
          ];

          // history is returned latest first from API, so reverse for chat timeline
          const chronological = [...history].reverse();
          for (const item of chronological) {
            restoredMessages.push({
              id: `q-${item.id}`,
              role: "user",
              text: item.question,
              createdAt: item.created_at,
            });

            const answerObj: AskAnswer = {
              text: item.answer_text,
              intent: item.intent ?? "unknown",
              metric: item.metric,
              period: item.period,
              period_label: item.period_label,
              headline: item.headline,
              table: item.table ?? { columns: [], rows: [] },
            };

            restoredMessages.push({
              id: `a-${item.id}`,
              role: "assistant",
              text: item.answer_text,
              answer: answerObj,
              createdAt: item.created_at,
            });
          }

          setMessages(restoredMessages);
        }
      } catch (err) {
        console.warn("Could not load chat history:", err);
      }
    }

    void loadHistory();
    return () => {
      isMounted = false;
    };
  }, []);

  async function submitQuestion(nextQuestion?: string) {
    const text = (nextQuestion ?? question).trim();
    if (!text || isWaiting) return;
    setQuestion("");
    setStatusMessage(null);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text }]);
    setIsWaiting(true);

    try {
      const answer = await api.ask(text);
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "assistant", text: answer.text, answer },
      ]);
      // Refresh saved history list
      api.chatHistory().then(setSavedHistory).catch(() => {});
    } catch (reason) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          error: true,
          text:
            reason instanceof ApiError
              ? reason.message
              : "I could not get an answer right now. Please try again.",
        },
      ]);
    } finally {
      setIsWaiting(false);
    }
  }

  async function handleClearHistory() {
    setIsClearingHistory(true);
    try {
      await api.clearChatHistory();
      setSavedHistory([]);
      setMessages([
        {
          id: "welcome-cleared",
          role: "assistant",
          text: "Chat history cleared. Ask me anything about your business sales, expenses, or profit.",
        },
      ]);
      setShowClearConfirm(false);
      setStatusMessage("Chat history cleared successfully.");
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Failed to clear history.");
    } finally {
      setIsClearingHistory(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion();
  }

  return (
    <section className="mx-auto max-w-4xl space-y-6">
      {/* Header with Title and History Actions */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="eyebrow">Ask AI</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">Ask about your business in plain language.</h1>
          <p className="mt-2 max-w-2xl leading-6 text-muted">
            Answers are calculated directly from your uploaded files. Questions and verified answers are automatically saved to your history.
          </p>
        </div>

        {/* History Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {savedHistory.length > 0 && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowHistoryDrawer(!showHistoryDrawer)}
                className="gap-1.5 text-xs font-medium"
              >
                <History size={14} className="text-brand" />
                <span>Past Questions ({savedHistory.length})</span>
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowClearConfirm(true)}
                className="gap-1.5 text-xs font-medium text-rose-600 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950/40"
              >
                <Trash2 size={14} />
                <span>Clear History</span>
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Status Feedback Banner */}
      {statusMessage && (
        <div className="flex items-center justify-between rounded-xl border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/40 dark:text-blue-200">
          <span>{statusMessage}</span>
          <button onClick={() => setStatusMessage(null)} className="text-blue-600 hover:text-blue-800">
            <X size={14} />
          </button>
        </div>
      )}

      {/* Confirmation Dialog for Clearing History */}
      {showClearConfirm && (
        <Card className="border-rose-200 bg-rose-50/60 p-4 dark:border-rose-900/50 dark:bg-rose-950/20">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-rose-900 dark:text-rose-200">Clear all saved chat history?</p>
              <p className="text-xs text-rose-700 dark:text-rose-300">
                This will delete your {savedHistory.length} saved conversation items from the database. This action cannot be undone.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowClearConfirm(false)}
                disabled={isClearingHistory}
                className="h-8 text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => void handleClearHistory()}
                disabled={isClearingHistory}
                className="h-8 gap-1.5 bg-rose-600 text-xs text-white hover:bg-rose-700"
              >
                {isClearingHistory && <LoaderCircle size={13} className="animate-spin" />}
                <span>Yes, Clear History</span>
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Collapsible Past Questions Drawer */}
      {showHistoryDrawer && savedHistory.length > 0 && (
        <Card className="border-brand/20 bg-surface p-4">
          <div className="flex items-center justify-between border-b pb-2">
            <div className="flex items-center gap-2">
              <MessageSquare size={16} className="text-brand" />
              <h2 className="text-sm font-semibold text-ink">Recently Asked Business Questions</h2>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowHistoryDrawer(false)}
              className="h-7 w-7 p-0 text-muted hover:text-ink"
            >
              <X size={14} />
            </Button>
          </div>
          <div className="mt-3 grid max-h-52 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
            {savedHistory.slice(0, 10).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setShowHistoryDrawer(false);
                  void submitQuestion(item.question);
                }}
                className="flex flex-col items-start rounded-xl border bg-background p-2.5 text-left text-xs transition-colors hover:border-brand hover:bg-brand/5"
              >
                <span className="font-medium text-ink">{item.question}</span>
                <span className="mt-1 text-[10px] text-muted">
                  {item.period_label || item.metric ? `${item.metric?.toUpperCase() || "QUERY"} • ${item.period_label || "ALL TIME"}` : "Saved Question"}
                </span>
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* Suggested Prompts Pills */}
      <div>
        <p className="text-xs font-medium text-muted">Suggested questions:</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={isWaiting}
              onClick={() => void submitQuestion(suggestion)}
              className="rounded-full border bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-brand hover:text-brand disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>

      {/* Main Chat Box */}
      <Card className="overflow-hidden shadow-sm">
        <div className="min-h-[420px] max-h-[600px] space-y-6 overflow-y-auto p-5 sm:p-7">
          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          {isWaiting && (
            <div className="flex gap-3">
              <Avatar type="assistant" />
              <div className="rounded-2xl rounded-tl-md bg-slate-100 px-4 py-3 text-sm text-muted dark:bg-slate-800">
                <span className="inline-flex items-center gap-2">
                  <LoaderCircle className="animate-spin text-brand" size={17} />
                  Analyzing your financial data… This takes a few seconds while numbers are calculated and verified.
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <form onSubmit={onSubmit} className="border-t bg-slate-50 p-4 dark:bg-slate-900">
          <label className="sr-only" htmlFor="ask-question">
            Ask a question about your business
          </label>
          <div className="flex items-end gap-3">
            <textarea
              id="ask-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submitQuestion();
                }
              }}
              disabled={isWaiting}
              rows={2}
              maxLength={2000}
              placeholder="Ask anything... e.g. Which products brought in the most revenue? (Press Enter to send)"
              className="min-h-11 flex-1 resize-none rounded-xl border bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-brand"
            />
            <Button
              type="submit"
              disabled={!question.trim() || isWaiting}
              aria-label="Send question"
              className="h-11 px-4"
            >
              <Send size={16} />
              <span className="hidden sm:inline">Ask</span>
            </Button>
          </div>
        </form>
      </Card>
    </section>
  );
}

function ChatMessage({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : ""}`}>
      {!isUser && <Avatar type="assistant" />}
      <div className={`max-w-[88%] ${isUser ? "order-first" : ""}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
            isUser
              ? "rounded-tr-md bg-brand text-white"
              : message.error
              ? "rounded-tl-md bg-rose-50 text-rose-800 dark:bg-rose-950 dark:text-rose-100"
              : "rounded-tl-md bg-slate-100 text-ink dark:bg-slate-800"
          }`}
        >
          <p className="whitespace-pre-wrap">{message.text}</p>
        </div>
        {message.answer && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <SourcePanel answer={message.answer} />
            <Button type="button" size="sm" variant="outline" onClick={() => void copyAnswer()}>
              {copied ? <Check size={15} /> : <Clipboard size={15} />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        )}
      </div>
      {isUser && <Avatar type="user" />}
    </div>
  );
}

function Avatar({ type }: { type: "assistant" | "user" }) {
  return (
    <span
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
        type === "assistant"
          ? "bg-blue-50 text-brand dark:bg-blue-950"
          : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100"
      }`}
    >
      {type === "assistant" ? <Bot size={18} /> : <UserRound size={18} />}
    </span>
  );
}

function SourcePanel({ answer }: { answer: AskAnswer }) {
  return (
    <details className="w-full rounded-xl border bg-surface p-3.5">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold">
        <Sparkles size={16} className="text-brand" />
        <span>How I got this</span>
        <span className="ml-auto text-xs font-normal text-muted">Calculated from your data</span>
      </summary>
      <div className="mt-4 space-y-3">
        <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
          <span>
            Question Intent: <strong className="font-semibold text-ink">{friendlyIntent(answer.intent)}</strong>
          </span>
          {answer.metric && (
            <span>
              Metric: <strong className="font-semibold uppercase text-ink">{answer.metric}</strong>
            </span>
          )}
          {answer.period_label && (
            <span>
              Period: <strong className="font-semibold text-ink">{answer.period_label}</strong>
            </span>
          )}
        </div>
        {answer.headline && (
          <div className="rounded-lg border border-blue-100 bg-blue-50/70 p-2.5 text-xs text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/40 dark:text-blue-200">
            <span className="mb-0.5 block font-semibold">Code-verified calculation:</span>
            {answer.headline}
          </div>
        )}
        {answer.table && answer.table.columns && answer.table.columns.length > 0 ? (
          <SourceTable columns={answer.table.columns} rows={answer.table.rows} />
        ) : (
          <p className="text-sm text-muted">There was no source table for this answer.</p>
        )}
      </div>
    </details>
  );
}

function SourceTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-xs">
        <thead className="border-b text-muted">
          <tr>
            {columns.map((column) => (
              <th key={column} className="whitespace-nowrap px-2 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="px-2 py-3 text-muted" colSpan={columns.length}>
                No rows were returned.
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={index} className="border-b last:border-0">
                {columns.map((column) => (
                  <td key={column} className="whitespace-nowrap px-2 py-2">
                    {String(row[column] ?? "—")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function friendlyIntent(intent: string) {
  return intent.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
