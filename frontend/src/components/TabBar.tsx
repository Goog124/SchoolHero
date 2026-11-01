import type { CSSProperties } from 'react';
import { Icon, type IconName } from './Icon';
import type { TabId } from '../types';

export type TabItem = {
  id: TabId;
  label: string;
  icon: IconName;
  badge?: number;
};

type TabBarProps = {
  tabs: TabItem[];
  active: TabId;
  onChange: (tab: TabId) => void;
};

export function TabBar({ tabs, active, onChange }: TabBarProps) {
  return (
    <nav
      className="tabbar"
      style={{ '--tab-count': tabs.length } as CSSProperties}
      aria-label="Основная навигация"
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            className={`tab ${selected ? 'tab--active' : ''}`.trim()}
            aria-current={selected ? 'page' : undefined}
            onClick={() => onChange(tab.id)}
          >
            <span className="tab__icon">
              <Icon name={tab.icon} size={21} filled={selected && tab.icon === 'flame'} />
              {tab.badge ? (
                <span className="tab__badge">{tab.badge > 9 ? '9+' : tab.badge}</span>
              ) : null}
            </span>
            <span className="tab__label">{tab.label}</span>
            <span className="tab__pip" aria-hidden="true" />
          </button>
        );
      })}
    </nav>
  );
}
