import { useState, type FormEvent } from "react";
import { Bot, Check, Clipboard, LoaderCircle, Send, Sparkles, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type AskAnswer } from "@/lib/api";

type Message = { id: string; role: "user" | "assistant"; text: string; answer?: AskAnswer; error?: boolean };

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
  const [messages, setMessages] = useState<Message[]>([{ id: "welcome", role: "assistant", text: "Hello. Ask me about sales, expenses, profit, products, unusual activity, or changes between months." }]);
  const [question, setQuestion] = useState("");
  const [isWaiting, setIsWaiting] = useState(false);

  async function submitQuestion(nextQuestion?: string) {
    const text = (nextQuestion ?? question).trim();
    if (!text || isWaiting) return;
    setQuestion("");
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text }]);
    setIsWaiting(true);
    try {
      const answer = await api.ask(text);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: answer.text, answer }]);
    } catch (reason) {
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", error: true, text: reason instanceof ApiError ? reason.message : "I could not get an answer right now. Please try again." }]);
    } finally {
      setIsWaiting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submitQuestion(); }

  return <section className="mx-auto max-w-4xl">
    <p className="eyebrow">Ask AI</p>
    <h1 className="mt-2 text-3xl font-bold tracking-tight">Ask about your business in plain language.</h1>
    <p className="mt-3 max-w-2xl leading-7 text-muted">Answers are calculated from your data. You can open the source table to see the numbers used.</p>
    <div className="mt-6 flex flex-wrap gap-2">{suggestions.map((suggestion) => <button key={suggestion} type="button" disabled={isWaiting} onClick={() => void submitQuestion(suggestion)} className="rounded-full border bg-surface px-3 py-2 text-sm font-medium text-ink transition-colors hover:border-brand hover:text-brand disabled:opacity-50">{suggestion}</button>)}</div>
    <Card className="mt-7 overflow-hidden"><div className="min-h-[420px] space-y-6 p-5 sm:p-7">{messages.map((message) => <ChatMessage key={message.id} message={message} />)}{isWaiting && <div className="flex gap-3"><Avatar type="assistant" /><div className="rounded-2xl rounded-tl-md bg-slate-100 px-4 py-3 text-sm text-muted dark:bg-slate-800"><span className="inline-flex items-center gap-2"><LoaderCircle className="animate-spin text-brand" size={17} /> Looking at your data… This can take 10–30 seconds while the local AI prepares an answer.</span></div></div>}</div><form onSubmit={onSubmit} className="border-t bg-slate-50 p-4 dark:bg-slate-900"><label className="sr-only" htmlFor="ask-question">Ask a question about your business</label><div className="flex items-end gap-3"><textarea id="ask-question" value={question} onChange={(event) => setQuestion(event.target.value)} disabled={isWaiting} rows={2} maxLength={2000} placeholder="For example: Which products brought in the most money?" className="min-h-11 flex-1 resize-none rounded-xl border bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted" /><Button type="submit" disabled={!question.trim() || isWaiting} aria-label="Send question"><Send size={18} /><span className="hidden sm:inline">Ask</span></Button></div></form></Card>
  </section>;
}

function ChatMessage({ message }: { message: Message }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  async function copyAnswer() {
    try { await navigator.clipboard.writeText(message.text); setCopied(true); window.setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); }
  }
  return <div className={`flex gap-3 ${isUser ? "justify-end" : ""}`}><>{!isUser && <Avatar type="assistant" />}</><div className={`max-w-[88%] ${isUser ? "order-first" : ""}`}><div className={`rounded-2xl px-4 py-3 text-sm leading-6 ${isUser ? "rounded-tr-md bg-brand text-white" : message.error ? "rounded-tl-md bg-rose-50 text-rose-800 dark:bg-rose-950 dark:text-rose-100" : "rounded-tl-md bg-slate-100 text-ink dark:bg-slate-800"}`}><p className="whitespace-pre-wrap">{message.text}</p></div>{message.answer && <div className="mt-3 flex flex-wrap items-center gap-2"><SourcePanel answer={message.answer} /><Button type="button" size="sm" variant="outline" onClick={() => void copyAnswer()}>{copied ? <Check size={15} /> : <Clipboard size={15} />}{copied ? "Copied" : "Copy"}</Button></div>}</div>{isUser && <Avatar type="user" />}</div>;
}

function Avatar({ type }: { type: "assistant" | "user" }) { return <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${type === "assistant" ? "bg-blue-50 text-brand dark:bg-blue-950" : "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100"}`}>{type === "assistant" ? <Bot size={18} /> : <UserRound size={18} />}</span>; }

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
          <span>Question Intent: <strong className="font-semibold text-ink">{friendlyIntent(answer.intent)}</strong></span>
          {answer.metric && <span>Metric: <strong className="font-semibold uppercase text-ink">{answer.metric}</strong></span>}
          {answer.period_label && <span>Period: <strong className="font-semibold text-ink">{answer.period_label}</strong></span>}
        </div>
        {answer.headline && (
          <div className="rounded-lg border border-blue-100 bg-blue-50/70 p-2.5 text-xs text-blue-900 dark:border-blue-900/40 dark:bg-blue-950/40 dark:text-blue-200">
            <span className="mb-0.5 block font-semibold">Code-verified calculation:</span>
            {answer.headline}
          </div>
        )}
        {answer.table.columns.length === 0 ? (
          <p className="text-sm text-muted">There was no source table for this answer.</p>
        ) : (
          <SourceTable columns={answer.table.columns} rows={answer.table.rows} />
        )}
      </div>
    </details>
  );
}

function SourceTable({ columns, rows }: { columns: string[]; rows: Array<Record<string, unknown>> }) { return <div className="overflow-x-auto"><table className="min-w-full text-left text-xs"><thead className="border-b text-muted"><tr>{columns.map((column) => <th key={column} className="whitespace-nowrap px-2 py-2 font-medium">{column}</th>)}</tr></thead><tbody>{rows.length === 0 ? <tr><td className="px-2 py-3 text-muted" colSpan={columns.length}>No rows were returned.</td></tr> : rows.map((row, index) => <tr key={index} className="border-b last:border-0">{columns.map((column) => <td key={column} className="whitespace-nowrap px-2 py-2">{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div>; }

function friendlyIntent(intent: string) { return intent.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
