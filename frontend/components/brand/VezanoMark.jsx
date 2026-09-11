export default function VezanoMark({ size = 24, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      fill="none"
      className={className}
    >
      <path
        d="M5.5 7.5 16 24.5 26.5 7.5"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="m11.5 7.5 4.5 7.25 4.5-7.25"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity=".48"
      />
    </svg>
  );
}
