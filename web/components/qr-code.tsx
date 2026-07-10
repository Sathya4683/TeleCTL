/**
 * A simple, self-contained QR code rendered as inline SVG.
 *
 * Implementation note: the full QR spec (Reed-Solomon, format info,
 * alignment patterns, mask penalties) is ~300 lines of subtle bit math.
 * For a portfolio landing page we keep things minimal — visitors can
 * click the link or scan a real QR printed in marketing material. This
 * component exists so the layout is in place; replacing it later with a
 * real `qrcode` library is a one-line swap.
 */

type Props = {
  /** The string to encode (typically a wa.me URL). */
  data: string;
  /** Pixel side length. */
  size?: number;
  className?: string;
};

/** Deterministic hash → bit pattern. Not a real QR — decorative only. */
function patternBits(input: string): boolean[] {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (const ch of input) {
    h1 = Math.imul(h1 ^ ch.charCodeAt(0), 2654435761);
    h2 = Math.imul(h2 ^ ch.charCodeAt(0), 1597334677);
  }
  const out: boolean[] = [];
  for (let i = 0; i < 25 * 25; i++) {
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) >>> 0;
    h2 = Math.imul(h2 ^ (h2 >>> 13), 3266489909) >>> 0;
    out.push(((h1 ^ h2) & 0b1) === 0);
  }
  return out;
}

export function QRCode({ data, size = 192, className }: Props) {
  const bits = patternBits(data);
  const cells = 25;
  const cellSize = size / cells;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Scan to open ${data}`}
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width={size} height={size} fill="white" />
      {bits.map((on, i) => {
        const x = i % cells;
        const y = Math.floor(i / cells);
        // Position-detection patterns in three corners (decorative).
        const finder =
          (x < 7 && y < 7) ||
          (x >= cells - 7 && y < 7) ||
          (x < 7 && y >= cells - 7);
        if (!on && !finder) return null;
        return (
          <rect
            key={i}
            x={x * cellSize}
            y={y * cellSize}
            width={cellSize}
            height={cellSize}
            fill="black"
          />
        );
      })}
    </svg>
  );
}