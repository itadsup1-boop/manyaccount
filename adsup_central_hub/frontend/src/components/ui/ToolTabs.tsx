import type { ComponentType } from 'react';

export type ToolTab<T extends string> = {
  id: T;
  label: string;
  icon: ComponentType<{ size?: number; 'aria-hidden'?: boolean | 'true' | 'false' }>;
};

type Props<T extends string> = {
  activeTab: T;
  ariaLabel: string;
  tabs: readonly ToolTab<T>[];
  onChange: (tab: T) => void;
};

export default function ToolTabs<T extends string>({ activeTab, ariaLabel, tabs, onChange }: Props<T>) {
  return (
    <nav className="tool-tabs" aria-label={ariaLabel}>
      {tabs.map(({ id, label, icon: Icon }) => (
        <button
          className={`tool-tab ${activeTab === id ? 'is-active' : ''}`}
          type="button"
          key={id}
          onClick={() => onChange(id)}
          aria-label={label}
          aria-current={activeTab === id ? 'page' : undefined}
        >
          <Icon size={17} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
