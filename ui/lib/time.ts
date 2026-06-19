const FULL_TIMESTAMP_OPTIONS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
};

const COMPACT_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
};

function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatLocalTimestamp(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  if (!date) return "-";
  return new Intl.DateTimeFormat(undefined, FULL_TIMESTAMP_OPTIONS).format(date);
}

export function formatLocalTime(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  if (!date) return "-";
  return new Intl.DateTimeFormat(undefined, COMPACT_TIME_OPTIONS).format(date);
}
