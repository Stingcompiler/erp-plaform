// Today's date as the person at the device sees it (YYYY-MM-DD).
//
// `new Date().toISOString().slice(0, 10)` is the UTC date: in Khartoum
// (UTC+2) an expense entered at 01:00 on the 1st defaulted to the last day
// of the previous month — the wrong period.
export function localToday(now = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
