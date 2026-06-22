import React, { memo } from "react";

interface Props {
  messageId: string;
  fading?: boolean;
}

/**
 * Premium inline mobile construction crane at the live text-generation edge.
 * Pure SVG + CSS transforms. One stable instance per assistant message.
 */
function ConstructionCraneTextBuilder({ messageId, fading = false }: Props) {
  return (
    <span
      className={`construction-crane-wrap${fading ? " construction-crane-wrap--fading" : ""}`}
      aria-hidden="true"
      data-message-id={messageId}
    >
      <svg
        className="construction-crane-svg"
        width="34"
        height="20"
        viewBox="0 0 96 54"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        focusable="false"
      >
        <defs>
          <linearGradient id="cc-body" x1="14" y1="18" x2="82" y2="42" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFF0A6" />
            <stop offset="45%" stopColor="#FFD54A" />
            <stop offset="100%" stopColor="#E6AD22" />
          </linearGradient>
          <linearGradient id="cc-boom" x1="56" y1="30" x2="90" y2="10" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#FFD54A" />
            <stop offset="100%" stopColor="#FFB15C" />
          </linearGradient>
          <linearGradient id="cc-highlight" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#FFF0A6" stopOpacity="0" />
            <stop offset="50%" stopColor="#FFF0A6" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#FFF0A6" stopOpacity="0" />
          </linearGradient>
        </defs>

        <ellipse cx="48" cy="50" rx="34" ry="2.2" fill="#000" opacity="0.18" />

        <g className="construction-crane-rig">
          <g className="construction-crane-body">
            <path
              d="M12 38h62a2.5 2.5 0 0 0 2.5-2.5V34H10v1.5A2.5 2.5 0 0 0 12 38z"
              fill="#263238"
            />
            <path
              d="M14 24h58a3 3 0 0 1 3 3v9H11v-9a3 3 0 0 1 3-3z"
              fill="url(#cc-body)"
            />
            <path d="M14 27h58" stroke="#FFF0A6" strokeOpacity="0.45" strokeWidth="0.6" />
            <rect x="16" y="26" width="14" height="11" rx="1.2" fill="#263238" />
            <rect x="18" y="28" width="5.5" height="4.5" rx="0.6" fill="#8ED8E8" opacity="0.55" />
            <rect x="24.5" y="28" width="3.5" height="4.5" rx="0.5" fill="#8ED8E8" opacity="0.35" />
            <rect x="16" y="26" width="14" height="11" rx="1.2" stroke="#CFD8DC" strokeOpacity="0.35" />
            <g className="construction-crane-highlight">
              <rect x="12" y="22" width="14" height="16" fill="url(#cc-highlight)" opacity="0.4" />
            </g>
          </g>

          <g className="construction-crane-rear-wheel">
            <circle cx="24" cy="46" r="6.2" fill="#111827" />
            <circle cx="24" cy="46" r="4.1" fill="#1f2937" />
            <line x1="20.5" y1="46" x2="27.5" y2="46" stroke="#CFD8DC" strokeWidth="0.65" opacity="0.6" />
            <line x1="24" y1="42.2" x2="24" y2="49.8" stroke="#CFD8DC" strokeWidth="0.65" opacity="0.6" />
            <circle cx="24" cy="46" r="1.35" fill="#FFD54A" />
          </g>

          <g className="construction-crane-front-wheel">
            <circle cx="68" cy="46" r="6.2" fill="#111827" />
            <circle cx="68" cy="46" r="4.1" fill="#1f2937" />
            <line x1="64.5" y1="46" x2="71.5" y2="46" stroke="#CFD8DC" strokeWidth="0.65" opacity="0.6" />
            <line x1="68" y1="42.2" x2="68" y2="49.8" stroke="#CFD8DC" strokeWidth="0.65" opacity="0.6" />
            <circle cx="68" cy="46" r="1.35" fill="#FFD54A" />
          </g>

          <g className="construction-crane-piston" transform="translate(44 36)">
            <g className="construction-crane-piston-rod">
              <rect x="0" y="-2.4" width="6.5" height="4.8" rx="1.1" fill="#263238" stroke="#CFD8DC" strokeWidth="0.45" />
              <rect x="5.5" y="-1" width="16" height="2" rx="0.55" fill="#CFD8DC" opacity="0.9" />
            </g>
          </g>

          <g className="construction-crane-boom-mount" transform="translate(58 30)">
            <g className="construction-crane-boom">
              <path
                d="M0 0 L30 -16"
                stroke="url(#cc-boom)"
                strokeWidth="3.2"
                strokeLinecap="round"
              />
              <path
                d="M0 0 L30 -16"
                stroke="#FFF0A6"
                strokeWidth="0.55"
                strokeLinecap="round"
                opacity="0.5"
              />
              <circle cx="0" cy="0" r="1.8" fill="#263238" stroke="#FFD54A" strokeWidth="0.65" />
            </g>
            <g className="construction-crane-hook" transform="translate(30 -16)">
              <g className="construction-crane-hook-sway">
                <line x1="0" y1="0" x2="0" y2="6.5" stroke="#CFD8DC" strokeWidth="0.55" />
                <path
                  d="M0 6.5c0 0 2.4 0.9 2.4 2.6S0 11.7 0 11.7"
                  stroke="#E6AD22"
                  strokeWidth="0.8"
                  fill="none"
                  strokeLinecap="round"
                />
              </g>
            </g>
          </g>
        </g>
      </svg>
    </span>
  );
}

export default memo(ConstructionCraneTextBuilder);
