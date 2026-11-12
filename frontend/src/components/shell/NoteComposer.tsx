import { Pencil, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, type NoteKind } from "../../lib/api";
import "./NoteComposer.css";

const KINDS: { kind: NoteKind; label: string }[] = [
  { kind: "bug", label: "Bug" },
  { kind: "wrong", label: "Wrong" },
  { kind: "unclear", label: "Unclear" },
  { kind: "idea", label: "Idea" },
  { kind: "praise", label: "Praise" },
];
const SEEN = "notes.answered-seen"; // ids of answered notes the player was already told about
// Right-click here keeps the browser's own menu: fields, links, and the composer itself.
const NATIVE_MENU = "input, textarea, select, a[href], [contenteditable], .note-composer";

const HEADING = "main h1, main h2, main h3";

/** The text of the page heading closest to an element: its own section's first, then further out. */
function headingNear(el: Element | null): string {
  for (let e = el; e && e !== document.body; e = e.parentElement) {
    const h = e.matches(HEADING) ? e : e.querySelector(HEADING);
    const text = h?.textContent?.trim();
    if (text) return text.slice(0, 240);
  }
  return "";
}

function readSeen(): number[] {
  try {
    return JSON.parse(localStorage.getItem(SEEN) ?? "[]");
  } catch {
    return []; // storage off: the player may be told twice
  }
}

/** Leave a note on any place in the app: right-click (Shift+right-click keeps the browser menu) or the
 * pencil button. Also tells the player, once, when the owner answered one of their notes. */
export function NoteComposer() {
  const { pathname } = useLocation();
  const dialog = useRef<HTMLDialogElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const [where, setWhere] = useState<{ anchor: string; quote: string } | null>(null);
  const [kind, setKind] = useState<NoteKind>("bug");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  const open = (near: Element | null) => {
    setWhere({ anchor: headingNear(near), quote: (getSelection()?.toString().trim() ?? "").slice(0, 600) });
    dialog.current?.showModal();
    field.current?.focus();
  };

  useEffect(() => {
    const onMenu = (e: MouseEvent) => {
      // The board draws arrows on right-click and prevents the menu itself; a touch long-press keeps text selection.
      if (e.defaultPrevented || e.shiftKey || (e as PointerEvent).pointerType === "touch") return;
      if (!(e.target instanceof Element) || e.target.closest(NATIVE_MENU)) return;
      e.preventDefault();
      open(e.target);
    };
    document.addEventListener("contextmenu", onMenu);
    return () => document.removeEventListener("contextmenu", onMenu);
  }, []);

  useEffect(() => {
    api.myNotes().then(({ notes }) => {
      const seen = readSeen();
      const answered = notes.filter((n) => n.status !== "open" && !seen.includes(n.id));
      if (!answered.length) return;
      try {
        localStorage.setItem(SEEN, JSON.stringify([...seen, ...answered.map((n) => n.id)]));
      } catch {
        /* storage off */
      }
      const [n] = answered;
      const more = answered.length > 1 ? ` (and ${answered.length - 1} more)` : "";
      setToast({ ok: true, text: `Your note on ${n.page} was ${n.status === "done" ? "acted on" : "declined"}${n.resolution ? `: ${n.resolution}` : "."}${more}` });
    }).catch((err) => console.warn("notes not loaded", err));
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 8000);
    return () => clearTimeout(t);
  }, [toast]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!where) return;
    setSending(true);
    try {
      await api.leaveNote({ page: pathname, anchor: where.anchor, quote: where.quote, kind, note });
      dialog.current?.close();
      setNote("");
      setToast({ ok: true, text: "Note sent. Thank you." });
    } catch (err) {
      setToast({ ok: false, text: `Note not sent: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <button type="button" className="btn note-fab" aria-label="Leave a note" title="Leave a note (or right-click anywhere)"
        onClick={() => open(document.querySelector("main"))}>
        <Pencil size={17} strokeWidth={1.75} />
      </button>
      <dialog ref={dialog} className="note-composer" aria-labelledby="note-title" onClose={() => setWhere(null)}>
        <form onSubmit={send}>
          <div className="card-title">
            <h2 id="note-title">Leave a note</h2>
            <button type="button" className="btn btn-ghost btn-sm" aria-label="Close" onClick={() => dialog.current?.close()}><X size={16} /></button>
          </div>
          <p className="note-where">On <strong>{pathname}</strong>{where?.anchor && <> · {where.anchor}</>}</p>
          {where?.quote && <blockquote className="note-quote">{where.quote}</blockquote>}
          <fieldset className="note-kinds">
            <legend className="sr-only">Kind of note</legend>
            {KINDS.map((k) => (
              <label key={k.kind} className="chip">
                <input type="radio" name="note-kind" className="sr-only" checked={kind === k.kind} onChange={() => setKind(k.kind)} />
                {k.label}
              </label>
            ))}
          </fieldset>
          <label className="sr-only" htmlFor="note-text">Your note</label>
          <textarea ref={field} id="note-text" className="input" required minLength={3} maxLength={2000} rows={4} value={note}
            onChange={(e) => setNote(e.target.value)} placeholder="What did you notice?" />
          <div className="row note-actions">
            <button type="submit" className="btn btn-primary" disabled={sending || note.trim().length < 3}>{sending ? "Sending…" : "Send note"}</button>
          </div>
        </form>
      </dialog>
      <div className="note-toast-region" role="status" aria-live="polite">
        {toast && (
          <div className={`note-toast ${toast.ok ? "" : "note-toast-error"}`}>
            <span>{toast.text}</span>
            <button type="button" className="btn btn-ghost btn-sm" aria-label="Dismiss" onClick={() => setToast(null)}><X size={14} /></button>
          </div>
        )}
      </div>
    </>
  );
}
