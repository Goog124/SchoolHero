import { useEffect, useId, useRef, useState } from 'react';
import { api } from '../api';
import type { CitySuggestion } from '../types';

export type CityStatus = {
  status: 'loading' | 'ready' | 'error';
  /** Сколько городов подходит под запрос (для пустого запроса: всего в каталоге). */
  total: number;
  /** Запрос, на который получен ответ. */
  query: string;
  names: string[];
};

type CityInputProps = {
  id: string;
  value: string;
  onChange: (text: string) => void;
  /** Выбор подсказки; без него подсказка просто подставляется в поле. */
  onPick?: (name: string) => void;
  onStatus?: (status: CityStatus) => void;
  /** Меняется, чтобы заново запросить подсказки (возврат на вкладку, фокус окна). */
  refreshKey?: number;
  placeholder?: string;
  invalid?: boolean;
  describedBy?: string;
  maxLength?: number;
  /** 'all': справочник городов России (форма директора); иначе города с активными школами. */
  scope?: '' | 'all';
};

/** Поле города с подсказками с сервера: role=combobox, стрелки, Enter, Escape. */
export function CityInput({
  id,
  value,
  onChange,
  onPick,
  onStatus,
  refreshKey = 0,
  placeholder,
  invalid,
  describedBy,
  maxLength = 60,
  scope = '',
}: CityInputProps) {
  const listId = useId();
  const [items, setItems] = useState<CitySuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const statusRef = useRef(onStatus);
  statusRef.current = onStatus;

  useEffect(() => {
    let alive = true;
    const query = value.trim();
    statusRef.current?.({ status: 'loading', total: -1, query, names: [] });
    const timer = window.setTimeout(() => {
      api
        .searchCities(query, 10, scope)
        .then((res) => {
          if (!alive) return;
          setItems(res.cities);
          setHighlight(-1);
          statusRef.current?.({
            status: 'ready',
            total: res.total,
            query,
            names: res.cities.map((c) => c.name),
          });
        })
        .catch(() => {
          if (!alive) return;
          setItems([]);
          statusRef.current?.({ status: 'error', total: -1, query, names: [] });
        });
    }, 200);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [value, refreshKey, scope]);

  const pick = (name: string) => {
    setOpen(false);
    setHighlight(-1);
    if (onPick) onPick(name);
    else onChange(name);
  };

  const expanded = open && items.length > 0;

  return (
    <div className="su-combo">
      <input
        id={id}
        className="ob-input"
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={expanded && highlight >= 0 ? `${listId}-${highlight}` : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setOpen(true);
            setHighlight((h) => (items.length === 0 ? -1 : (h + 1) % items.length));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setOpen(true);
            setHighlight((h) => (items.length === 0 ? -1 : (h <= 0 ? items.length - 1 : h - 1)));
          } else if (e.key === 'Enter' && expanded && highlight >= 0) {
            e.preventDefault();
            pick(items[highlight].name);
          } else if (e.key === 'Escape' && expanded) {
            e.preventDefault();
            setOpen(false);
          }
        }}
      />
      <ul
        id={listId}
        className="su-combo__list"
        role="listbox"
        aria-label="Подсказки городов"
        hidden={!expanded}
      >
        {items.map((item, index) => (
          <li
            key={item.name}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === highlight}
            className="su-combo__option"
            onMouseDown={(e) => {
              e.preventDefault();
              pick(item.name);
            }}
          >
            {item.name}
          </li>
        ))}
      </ul>
    </div>
  );
}
