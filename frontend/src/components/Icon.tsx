import type { SVGProps } from 'react';

export type IconName =
  | 'home'
  | 'shield'
  | 'list'
  | 'trophy'
  | 'shirt'
  | 'user'
  | 'book'
  | 'compass'
  | 'heart'
  | 'star'
  | 'flag'
  | 'flame'
  | 'sparkles'
  | 'bolt'
  | 'clock'
  | 'check'
  | 'x'
  | 'chevronRight'
  | 'chevronLeft'
  | 'chevronDown'
  | 'arrowLeft'
  | 'arrowUp'
  | 'arrowDown'
  | 'plus'
  | 'share'
  | 'settings'
  | 'info'
  | 'alert'
  | 'lock'
  | 'users'
  | 'crown'
  | 'chart'
  | 'calendar'
  | 'target'
  | 'medal'
  | 'send'
  | 'edit'
  | 'refresh'
  | 'mapPin'
  | 'gift'
  | 'eye'
  | 'spark'
  | 'sword'
  | 'play'
  | 'archive'
  | 'search'
  | 'max';

type IconProps = SVGProps<SVGSVGElement> & {
  name: IconName;
  size?: number;
  filled?: boolean;
};

export function Icon({ name, size = 20, filled = false, ...props }: IconProps) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: filled ? 'currentColor' : 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
    ...props,
  };

  switch (name) {
    case 'home':
      return (
        <svg {...common}>
          <path d="M3.5 10.8 12 3.5l8.5 7.3" />
          <path d="M5.5 9.4V20a.8.8 0 0 0 .8.8h11.4a.8.8 0 0 0 .8-.8V9.4" />
          <path d="M9.5 20.8v-6.2h5v6.2" />
        </svg>
      );
    case 'shield':
      return (
        <svg {...common}>
          <path d="M12 3.2 19.5 6v5.2c0 4.6-3.1 7.9-7.5 9.6-4.4-1.7-7.5-5-7.5-9.6V6L12 3.2Z" />
          <path d="m9 11.7 2 2 4-4.2" />
        </svg>
      );
    case 'list':
      return (
        <svg {...common}>
          <path d="M9 6h11M9 12h11M9 18h11" />
          <path d="m3.6 5.8.9.9 1.8-1.8M3.6 11.8l.9.9 1.8-1.8M3.6 17.8l.9.9 1.8-1.8" />
        </svg>
      );
    case 'trophy':
      return (
        <svg {...common}>
          <path d="M8 4h8v4.6a4 4 0 0 1-8 0V4Z" />
          <path d="M8 5H4.8v1.7A3.3 3.3 0 0 0 8 10M16 5h3.2v1.7A3.3 3.3 0 0 1 16 10" />
          <path d="M12 12.6V17M8.4 21h7.2M9.7 17h4.6" />
        </svg>
      );
    case 'shirt':
      return (
        <svg {...common}>
          <path d="m8 4-4.4 2.4 2 4.2 2-1v10.2h8.8V9.6l2 1 2-4.2L16 4a4 4 0 0 1-8 0Z" />
        </svg>
      );
    case 'user':
      return (
        <svg {...common}>
          <circle cx="12" cy="8" r="3.6" />
          <path d="M4.8 20.5c.6-3.5 3.5-5.7 7.2-5.7s6.6 2.2 7.2 5.7" />
        </svg>
      );
    case 'book':
      return (
        <svg {...common}>
          <path d="M4 5.3c2.7-.8 5.3-.4 8 1.4v13.1c-2.7-1.8-5.3-2.2-8-1.4V5.3Z" />
          <path d="M20 5.3c-2.7-.8-5.3-.4-8 1.4v13.1c2.7-1.8 5.3-2.2 8-1.4V5.3Z" />
        </svg>
      );
    case 'compass':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.7" />
          <path d="m15.6 8.4-2.2 5-5 2.2 2.2-5 5-2.2Z" />
        </svg>
      );
    case 'heart':
      return (
        <svg {...common}>
          <path d="M20.3 5.8a5.2 5.2 0 0 0-7.4 0L12 6.7l-.9-.9a5.2 5.2 0 0 0-7.4 7.4L12 21l8.3-7.8a5.2 5.2 0 0 0 0-7.4Z" />
        </svg>
      );
    case 'star':
      return (
        <svg {...common}>
          <path d="m12 3.2 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3.2Z" />
        </svg>
      );
    case 'flag':
      return (
        <svg {...common}>
          <path d="M5.5 21V4.2" />
          <path d="M5.8 4.7c4.1-2.2 8.2 2.2 12.7 0v9.1c-4.5 2.2-8.6-2.2-12.7 0V4.7Z" />
        </svg>
      );
    case 'flame':
      return (
        <svg {...common}>
          <path d="M13.2 2.7c.6 3-1.2 4.3-2.8 5.9-1.7 1.8-3.2 3.6-3.2 6.3a4.8 4.8 0 0 0 9.6 0c0-1.8-.7-3.1-1.5-4.2-.3 1.2-1 2.1-2 2.7.6-3.4-.6-6.2-2.1-8.2-.2 2-1 3.5-2.2 4.8" />
        </svg>
      );
    case 'sparkles':
      return (
        <svg {...common}>
          <path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3Z" />
          <path d="m18.5 14 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z" />
          <path d="m5 14 .8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8L5 14Z" />
        </svg>
      );
    case 'spark':
      return (
        <svg {...common}>
          <path d="m12 3 2 6 7 3-7 3-2 6-2-6-7-3 7-3 2-6Z" />
        </svg>
      );
    case 'bolt':
      return (
        <svg {...common}>
          <path d="m13.5 2.5-8 11h5.8l-.8 8 8-11h-5.8l.8-8Z" />
        </svg>
      );
    case 'clock':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.8" />
          <path d="M12 7.2V12l3.2 2" />
        </svg>
      );
    case 'check':
      return (
        <svg {...common}>
          <path d="m4.5 12.5 5 5 10-11" />
        </svg>
      );
    case 'x':
      return (
        <svg {...common}>
          <path d="M5 5l14 14M19 5 5 19" />
        </svg>
      );
    case 'chevronRight':
      return (
        <svg {...common}>
          <path d="m9 5 7 7-7 7" />
        </svg>
      );
    case 'chevronLeft':
      return (
        <svg {...common}>
          <path d="m15 5-7 7 7 7" />
        </svg>
      );
    case 'chevronDown':
      return (
        <svg {...common}>
          <path d="m5 9 7 7 7-7" />
        </svg>
      );
    case 'arrowLeft':
      return (
        <svg {...common}>
          <path d="M20 12H4M10 6l-6 6 6 6" />
        </svg>
      );
    case 'arrowUp':
      return (
        <svg {...common}>
          <path d="M12 20V4M6 10l6-6 6 6" />
        </svg>
      );
    case 'arrowDown':
      return (
        <svg {...common}>
          <path d="M12 4v16M6 14l6 6 6-6" />
        </svg>
      );
    case 'plus':
      return (
        <svg {...common}>
          <path d="M12 4v16M4 12h16" />
        </svg>
      );
    case 'share':
      return (
        <svg {...common}>
          <circle cx="18" cy="5" r="2.8" />
          <circle cx="6" cy="12" r="2.8" />
          <circle cx="18" cy="19" r="2.8" />
          <path d="m8.5 10.7 7-4.2M8.5 13.3l7 4.2" />
        </svg>
      );
    case 'settings':
      return (
        <svg {...common}>
          <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
          <circle cx="15" cy="7" r="2" />
          <circle cx="9" cy="17" r="2" />
        </svg>
      );
    case 'info':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.8" />
          <path d="M12 11v5.5M12 7.6v.2" />
        </svg>
      );
    case 'alert':
      return (
        <svg {...common}>
          <path d="M12 3.5 21 20H3L12 3.5Z" />
          <path d="M12 9v4.5M12 17v.2" />
        </svg>
      );
    case 'lock':
      return (
        <svg {...common}>
          <rect x="5" y="10" width="14" height="10" rx="1.6" />
          <path d="M8.2 10V7.3a3.8 3.8 0 0 1 7.6 0V10" />
        </svg>
      );
    case 'users':
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3.2" />
          <path d="M3.5 19.5c.4-3.1 2.7-5 5.5-5s5.1 1.9 5.5 5" />
          <path d="M15.5 5.4a3.1 3.1 0 0 1 0 5.9M17 14.8c2.2.3 3.7 2 4 4.7" />
        </svg>
      );
    case 'crown':
      return (
        <svg {...common}>
          <path d="m3.5 7.5 4.2 3L12 4l4.3 6.5 4.2-3-1.6 10H5.1L3.5 7.5Z" />
          <path d="M5.4 20.5h13.2" />
        </svg>
      );
    case 'chart':
      return (
        <svg {...common}>
          <path d="M4 20V4" />
          <path d="M4 20h16" />
          <path d="M8 16.5v-4M12.5 16.5V8M17 16.5v-6.5" />
        </svg>
      );
    case 'calendar':
      return (
        <svg {...common}>
          <rect x="3.5" y="5" width="17" height="15.5" rx="1.8" />
          <path d="M7.5 3v4M16.5 3v4M3.5 10h17" />
        </svg>
      );
    case 'target':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <circle cx="12" cy="12" r="4.8" />
          <circle cx="12" cy="12" r="1.2" />
        </svg>
      );
    case 'medal':
      return (
        <svg {...common}>
          <circle cx="12" cy="14.5" r="5.3" />
          <path d="m8.3 10.1-3-6.1h4.3L12 9l2.4-5h4.3l-3 6.1M12 12.2l.9 1.7 1.9.3-1.4 1.3.3 1.9-1.7-.9-1.7.9.3-1.9-1.4-1.3 1.9-.3.9-1.7Z" />
        </svg>
      );
    case 'send':
      return (
        <svg {...common}>
          <path d="m21 3-7.1 18-3.3-7.6L3 10.1 21 3Z" />
          <path d="M10.6 13.4 21 3" />
        </svg>
      );
    case 'edit':
      return (
        <svg {...common}>
          <path d="M14.5 4.5 19.5 9.5 8.5 20.5H3.5v-5L14.5 4.5Z" />
          <path d="m12.5 6.5 5 5" />
        </svg>
      );
    case 'refresh':
      return (
        <svg {...common}>
          <path d="M20 11a8 8 0 0 0-14.7-4.4L3 9" />
          <path d="M3 4v5h5M4 13a8 8 0 0 0 14.7 4.4L21 15" />
          <path d="M21 20v-5h-5" />
        </svg>
      );
    case 'mapPin':
      return (
        <svg {...common}>
          <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z" />
          <circle cx="12" cy="10" r="2.4" />
        </svg>
      );
    case 'gift':
      return (
        <svg {...common}>
          <path d="M4 10h16v10H4V10ZM3 6.8h18V10H3V6.8ZM12 6.8V20" />
          <path d="M12 6.8H8.4a2.2 2.2 0 1 1 0-4.4C10.8 2.4 12 6.8 12 6.8ZM12 6.8h3.6a2.2 2.2 0 1 0 0-4.4C13.2 2.4 12 6.8 12 6.8Z" />
        </svg>
      );
    case 'eye':
      return (
        <svg {...common}>
          <path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12Z" />
          <circle cx="12" cy="12" r="3.1" />
        </svg>
      );
    case 'sword':
      return (
        <svg {...common}>
          <path d="M14.5 3.5 21 3l-.5 6.5-8 8-3-3 8-8Z" />
          <path d="m9.5 14.5-2 2M6 18l-2.5 2.5M13 8l3 3" />
          <path d="m4.5 16.5 3 3" />
        </svg>
      );
    case 'play':
      return (
        <svg {...common}>
          <path d="m8 5 11 7-11 7V5Z" />
        </svg>
      );
    case 'archive':
      return (
        <svg {...common}>
          <rect x="3.5" y="4" width="17" height="4.5" rx="1" />
          <path d="M5 8.5V20h14V8.5M10 12.5h4" />
        </svg>
      );
    case 'search':
      return (
        <svg {...common}>
          <circle cx="10.8" cy="10.8" r="6.6" />
          <path d="m15.6 15.6 4.9 4.9" />
        </svg>
      );
    case 'max':
      return (
        <svg {...common}>
          <path d="M4 18V7l5 6 3-4 3 4 5-6v11" />
        </svg>
      );
  }
}
