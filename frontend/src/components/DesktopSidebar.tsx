import { AvatarFrame } from './AvatarFrame';
import { BrandLogo } from './BrandLogo';
import { Icon } from './Icon';
import { formatNumber } from '../game';
import type { TabItem } from './TabBar';
import type { TabId, Viewer } from '../types';

type Role = 'student' | 'teacher' | 'director';

type DesktopSidebarProps = {
  tabs: TabItem[];
  active: TabId;
  onChange: (tab: TabId) => void;
  viewer: Viewer;
  theme: 'light' | 'dark';
  onThemeToggle: () => void;
  onProfile: () => void;
  /** Переключатель ролей: передаётся только в демо-режиме. */
  onRoleSwitch?: (role: Role) => void;
};

const ROLES: { id: Role; label: string }[] = [
  { id: 'student', label: 'Ученик' },
  { id: 'teacher', label: 'Педагог' },
  { id: 'director', label: 'Директор' },
];

export function DesktopSidebar({
  tabs,
  active,
  onChange,
  viewer,
  theme,
  onThemeToggle,
  onProfile,
  onRoleSwitch,
}: DesktopSidebarProps) {
  const isStudent = viewer.role === 'student';
  const roleLabel =
    viewer.role === 'director'
      ? 'Администрация'
      : viewer.role === 'teacher'
      ? 'Педагог'
      : viewer.class_name;

  return (
    <aside className="sidebar" aria-label="Боковая панель">
      <div>
        <BrandLogo size="md" subtitle={roleLabel || undefined} />
        {viewer.school_name ? (
          <div className="sidebar__school">
            <span title={viewer.school_name}>{viewer.school_name}</span>
          </div>
        ) : null}

        <nav className="sidebar__nav" aria-label="Разделы">
          {tabs.map((tab) => {
            const selected = tab.id === active;
            return (
              <button
                key={tab.id}
                type="button"
                className={`sidebar__item ${selected ? 'is-active' : ''}`.trim()}
                aria-current={selected ? 'page' : undefined}
                onClick={() => onChange(tab.id)}
              >
                <span className="sidebar__item-main">
                  <Icon name={tab.icon} size={18} />
                  <span>{tab.label}</span>
                </span>
                {tab.badge ? (
                  <span className="sidebar__badge" aria-label={`Новых: ${tab.badge}`}>
                    {tab.badge > 9 ? '9+' : tab.badge}
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="sidebar__foot">
        <button type="button" className="sidebar__user" onClick={onProfile} aria-label="Открыть профиль">
          {isStudent ? <AvatarFrame avatar={viewer.avatar} size={40} decorative /> : null}
          <span className="sidebar__user-text">
            <span className="sidebar__user-name">{viewer.name}</span>
            <span className="sidebar__user-sub">
              {isStudent ? `Ранг ${viewer.level.level} · ${viewer.level.title}` : roleLabel}
            </span>
          </span>
          <Icon name="chevronRight" size={16} />
        </button>

        <div className="sidebar__row">
          {isStudent ? (
            <span className="topbar__sparks" aria-label={`Баллы: ${viewer.sparks}`}>
              <Icon name="spark" size={14} filled />
              {formatNumber(viewer.sparks)}
            </span>
          ) : (
            <span />
          )}
          <button
            type="button"
            className="sidebar__theme"
            onClick={onThemeToggle}
            aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
          >
            {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
          </button>
        </div>

        {onRoleSwitch ? (
          <div className="role-switch" role="group" aria-label="Роль в демо">
            <span className="role-switch__label">Демо: роль</span>
            {ROLES.map((role) => (
              <button
                key={role.id}
                type="button"
                aria-pressed={viewer.role === role.id}
                onClick={() => onRoleSwitch(role.id)}
              >
                {role.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </aside>
  );
}
