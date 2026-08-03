import type { ReactNode, SVGProps } from "react";

type IconName =
  | "arrow"
  | "check"
  | "chevron"
  | "clock"
  | "document"
  | "download"
  | "edit"
  | "external"
  | "file"
  | "hospital"
  | "info"
  | "location"
  | "refresh"
  | "search"
  | "shield"
  | "sparkle"
  | "upload"
  | "warning"
  | "x";

const paths: Record<IconName, ReactNode> = {
  arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
  check: <path d="m5 12 4 4L19 6" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  document: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></>,
  download: <><path d="M12 3v12m-4-4 4 4 4-4" /><path d="M5 19h14" /></>,
  edit: <><path d="m4 20 4.2-1 10.5-10.5a2 2 0 0 0-2.8-2.8L5.4 16.2Z" /><path d="m14.5 7.1 2.8 2.8" /></>,
  external: <><path d="M14 5h5v5M19 5l-8 8" /><path d="M18 13v6H5V6h6" /></>,
  file: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v5h5" /></>,
  hospital: <><path d="M4 21V8h16v13M8 8V3h8v5M9 13h6M12 10v6M8 21v-3h8v3" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 8h.01" /></>,
  location: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M18.2 9A7 7 0 0 0 6.1 6.1L4 9m16 6-2.1 2.9A7 7 0 0 1 5.8 15" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  shield: <><path d="M12 3 4.5 6v5c0 4.8 3 8.2 7.5 10 4.5-1.8 7.5-5.2 7.5-10V6Z" /><path d="m9 12 2 2 4-4" /></>,
  sparkle: <><path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5Z" /><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7Z" /></>,
  upload: <><path d="M12 16V4m-5 5 5-5 5 5" /><path d="M5 15v5h14v-5" /></>,
  warning: <><path d="m12 3 10 18H2Z" /><path d="M12 9v5M12 17h.01" /></>,
  x: <path d="m6 6 12 12M18 6 6 18" />,
};

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 20, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
