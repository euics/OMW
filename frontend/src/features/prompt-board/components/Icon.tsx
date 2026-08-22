import type { ReactNode } from 'react'

export type IconName =
  | 'archive'
  | 'arrowUpRight'
  | 'check'
  | 'chevronDown'
  | 'chevronRight'
  | 'close'
  | 'command'
  | 'copy'
  | 'edit'
  | 'info'
  | 'loader'
  | 'more'
  | 'plug'
  | 'plus'
  | 'prompt'
  | 'search'
  | 'send'
  | 'trash'

const iconPaths: Record<IconName, ReactNode> = {
  archive: (
    <>
      <path d="M4 7h16v13H4zM3 4h18v3H3z" />
      <path d="M9 11h6" />
    </>
  ),
  arrowUpRight: <path d="M7 17 17 7M8 7h9v9" />,
  check: <path d="m5 12 4 4L19 6" />,
  chevronDown: <path d="m7 9 5 5 5-5" />,
  chevronRight: <path d="m9 18 6-6-6-6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  command: (
    <>
      <path d="M9 6V5a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v14a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6Z" />
    </>
  ),
  copy: (
    <>
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </>
  ),
  edit: (
    <>
      <path d="M12 20h9" />
      <path d="m16.5 3.5 4 4L8 20H4v-4Z" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </>
  ),
  loader: <path d="M21 12a9 9 0 1 1-5.3-8.2" />,
  more: <path d="M5 12h.01M12 12h.01M19 12h.01" />,
  plug: (
    <>
      <path d="m7 12 5 5M17 2l-1.5 1.5M22 7l-1.5 1.5M15 5l4 4-6 6-4-4Z" />
      <path d="m8 16-4 4" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  prompt: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="m7 9 3 3-3 3M13 15h4" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4-4" />
    </>
  ),
  send: <path d="m22 2-7 20-4-9-9-4ZM22 2 11 13" />,
  trash: (
    <>
      <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5" />
    </>
  ),
}

export function Icon({
  name,
  size = 18,
}: {
  name: IconName
  size?: number
}) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {iconPaths[name]}
    </svg>
  )
}
