export default function (component) {
  const {data, parentElement, setTriggerValue} = component;
  const root = parentElement.querySelector('.sb-calendar');
  root.replaceChildren();
  root.setAttribute('aria-label', `ปฏิทินอุปกรณ์ ${data.title}`);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const header = el('div', 'cal-weekdays');
  header.setAttribute('role', 'row');
  data.weekdays.forEach((label, index) => {
    const cell = el('div', 'cal-weekday' + (index >= 5 ? ' is-weekend' : ''), label);
    cell.setAttribute('role', 'columnheader');
    header.appendChild(cell);
  });
  root.appendChild(header);
  for (let week = 0; week < 6; week++) {
    const row = el('div', 'cal-week');
    row.setAttribute('role', 'row');
    data.days.slice(week * 7, week * 7 + 7).forEach((day, index) => {
      const cell = el('div', 'cal-day' + (!day.in_month ? ' is-outside' : '') +
        (day.selected ? ' is-selected' : '') + (index >= 5 ? ' is-weekend' : ''));
      cell.setAttribute('role', 'gridcell');
      cell.setAttribute('aria-selected', String(day.selected));
      const dateButton = el('button', 'cal-date' + (day.is_today ? ' is-today' : ''), String(day.number));
      dateButton.type = 'button';
      dateButton.dataset.day = day.date;
      dateButton.setAttribute('aria-label', `${day.label} · ${day.events.length} รายการ`);
      dateButton.setAttribute('aria-pressed', String(day.selected));
      if (day.is_today) dateButton.setAttribute('aria-current', 'date');
      cell.appendChild(dateButton);
      const events = el('div', 'cal-events');
      day.events.slice(0, 2).forEach(event => {
        const button = el('button', 'cal-event ' + event.tone);
        button.type = 'button';
        button.dataset.day = day.date;
        button.dataset.reference = event.reference;
        const personLabel = event.reference.startsWith('จอง') ? 'ผู้จอง' : 'ผู้ยืม';
        const label = `${event.equipment_code} · ${event.equipment_name} · ${event.amount} ชิ้น · ${event.status}${event.booker_name ? ' · ' + personLabel + ': ' + event.booker_name : ''}`;
        button.title = label;
        button.setAttribute('aria-label', `${day.label} · ${event.reference} · ${label}`);
        button.appendChild(el('span', 'cal-event-name', event.equipment_name + (event.booker_name ? ' · ' + event.booker_name : '')));
        button.appendChild(el('span', 'cal-event-code', event.equipment_code));
        button.appendChild(el('span', 'cal-event-amount', String(event.amount)));
        events.appendChild(button);
      });
      if (day.events.length > 2) {
        const more = el('button', 'cal-more', `+${day.events.length - 2} รายการ`);
        more.type = 'button';
        more.dataset.day = day.date;
        more.setAttribute('aria-label', `ดูทั้งหมด ${day.events.length} รายการ วันที่ ${day.label}`);
        events.appendChild(more);
      }
      cell.appendChild(events);
      cell.dataset.day = day.date;
      row.appendChild(cell);
    });
    root.appendChild(row);
  }
  const click = event => {
    const target = event.target.closest('button[data-day]') || event.target.closest('.cal-day');
    if (target && root.contains(target)) {
      setTriggerValue('selection', {day: target.dataset.day, reference: target.dataset.reference || ''});
    }
  };
  root.addEventListener('click', click);
  return () => root.removeEventListener('click', click);
}
