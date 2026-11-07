import type { SandboxUser } from '../sandbox';
import { Icon } from './Icon';

type SandboxBarProps = {
  users: SandboxUser[];
  active: string;
  notice?: string | null;
  onDismissNotice?: () => void;
  onSwitch: (clientId: string) => void;
  onNew: () => void;
  isAdmin: boolean;
  adminBusy?: boolean;
  onToggleAdmin: (enabled: boolean) => void;
};

export function SandboxBar({
  users,
  active,
  notice,
  onDismissNotice,
  onSwitch,
  onNew,
  isAdmin,
  adminBusy,
  onToggleAdmin,
}: SandboxBarProps) {
  return (
    <div className="sb-bar" role="group" aria-label="Песочница">
      <span className="sb-bar__badge">Песочница</span>
      <label className="sb-bar__field">
        <span className="sb-bar__sr">Тестовый пользователь</span>
        <select
          className="sb-bar__select"
          value={active}
          onChange={(e) => onSwitch(e.target.value)}
        >
          {users.map((user) => (
            <option key={user.clientId} value={user.clientId}>
              {`${user.label}${user.detail ?? ''}`}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="sb-bar__new" onClick={onNew}>
        <Icon name="plus" size={16} />
        Новый пользователь
      </button>
      <label className="sb-bar__admin">
        <input
          type="checkbox"
          checked={isAdmin}
          disabled={adminBusy}
          onChange={(e) => onToggleAdmin(e.target.checked)}
        />
        <span>Администратор платформы</span>
      </label>
      {notice ? (
        <div className="sb-bar__notice" role="status">
          <span>{notice}</span>
          {onDismissNotice ? (
            <button type="button" className="sb-bar__dismiss" onClick={onDismissNotice}>
              Понятно
            </button>
          ) : null}
        </div>
      ) : null}
      <p className="sb-bar__hint">
        База сохраняется между запусками. Чтобы стереть её, запустите npm run sandbox-wipe.
      </p>
    </div>
  );
}
