/** Karen mosaic tile — varied chat icons that sit ON the teal digit. */
export const BUBBLE_PATTERN_W = 48;
export const BUBBLE_PATTERN_H = 48;

/**
 * Soft “on surface” shadow: dark oval under a bubble (no filter — pattern-safe).
 * @param {{ cx: number, cy: number, rx: number, ry: number }} props
 */
function SoftPad({ cx, cy, rx, ry }) {
  return (
    <>
      <ellipse cx={cx + 0.15} cy={cy + 0.75} rx={rx * 1.05} ry={ry * 1.08} fill="#022821" opacity="0.45" />
      <ellipse cx={cx} cy={cy + 0.35} rx={rx} ry={ry} fill="#03352F" opacity="0.28" />
    </>
  );
}

/**
 * Typing (…) bubble — rounded rect + tail.
 * @param {{ x: number, y: number, w?: number, h?: number, fill?: string }} props
 */
function TypingBubble({ x, y, w = 11, h = 7.2, fill = '#FFFFFF' }) {
  const r = 1.7;
  const midY = y + h * 0.42;
  return (
    <g>
      <SoftPad cx={x + w / 2} cy={y + h / 2} rx={w / 2.1} ry={h / 2.2} />
      <path
        d={`M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r - 1.2}a${r} ${r} 0 0 1 ${-r} ${r}H${x + w * 0.42}L${x + w * 0.22} ${y + h}V${y + h - 1.2}H${x + r}a${r} ${r} 0 0 1 ${-r} ${-r}V${y + r}a${r} ${r} 0 0 1 ${r} ${-r}z`}
        fill={fill}
      />
      <circle cx={x + w * 0.28} cy={midY} r={0.85} fill="#0A5348" />
      <circle cx={x + w * 0.5} cy={midY} r={0.85} fill="#0A5348" />
      <circle cx={x + w * 0.72} cy={midY} r={0.85} fill="#0A5348" />
    </g>
  );
}

/**
 * Text-lines bubble.
 * @param {{ x: number, y: number, w?: number, h?: number, fill?: string }} props
 */
function TextBubble({ x, y, w = 12, h = 7.5, fill = '#C9F8E8' }) {
  const r = 1.65;
  return (
    <g>
      <SoftPad cx={x + w / 2} cy={y + h / 2} rx={w / 2.1} ry={h / 2.2} />
      <path
        d={`M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r - 1.1}a${r} ${r} 0 0 1 ${-r} ${r}H${x + w * 0.55}L${x + w * 0.35} ${y + h}V${y + h - 1.1}H${x + r}a${r} ${r} 0 0 1 ${-r} ${-r}V${y + r}a${r} ${r} 0 0 1 ${r} ${-r}z`}
        fill={fill}
      />
      <rect x={x + 2.2} y={y + 2.1} width={w * 0.55} height={0.9} rx={0.4} fill="#0A5348" opacity="0.42" />
      <rect x={x + 2.2} y={y + 3.7} width={w * 0.4} height={0.9} rx={0.4} fill="#0A5348" opacity="0.42" />
    </g>
  );
}

/**
 * Round / oval chat bubble.
 * @param {{ cx: number, cy: number, rx?: number, ry?: number, fill?: string }} props
 */
function RoundBubble({ cx, cy, rx = 3.6, ry = 2.9, fill = '#F4FFFB' }) {
  return (
    <g>
      <SoftPad cx={cx} cy={cy} rx={rx} ry={ry} />
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill={fill} />
      <path d={`M${cx - 1.2} ${cy + ry * 0.55}l${rx * 0.35} ${ry * 0.85} ${rx * 0.45} ${-ry * 0.9}`} fill={fill} />
    </g>
  );
}

/** Dense tile: typing / text / round / dots — organic sizes. */
export function BubblePatternContent() {
  return (
    <>
      <rect width="48" height="48" fill="#0A5348" />

      <TypingBubble x={1.5} y={1.2} w={12.5} h={8} fill="#FFFFFF" />
      <TextBubble x={16.5} y={2.2} w={11.5} h={7.2} fill="#B8F5E4" />
      <RoundBubble cx={38.2} cy={6.2} rx={4.2} ry={3.3} fill="#FFFFFF" />
      <circle cx={30.5} cy={2.4} r={1.15} fill="#E8FFF8" />

      <TextBubble x={2} y={13.5} w={10.5} h={7} fill="#E8FFF8" />
      <TypingBubble x={15.2} y={14.8} w={10.8} h={7.2} fill="#9BE6D0" />
      <RoundBubble cx={35.8} cy={17.5} rx={3.4} ry={2.7} fill="#C9F8E8" />
      <circle cx={44.2} cy={14.2} r={0.95} fill="#FFFFFF" opacity="0.95" />
      <circle cx={12.8} cy={12.2} r={0.8} fill="#9BE6D0" />

      <RoundBubble cx={7.2} cy={28.2} rx={3.8} ry={3} fill="#FFFFFF" />
      <TypingBubble x={14.5} y={25.2} w={13} h={8.2} fill="#F4FFFB" />
      <TextBubble x={30.2} y={26.5} w={12} h={7.4} fill="#B8F5E4" />
      <circle cx={44.8} cy={25.5} r={1.05} fill="#C9F8E8" />

      <TextBubble x={1.8} y={36.2} w={11} h={7} fill="#9BE6D0" />
      <TypingBubble x={16} y={37} w={11.2} h={7.4} fill="#FFFFFF" />
      <RoundBubble cx={36.5} cy={40.5} rx={3.2} ry={2.6} fill="#E8FFF8" />
      <circle cx={44} cy={37.8} r={0.9} fill="#FFFFFF" />
      <circle cx={28.8} cy={35.6} r={0.75} fill="#B8F5E4" />
      <circle cx={42.5} cy={45.2} r={0.7} fill="#9BE6D0" />
      {/* Extra micro chips — fills gaps between larger bubbles */}
      <circle cx={23.5} cy={11.5} r={1.1} fill="#FFFFFF" opacity="0.92" />
      <circle cx={41.2} cy={21.8} r={0.85} fill="#E8FFF8" />
      <ellipse cx={11.2} cy={34.2} rx={1.6} ry={1.25} fill="#C9F8E8" />
      <circle cx={27.2} cy={45.5} r={0.95} fill="#FFFFFF" />
    </>
  );
}
