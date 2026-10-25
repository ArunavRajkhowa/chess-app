import "./Art.css";

/** The home hero: a corner of the board with a knight, and the coach's brass arrow over it. */
export function Hero({ width = 160, className = "" }: { width?: number; className?: string }) {
  return (
    <svg className={`art ${className}`} width={width} height={width * 0.75} viewBox="0 0 160 120" aria-hidden="true">
      <rect x="20" y="20" width="40" height="40" className="fill-soft" />
      <rect x="60" y="60" width="40" height="40" className="fill-soft" />
      <rect x="100" y="20" width="40" height="40" className="fill-soft" />
      <path d="M20 20h120M20 60h120M20 100h120M60 20v80M100 20v80" className="line" />
      <path d="M70 92h20l-2-6c7-3 9-10 7-16-1.5-4.5-5.5-7.5-10-8.5l-1.5-3.5-2.5 4c-6 2-9 7.5-9 13l5 2.5 2.5-3c0 4.5-4 7.5-8 10.5zM83 68a1.2 1.2 0 1 0 .01 0" className="line" />
      <path d="M78 54L112 30" className="line" style={{ stroke: "var(--brand)", strokeWidth: 4 }} />
      <path d="M104 26l12-2-3 12z" className="fill" />
    </svg>
  );
}
