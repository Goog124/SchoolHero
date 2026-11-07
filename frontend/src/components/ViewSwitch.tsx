import { InfoButton } from './InfoButton';
import { ViewSwitchInfo } from './infoTexts';
import type { Viewer } from '../types';

type ViewSwitchProps = {
  viewer: Viewer;
  onChange: (view: 'director' | 'teacher') => void;
  busy?: boolean;
};

const OPTIONS: { id: 'director' | 'teacher'; label: string }[] = [
  { id: 'director', label: 'Директор' },
  { id: 'teacher', label: 'Педагог' },
];

/**
 * Переключатель режима директора, который ведёт класс. Точка на неактивной
 * стороне: там что-то ждёт (работы на проверке, заявки). Не путать с демо-ролями.
 */
export function ViewSwitch({ viewer, onChange, busy = false }: ViewSwitchProps) {
  const current = viewer.active_view === 'teacher' ? 'teacher' : 'director';
  const waiting = viewer.other_view_pending > 0;

  return (
    <div className="view-switch">
      <div className="view-switch__row" role="group" aria-label="Режим: директор или педагог">
        {OPTIONS.map((option) => {
          const active = option.id === current;
          const dot = !active && waiting;
          return (
            <button
              key={option.id}
              type="button"
              className={`view-switch__item ${active ? 'is-active' : ''}`.trim()}
              aria-pressed={active}
              disabled={busy}
              onClick={() => {
                if (!active) onChange(option.id);
              }}
            >
              <span>{option.label}</span>
              {dot ? (
                <span
                  className="view-switch__dot"
                  role="img"
                  aria-label={`Ожидает: ${viewer.other_view_pending}`}
                />
              ) : null}
            </button>
          );
        })}
      </div>
      <InfoButton title="Режим директора и педагога">
        <ViewSwitchInfo />
      </InfoButton>
    </div>
  );
}
