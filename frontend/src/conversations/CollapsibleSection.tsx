import { type JSX } from "solid-js";

export interface CollapsibleSectionProps {
  label: string;
  /** Optional leading icon rendered before the label */
  leadingIcon?: JSX.Element;
  children: JSX.Element;
  expanded?: boolean;
  onToggle?: (expanded: boolean) => void;
}

export function CollapsibleSection(props: CollapsibleSectionProps) {
  const expanded = () => props.expanded ?? true;

  const toggle = () => {
    props.onToggle?.(!expanded());
  };

  return (
    <div>
      <button
        onClick={toggle}
        class="flex items-center gap-1.5 text-xs font-medium text-(--text-secondary) hover:text-(--accent) transition-colors cursor-pointer w-full text-left"
      >
        {props.leadingIcon}
        <span class="flex items-center gap-1">
          {props.label}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class={`h-3 w-3 mt-[2.6px] transition-transform duration-200 ${expanded() ? "rotate-90" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fill-rule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clip-rule="evenodd"
            />
          </svg>
        </span>
      </button>
      <div
        class="overflow-hidden transition-all duration-300 ease-in-out"
        classList={{
          "max-h-0 opacity-0": !expanded(),
          "max-h-80 opacity-100": expanded(),
        }}
      >
        <div class="mt-1">
          {props.children}
        </div>
      </div>
    </div>
  );
}
