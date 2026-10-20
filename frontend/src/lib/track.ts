import type { EventName, EventProps } from "./api";

/** Sends one analytics event. A failure is logged and never interrupts play. */
export function track<N extends EventName>(name: N, props: EventProps[N]): void {
  fetch("/api/events", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, props }) })
    .then((res) => { if (!res.ok) console.warn(`analytics event ${name} refused: HTTP ${res.status}`); })
    .catch((err) => console.warn(`analytics event ${name} not sent`, err));
}
