import type { SandboxUser } from '../sandbox';
import { Icon } from './Icon';

type SandboxBarProps = {
  users: SandboxUser[];
  active: string;
  onSwitch: (clientId: string) => void;
  onNew: () => void;
};

export function SandboxBar({ users, active, onSwitch, onNew }: SandboxBarProps) {
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
              {user.detail ? `${user.label} — ${user.detail}` : user.label}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="sb-bar__new" onClick={onNew}>
        <Icon name="plus" size={16} />
        Новый пользователь
      </button>
    </div>
  );
}
